"""Tests for timeline view module."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from itk.trace.span_model import Span
from itk.trace.trace_model import Trace
from itk.diagrams.timeline_view import (
    TimelineSpan,
    _parse_timestamp,
    _compute_duration_ms,
    _get_component_type,
    _build_span_tree,
    _find_critical_path,
    _extract_timeline_spans,
    _render_timeline_bar,
    _render_time_axis,
    render_timeline_viewer,
    render_mini_timeline,
)


# ============================================================================
# Test timestamp parsing
# ============================================================================


class TestTimestampParsing:
    """Tests for timestamp parsing functions."""

    def test_parse_valid_iso_timestamp(self) -> None:
        ts = "2024-01-15T10:30:00+00:00"
        result = _parse_timestamp(ts)
        assert result is not None
        assert result.year == 2024
        assert result.hour == 10

    def test_parse_z_suffix_timestamp(self) -> None:
        ts = "2024-01-15T10:30:00Z"
        result = _parse_timestamp(ts)
        assert result is not None
        assert result.year == 2024

    def test_parse_none_timestamp(self) -> None:
        result = _parse_timestamp(None)
        assert result is None

    def test_parse_invalid_timestamp(self) -> None:
        result = _parse_timestamp("not-a-date")
        assert result is None

    def test_compute_duration_valid(self) -> None:
        start = "2024-01-15T10:30:00+00:00"
        end = "2024-01-15T10:30:01+00:00"
        duration = _compute_duration_ms(start, end)
        assert duration == 1000.0

    def test_compute_duration_none_timestamps(self) -> None:
        duration = _compute_duration_ms(None, None)
        assert duration is None

    def test_compute_duration_partial_timestamps(self) -> None:
        duration = _compute_duration_ms("2024-01-15T10:30:00+00:00", None)
        assert duration is None


# ============================================================================
# Test helper functions
# ============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_component_type_with_colon(self) -> None:
        assert _get_component_type("lambda:handler") == "lambda"

    def test_get_component_type_without_colon(self) -> None:
        assert _get_component_type("lambda") == "lambda"

    def test_get_component_type_uppercase(self) -> None:
        assert _get_component_type("LAMBDA:Handler") == "lambda"

    def test_build_span_tree(self) -> None:
        spans = [
            Span(span_id="root", parent_span_id=None, component="comp", operation="op"),
            Span(span_id="child1", parent_span_id="root", component="comp", operation="op"),
            Span(span_id="child2", parent_span_id="root", component="comp", operation="op"),
        ]
        tree = _build_span_tree(spans)
        assert "root" in tree
        assert set(tree["root"]) == {"child1", "child2"}

    def test_build_span_tree_empty(self) -> None:
        tree = _build_span_tree([])
        assert tree == {}


# ============================================================================
# Test critical path detection
# ============================================================================


class TestCriticalPath:
    """Tests for critical path detection."""

    def test_find_critical_path_single_span(self) -> None:
        spans = [
            Span(
                span_id="s1", parent_span_id=None, component="comp", operation="op",
                ts_start="2024-01-15T10:00:00Z", ts_end="2024-01-15T10:00:01Z",
            ),
        ]
        span_map = {s.span_id: s for s in spans}
        tree = _build_span_tree(spans)
        
        critical = _find_critical_path(spans, span_map, tree)
        assert "s1" in critical

    def test_find_critical_path_chain(self) -> None:
        spans = [
            Span(
                span_id="s1", parent_span_id=None, component="comp", operation="op",
                ts_start="2024-01-15T10:00:00Z", ts_end="2024-01-15T10:00:01Z",
            ),
            Span(
                span_id="s2", parent_span_id="s1", component="comp", operation="op",
                ts_start="2024-01-15T10:00:01Z", ts_end="2024-01-15T10:00:03Z",
            ),
            Span(
                span_id="s3", parent_span_id="s1", component="comp", operation="op",
                ts_start="2024-01-15T10:00:01Z", ts_end="2024-01-15T10:00:01.5Z",
            ),
        ]
        span_map = {s.span_id: s for s in spans}
        tree = _build_span_tree(spans)
        
        critical = _find_critical_path(spans, span_map, tree)
        # s2 is longer than s3, so critical path should include s1 and s2
        assert "s1" in critical
        assert "s2" in critical

    def test_find_critical_path_empty(self) -> None:
        critical = _find_critical_path([], {}, {})
        assert critical == set()


# ============================================================================
# Test timeline extraction
# ============================================================================


class TestTimelineExtraction:
    """Tests for timeline span extraction."""

    def test_extract_timeline_spans_basic(self) -> None:
        spans = [
            Span(
                span_id="s1", parent_span_id=None, component="lambda:handler", operation="invoke",
                ts_start="2024-01-15T10:00:00Z", ts_end="2024-01-15T10:00:01Z",
            ),
            Span(
                span_id="s2", parent_span_id="s1", component="agent:supervisor", operation="process",
                ts_start="2024-01-15T10:00:00.5Z", ts_end="2024-01-15T10:00:00.8Z",
            ),
        ]
        trace = Trace(spans=spans)
        
        timeline_spans, min_t, max_t = _extract_timeline_spans(trace)
        
        assert len(timeline_spans) == 2
        assert max_t > min_t

    def test_extract_timeline_spans_no_timestamps(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp", operation="op"),
            Span(span_id="s2", parent_span_id="s1", component="comp2", operation="op"),
        ]
        trace = Trace(spans=spans)
        
        timeline_spans, min_t, max_t = _extract_timeline_spans(trace)
        
        # Should use sequential positioning
        assert len(timeline_spans) == 2
        assert timeline_spans[0].start_ms != timeline_spans[1].start_ms

    def test_extract_timeline_spans_empty(self) -> None:
        trace = Trace(spans=[])
        timeline_spans, min_t, max_t = _extract_timeline_spans(trace)
        assert timeline_spans == []

    def test_extract_timeline_spans_sorted_by_start(self) -> None:
        spans = [
            Span(
                span_id="s2", parent_span_id=None, component="comp", operation="op",
                ts_start="2024-01-15T10:00:01Z", ts_end="2024-01-15T10:00:02Z",
            ),
            Span(
                span_id="s1", parent_span_id=None, component="comp", operation="op",
                ts_start="2024-01-15T10:00:00Z", ts_end="2024-01-15T10:00:01Z",
            ),
        ]
        trace = Trace(spans=spans)
        
        timeline_spans, _, _ = _extract_timeline_spans(trace)
        
        # Should be sorted by start time, so s1 first
        assert timeline_spans[0].span.span_id == "s1"
        assert timeline_spans[1].span.span_id == "s2"


# ============================================================================
# Test SVG rendering
# ============================================================================


class TestSVGRendering:
    """Tests for SVG rendering functions."""

    def test_render_timeline_bar_basic(self) -> None:
        span = Span(span_id="s1", parent_span_id=None, component="lambda:handler", operation="invoke")
        ts = TimelineSpan(
            span=span,
            row=0,
            start_ms=0,
            end_ms=100,
            duration_ms=100,
            component_type="lambda",
            is_critical=False,
        )
        
        svg = _render_timeline_bar(ts, 1000, 800)
        
        assert "timeline-row" in svg
        assert "timeline-bar" in svg
        assert "invoke" in svg

    def test_render_timeline_bar_critical(self) -> None:
        span = Span(span_id="s1", parent_span_id=None, component="lambda:handler", operation="invoke")
        ts = TimelineSpan(
            span=span,
            row=0,
            start_ms=0,
            end_ms=100,
            duration_ms=100,
            component_type="lambda",
            is_critical=True,
        )
        
        svg = _render_timeline_bar(ts, 1000, 800)
        
        assert "critical" in svg
        assert "critical-dot" in svg

    def test_render_timeline_bar_error(self) -> None:
        span = Span(
            span_id="s1", parent_span_id=None, component="comp", operation="op",
            error={"message": "test error"},
        )
        ts = TimelineSpan(
            span=span,
            row=0,
            start_ms=0,
            end_ms=100,
            duration_ms=100,
            component_type="lambda",
            is_critical=False,
        )
        
        svg = _render_timeline_bar(ts, 1000, 800)
        
        assert "error" in svg

    def test_render_time_axis(self) -> None:
        svg = _render_time_axis(1000, 800, 5)
        
        assert "time-axis" in svg
        assert "axis-label" in svg


# ============================================================================
# Test full HTML rendering
# ============================================================================


class TestFullRendering:
    """Tests for full HTML document rendering."""

    def test_render_timeline_viewer_basic(self) -> None:
        spans = [
            Span(
                span_id="s1", parent_span_id=None, component="lambda:handler", operation="invoke",
                ts_start="2024-01-15T10:00:00Z", ts_end="2024-01-15T10:00:01Z",
            ),
        ]
        trace = Trace(spans=spans)
        
        html = render_timeline_viewer(trace, title="Test Timeline")
        
        assert "<!DOCTYPE html>" in html
        assert "<title>Test Timeline</title>" in html
        assert "timeline" in html
        assert "svgPanZoom" in html

    def test_render_timeline_viewer_has_stats(self) -> None:
        spans = [
            Span(
                span_id="s1", parent_span_id=None, component="comp", operation="op",
                ts_start="2024-01-15T10:00:00Z", ts_end="2024-01-15T10:00:01Z",
            ),
            Span(
                span_id="s2", parent_span_id="s1", component="comp2", operation="op",
                ts_start="2024-01-15T10:00:00.5Z", ts_end="2024-01-15T10:00:00.8Z",
                error={"message": "error"},
            ),
        ]
        trace = Trace(spans=spans)
        
        html = render_timeline_viewer(trace)
        
        assert "Spans:" in html
        assert "Total Duration:" in html
        assert "Critical Path:" in html
        assert "Errors:" in html

    def test_render_timeline_viewer_has_dark_mode(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp", operation="op"),
        ]
        trace = Trace(spans=spans)
        
        html = render_timeline_viewer(trace)
        
        assert 'data-theme="dark"' in html or "toggleTheme" in html
        assert "[data-theme" in html

    def test_render_timeline_viewer_has_details_panel(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp", operation="op"),
        ]
        trace = Trace(spans=spans)
        
        html = render_timeline_viewer(trace)
        
        assert "details-panel" in html
        assert "showDetails" in html

    def test_render_timeline_viewer_has_legend(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp", operation="op"),
        ]
        trace = Trace(spans=spans)
        
        html = render_timeline_viewer(trace)
        
        assert "legend" in html
        assert "Critical Path" in html

    def test_render_timeline_viewer_empty_trace(self) -> None:
        trace = Trace(spans=[])
        
        html = render_timeline_viewer(trace)
        
        assert "<!DOCTYPE html>" in html
        assert "Spans:" in html

    def test_render_timeline_viewer_includes_payloads(self) -> None:
        spans = [
            Span(
                span_id="s1", parent_span_id=None, component="comp", operation="op",
                request={"input": "hello"},
                response={"output": "world"},
            ),
        ]
        trace = Trace(spans=spans)
        
        html = render_timeline_viewer(trace)
        
        # Payloads should be in spans data for details panel
        assert '"request":' in html
        assert '"response":' in html


# ============================================================================
# Test mini timeline
# ============================================================================


class TestMiniTimeline:
    """Tests for mini timeline thumbnail rendering."""

    def test_render_mini_timeline_basic(self) -> None:
        spans = [
            Span(
                span_id="s1", parent_span_id=None, component="lambda:handler", operation="invoke",
                ts_start="2024-01-15T10:00:00Z", ts_end="2024-01-15T10:00:01Z",
            ),
        ]
        trace = Trace(spans=spans)
        
        svg = render_mini_timeline(trace)
        
        assert "<svg" in svg
        assert "width=" in svg
        assert "rect" in svg

    def test_render_mini_timeline_custom_dimensions(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp", operation="op"),
        ]
        trace = Trace(spans=spans)
        
        svg = render_mini_timeline(trace, width=300, height=100)
        
        assert 'width="300"' in svg
        assert 'height="100"' in svg

    def test_render_mini_timeline_critical_highlighting(self) -> None:
        spans = [
            Span(
                span_id="s1", parent_span_id=None, component="comp", operation="op",
                ts_start="2024-01-15T10:00:00Z", ts_end="2024-01-15T10:00:01Z",
            ),
        ]
        trace = Trace(spans=spans)
        
        svg = render_mini_timeline(trace)
        
        # Critical spans should have amber stroke
        assert "#f59e0b" in svg

    def test_render_mini_timeline_error_highlighting(self) -> None:
        spans = [
            Span(
                span_id="s1", parent_span_id=None, component="comp", operation="op",
                error={"message": "error"},
            ),
        ]
        trace = Trace(spans=spans)
        
        svg = render_mini_timeline(trace)
        
        # Error spans should have red stroke
        assert "#ef4444" in svg

    def test_render_mini_timeline_empty(self) -> None:
        trace = Trace(spans=[])
        
        svg = render_mini_timeline(trace)
        
        assert "<svg" in svg


# ============================================================================
# Test component colors
# ============================================================================


class TestComponentColors:
    """Tests for component color assignment."""

    def test_lambda_color(self) -> None:
        span = Span(span_id="s1", parent_span_id=None, component="lambda:handler", operation="op")
        ts = TimelineSpan(
            span=span, row=0, start_ms=0, end_ms=100, duration_ms=100,
            component_type="lambda", is_critical=False,
        )
        svg = _render_timeline_bar(ts, 1000, 800)
        assert "#ff9900" in svg  # Lambda orange

    def test_agent_color(self) -> None:
        span = Span(span_id="s1", parent_span_id=None, component="agent:supervisor", operation="op")
        ts = TimelineSpan(
            span=span, row=0, start_ms=0, end_ms=100, duration_ms=100,
            component_type="agent", is_critical=False,
        )
        svg = _render_timeline_bar(ts, 1000, 800)
        assert "#00a4ef" in svg  # Agent blue

    def test_unknown_component_uses_default(self) -> None:
        span = Span(span_id="s1", parent_span_id=None, component="unknown:thing", operation="op")
        ts = TimelineSpan(
            span=span, row=0, start_ms=0, end_ms=100, duration_ms=100,
            component_type="unknown", is_critical=False,
        )
        svg = _render_timeline_bar(ts, 1000, 800)
        assert "#6b7280" in svg  # Default gray
