"""Invariant checks for trace validation.

Invariants are assertions about trace structure and content that should
hold true for valid executions. Failed invariants indicate bugs or
unexpected behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Sequence

from itk.trace.trace_model import Trace
from itk.trace.span_model import Span


@dataclass(frozen=True)
class InvariantResult:
    """Result of an invariant check."""

    name: str
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class InvariantConfig:
    """Configuration for invariant checks."""

    # Maximum allowed retry count (0 = no retries allowed)
    max_retry_count: int = 5

    # Required components (empty = no requirement)
    required_components: list[str] = field(default_factory=list)

    # Whether to check for orphan spans
    check_orphans: bool = True

    # Whether to validate timestamps
    check_timestamps: bool = True


def _check_has_spans(trace: Trace) -> InvariantResult:
    """Check that trace has at least one span."""
    return InvariantResult(
        name="has_spans",
        passed=len(trace.spans) > 0,
        details={"count": len(trace.spans)},
    )


def _check_no_duplicate_span_ids(trace: Trace) -> InvariantResult:
    """Check that all span IDs are unique."""
    seen: set[str] = set()
    duplicates: list[str] = []

    for span in trace.spans:
        if span.span_id in seen:
            duplicates.append(span.span_id)
        seen.add(span.span_id)

    return InvariantResult(
        name="no_duplicate_span_ids",
        passed=len(duplicates) == 0,
        details={"duplicates": duplicates} if duplicates else {},
    )


def _check_no_orphan_spans(trace: Trace) -> InvariantResult:
    """Check that all spans with parent_span_id reference valid spans.

    A span is orphaned if it has a parent_span_id that doesn't exist in the trace.
    Root spans (parent_span_id=None) are not orphans.
    """
    span_ids = {s.span_id for s in trace.spans}
    orphans: list[str] = []

    for span in trace.spans:
        if span.parent_span_id is not None and span.parent_span_id not in span_ids:
            orphans.append(span.span_id)

    return InvariantResult(
        name="no_orphan_spans",
        passed=len(orphans) == 0,
        details={"orphan_span_ids": orphans} if orphans else {},
    )


def _parse_timestamp(ts: str) -> Optional[datetime]:
    """Parse an ISO timestamp string."""
    try:
        ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _check_valid_timestamps(trace: Trace) -> InvariantResult:
    """Check that ts_end >= ts_start for all spans with both timestamps."""
    invalid: list[dict[str, Any]] = []

    for span in trace.spans:
        if span.ts_start and span.ts_end:
            start = _parse_timestamp(span.ts_start)
            end = _parse_timestamp(span.ts_end)

            if start and end and end < start:
                invalid.append({
                    "span_id": span.span_id,
                    "ts_start": span.ts_start,
                    "ts_end": span.ts_end,
                })

    return InvariantResult(
        name="valid_timestamps",
        passed=len(invalid) == 0,
        details={"invalid_spans": invalid} if invalid else {},
    )


def _check_max_retry_count(trace: Trace, max_retries: int) -> InvariantResult:
    """Check that no span exceeds the maximum retry count."""
    excessive: list[dict[str, Any]] = []

    for span in trace.spans:
        if span.attempt is not None:
            # attempt is 1-indexed, so retries = attempt - 1
            retries = span.attempt - 1
            if retries > max_retries:
                excessive.append({
                    "span_id": span.span_id,
                    "component": span.component,
                    "attempt": span.attempt,
                    "retries": retries,
                })

    return InvariantResult(
        name="max_retry_count",
        passed=len(excessive) == 0,
        details={
            "max_allowed": max_retries,
            "excessive_spans": excessive,
        } if excessive else {"max_allowed": max_retries},
    )


def _check_required_components(
    trace: Trace, required: Sequence[str]
) -> InvariantResult:
    """Check that all required components appear in the trace."""
    if not required:
        return InvariantResult(
            name="required_components",
            passed=True,
            details={"required": [], "found": []},
        )

    present = {s.component for s in trace.spans}
    missing = [c for c in required if c not in present]

    return InvariantResult(
        name="required_components",
        passed=len(missing) == 0,
        details={
            "required": list(required),
            "missing": missing,
            "found": list(present),
        },
    )


def _check_has_entrypoint(trace: Trace) -> InvariantResult:
    """Check that trace has at least one root span (entrypoint)."""
    roots = [s for s in trace.spans if s.parent_span_id is None]
    return InvariantResult(
        name="has_entrypoint",
        passed=len(roots) > 0,
        details={"root_count": len(roots)},
    )


def _check_no_error_spans(trace: Trace) -> InvariantResult:
    """Check that no spans have errors (useful for success-path tests)."""
    errors: list[dict[str, Any]] = []

    for span in trace.spans:
        if span.error:
            errors.append({
                "span_id": span.span_id,
                "component": span.component,
                "error": span.error.get("message", str(span.error)),
            })

    return InvariantResult(
        name="no_error_spans",
        passed=len(errors) == 0,
        details={"error_spans": errors} if errors else {},
    )


def run_invariants(
    trace: Trace,
    config: Optional[InvariantConfig] = None,
) -> list[InvariantResult]:
    """Run all configured invariants on a trace.

    Args:
        trace: The trace to validate
        config: Optional configuration (uses defaults if None)

    Returns:
        List of InvariantResult objects
    """
    if config is None:
        config = InvariantConfig()

    results: list[InvariantResult] = []

    # Always run these
    results.append(_check_has_spans(trace))
    results.append(_check_no_duplicate_span_ids(trace))
    results.append(_check_has_entrypoint(trace))

    # Configurable checks
    if config.check_orphans:
        results.append(_check_no_orphan_spans(trace))

    if config.check_timestamps:
        results.append(_check_valid_timestamps(trace))

    results.append(_check_max_retry_count(trace, config.max_retry_count))

    if config.required_components:
        results.append(_check_required_components(trace, config.required_components))

    return results


def run_all_invariants(trace: Trace) -> list[InvariantResult]:
    """Run ALL invariants including optional ones.

    Useful for comprehensive validation and testing.
    """
    results = run_invariants(trace)
    results.append(_check_no_error_spans(trace))
    return results
