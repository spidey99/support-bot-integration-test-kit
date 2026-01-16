"""Tests for soak testing module."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from itk.soak import (
    SoakConfig,
    SoakIteration,
    SoakMode,
    SoakResult,
    ThrottleEvent,
    ThrottleType,
    generate_soak_id,
)
from itk.soak.rate_controller import (
    RateController,
    RateControllerConfig,
    RateChange,
    create_rate_controller,
)
from itk.soak.soak_runner import detect_throttle_in_spans, run_soak


# ===== SoakConfig tests =====


def test_soak_config_defaults():
    """Test SoakConfig default values."""
    config = SoakConfig()
    assert config.mode == SoakMode.DURATION
    assert config.duration_seconds == 3600
    assert config.iterations == 100
    assert config.initial_rate == 1.0


def test_soak_config_iteration_mode():
    """Test SoakConfig in iteration mode."""
    config = SoakConfig(mode=SoakMode.ITERATIONS, iterations=50)
    assert config.mode == SoakMode.ITERATIONS
    assert config.iterations == 50


# ===== ThrottleEvent tests =====


def test_throttle_event_creation():
    """Test ThrottleEvent creation."""
    event = ThrottleEvent(
        timestamp="2024-01-01T00:00:00Z",
        throttle_type=ThrottleType.HTTP_429,
        source="span-123",
        details="Rate limit exceeded",
    )
    assert event.throttle_type == ThrottleType.HTTP_429
    assert event.source == "span-123"


def test_throttle_event_to_dict():
    """Test ThrottleEvent serialization."""
    event = ThrottleEvent(
        timestamp="2024-01-01T00:00:00Z",
        throttle_type=ThrottleType.AWS_THROTTLE,
        source="dynamodb-call",
        iteration=5,
    )
    d = event.to_dict()
    assert d["throttle_type"] == "aws_throttle"
    assert d["iteration"] == 5


# ===== SoakIteration tests =====


def test_soak_iteration_creation():
    """Test SoakIteration creation."""
    it = SoakIteration(iteration=0, passed=True, duration_ms=150.0)
    assert it.iteration == 0
    assert it.passed
    assert it.duration_ms == 150.0
    assert not it.throttle_detected


def test_soak_iteration_with_throttle():
    """Test SoakIteration with throttle events."""
    event = ThrottleEvent(
        timestamp="2024-01-01T00:00:00Z",
        throttle_type=ThrottleType.HTTP_429,
        source="api",
    )
    it = SoakIteration(iteration=1, passed=False, throttle_events=[event])
    assert it.throttle_detected
    assert len(it.throttle_events) == 1


def test_soak_iteration_to_dict():
    """Test SoakIteration serialization."""
    it = SoakIteration(
        iteration=0,
        passed=True,
        duration_ms=100.0,
        span_count=5,
        error_count=0,
    )
    d = it.to_dict()
    assert d["iteration"] == 0
    assert d["passed"]
    assert d["duration_ms"] == 100.0


# ===== SoakResult tests =====


def test_soak_result_creation():
    """Test SoakResult creation."""
    result = SoakResult(
        soak_id="soak-test",
        case_name="test-case",
        mode=SoakMode.ITERATIONS,
        start_time="2024-01-01T00:00:00Z",
    )
    assert result.soak_id == "soak-test"
    assert result.total_iterations == 0
    assert result.pass_rate == 0.0


def test_soak_result_pass_rate():
    """Test SoakResult pass_rate calculation."""
    iterations = [
        SoakIteration(iteration=0, passed=True, duration_ms=100),
        SoakIteration(iteration=1, passed=True, duration_ms=100),
        SoakIteration(iteration=2, passed=False, duration_ms=100),
        SoakIteration(iteration=3, passed=True, duration_ms=100),
    ]
    result = SoakResult(
        soak_id="test",
        case_name="test",
        mode=SoakMode.ITERATIONS,
        start_time="2024-01-01T00:00:00Z",
        iterations=iterations,
    )
    assert result.total_iterations == 4
    assert result.total_passed == 3
    assert result.pass_rate == 0.75


def test_soak_result_avg_iteration_ms():
    """Test SoakResult average iteration duration."""
    iterations = [
        SoakIteration(iteration=0, passed=True, duration_ms=100),
        SoakIteration(iteration=1, passed=True, duration_ms=200),
        SoakIteration(iteration=2, passed=True, duration_ms=300),
    ]
    result = SoakResult(
        soak_id="test",
        case_name="test",
        mode=SoakMode.ITERATIONS,
        start_time="2024-01-01T00:00:00Z",
        iterations=iterations,
    )
    assert result.avg_iteration_ms == 200.0


def test_soak_result_all_throttle_events():
    """Test SoakResult collects all throttle events."""
    event1 = ThrottleEvent(
        timestamp="2024-01-01T00:00:00Z",
        throttle_type=ThrottleType.HTTP_429,
        source="api",
    )
    event2 = ThrottleEvent(
        timestamp="2024-01-01T00:00:01Z",
        throttle_type=ThrottleType.AWS_THROTTLE,
        source="dynamo",
    )
    iterations = [
        SoakIteration(iteration=0, passed=False, throttle_events=[event1]),
        SoakIteration(iteration=1, passed=True),
        SoakIteration(iteration=2, passed=False, throttle_events=[event2]),
    ]
    result = SoakResult(
        soak_id="test",
        case_name="test",
        mode=SoakMode.ITERATIONS,
        start_time="2024-01-01T00:00:00Z",
        iterations=iterations,
    )
    assert len(result.all_throttle_events) == 2


def test_soak_result_to_dict():
    """Test SoakResult JSON serialization."""
    result = SoakResult(
        soak_id="soak-test",
        case_name="test",
        mode=SoakMode.ITERATIONS,
        start_time="2024-01-01T00:00:00Z",
        final_rate=2.5,
    )
    d = result.to_dict()
    assert d["soak_id"] == "soak-test"
    assert d["mode"] == "iterations"
    assert d["summary"]["final_rate"] == 2.5


# ===== generate_soak_id tests =====


def test_generate_soak_id_format():
    """Test soak ID format."""
    soak_id = generate_soak_id()
    assert soak_id.startswith("soak-")
    assert len(soak_id) == 20  # soak-YYYYMMDD-HHMMSS


# ===== RateControllerConfig tests =====


def test_rate_controller_config_defaults():
    """Test RateControllerConfig defaults."""
    config = RateControllerConfig()
    assert config.initial_rate == 1.0
    assert config.min_rate == 0.1
    assert config.max_rate == 10.0
    assert config.multiplicative_decrease == 0.5


# ===== RateController tests =====


def test_rate_controller_creation():
    """Test RateController initialization."""
    rc = create_rate_controller(initial_rate=2.0)
    assert rc.current_rate == 2.0
    assert rc.interval_seconds == 0.5


def test_rate_controller_record_throttle():
    """Test rate decrease on throttle."""
    rc = create_rate_controller(initial_rate=2.0)
    rc.record_throttle(iteration=0)
    # Rate should decrease by multiplicative_decrease (0.5)
    assert rc.current_rate == 1.0


def test_rate_controller_min_rate_floor():
    """Test rate doesn't go below min_rate."""
    rc = create_rate_controller(initial_rate=0.2, min_rate=0.1)
    rc.record_throttle(iteration=0)
    # 0.2 * 0.5 = 0.1 (at floor)
    assert rc.current_rate == 0.1
    # Another throttle shouldn't go below floor
    rc.last_rate_change_time = None  # Reset cooldown for test
    rc.record_throttle(iteration=1)
    assert rc.current_rate == 0.1


def test_rate_controller_max_rate_ceiling():
    """Test rate doesn't go above max_rate."""
    config = RateControllerConfig(
        initial_rate=9.5,
        max_rate=10.0,
        additive_increase=1.0,
        stability_window=0.0,  # No wait for test
    )
    rc = RateController(config=config)
    rc.last_stable_since = 0  # Pretend we've been stable
    rc.record_success(iteration=0)
    assert rc.current_rate == 10.0


def test_rate_controller_history():
    """Test rate change history tracking."""
    rc = create_rate_controller(initial_rate=2.0)
    rc.record_throttle(iteration=0)
    assert len(rc.history) == 1
    assert rc.history[0].reason == "throttle"
    assert rc.history[0].old_rate == 2.0
    assert rc.history[0].new_rate == 1.0


def test_rate_controller_set_rate():
    """Test manual rate setting."""
    rc = create_rate_controller(initial_rate=1.0)
    rc.set_rate(5.0, reason="manual")
    assert rc.current_rate == 5.0
    assert len(rc.history) == 1
    assert rc.history[0].reason == "manual"


def test_rate_controller_reset():
    """Test controller reset."""
    rc = create_rate_controller(initial_rate=2.0)
    rc.record_throttle(iteration=0)
    rc.reset()
    assert rc.current_rate == 2.0
    assert len(rc.history) == 0


def test_rate_controller_get_stats():
    """Test stats calculation."""
    rc = create_rate_controller(initial_rate=2.0)
    rc.record_throttle(iteration=0)
    stats = rc.get_stats()
    assert stats["current_rate"] == 1.0
    assert stats["throttle_decreases"] == 1
    assert stats["stability_increases"] == 0


# ===== detect_throttle_in_spans tests =====


def test_detect_throttle_http_429():
    """Test detection of HTTP 429 status."""
    spans = [{"span_id": "s1", "status_code": 429, "target": "api.example.com"}]
    events = detect_throttle_in_spans(spans)
    assert len(events) == 1
    assert events[0].throttle_type == ThrottleType.HTTP_429


def test_detect_throttle_aws_throttling_exception():
    """Test detection of AWS ThrottlingException."""
    spans = [{"span_id": "s1", "error": "ThrottlingException: Rate exceeded"}]
    events = detect_throttle_in_spans(spans)
    assert len(events) == 1
    assert events[0].throttle_type == ThrottleType.AWS_THROTTLE


def test_detect_throttle_provisioned_throughput():
    """Test detection of ProvisionedThroughputExceededException."""
    spans = [{"span_id": "s1", "error": "ProvisionedThroughputExceededException: Table full"}]
    events = detect_throttle_in_spans(spans)
    assert len(events) == 1
    assert events[0].throttle_type == ThrottleType.AWS_THROTTLE


def test_detect_throttle_retry_storm():
    """Test detection of high retry counts."""
    spans = [{"span_id": "s1", "retry_count": 5}]
    events = detect_throttle_in_spans(spans)
    assert len(events) == 1
    assert events[0].throttle_type == ThrottleType.RETRY_STORM


def test_detect_throttle_timeout():
    """Test detection of timeout errors."""
    spans = [{"span_id": "s1", "attributes": {"timeout": True}}]
    events = detect_throttle_in_spans(spans)
    assert len(events) == 1
    assert events[0].throttle_type == ThrottleType.TIMEOUT


def test_detect_throttle_no_events():
    """Test no throttle events for normal spans."""
    spans = [
        {"span_id": "s1", "status_code": 200},
        {"span_id": "s2", "status_code": 201},
    ]
    events = detect_throttle_in_spans(spans)
    assert len(events) == 0


def test_detect_throttle_multiple():
    """Test detection of multiple throttle types."""
    spans = [
        {"span_id": "s1", "status_code": 429},
        {"span_id": "s2", "error": "ThrottlingException"},
        {"span_id": "s3", "retry_count": 5},
    ]
    events = detect_throttle_in_spans(spans)
    assert len(events) == 3


# ===== run_soak tests =====


def test_run_soak_iterations_mode():
    """Test soak run in iterations mode."""
    config = SoakConfig(mode=SoakMode.ITERATIONS, iterations=5)
    call_count = 0

    def run_iteration(i: int) -> tuple[bool, list[dict], float]:
        nonlocal call_count
        call_count += 1
        return True, [], 10.0

    result = run_soak(config, run_iteration)

    assert call_count == 5
    assert result.total_iterations == 5
    assert result.pass_rate == 1.0


def test_run_soak_with_failures():
    """Test soak run with some failures."""
    config = SoakConfig(mode=SoakMode.ITERATIONS, iterations=4)

    def run_iteration(i: int) -> tuple[bool, list[dict], float]:
        # Fail every other iteration
        return i % 2 == 0, [], 10.0

    result = run_soak(config, run_iteration)

    assert result.total_iterations == 4
    assert result.total_passed == 2
    assert result.pass_rate == 0.5


def test_run_soak_with_throttle():
    """Test soak run with throttle detection."""
    config = SoakConfig(mode=SoakMode.ITERATIONS, iterations=3)

    def run_iteration(i: int) -> tuple[bool, list[dict], float]:
        # Second iteration has throttle
        spans = [{"span_id": "s1", "status_code": 429}] if i == 1 else []
        return True, spans, 10.0

    result = run_soak(config, run_iteration)

    assert result.total_iterations == 3
    assert len(result.all_throttle_events) == 1
    # Rate should have decreased after throttle
    assert result.final_rate < config.initial_rate


def test_run_soak_callbacks():
    """Test soak run callbacks."""
    config = SoakConfig(mode=SoakMode.ITERATIONS, iterations=3)
    iterations_seen = []
    rate_changes = []

    def run_iteration(i: int) -> tuple[bool, list[dict], float]:
        return True, [], 10.0

    def on_iteration(it: SoakIteration):
        iterations_seen.append(it.iteration)

    def on_rate_change(old: float, new: float, reason: str):
        rate_changes.append((old, new, reason))

    run_soak(
        config,
        run_iteration,
        on_iteration=on_iteration,
        on_rate_change=on_rate_change,
    )

    assert iterations_seen == [0, 1, 2]
