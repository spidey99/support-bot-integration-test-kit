"""Tests for the historical execution viewer module.

Tests cover:
- Execution grouping logic
- Status analysis
- Duration computation
- Gallery HTML rendering
- Local file loading
- Filtering
"""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from itk.report.historical_viewer import (
    ExecutionSummary,
    ViewResult,
    group_spans_by_execution,
    analyze_execution,
    compute_execution_duration,
    get_execution_timestamp,
    get_unique_components,
    build_execution_summary,
    filter_executions,
    render_gallery_html,
    load_logs_from_file,
)
from itk.trace.span_model import Span


def make_span(
    span_id: str = "span-1",
    component: str = "lambda",
    operation: str = "invoke",
    trace_id: str | None = "trace-abc",
    session_id: str | None = None,
    request_id: str | None = None,
    ts_start: str | None = "2026-01-18T10:00:00Z",
    ts_end: str | None = "2026-01-18T10:00:01Z",
    error: dict | None = None,
    attempt: int | None = None,
) -> Span:
    """Create a test span."""
    return Span(
        span_id=span_id,
        parent_span_id=None,
        operation=operation,
        component=component,
        ts_start=ts_start,
        ts_end=ts_end,
        request={"input": "test"},
        response={"output": "test"},
        error=error,
        attempt=attempt,
        itk_trace_id=trace_id,
        lambda_request_id=request_id,
        bedrock_session_id=session_id,
    )


class TestGroupSpansByExecution(unittest.TestCase):
    """Tests for group_spans_by_execution."""

    def test_groups_by_trace_id(self) -> None:
        """Spans with same trace_id are grouped together."""
        spans = [
            make_span(span_id="s1", trace_id="trace-1"),
            make_span(span_id="s2", trace_id="trace-1"),
            make_span(span_id="s3", trace_id="trace-2"),
        ]
        
        groups, orphans = group_spans_by_execution(spans)
        
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(groups["trace-1"]), 2)
        self.assertEqual(len(groups["trace-2"]), 1)
        self.assertEqual(len(orphans), 0)

    def test_groups_by_session_id_fallback(self) -> None:
        """Spans with session_id but no trace_id are grouped by session."""
        spans = [
            make_span(span_id="s1", trace_id=None, session_id="session-1"),
            make_span(span_id="s2", trace_id=None, session_id="session-1"),
        ]
        
        groups, orphans = group_spans_by_execution(spans)
        
        self.assertEqual(len(groups), 1)
        self.assertIn("session-1", groups)
        self.assertEqual(len(groups["session-1"]), 2)

    def test_groups_by_request_id_fallback(self) -> None:
        """Spans with request_id but no trace/session are grouped by request."""
        spans = [
            make_span(span_id="s1", trace_id=None, session_id=None, request_id="req-1"),
            make_span(span_id="s2", trace_id=None, session_id=None, request_id="req-1"),
        ]
        
        groups, orphans = group_spans_by_execution(spans)
        
        self.assertEqual(len(groups), 1)
        self.assertIn("req-1", groups)

    def test_orphan_spans_no_correlation_id(self) -> None:
        """Spans with no correlation ID are placed in orphans."""
        spans = [
            make_span(span_id="s1", trace_id=None, session_id=None, request_id=None),
        ]
        
        groups, orphans = group_spans_by_execution(spans)
        
        self.assertEqual(len(groups), 0)
        self.assertEqual(len(orphans), 1)

    def test_empty_input(self) -> None:
        """Empty span list returns empty results."""
        groups, orphans = group_spans_by_execution([])
        
        self.assertEqual(len(groups), 0)
        self.assertEqual(len(orphans), 0)


class TestAnalyzeExecution(unittest.TestCase):
    """Tests for analyze_execution."""

    def test_passed_status(self) -> None:
        """Clean execution returns passed status."""
        spans = [
            make_span(span_id="s1", error=None, attempt=None),
            make_span(span_id="s2", error=None, attempt=0),
        ]
        
        status, error_count, retry_count = analyze_execution(spans)
        
        self.assertEqual(status, "passed")
        self.assertEqual(error_count, 0)
        self.assertEqual(retry_count, 0)

    def test_error_status(self) -> None:
        """Execution with errors returns error status."""
        spans = [
            make_span(span_id="s1", error={"message": "fail"}),
            make_span(span_id="s2", error=None),
        ]
        
        status, error_count, retry_count = analyze_execution(spans)
        
        self.assertEqual(status, "error")
        self.assertEqual(error_count, 1)

    def test_warning_status_with_retries(self) -> None:
        """Execution with retries but no errors returns warning status."""
        spans = [
            make_span(span_id="s1", error=None, attempt=2),
            make_span(span_id="s2", error=None, attempt=1),
        ]
        
        status, error_count, retry_count = analyze_execution(spans)
        
        self.assertEqual(status, "warning")
        self.assertEqual(retry_count, 1)


class TestComputeExecutionDuration(unittest.TestCase):
    """Tests for compute_execution_duration."""

    def test_computes_duration(self) -> None:
        """Duration is computed from earliest start to latest end."""
        spans = [
            make_span(span_id="s1", ts_start="2026-01-18T10:00:00Z", ts_end="2026-01-18T10:00:02Z"),
            make_span(span_id="s2", ts_start="2026-01-18T10:00:01Z", ts_end="2026-01-18T10:00:03Z"),
        ]
        
        duration = compute_execution_duration(spans)
        
        # From 10:00:00 to 10:00:03 = 3000ms
        self.assertEqual(duration, 3000.0)

    def test_empty_spans_returns_zero(self) -> None:
        """Empty span list returns 0."""
        duration = compute_execution_duration([])
        self.assertEqual(duration, 0.0)

    def test_missing_timestamps_returns_zero(self) -> None:
        """Spans with no timestamps return 0."""
        spans = [make_span(ts_start=None, ts_end=None)]
        duration = compute_execution_duration(spans)
        self.assertEqual(duration, 0.0)


class TestGetExecutionTimestamp(unittest.TestCase):
    """Tests for get_execution_timestamp."""

    def test_returns_earliest_start(self) -> None:
        """Returns the earliest ts_start from all spans."""
        spans = [
            make_span(ts_start="2026-01-18T10:00:05Z"),
            make_span(ts_start="2026-01-18T10:00:00Z"),
        ]
        
        ts = get_execution_timestamp(spans)
        
        self.assertEqual(ts.hour, 10)
        self.assertEqual(ts.minute, 0)
        self.assertEqual(ts.second, 0)

    def test_empty_returns_min(self) -> None:
        """Empty list returns datetime.min."""
        ts = get_execution_timestamp([])
        self.assertEqual(ts.year, 1)


class TestGetUniqueComponents(unittest.TestCase):
    """Tests for get_unique_components."""

    def test_returns_sorted_unique_components(self) -> None:
        """Returns unique component names sorted."""
        spans = [
            make_span(component="lambda"),
            make_span(component="bedrock"),
            make_span(component="lambda"),
        ]
        
        components = get_unique_components(spans)
        
        self.assertEqual(components, ["bedrock", "lambda"])


class TestBuildExecutionSummary(unittest.TestCase):
    """Tests for build_execution_summary."""

    def test_builds_summary(self) -> None:
        """Builds a complete execution summary."""
        spans = [
            make_span(
                span_id="s1",
                component="lambda",
                ts_start="2026-01-18T10:00:00Z",
                ts_end="2026-01-18T10:00:01Z",
            ),
        ]
        
        summary = build_execution_summary("exec-123", spans, "exec-123")
        
        self.assertEqual(summary.execution_id, "exec-123")
        self.assertEqual(summary.span_count, 1)
        self.assertEqual(summary.status, "passed")
        self.assertEqual(summary.components, ["lambda"])
        self.assertEqual(summary.artifact_dir, "exec-123")

    def test_status_icon(self) -> None:
        """Status icon property returns correct icon."""
        summary = ExecutionSummary(
            execution_id="test",
            timestamp=datetime.now(timezone.utc),
            span_count=1,
            duration_ms=100,
            status="passed",
            error_count=0,
            retry_count=0,
            components=[],
            artifact_dir="test",
        )
        
        self.assertEqual(summary.status_icon, "✅")


class TestFilterExecutions(unittest.TestCase):
    """Tests for filter_executions."""

    def make_summary(self, status: str) -> ExecutionSummary:
        """Create a test summary."""
        return ExecutionSummary(
            execution_id=f"exec-{status}",
            timestamp=datetime.now(timezone.utc),
            span_count=1,
            duration_ms=100,
            status=status,
            error_count=1 if status == "error" else 0,
            retry_count=1 if status == "warning" else 0,
            components=[],
            artifact_dir=f"exec-{status}",
        )

    def test_filter_all(self) -> None:
        """Filter 'all' returns all executions."""
        execs = [self.make_summary("passed"), self.make_summary("error")]
        
        filtered = filter_executions(execs, "all")
        
        self.assertEqual(len(filtered), 2)

    def test_filter_errors(self) -> None:
        """Filter 'errors' returns only error executions."""
        execs = [self.make_summary("passed"), self.make_summary("error")]
        
        filtered = filter_executions(execs, "errors")
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].status, "error")

    def test_filter_warnings(self) -> None:
        """Filter 'warnings' returns warnings and errors."""
        execs = [
            self.make_summary("passed"),
            self.make_summary("warning"),
            self.make_summary("error"),
        ]
        
        filtered = filter_executions(execs, "warnings")
        
        self.assertEqual(len(filtered), 2)

    def test_filter_passed(self) -> None:
        """Filter 'passed' returns only passed executions."""
        execs = [self.make_summary("passed"), self.make_summary("error")]
        
        filtered = filter_executions(execs, "passed")
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].status, "passed")


class TestRenderGalleryHtml(unittest.TestCase):
    """Tests for render_gallery_html."""

    def test_renders_html_with_title(self) -> None:
        """Gallery HTML includes custom title."""
        result = ViewResult(
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc),
            total_logs=100,
            executions=[],
        )
        
        html = render_gallery_html(result, title="Test Gallery")
        
        self.assertIn("Test Gallery", html)
        self.assertIn("<!DOCTYPE html>", html)

    def test_renders_execution_rows(self) -> None:
        """Gallery HTML includes execution rows."""
        summary = ExecutionSummary(
            execution_id="exec-abc123def456",
            timestamp=datetime(2026, 1, 18, 10, 0, 0, tzinfo=timezone.utc),
            span_count=5,
            duration_ms=1500,
            status="passed",
            error_count=0,
            retry_count=0,
            components=["lambda", "bedrock"],
            artifact_dir="exec-abc123",
        )
        result = ViewResult(
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc),
            total_logs=100,
            executions=[summary],
        )
        
        html = render_gallery_html(result)
        
        self.assertIn("exec-abc123", html)  # Short ID
        self.assertIn("1.50s", html)  # Duration
        self.assertIn("lambda", html)  # Component badge
        self.assertIn("trace-viewer.html", html)  # View link

    def test_includes_stats(self) -> None:
        """Gallery HTML includes summary stats."""
        result = ViewResult(
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc),
            total_logs=500,
            executions=[],
        )
        
        html = render_gallery_html(result)
        
        self.assertIn("500", html)  # Total logs
        self.assertIn("Total Executions", html)

    def test_includes_filter_buttons(self) -> None:
        """Gallery HTML includes filter buttons."""
        result = ViewResult(
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc),
            total_logs=100,
            executions=[],
        )
        
        html = render_gallery_html(result)
        
        self.assertIn("filter-btn", html)
        self.assertIn("filterTable", html)

    def test_includes_dark_mode(self) -> None:
        """Gallery HTML includes dark mode support."""
        result = ViewResult(
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc),
            total_logs=100,
            executions=[],
        )
        
        html = render_gallery_html(result)
        
        self.assertIn("data-theme", html)
        self.assertIn("toggleTheme", html)


class TestLoadLogsFromFile(unittest.TestCase):
    """Tests for load_logs_from_file."""

    def test_loads_jsonl_file(self) -> None:
        """Loads JSONL file with log events."""
        with TemporaryDirectory() as tmp:
            logs_path = Path(tmp) / "test.jsonl"
            logs_path.write_text(
                '{"timestamp": "2026-01-18T10:00:00Z", "message": "test1"}\n'
                '{"timestamp": "2026-01-18T10:00:01Z", "message": "test2"}\n'
            )
            
            events = load_logs_from_file(logs_path)
            
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["message"], "test1")

    def test_handles_plain_text_lines(self) -> None:
        """Wraps plain text lines as messages."""
        with TemporaryDirectory() as tmp:
            logs_path = Path(tmp) / "test.jsonl"
            logs_path.write_text("plain text line\n")
            
            events = load_logs_from_file(logs_path)
            
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["message"], "plain text line")

    def test_skips_empty_lines(self) -> None:
        """Empty lines are skipped."""
        with TemporaryDirectory() as tmp:
            logs_path = Path(tmp) / "test.jsonl"
            logs_path.write_text('{"message": "test"}\n\n\n')
            
            events = load_logs_from_file(logs_path)
            
            self.assertEqual(len(events), 1)


class TestViewResult(unittest.TestCase):
    """Tests for ViewResult dataclass."""

    def test_properties(self) -> None:
        """ViewResult computes properties correctly."""
        passed = ExecutionSummary(
            execution_id="e1", timestamp=datetime.now(timezone.utc),
            span_count=1, duration_ms=100, status="passed",
            error_count=0, retry_count=0, components=[], artifact_dir="e1"
        )
        error = ExecutionSummary(
            execution_id="e2", timestamp=datetime.now(timezone.utc),
            span_count=1, duration_ms=100, status="error",
            error_count=1, retry_count=0, components=[], artifact_dir="e2"
        )
        warning = ExecutionSummary(
            execution_id="e3", timestamp=datetime.now(timezone.utc),
            span_count=1, duration_ms=100, status="warning",
            error_count=0, retry_count=1, components=[], artifact_dir="e3"
        )
        
        result = ViewResult(
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc),
            total_logs=100,
            executions=[passed, error, warning],
        )
        
        self.assertEqual(result.execution_count, 3)
        self.assertEqual(result.passed_count, 1)
        self.assertEqual(result.error_count, 1)
        self.assertEqual(result.warning_count, 1)


if __name__ == "__main__":
    unittest.main()
