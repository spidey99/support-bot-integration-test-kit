"""Tests for compare module - path signatures and delta detection."""
from __future__ import annotations

import pytest

from itk.trace.span_model import Span
from itk.trace.trace_model import Trace
from itk.compare.path_signature import (
    PathSignature,
    extract_path_signature,
    compute_trace_latency_ms,
)
from itk.compare.compare import (
    PathDelta,
    CompareResult,
    compare_traces,
    compare_trace_sets,
)


class TestPathSignature:
    """Tests for PathSignature dataclass."""

    def test_signature_string_simple(self) -> None:
        sig = PathSignature(
            steps=(("lambda:foo", "Invoke"), ("model:claude", "InvokeModel")),
            has_error=False,
            retry_count=0,
        )
        assert sig.signature_string == "lambda:foo:Invoke -> model:claude:InvokeModel"

    def test_signature_string_with_error(self) -> None:
        sig = PathSignature(
            steps=(("lambda:foo", "Invoke"),),
            has_error=True,
            retry_count=0,
        )
        assert "[ERROR]" in sig.signature_string

    def test_signature_string_with_retries(self) -> None:
        sig = PathSignature(
            steps=(("lambda:foo", "Invoke"),),
            has_error=False,
            retry_count=2,
        )
        assert "[RETRIES:2]" in sig.signature_string

    def test_signature_equality(self) -> None:
        sig1 = PathSignature(steps=(("a", "b"),), has_error=False)
        sig2 = PathSignature(steps=(("a", "b"),), has_error=False)
        sig3 = PathSignature(steps=(("a", "b"),), has_error=True)
        assert sig1 == sig2
        assert sig1 != sig3


class TestExtractPathSignature:
    """Tests for extract_path_signature function."""

    def test_empty_trace(self) -> None:
        trace = Trace(spans=[])
        sig = extract_path_signature(trace)
        assert sig.steps == ()
        assert not sig.has_error

    def test_single_span(self) -> None:
        span = Span(
            span_id="s1",
            parent_span_id=None,
            component="lambda:foo",
            operation="Invoke",
        )
        trace = Trace(spans=[span])
        sig = extract_path_signature(trace)
        assert sig.steps == (("lambda:foo", "Invoke"),)

    def test_ordered_by_timestamp(self) -> None:
        spans = [
            Span(
                span_id="s2",
                parent_span_id=None,
                component="model:claude",
                operation="InvokeModel",
                ts_start="2026-01-15T12:00:01.000Z",
            ),
            Span(
                span_id="s1",
                parent_span_id=None,
                component="lambda:foo",
                operation="Invoke",
                ts_start="2026-01-15T12:00:00.000Z",
            ),
        ]
        trace = Trace(spans=spans)
        sig = extract_path_signature(trace)
        # Should be ordered by timestamp
        assert sig.steps[0] == ("lambda:foo", "Invoke")
        assert sig.steps[1] == ("model:claude", "InvokeModel")

    def test_detects_error(self) -> None:
        span = Span(
            span_id="s1",
            parent_span_id=None,
            component="lambda:foo",
            operation="Invoke",
            error={"message": "boom"},
        )
        trace = Trace(spans=[span])
        sig = extract_path_signature(trace)
        assert sig.has_error

    def test_counts_retries(self) -> None:
        spans = [
            Span(
                span_id="s1",
                parent_span_id=None,
                component="model:claude",
                operation="InvokeModel",
                attempt=1,
            ),
            Span(
                span_id="s2",
                parent_span_id=None,
                component="model:claude",
                operation="InvokeModel",
                attempt=2,
            ),
            Span(
                span_id="s3",
                parent_span_id=None,
                component="model:claude",
                operation="InvokeModel",
                attempt=3,
            ),
        ]
        trace = Trace(spans=spans)
        sig = extract_path_signature(trace)
        assert sig.retry_count == 2  # 3 attempts = 2 retries


class TestComputeTraceLatency:
    """Tests for compute_trace_latency_ms function."""

    def test_empty_trace(self) -> None:
        trace = Trace(spans=[])
        assert compute_trace_latency_ms(trace) == 0.0

    def test_no_timestamps(self) -> None:
        span = Span(
            span_id="s1",
            parent_span_id=None,
            component="lambda:foo",
            operation="Invoke",
        )
        trace = Trace(spans=[span])
        assert compute_trace_latency_ms(trace) == 0.0

    def test_computes_latency(self) -> None:
        spans = [
            Span(
                span_id="s1",
                parent_span_id=None,
                component="lambda:foo",
                operation="Invoke",
                ts_start="2026-01-15T12:00:00.000Z",
                ts_end="2026-01-15T12:00:01.000Z",
            ),
        ]
        trace = Trace(spans=spans)
        latency = compute_trace_latency_ms(trace)
        assert latency == pytest.approx(1000.0, abs=1.0)


class TestPathDelta:
    """Tests for PathDelta dataclass."""

    def test_is_new(self) -> None:
        sig = PathSignature(steps=(("a", "b"),))
        delta = PathDelta(signature=sig, baseline_count=0, current_count=1)
        assert delta.is_new
        assert not delta.is_missing

    def test_is_missing(self) -> None:
        sig = PathSignature(steps=(("a", "b"),))
        delta = PathDelta(signature=sig, baseline_count=1, current_count=0)
        assert delta.is_missing
        assert not delta.is_new

    def test_latency_delta(self) -> None:
        sig = PathSignature(steps=(("a", "b"),))
        delta = PathDelta(
            signature=sig,
            baseline_count=1,
            current_count=1,
            baseline_avg_latency_ms=100.0,
            current_avg_latency_ms=150.0,
        )
        assert delta.latency_delta_ms == 50.0
        assert delta.latency_delta_pct == pytest.approx(50.0)

    def test_error_rate_delta(self) -> None:
        sig = PathSignature(steps=(("a", "b"),))
        delta = PathDelta(
            signature=sig,
            baseline_count=10,
            current_count=10,
            baseline_error_count=1,
            current_error_count=3,
        )
        assert delta.error_rate_baseline == pytest.approx(0.1)
        assert delta.error_rate_current == pytest.approx(0.3)
        assert delta.error_rate_delta == pytest.approx(0.2)


class TestCompareTraces:
    """Tests for compare_traces function."""

    def test_identical_traces(self) -> None:
        span = Span(
            span_id="s1",
            parent_span_id=None,
            component="lambda:foo",
            operation="Invoke",
        )
        trace_a = Trace(spans=[span])
        trace_b = Trace(spans=[span])
        result = compare_traces(trace_a, trace_b)
        assert not result.has_regressions
        assert len(result.new_paths) == 0
        assert len(result.missing_paths) == 0

    def test_detect_new_path(self) -> None:
        trace_a = Trace(spans=[])
        trace_b = Trace(spans=[
            Span(
                span_id="s1",
                parent_span_id=None,
                component="lambda:foo",
                operation="Invoke",
            )
        ])
        result = compare_traces(trace_a, trace_b)
        assert len(result.new_paths) == 1

    def test_detect_missing_path(self) -> None:
        trace_a = Trace(spans=[
            Span(
                span_id="s1",
                parent_span_id=None,
                component="lambda:foo",
                operation="Invoke",
            )
        ])
        trace_b = Trace(spans=[])
        result = compare_traces(trace_a, trace_b)
        assert len(result.missing_paths) == 1
        assert result.has_regressions


class TestCompareTraceSets:
    """Tests for compare_trace_sets function."""

    def test_aggregate_stats(self) -> None:
        span = Span(
            span_id="s1",
            parent_span_id=None,
            component="lambda:foo",
            operation="Invoke",
            ts_start="2026-01-15T12:00:00.000Z",
            ts_end="2026-01-15T12:00:01.000Z",
        )
        baselines = [Trace(spans=[span]) for _ in range(5)]
        currents = [Trace(spans=[span]) for _ in range(3)]
        result = compare_trace_sets(baselines, currents)
        assert len(result.deltas) == 1
        assert result.deltas[0].baseline_count == 5
        assert result.deltas[0].current_count == 3

    def test_error_regression_detected(self) -> None:
        # Same span structure, but different path due to error presence
        # The error changes the path signature, resulting in a "new" error path
        # and a "missing" success path
        good_span = Span(
            span_id="s1",
            parent_span_id=None,
            component="lambda:foo",
            operation="Invoke",
        )
        bad_span = Span(
            span_id="s1",
            parent_span_id=None,
            component="lambda:foo",
            operation="Invoke",
            error={"message": "boom"},
        )
        baselines = [Trace(spans=[good_span])]
        currents = [Trace(spans=[bad_span])]
        result = compare_trace_sets(baselines, currents)
        # The error path is "new" and the success path is "missing"
        assert result.has_regressions  # missing path = regression
        assert len(result.missing_paths) == 1  # good path missing
        assert len(result.new_paths) == 1  # error path is new


class TestCompareResult:
    """Tests for CompareResult properties."""

    def test_significant_latency_changes(self) -> None:
        sig = PathSignature(steps=(("a", "b"),))
        result = CompareResult(
            baseline_label="a",
            current_label="b",
            deltas=[
                PathDelta(
                    signature=sig,
                    baseline_count=1,
                    current_count=1,
                    baseline_avg_latency_ms=100.0,
                    current_avg_latency_ms=150.0,  # 50% increase
                ),
            ],
        )
        assert len(result.significant_latency_changes) == 1
