"""Soak test runner - repeatedly execute cases with rate control.

Supports two modes:
- DURATION: Run for a fixed duration (e.g., 30 minutes)
- ITERATIONS: Run for a fixed number of iterations (e.g., 100 times)

Integrates with RateController for adaptive rate limiting.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from . import (
    SoakConfig,
    SoakIteration,
    SoakMode,
    SoakResult,
    ThrottleEvent,
    ThrottleType,
    generate_soak_id,
)
from .rate_controller import RateController, RateControllerConfig


@dataclass
class IterationResult:
    """Result from running one iteration."""

    passed: bool
    status: str  # 'passed', 'warning', 'failed', 'error'
    spans: list[dict]
    duration_ms: float
    retry_count: int = 0
    error_count: int = 0
    artifacts_dir: Optional[str] = None


def detect_throttle_in_spans(spans: list[dict]) -> list[ThrottleEvent]:
    """Detect throttle events from span data.

    Looks for:
    - HTTP 429 status codes
    - AWS ThrottlingException errors
    - ProvisionedThroughputExceededException
    - High retry counts (retry storm)
    - Timeout errors that might indicate overload

    Args:
        spans: List of span dictionaries.

    Returns:
        List of ThrottleEvent objects detected.
    """
    events: list[ThrottleEvent] = []
    now = datetime.now(timezone.utc).isoformat()

    for span in spans:
        span_id = span.get("span_id", "unknown")
        error = span.get("error", "")
        status_code = span.get("status_code")
        retry_count = span.get("retry_count", 0)
        attributes = span.get("attributes", {})

        # Check for HTTP 429
        if status_code == 429:
            events.append(
                ThrottleEvent(
                    timestamp=now,
                    throttle_type=ThrottleType.HTTP_429,
                    source=span_id,
                    details=f"HTTP 429 from {span.get('target', 'unknown')}",
                )
            )
            continue

        # Check error messages for AWS throttling
        error_lower = error.lower() if error else ""
        throttle_patterns = [
            ("throttlingexception", ThrottleType.AWS_THROTTLE),
            ("provisionedthroughputexceeded", ThrottleType.AWS_THROTTLE),
            ("rate exceeded", ThrottleType.RATE_LIMIT),
            ("too many requests", ThrottleType.RATE_LIMIT),
            ("request limit exceeded", ThrottleType.RATE_LIMIT),
        ]

        for pattern, throttle_type in throttle_patterns:
            if pattern in error_lower:
                events.append(
                    ThrottleEvent(
                        timestamp=now,
                        throttle_type=throttle_type,
                        source=span_id,
                        details=error[:200],  # Truncate long errors
                    )
                )
                break

        # Check for retry storm (high retry count)
        if retry_count >= 3:
            events.append(
                ThrottleEvent(
                    timestamp=now,
                    throttle_type=ThrottleType.RETRY_STORM,
                    source=span_id,
                    details=f"High retry count: {retry_count}",
                )
            )

        # Check attributes for timeout
        if attributes.get("timeout", False) or "timeout" in error_lower:
            events.append(
                ThrottleEvent(
                    timestamp=now,
                    throttle_type=ThrottleType.TIMEOUT,
                    source=span_id,
                    details="Request timeout",
                )
            )

    return events


def run_soak(
    config: SoakConfig,
    run_iteration: Callable[[int], IterationResult],
    on_iteration: Optional[Callable[[SoakIteration], None]] = None,
    on_rate_change: Optional[Callable[[float, float, str], None]] = None,
) -> SoakResult:
    """Execute a soak test.

    Args:
        config: Soak test configuration.
        run_iteration: Callback to run one iteration.
            Takes iteration number, returns IterationResult.
        on_iteration: Optional callback after each iteration.
        on_rate_change: Optional callback when rate changes (old, new, reason).

    Returns:
        SoakResult with all iterations and statistics.
    """
    # Initialize rate controller
    rate_config = RateControllerConfig(
        initial_rate=config.initial_rate,
        min_rate=config.min_rate,
        max_rate=config.max_rate,
    )
    rate_controller = RateController(config=rate_config)

    # Initialize result
    soak_id = generate_soak_id()
    start_time = datetime.now(timezone.utc)
    iterations: list[SoakIteration] = []

    # Determine stop condition
    if config.mode == SoakMode.DURATION:
        end_time = time.monotonic() + config.duration_seconds
        should_continue = lambda i: time.monotonic() < end_time
    else:
        should_continue = lambda i: i < config.iterations

    iteration_num = 0
    while should_continue(iteration_num):
        iteration_start = time.monotonic()

        # Run the iteration
        iter_result = run_iteration(iteration_num)

        # Detect throttles
        throttle_events = detect_throttle_in_spans(iter_result.spans)

        # Update rate controller
        old_rate = rate_controller.current_rate
        if throttle_events:
            rate_controller.record_throttle(iteration_num)
        else:
            rate_controller.record_success(iteration_num)
        new_rate = rate_controller.current_rate

        # Callback if rate changed
        if on_rate_change and old_rate != new_rate:
            reason = "throttle" if throttle_events else "stability"
            on_rate_change(old_rate, new_rate, reason)

        # Record iteration with full detail
        iteration = SoakIteration(
            iteration=iteration_num,
            passed=iter_result.passed,
            status=iter_result.status,
            duration_ms=iter_result.duration_ms,
            span_count=len(iter_result.spans),
            error_count=iter_result.error_count,
            retry_count=iter_result.retry_count,
            throttle_events=throttle_events,
            timestamp=datetime.now(timezone.utc).isoformat(),
            artifacts_dir=iter_result.artifacts_dir,
        )
        iterations.append(iteration)

        # Callback
        if on_iteration:
            on_iteration(iteration)

        iteration_num += 1

        # Rate-controlled delay before next iteration
        elapsed = time.monotonic() - iteration_start
        target_interval = rate_controller.interval_seconds
        sleep_time = max(0, target_interval - elapsed)

        if sleep_time > 0 and should_continue(iteration_num):
            time.sleep(sleep_time)

    # Build result
    end_time_dt = datetime.now(timezone.utc)
    duration_seconds = (end_time_dt - start_time).total_seconds()

    return SoakResult(
        soak_id=soak_id,
        case_name=config.case_name or "unnamed",
        mode=config.mode,
        start_time=start_time.isoformat(),
        end_time=end_time_dt.isoformat(),
        duration_seconds=duration_seconds,
        iterations=iterations,
        rate_history=rate_controller.history,
        final_rate=rate_controller.current_rate,
    )


def run_soak_with_case(
    case_path: Path,
    config: SoakConfig,
    out_dir: Path,
    mode: str = "dev-fixtures",
    detailed: bool = True,
    on_iteration: Optional[Callable[[SoakIteration], None]] = None,
) -> SoakResult:
    """Run a soak test using a case file.

    Args:
        case_path: Path to the case YAML file.
        config: Soak configuration.
        out_dir: Output directory for soak artifacts.
        mode: Execution mode ("dev-fixtures" or "live").
        detailed: If True, save per-iteration artifacts to iterations/NNN/.
        on_iteration: Optional callback after each iteration.

    Returns:
        SoakResult with all iterations.
    """
    # Import here to avoid circular imports
    from ..report.suite_runner import run_case_dev_fixtures

    # Create iterations dir for detailed mode
    iterations_dir = out_dir / "iterations"
    if detailed:
        iterations_dir.mkdir(parents=True, exist_ok=True)

    # Override case name from path
    config_with_name = SoakConfig(
        mode=config.mode,
        duration_seconds=config.duration_seconds,
        iterations=config.iterations,
        interval_seconds=config.interval_seconds,
        max_inflight=config.max_inflight,
        initial_rate=config.initial_rate,
        min_rate=config.min_rate,
        max_rate=config.max_rate,
        case_name=case_path.stem,
    )

    def run_iteration(iteration: int) -> IterationResult:
        """Run one iteration of the case."""
        start = time.monotonic()

        # Determine output dir for this iteration (if detailed)
        iter_out_dir: Optional[Path] = None
        if detailed:
            iter_out_dir = iterations_dir / f"{iteration:04d}"
            iter_out_dir.mkdir(parents=True, exist_ok=True)

        if mode == "dev-fixtures":
            result = run_case_dev_fixtures(case_path, out_dir=iter_out_dir)
            elapsed = (time.monotonic() - start) * 1000

            # Extract spans as dicts for throttle detection
            # error may be a dict, so convert to string for pattern matching
            spans = [
                {
                    "span_id": s.span_id,
                    "error": str(s.error) if s.error else "",
                    "status_code": getattr(s, "status_code", None),
                    "retry_count": getattr(s, "retry_count", 0),
                    "attributes": getattr(s, "attributes", {}),
                }
                for s in result.spans
            ]

            # Map CaseStatus to string
            status_map = {
                "passed": "passed",
                "passed_with_warnings": "warning",
                "failed": "failed",
                "error": "error",
                "skipped": "skipped",
            }
            status = status_map.get(result.status.value, "error")

            return IterationResult(
                passed=result.passed,
                status=status,
                spans=spans,
                duration_ms=elapsed,
                retry_count=result.retry_count,
                error_count=result.error_count,
                artifacts_dir=str(iter_out_dir) if iter_out_dir else None,
            )
        else:
            # Live mode - not implemented in Tier-2
            raise NotImplementedError("Live mode not available in Tier-2")

    return run_soak(
        config=config_with_name,
        run_iteration=run_iteration,
        on_iteration=on_iteration,
    )
