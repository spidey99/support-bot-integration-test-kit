"""Tests for invariant checks."""
from __future__ import annotations

import pytest

from itk.trace.span_model import Span
from itk.trace.trace_model import Trace
from itk.assertions.invariants import (
    InvariantConfig,
    InvariantResult,
    run_invariants,
    run_all_invariants,
    _check_has_spans,
    _check_no_duplicate_span_ids,
    _check_no_orphan_spans,
    _check_valid_timestamps,
    _check_max_retry_count,
    _check_required_components,
    _check_has_entrypoint,
    _check_no_error_spans,
)


def make_span(
    span_id: str = "s1",
    parent_span_id: str | None = None,
    component: str = "lambda:test",
    operation: str = "Invoke",
    **kwargs,
) -> Span:
    """Helper to create test spans."""
    return Span(
        span_id=span_id,
        parent_span_id=parent_span_id,
        component=component,
        operation=operation,
        **kwargs,
    )


class TestHasSpans:
    """Tests for has_spans invariant."""

    def test_passes_with_spans(self) -> None:
        trace = Trace(spans=[make_span()])
        result = _check_has_spans(trace)
        assert result.passed
        assert result.details["count"] == 1

    def test_fails_with_empty_trace(self) -> None:
        trace = Trace(spans=[])
        result = _check_has_spans(trace)
        assert not result.passed
        assert result.details["count"] == 0


class TestNoDuplicateSpanIds:
    """Tests for no_duplicate_span_ids invariant."""

    def test_passes_with_unique_ids(self) -> None:
        trace = Trace(spans=[
            make_span(span_id="s1"),
            make_span(span_id="s2"),
            make_span(span_id="s3"),
        ])
        result = _check_no_duplicate_span_ids(trace)
        assert result.passed

    def test_fails_with_duplicates(self) -> None:
        trace = Trace(spans=[
            make_span(span_id="s1"),
            make_span(span_id="s1"),  # duplicate
            make_span(span_id="s2"),
        ])
        result = _check_no_duplicate_span_ids(trace)
        assert not result.passed
        assert "s1" in result.details["duplicates"]


class TestNoOrphanSpans:
    """Tests for no_orphan_spans invariant."""

    def test_passes_with_root_spans(self) -> None:
        trace = Trace(spans=[
            make_span(span_id="s1", parent_span_id=None),
        ])
        result = _check_no_orphan_spans(trace)
        assert result.passed

    def test_passes_with_valid_parent_refs(self) -> None:
        trace = Trace(spans=[
            make_span(span_id="s1", parent_span_id=None),
            make_span(span_id="s2", parent_span_id="s1"),
        ])
        result = _check_no_orphan_spans(trace)
        assert result.passed

    def test_fails_with_orphan(self) -> None:
        trace = Trace(spans=[
            make_span(span_id="s1", parent_span_id=None),
            make_span(span_id="s2", parent_span_id="nonexistent"),
        ])
        result = _check_no_orphan_spans(trace)
        assert not result.passed
        assert "s2" in result.details["orphan_span_ids"]


class TestValidTimestamps:
    """Tests for valid_timestamps invariant."""

    def test_passes_with_valid_timestamps(self) -> None:
        trace = Trace(spans=[
            make_span(
                ts_start="2026-01-15T12:00:00.000Z",
                ts_end="2026-01-15T12:00:01.000Z",
            ),
        ])
        result = _check_valid_timestamps(trace)
        assert result.passed

    def test_passes_with_equal_timestamps(self) -> None:
        trace = Trace(spans=[
            make_span(
                ts_start="2026-01-15T12:00:00.000Z",
                ts_end="2026-01-15T12:00:00.000Z",
            ),
        ])
        result = _check_valid_timestamps(trace)
        assert result.passed

    def test_fails_with_end_before_start(self) -> None:
        trace = Trace(spans=[
            make_span(
                span_id="bad",
                ts_start="2026-01-15T12:00:01.000Z",
                ts_end="2026-01-15T12:00:00.000Z",
            ),
        ])
        result = _check_valid_timestamps(trace)
        assert not result.passed
        assert len(result.details["invalid_spans"]) == 1
        assert result.details["invalid_spans"][0]["span_id"] == "bad"

    def test_passes_with_missing_timestamps(self) -> None:
        trace = Trace(spans=[
            make_span(ts_start=None, ts_end=None),
        ])
        result = _check_valid_timestamps(trace)
        assert result.passed


class TestMaxRetryCount:
    """Tests for max_retry_count invariant."""

    def test_passes_within_limit(self) -> None:
        trace = Trace(spans=[
            make_span(span_id="s1", attempt=1),
            make_span(span_id="s2", attempt=2),
            make_span(span_id="s3", attempt=3),
        ])
        result = _check_max_retry_count(trace, max_retries=5)
        assert result.passed

    def test_fails_exceeding_limit(self) -> None:
        trace = Trace(spans=[
            make_span(span_id="s1", attempt=1),
            make_span(span_id="excessive", attempt=10),  # 9 retries
        ])
        result = _check_max_retry_count(trace, max_retries=5)
        assert not result.passed
        assert len(result.details["excessive_spans"]) == 1
        assert result.details["excessive_spans"][0]["span_id"] == "excessive"

    def test_passes_with_no_attempts(self) -> None:
        trace = Trace(spans=[
            make_span(attempt=None),
        ])
        result = _check_max_retry_count(trace, max_retries=0)
        assert result.passed


class TestRequiredComponents:
    """Tests for required_components invariant."""

    def test_passes_with_all_required(self) -> None:
        trace = Trace(spans=[
            make_span(component="lambda:foo"),
            make_span(span_id="s2", component="model:claude"),
        ])
        result = _check_required_components(trace, ["lambda:foo", "model:claude"])
        assert result.passed

    def test_fails_with_missing(self) -> None:
        trace = Trace(spans=[
            make_span(component="lambda:foo"),
        ])
        result = _check_required_components(trace, ["lambda:foo", "model:claude"])
        assert not result.passed
        assert "model:claude" in result.details["missing"]

    def test_passes_with_empty_required(self) -> None:
        trace = Trace(spans=[make_span()])
        result = _check_required_components(trace, [])
        assert result.passed


class TestHasEntrypoint:
    """Tests for has_entrypoint invariant."""

    def test_passes_with_root_span(self) -> None:
        trace = Trace(spans=[
            make_span(parent_span_id=None),
        ])
        result = _check_has_entrypoint(trace)
        assert result.passed
        assert result.details["root_count"] == 1

    def test_fails_with_no_roots(self) -> None:
        trace = Trace(spans=[
            make_span(parent_span_id="nonexistent"),
        ])
        result = _check_has_entrypoint(trace)
        assert not result.passed
        assert result.details["root_count"] == 0


class TestNoErrorSpans:
    """Tests for no_error_spans invariant."""

    def test_passes_without_errors(self) -> None:
        trace = Trace(spans=[
            make_span(error=None),
        ])
        result = _check_no_error_spans(trace)
        assert result.passed

    def test_fails_with_errors(self) -> None:
        trace = Trace(spans=[
            make_span(error={"message": "boom"}),
        ])
        result = _check_no_error_spans(trace)
        assert not result.passed
        assert len(result.details["error_spans"]) == 1


class TestRunInvariants:
    """Tests for run_invariants function."""

    def test_runs_default_invariants(self) -> None:
        trace = Trace(spans=[make_span()])
        results = run_invariants(trace)

        # Should have standard invariants
        names = {r.name for r in results}
        assert "has_spans" in names
        assert "no_duplicate_span_ids" in names
        assert "has_entrypoint" in names
        assert "no_orphan_spans" in names
        assert "valid_timestamps" in names
        assert "max_retry_count" in names

    def test_respects_config(self) -> None:
        trace = Trace(spans=[
            make_span(component="lambda:foo"),
        ])
        config = InvariantConfig(
            required_components=["lambda:foo", "model:claude"],
            check_orphans=False,
        )
        results = run_invariants(trace, config)

        names = {r.name for r in results}
        assert "required_components" in names
        # Should fail because model:claude is missing
        req_result = next(r for r in results if r.name == "required_components")
        assert not req_result.passed

    def test_all_pass_for_valid_trace(self) -> None:
        trace = Trace(spans=[
            make_span(
                span_id="s1",
                parent_span_id=None,
                ts_start="2026-01-15T12:00:00Z",
                ts_end="2026-01-15T12:00:01Z",
            ),
        ])
        results = run_invariants(trace)
        assert all(r.passed for r in results)


class TestRunAllInvariants:
    """Tests for run_all_invariants function."""

    def test_includes_error_check(self) -> None:
        trace = Trace(spans=[make_span()])
        results = run_all_invariants(trace)
        names = {r.name for r in results}
        assert "no_error_spans" in names
