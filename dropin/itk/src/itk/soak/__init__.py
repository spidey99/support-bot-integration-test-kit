"""Soak testing module for ITK.

This module provides sustained/endurance testing capabilities:
- Run tests repeatedly over time (duration or iteration-based)
- Adaptive rate control based on throttle detection
- Continuous reporting during soak runs
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class SoakMode(Enum):
    """How the soak run determines when to stop."""

    DURATION = "duration"  # Run for a specified time period
    ITERATIONS = "iterations"  # Run for a specified number of iterations


class ThrottleType(Enum):
    """Types of throttling detected."""

    HTTP_429 = "http_429"
    AWS_THROTTLE = "aws_throttle"
    RETRY_STORM = "retry_storm"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"


@dataclass
class SoakConfig:
    """Configuration for a soak test run.

    Attributes:
        mode: Whether to run by duration or iterations.
        duration_seconds: How long to run (if mode=DURATION).
        iterations: How many iterations to run (if mode=ITERATIONS).
        interval_seconds: Delay between iterations.
        max_inflight: Maximum concurrent test executions.
        case_name: Name of the case being soaked.
        out_dir: Output directory for artifacts.
        initial_rate: Starting requests per second.
        min_rate: Minimum rate (floor for backoff).
        max_rate: Maximum rate (ceiling for ramp-up).
    """

    mode: SoakMode = SoakMode.DURATION
    duration_seconds: int = 3600  # 1 hour default
    iterations: int = 100
    interval_seconds: float = 1.0
    max_inflight: int = 1
    case_name: Optional[str] = None
    out_dir: str = "./soak-output"
    initial_rate: float = 1.0  # 1 req/sec
    min_rate: float = 0.1  # Floor: 1 req per 10 sec
    max_rate: float = 10.0  # Ceiling: 10 req/sec


@dataclass
class ThrottleEvent:
    """Record of a throttle detection.

    Attributes:
        timestamp: When the throttle was detected.
        throttle_type: Type of throttle.
        source: What triggered it (error message, status code, etc).
        details: Additional details about the throttle.
        iteration: Which iteration this occurred on.
    """

    timestamp: str
    throttle_type: ThrottleType
    source: str
    details: Optional[str] = None
    iteration: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "throttle_type": self.throttle_type.value,
            "source": self.source,
            "details": self.details,
            "iteration": self.iteration,
        }


@dataclass
class SoakIteration:
    """Result of a single soak iteration.

    Attributes:
        iteration: Iteration number (0-indexed).
        timestamp: ISO timestamp when iteration ran.
        passed: Whether the iteration passed.
        duration_ms: How long the iteration took.
        span_count: Number of spans in the trace.
        error_count: Number of error spans.
        throttle_events: List of throttle events in this iteration.
        retry_count: Number of retry attempts in this iteration.
        status: Status string ('passed', 'warning', 'failed', 'error').
        artifacts_dir: Path to iteration artifacts (if detailed mode).
    """

    iteration: int
    passed: bool = True
    duration_ms: float = 0.0
    span_count: int = 0
    error_count: int = 0
    throttle_events: list[ThrottleEvent] = field(default_factory=list)
    timestamp: Optional[str] = None
    retry_count: int = 0
    status: str = "passed"  # passed, warning, failed, error
    artifacts_dir: Optional[str] = None

    @property
    def is_clean_pass(self) -> bool:
        """Whether this iteration passed without any retries or errors."""
        return self.passed and self.retry_count == 0 and self.error_count == 0

    @property
    def is_warning(self) -> bool:
        """Whether this iteration passed but with retries or errors."""
        return self.status == "warning"

    @property
    def throttle_detected(self) -> bool:
        """Whether any throttling was detected."""
        return len(self.throttle_events) > 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "iteration": self.iteration,
            "timestamp": self.timestamp,
            "passed": self.passed,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "span_count": self.span_count,
            "error_count": self.error_count,
            "retry_count": self.retry_count,
            "is_clean_pass": self.is_clean_pass,
            "throttle_detected": self.throttle_detected,
            "throttle_events": [e.to_dict() for e in self.throttle_events],
            "artifacts_dir": self.artifacts_dir,
        }


@dataclass
class SoakResult:
    """Result of a complete soak test run.

    Attributes:
        soak_id: Unique identifier for the soak run.
        case_name: Name of the case being soaked.
        mode: How the soak run determined when to stop.
        start_time: ISO timestamp when soak started.
        end_time: ISO timestamp when soak finished.
        duration_seconds: Total soak duration in seconds.
        iterations: List of iteration results.
        rate_history: History of rate changes.
        final_rate: Rate controller value at end.
    """

    soak_id: str
    case_name: str
    mode: SoakMode
    start_time: str
    end_time: Optional[str] = None
    duration_seconds: float = 0.0
    iterations: list[SoakIteration] = field(default_factory=list)
    rate_history: list[Any] = field(default_factory=list)  # RateChange objects
    final_rate: float = 1.0

    @property
    def total_iterations(self) -> int:
        """Total number of iterations completed."""
        return len(self.iterations)

    @property
    def total_passed(self) -> int:
        """Number of iterations that passed (including warnings)."""
        return sum(1 for i in self.iterations if i.passed)

    @property
    def total_clean_passes(self) -> int:
        """Number of iterations that passed without retries/errors."""
        return sum(1 for i in self.iterations if i.is_clean_pass)

    @property
    def total_warnings(self) -> int:
        """Number of iterations that passed but with retries/errors."""
        return sum(1 for i in self.iterations if i.is_warning)

    @property
    def total_failures(self) -> int:
        """Number of iterations that failed."""
        return sum(1 for i in self.iterations if not i.passed)

    @property
    def consistency_score(self) -> float:
        """Clean passes divided by total passes (0.0 to 1.0).

        If 97% pass but all had retries, consistency = 0%.
        This reveals LLM non-determinism masked by retries.
        """
        if self.total_passed == 0:
            return 0.0
        return self.total_clean_passes / self.total_passed

    @property
    def warning_rate(self) -> float:
        """Percentage of passing iterations that had warnings."""
        if self.total_passed == 0:
            return 0.0
        return self.total_warnings / self.total_passed

    @property
    def total_retries(self) -> int:
        """Total retry count across all iterations."""
        return sum(i.retry_count for i in self.iterations)

    @property
    def avg_retries_per_iteration(self) -> float:
        """Average retries per iteration."""
        if not self.iterations:
            return 0.0
        return self.total_retries / len(self.iterations)

    @property
    def max_retries(self) -> int:
        """Maximum retry count in any single iteration."""
        if not self.iterations:
            return 0
        return max(i.retry_count for i in self.iterations)

    @property
    def pass_rate(self) -> float:
        """Calculate pass rate as fraction (0.0 to 1.0)."""
        if self.total_iterations == 0:
            return 0.0
        return self.total_passed / self.total_iterations

    @property
    def avg_iteration_ms(self) -> float:
        """Average iteration duration in milliseconds."""
        if not self.iterations:
            return 0.0
        return sum(i.duration_ms for i in self.iterations) / len(self.iterations)

    @property
    def all_throttle_events(self) -> list[ThrottleEvent]:
        """All throttle events across all iterations."""
        events = []
        for it in self.iterations:
            events.extend(it.throttle_events)
        return events

    @property
    def throttle_rate(self) -> float:
        """Percentage of iterations that hit throttling."""
        if self.total_iterations == 0:
            return 0.0
        throttled = sum(1 for i in self.iterations if i.throttle_detected)
        return throttled / self.total_iterations

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "soak_id": self.soak_id,
            "case_name": self.case_name,
            "mode": self.mode.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "summary": {
                "total_iterations": self.total_iterations,
                "total_passed": self.total_passed,
                "total_clean_passes": self.total_clean_passes,
                "total_warnings": self.total_warnings,
                "total_failures": self.total_failures,
                "pass_rate": self.pass_rate,
                "consistency_score": self.consistency_score,
                "warning_rate": self.warning_rate,
                "avg_iteration_ms": self.avg_iteration_ms,
                "total_retries": self.total_retries,
                "avg_retries_per_iteration": self.avg_retries_per_iteration,
                "max_retries": self.max_retries,
                "total_throttle_events": len(self.all_throttle_events),
                "throttle_rate": self.throttle_rate,
                "final_rate": self.final_rate,
            },
            "rate_history": [
                {
                    "timestamp": r.timestamp,
                    "old_rate": r.old_rate,
                    "new_rate": r.new_rate,
                    "reason": r.reason,
                }
                for r in self.rate_history
            ],
            "iterations": [i.to_dict() for i in self.iterations],
        }


def generate_soak_id() -> str:
    """Generate a unique soak ID based on timestamp."""
    return datetime.now(timezone.utc).strftime("soak-%Y%m%d-%H%M%S")
