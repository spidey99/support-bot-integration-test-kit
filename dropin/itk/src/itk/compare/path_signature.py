"""Path signature extraction from traces.

A path signature is a canonical representation of the execution flow,
consisting of the ordered sequence of (component, operation) pairs.
This allows comparing traces to detect structural changes in behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from itk.trace.trace_model import Trace
from itk.trace.span_model import Span


@dataclass(frozen=True)
class PathSignature:
    """A canonical representation of execution flow.

    The signature is a tuple of (component, operation) pairs representing
    the ordered sequence of boundary crossings.
    """

    steps: tuple[tuple[str, str], ...]
    has_error: bool = False
    retry_count: int = 0

    @property
    def signature_string(self) -> str:
        """Return a human-readable signature string."""
        parts = [f"{comp}:{op}" for comp, op in self.steps]
        suffix = ""
        if self.has_error:
            suffix += " [ERROR]"
        if self.retry_count > 0:
            suffix += f" [RETRIES:{self.retry_count}]"
        return " -> ".join(parts) + suffix

    def __hash__(self) -> int:
        return hash((self.steps, self.has_error))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PathSignature):
            return False
        return self.steps == other.steps and self.has_error == other.has_error


def extract_path_signature(trace: Trace) -> PathSignature:
    """Extract a path signature from a trace.

    Orders spans by timestamp if available, then extracts the sequence
    of (component, operation) pairs. Detects errors and retry counts.
    """
    if not trace.spans:
        return PathSignature(steps=(), has_error=False, retry_count=0)

    # Sort spans by timestamp if available
    def sort_key(span: Span) -> str:
        return span.ts_start or span.span_id

    sorted_spans = sorted(trace.spans, key=sort_key)

    # Extract steps
    steps: list[tuple[str, str]] = []
    has_error = False
    max_attempt = 0

    for span in sorted_spans:
        steps.append((span.component, span.operation))
        if span.error:
            has_error = True
        if span.attempt is not None and span.attempt > max_attempt:
            max_attempt = span.attempt

    # Retry count is max_attempt - 1 (attempt 1 is the first try)
    retry_count = max(0, max_attempt - 1)

    return PathSignature(
        steps=tuple(steps),
        has_error=has_error,
        retry_count=retry_count,
    )


@dataclass
class PathStats:
    """Statistics for a path signature across multiple traces."""

    signature: PathSignature
    count: int = 0
    total_latency_ms: float = 0.0
    min_latency_ms: Optional[float] = None
    max_latency_ms: Optional[float] = None
    error_count: int = 0

    @property
    def avg_latency_ms(self) -> float:
        if self.count == 0:
            return 0.0
        return self.total_latency_ms / self.count

    def add_trace(self, trace: Trace, latency_ms: float, has_error: bool) -> None:
        """Add a trace's stats to this path."""
        self.count += 1
        self.total_latency_ms += latency_ms
        if self.min_latency_ms is None or latency_ms < self.min_latency_ms:
            self.min_latency_ms = latency_ms
        if self.max_latency_ms is None or latency_ms > self.max_latency_ms:
            self.max_latency_ms = latency_ms
        if has_error:
            self.error_count += 1


def compute_trace_latency_ms(trace: Trace) -> float:
    """Compute total latency of a trace in milliseconds.

    Uses the first and last timestamps from spans.
    Returns 0.0 if timestamps are not available.
    """
    if not trace.spans:
        return 0.0

    starts: list[str] = []
    ends: list[str] = []

    for span in trace.spans:
        if span.ts_start:
            starts.append(span.ts_start)
        if span.ts_end:
            ends.append(span.ts_end)

    if not starts or not ends:
        return 0.0

    try:
        from datetime import datetime

        # Parse ISO timestamps
        def parse_ts(ts: str) -> datetime:
            # Handle various ISO formats
            ts = ts.replace("Z", "+00:00")
            if "." in ts:
                # Handle microseconds
                return datetime.fromisoformat(ts)
            return datetime.fromisoformat(ts)

        first_start = min(parse_ts(ts) for ts in starts)
        last_end = max(parse_ts(ts) for ts in ends)

        delta = last_end - first_start
        return delta.total_seconds() * 1000.0
    except (ValueError, TypeError):
        return 0.0
