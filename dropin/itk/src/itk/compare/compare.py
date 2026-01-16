"""Compare two trace runs and produce a delta report.

Comparison detects:
- New paths (in B but not A)
- Missing paths (in A but not B)
- Latency changes (for paths in both)
- Error rate changes (for paths in both)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from itk.trace.trace_model import Trace
from itk.compare.path_signature import (
    PathSignature,
    extract_path_signature,
    compute_trace_latency_ms,
)


@dataclass
class PathDelta:
    """Delta for a single path between baseline and current."""

    signature: PathSignature
    baseline_count: int = 0
    current_count: int = 0
    baseline_avg_latency_ms: float = 0.0
    current_avg_latency_ms: float = 0.0
    baseline_error_count: int = 0
    current_error_count: int = 0

    @property
    def is_new(self) -> bool:
        """Path exists in current but not baseline."""
        return self.baseline_count == 0 and self.current_count > 0

    @property
    def is_missing(self) -> bool:
        """Path exists in baseline but not current."""
        return self.baseline_count > 0 and self.current_count == 0

    @property
    def latency_delta_ms(self) -> float:
        """Change in average latency (positive = slower)."""
        if self.baseline_count == 0 or self.current_count == 0:
            return 0.0
        return self.current_avg_latency_ms - self.baseline_avg_latency_ms

    @property
    def latency_delta_pct(self) -> float:
        """Percentage change in latency."""
        if self.baseline_avg_latency_ms == 0:
            return 0.0
        return (self.latency_delta_ms / self.baseline_avg_latency_ms) * 100.0

    @property
    def error_rate_baseline(self) -> float:
        """Error rate in baseline (0.0 to 1.0)."""
        if self.baseline_count == 0:
            return 0.0
        return self.baseline_error_count / self.baseline_count

    @property
    def error_rate_current(self) -> float:
        """Error rate in current (0.0 to 1.0)."""
        if self.current_count == 0:
            return 0.0
        return self.current_error_count / self.current_count

    @property
    def error_rate_delta(self) -> float:
        """Change in error rate (positive = more errors)."""
        return self.error_rate_current - self.error_rate_baseline


@dataclass
class CompareResult:
    """Result of comparing two trace runs."""

    baseline_label: str
    current_label: str
    deltas: list[PathDelta] = field(default_factory=list)

    @property
    def new_paths(self) -> list[PathDelta]:
        """Paths that are new in current."""
        return [d for d in self.deltas if d.is_new]

    @property
    def missing_paths(self) -> list[PathDelta]:
        """Paths that are missing from current."""
        return [d for d in self.deltas if d.is_missing]

    @property
    def changed_paths(self) -> list[PathDelta]:
        """Paths with latency or error rate changes."""
        return [d for d in self.deltas if not d.is_new and not d.is_missing]

    @property
    def significant_latency_changes(self) -> list[PathDelta]:
        """Paths with >10% latency change."""
        return [d for d in self.changed_paths if abs(d.latency_delta_pct) > 10.0]

    @property
    def error_regressions(self) -> list[PathDelta]:
        """Paths with increased error rate."""
        return [d for d in self.changed_paths if d.error_rate_delta > 0.0]

    @property
    def has_regressions(self) -> bool:
        """True if there are any regressions (new errors or missing paths)."""
        return bool(self.missing_paths) or bool(self.error_regressions)


def compare_traces(
    baseline: Trace,
    current: Trace,
    baseline_label: str = "baseline",
    current_label: str = "current",
) -> CompareResult:
    """Compare two traces and produce a delta report.

    This compares single traces. For comparing multiple traces,
    use compare_trace_sets().
    """
    baseline_sig = extract_path_signature(baseline)
    current_sig = extract_path_signature(current)

    baseline_latency = compute_trace_latency_ms(baseline)
    current_latency = compute_trace_latency_ms(current)

    baseline_has_error = baseline_sig.has_error
    current_has_error = current_sig.has_error

    # Collect all unique signatures
    all_sigs: set[PathSignature] = set()
    if baseline_sig.steps:
        all_sigs.add(baseline_sig)
    if current_sig.steps:
        all_sigs.add(current_sig)

    deltas: list[PathDelta] = []

    for sig in all_sigs:
        delta = PathDelta(signature=sig)

        # Check baseline
        if sig == baseline_sig:
            delta.baseline_count = 1
            delta.baseline_avg_latency_ms = baseline_latency
            delta.baseline_error_count = 1 if baseline_has_error else 0

        # Check current
        if sig == current_sig:
            delta.current_count = 1
            delta.current_avg_latency_ms = current_latency
            delta.current_error_count = 1 if current_has_error else 0

        deltas.append(delta)

    return CompareResult(
        baseline_label=baseline_label,
        current_label=current_label,
        deltas=deltas,
    )


def compare_trace_sets(
    baselines: list[Trace],
    currents: list[Trace],
    baseline_label: str = "baseline",
    current_label: str = "current",
) -> CompareResult:
    """Compare sets of traces and produce aggregate delta report.

    Groups traces by path signature and computes aggregate statistics.
    """
    # Aggregate baseline stats by signature
    baseline_stats: dict[PathSignature, dict] = {}
    for trace in baselines:
        sig = extract_path_signature(trace)
        if sig.steps:
            if sig not in baseline_stats:
                baseline_stats[sig] = {
                    "count": 0,
                    "total_latency": 0.0,
                    "error_count": 0,
                }
            stats = baseline_stats[sig]
            stats["count"] += 1
            stats["total_latency"] += compute_trace_latency_ms(trace)
            if sig.has_error:
                stats["error_count"] += 1

    # Aggregate current stats by signature
    current_stats: dict[PathSignature, dict] = {}
    for trace in currents:
        sig = extract_path_signature(trace)
        if sig.steps:
            if sig not in current_stats:
                current_stats[sig] = {
                    "count": 0,
                    "total_latency": 0.0,
                    "error_count": 0,
                }
            stats = current_stats[sig]
            stats["count"] += 1
            stats["total_latency"] += compute_trace_latency_ms(trace)
            if sig.has_error:
                stats["error_count"] += 1

    # Build deltas for all signatures
    all_sigs = set(baseline_stats.keys()) | set(current_stats.keys())
    deltas: list[PathDelta] = []

    for sig in all_sigs:
        delta = PathDelta(signature=sig)

        if sig in baseline_stats:
            stats = baseline_stats[sig]
            delta.baseline_count = stats["count"]
            delta.baseline_avg_latency_ms = (
                stats["total_latency"] / stats["count"] if stats["count"] > 0 else 0.0
            )
            delta.baseline_error_count = stats["error_count"]

        if sig in current_stats:
            stats = current_stats[sig]
            delta.current_count = stats["count"]
            delta.current_avg_latency_ms = (
                stats["total_latency"] / stats["count"] if stats["count"] > 0 else 0.0
            )
            delta.current_error_count = stats["error_count"]

        deltas.append(delta)

    # Sort deltas: regressions first, then by impact
    def sort_key(d: PathDelta) -> tuple:
        # Regressions first (missing paths, error increases)
        is_regression = d.is_missing or d.error_rate_delta > 0
        # Then by impact (latency change magnitude)
        return (not is_regression, -abs(d.latency_delta_pct))

    deltas.sort(key=sort_key)

    return CompareResult(
        baseline_label=baseline_label,
        current_label=current_label,
        deltas=deltas,
    )
