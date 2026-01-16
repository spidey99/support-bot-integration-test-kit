"""Tests for enhanced interactive trace viewer."""
from __future__ import annotations

import json
import pytest

from itk.diagrams.trace_viewer import (
    render_trace_viewer,
    render_mini_svg,
    _extract_participants,
    _extract_messages,
    _get_component_type,
    _safe_id,
    _compute_latency,
    _build_span_tree,
    _get_ancestors,
    _get_descendants,
    _render_svg_participant,
    _render_svg_message,
    _load_vendor_js,
    ParticipantInfo,
    MessageInfo,
    COMPONENT_COLORS,
    PARTICIPANT_WIDTH,
    PARTICIPANT_GAP,
    PADDING,
)
from itk.trace.span_model import Span
from itk.trace.trace_model import Trace


# ============================================================================
# Test helper functions
# ============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_component_type_with_colon(self) -> None:
        assert _get_component_type("lambda:handler") == "lambda"
        assert _get_component_type("agent:gatekeeper") == "agent"
        assert _get_component_type("model:claude-3-sonnet") == "model"

    def test_get_component_type_without_colon(self) -> None:
        assert _get_component_type("lambda") == "lambda"
        assert _get_component_type("SQS") == "sqs"
        assert _get_component_type("BEDROCK") == "bedrock"

    def test_safe_id_special_chars(self) -> None:
        assert _safe_id("lambda:handler") == "lambda_handler"
        assert _safe_id("span-001") == "span_001"
        assert _safe_id("my.component") == "my_component"

    def test_safe_id_starts_with_digit(self) -> None:
        assert _safe_id("123span") == "id_123span"
        assert _safe_id("1-test") == "id_1_test"

    def test_safe_id_empty(self) -> None:
        assert _safe_id("") == "unknown"

    def test_compute_latency_valid(self) -> None:
        span = Span(
            span_id="s1",
            parent_span_id=None,
            component="test",
            operation="op",
            ts_start="2024-01-01T00:00:00Z",
            ts_end="2024-01-01T00:00:01Z",
        )
        latency = _compute_latency(span)
        assert latency is not None
        assert abs(latency - 1000.0) < 1  # 1 second = 1000ms

    def test_compute_latency_milliseconds(self) -> None:
        span = Span(
            span_id="s1",
            parent_span_id=None,
            component="test",
            operation="op",
            ts_start="2024-01-01T00:00:00.000Z",
            ts_end="2024-01-01T00:00:00.250Z",
        )
        latency = _compute_latency(span)
        assert latency is not None
        assert abs(latency - 250.0) < 1  # 250ms

    def test_compute_latency_no_timestamps(self) -> None:
        span = Span(
            span_id="s1",
            parent_span_id=None,
            component="test",
            operation="op",
        )
        assert _compute_latency(span) is None

    def test_compute_latency_partial_timestamps(self) -> None:
        span = Span(
            span_id="s1",
            parent_span_id=None,
            component="test",
            operation="op",
            ts_start="2024-01-01T00:00:00Z",
        )
        assert _compute_latency(span) is None


# ============================================================================
# Test participant extraction
# ============================================================================


class TestParticipantExtraction:
    """Tests for participant extraction."""

    def test_extract_unique_participants(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="lambda:handler", operation="invoke"),
            Span(span_id="s2", parent_span_id="s1", component="agent:supervisor", operation="process"),
            Span(span_id="s3", parent_span_id=None, component="lambda:handler", operation="invoke"),
        ]
        trace = Trace(spans=spans)

        participants = _extract_participants(trace)

        assert len(participants) == 2
        labels = {p.label for p in participants}
        assert "lambda:handler" in labels
        assert "agent:supervisor" in labels

    def test_participant_color_assignment(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="lambda:handler", operation="invoke"),
            Span(span_id="s2", parent_span_id=None, component="unknown:component", operation="op"),
        ]
        trace = Trace(spans=spans)

        participants = _extract_participants(trace)

        lambda_p = next(p for p in participants if "lambda" in p.label)
        assert lambda_p.color == COMPONENT_COLORS["lambda"]

        unknown_p = next(p for p in participants if "unknown" in p.label)
        assert unknown_p.color == COMPONENT_COLORS["default"]

    def test_participant_ordering(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="first", operation="op"),
            Span(span_id="s2", parent_span_id=None, component="second", operation="op"),
            Span(span_id="s3", parent_span_id=None, component="third", operation="op"),
        ]
        trace = Trace(spans=spans)

        participants = _extract_participants(trace)

        assert participants[0].label == "first"
        assert participants[0].index == 0
        assert participants[1].label == "second"
        assert participants[1].index == 1
        assert participants[2].label == "third"
        assert participants[2].index == 2

    def test_participant_x_center_calculation(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp1", operation="op"),
            Span(span_id="s2", parent_span_id=None, component="comp2", operation="op"),
        ]
        trace = Trace(spans=spans)

        participants = _extract_participants(trace)

        p1 = participants[0]
        expected_x1 = PADDING + 0 * (PARTICIPANT_WIDTH + PARTICIPANT_GAP) + PARTICIPANT_WIDTH // 2
        assert p1.x_center == expected_x1

        p2 = participants[1]
        expected_x2 = PADDING + 1 * (PARTICIPANT_WIDTH + PARTICIPANT_GAP) + PARTICIPANT_WIDTH // 2
        assert p2.x_center == expected_x2


# ============================================================================
# Test message extraction
# ============================================================================


class TestMessageExtraction:
    """Tests for message extraction."""

    def test_extract_messages_basic(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp1", operation="invoke"),
            Span(span_id="s2", parent_span_id="s1", component="comp2", operation="process"),
        ]
        trace = Trace(spans=spans)
        participants = _extract_participants(trace)

        messages = _extract_messages(trace, participants)

        assert len(messages) == 2
        assert messages[0].span_id == "s1"
        assert messages[1].span_id == "s2"

    def test_extract_messages_with_error(self) -> None:
        spans = [
            Span(
                span_id="s1",
                parent_span_id=None,
                component="comp",
                operation="op",
                error={"message": "fail"},
            ),
        ]
        trace = Trace(spans=spans)
        participants = _extract_participants(trace)

        messages = _extract_messages(trace, participants)

        assert messages[0].has_error is True

    def test_extract_messages_with_retry(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp", operation="op", attempt=3),
        ]
        trace = Trace(spans=spans)
        participants = _extract_participants(trace)

        messages = _extract_messages(trace, participants)

        assert messages[0].attempt == 3

    def test_extract_messages_with_payloads(self) -> None:
        spans = [
            Span(
                span_id="s1",
                parent_span_id=None,
                component="comp",
                operation="op",
                request={"input": "test"},
                response={"output": "result"},
            ),
        ]
        trace = Trace(spans=spans)
        participants = _extract_participants(trace)

        messages = _extract_messages(trace, participants)

        assert messages[0].request == {"input": "test"}
        assert messages[0].response == {"output": "result"}


# ============================================================================
# Test span tree operations
# ============================================================================


class TestSpanTree:
    """Tests for span tree building and traversal."""

    def test_build_span_tree(self) -> None:
        spans = [
            Span(span_id="root", parent_span_id=None, component="comp", operation="op"),
            Span(span_id="child1", parent_span_id="root", component="comp", operation="op"),
            Span(span_id="child2", parent_span_id="root", component="comp", operation="op"),
            Span(span_id="grandchild", parent_span_id="child1", component="comp", operation="op"),
        ]
        trace = Trace(spans=spans)

        tree = _build_span_tree(trace)

        assert "root" in tree
        assert set(tree["root"]) == {"child1", "child2"}
        assert "child1" in tree
        assert tree["child1"] == ["grandchild"]

    def test_get_descendants(self) -> None:
        tree = {
            "root": ["child1", "child2"],
            "child1": ["grandchild1", "grandchild2"],
            "grandchild1": ["greatgrand"],
        }

        descendants = _get_descendants("root", tree)

        assert set(descendants) == {"child1", "child2", "grandchild1", "grandchild2", "greatgrand"}

    def test_get_descendants_empty(self) -> None:
        tree = {"root": ["child"]}

        descendants = _get_descendants("child", tree)

        assert descendants == []


# ============================================================================
# Test SVG rendering
# ============================================================================


class TestSVGRendering:
    """Tests for SVG element rendering."""

    def test_render_svg_participant(self) -> None:
        p = ParticipantInfo(
            id="test_id",
            label="test:component",
            component_type="lambda",
            index=0,
        )

        svg = _render_svg_participant(p, height=500)

        assert 'class="participant"' in svg
        assert 'data-participant="test_id"' in svg
        assert 'class="lifeline"' in svg
        assert "test:component" in svg

    def test_render_svg_message(self) -> None:
        p1 = ParticipantInfo(id="p1", label="comp1", component_type="lambda", index=0)
        p2 = ParticipantInfo(id="p2", label="comp2", component_type="agent", index=1)

        span = Span(span_id="s1", parent_span_id=None, component="comp1", operation="invoke")

        msg = MessageInfo(
            span_id="s1",
            span=span,
            from_participant=p1,
            to_participant=p2,
            operation="invoke",
            attempt=1,
            latency_ms=100.0,
            has_error=False,
            y_position=100,
            request=None,
            response=None,
            error=None,
        )

        svg = _render_svg_message(msg, {})

        assert 'class="message' in svg
        assert 'data-span-id="s1"' in svg
        assert "invoke" in svg

    def test_render_svg_message_error(self) -> None:
        p = ParticipantInfo(id="p1", label="comp", component_type="lambda", index=0)

        span = Span(span_id="s1", parent_span_id=None, component="comp", operation="op")

        msg = MessageInfo(
            span_id="s1",
            span=span,
            from_participant=p,
            to_participant=p,
            operation="op",
            attempt=1,
            latency_ms=None,
            has_error=True,
            y_position=100,
            request=None,
            response=None,
            error={"message": "fail"},
        )

        svg = _render_svg_message(msg, {})

        assert "error" in svg

    def test_render_svg_message_retry(self) -> None:
        p = ParticipantInfo(id="p1", label="comp", component_type="lambda", index=0)

        span = Span(span_id="s1", parent_span_id=None, component="comp", operation="op")

        msg = MessageInfo(
            span_id="s1",
            span=span,
            from_participant=p,
            to_participant=p,
            operation="op",
            attempt=3,
            latency_ms=None,
            has_error=False,
            y_position=100,
            request=None,
            response=None,
            error=None,
        )

        svg = _render_svg_message(msg, {})

        assert "retry 3" in svg
        assert "retry-badge" in svg

    def test_render_svg_message_has_call_and_return_arrows(self) -> None:
        """Test that messages have both call and return arrows."""
        p1 = ParticipantInfo(id="p1", label="comp1", component_type="lambda", index=0)
        p2 = ParticipantInfo(id="p2", label="comp2", component_type="agent", index=1)

        span = Span(span_id="s1", parent_span_id=None, component="comp1", operation="invoke")

        msg = MessageInfo(
            span_id="s1",
            span=span,
            from_participant=p1,
            to_participant=p2,
            operation="invoke",
            attempt=1,
            latency_ms=100.0,
            has_error=False,
            y_position=100,
            request=None,
            response=None,
            error=None,
        )

        svg = _render_svg_message(msg, {})

        # Should have call arrow (solid)
        assert 'marker-end="url(#arrowhead)"' in svg
        # Should have return arrow (dashed)
        assert 'stroke-dasharray="4,2"' in svg
        assert 'marker-end="url(#arrowhead-return)"' in svg
        # Should have activation box
        assert 'class="activation-box"' in svg

    def test_render_svg_message_has_status_indicator(self) -> None:
        """Test that messages have status indicators."""
        p1 = ParticipantInfo(id="p1", label="comp1", component_type="lambda", index=0)
        p2 = ParticipantInfo(id="p2", label="comp2", component_type="agent", index=1)

        # Success case
        span_ok = Span(span_id="s1", parent_span_id=None, component="comp1", operation="op")
        msg_ok = MessageInfo(
            span_id="s1", span=span_ok, from_participant=p1, to_participant=p2,
            operation="op", attempt=1, latency_ms=100, has_error=False,
            y_position=100, request=None, response=None, error=None,
        )
        svg_ok = _render_svg_message(msg_ok, {})
        assert "✅" in svg_ok
        assert "status-success" in svg_ok

        # Error case
        span_err = Span(span_id="s2", parent_span_id=None, component="comp1", operation="op")
        msg_err = MessageInfo(
            span_id="s2", span=span_err, from_participant=p1, to_participant=p2,
            operation="op", attempt=1, latency_ms=100, has_error=True,
            y_position=100, request=None, response=None, error={"msg": "fail"},
        )
        svg_err = _render_svg_message(msg_err, {})
        assert "❌" in svg_err
        assert "status-error" in svg_err

    def test_render_svg_message_async_no_return_arrow(self) -> None:
        """Test that async spans don't have return arrows."""
        p1 = ParticipantInfo(id="p1", label="comp1", component_type="lambda", index=0)
        p2 = ParticipantInfo(id="p2", label="comp2", component_type="sqs", index=1)

        span = Span(
            span_id="s1", parent_span_id=None, component="comp1", operation="send",
            is_async=True,  # Fire-and-forget
        )
        msg = MessageInfo(
            span_id="s1", span=span, from_participant=p1, to_participant=p2,
            operation="send", attempt=1, latency_ms=50, has_error=False,
            y_position=100, request=None, response=None, error=None,
        )

        svg = _render_svg_message(msg, {})

        # Should have call arrow
        assert 'marker-end="url(#arrowhead)"' in svg
        # Should NOT have return arrow
        assert 'marker-end="url(#arrowhead-return)"' not in svg


# ============================================================================
# Test full render
# ============================================================================


class TestFullRender:
    """Tests for full trace viewer rendering."""

    def test_render_trace_viewer_basic(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="lambda:handler", operation="invoke"),
            Span(span_id="s2", parent_span_id="s1", component="agent:supervisor", operation="process"),
        ]
        trace = Trace(spans=spans)

        html = render_trace_viewer(trace, title="Test Viewer")

        assert "<!DOCTYPE html>" in html
        assert "<title>Test Viewer</title>" in html
        assert "svg" in html
        assert "svgPanZoom" in html
        assert "Fuse" in html

    def test_render_trace_viewer_includes_stats(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp1", operation="op"),
            Span(span_id="s2", parent_span_id=None, component="comp2", operation="op", error={"msg": "fail"}),
            Span(span_id="s3", parent_span_id=None, component="comp1", operation="op", attempt=2),
        ]
        trace = Trace(spans=spans)

        html = render_trace_viewer(trace)

        # Check stats bar content
        assert "Spans:" in html
        assert "Participants:" in html
        assert "Errors:" in html
        assert "Retries:" in html

    def test_render_trace_viewer_has_dark_mode(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp", operation="op"),
        ]
        trace = Trace(spans=spans)

        html = render_trace_viewer(trace)

        assert '[data-theme="dark"]' in html
        assert "toggleTheme" in html

    def test_render_trace_viewer_has_search(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp", operation="op"),
        ]
        trace = Trace(spans=spans)

        html = render_trace_viewer(trace)

        assert 'class="search-input"' in html
        assert 'fuse.search' in html

    def test_render_trace_viewer_has_filters(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp", operation="op"),
        ]
        trace = Trace(spans=spans)

        html = render_trace_viewer(trace)

        assert 'data-filter="errors"' in html
        assert 'data-filter="retries"' in html

    def test_render_trace_viewer_has_keyboard_shortcuts(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp", operation="op"),
        ]
        trace = Trace(spans=spans)

        html = render_trace_viewer(trace)

        assert "e.key === '/'" in html
        assert "e.key === 'Escape'" in html
        assert "ArrowDown" in html
        assert "ArrowUp" in html

    def test_render_trace_viewer_has_details_panel(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp", operation="op"),
        ]
        trace = Trace(spans=spans)

        html = render_trace_viewer(trace)

        assert 'class="details-panel' in html
        assert "showDetails" in html
        assert "closeDetails" in html

    def test_render_trace_viewer_includes_payload_data(self) -> None:
        """Test that payload data is passed to JavaScript for details panel."""
        spans = [
            Span(
                span_id="s1",
                parent_span_id=None,
                component="lambda:handler",
                operation="invoke",
                request={"input": "hello"},
                response={"output": "world"},
            ),
            Span(
                span_id="s2",
                parent_span_id="s1",
                component="agent:supervisor",
                operation="process",
                error={"message": "test error"},
            ),
        ]
        trace = Trace(spans=spans)

        html = render_trace_viewer(trace)

        # Verify request/response/error data is included in spans_json
        assert '"request":' in html
        assert '"response":' in html
        assert '"error":' in html
        assert '"input": "hello"' in html
        assert '"output": "world"' in html
        assert '"message": "test error"' in html
        # Verify target field is included
        assert '"target":' in html

    def test_render_trace_viewer_has_payload_helpers(self) -> None:
        """Test that payload rendering helper functions are included."""
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp", operation="op"),
        ]
        trace = Trace(spans=spans)

        html = render_trace_viewer(trace)

        # Verify payload helper functions
        assert "renderPayloadSection" in html
        assert "formatBytes" in html
        assert "copyPayload" in html
        # Verify copy button and size indicator CSS
        assert ".copy-btn" in html
        assert ".payload-size" in html
        assert ".payload-truncated" in html
        # Verify truncation constant
        assert "MAX_PAYLOAD_DISPLAY" in html

    def test_render_trace_viewer_empty_trace(self) -> None:
        trace = Trace(spans=[])

        html = render_trace_viewer(trace)

        assert "<!DOCTYPE html>" in html
        assert "Spans:" in html


# ============================================================================
# Test mini SVG
# ============================================================================


class TestMiniSVG:
    """Tests for mini SVG thumbnail rendering."""

    def test_render_mini_svg_basic(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp1", operation="op"),
            Span(span_id="s2", parent_span_id="s1", component="comp2", operation="op"),
        ]
        trace = Trace(spans=spans)

        svg = render_mini_svg(trace)

        assert "<svg" in svg
        assert "width=" in svg
        assert "height=" in svg
        assert "<line" in svg
        assert "<circle" in svg

    def test_render_mini_svg_custom_dimensions(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp", operation="op"),
        ]
        trace = Trace(spans=spans)

        svg = render_mini_svg(trace, width=100, height=50)

        assert 'width="100"' in svg
        assert 'height="50"' in svg

    def test_render_mini_svg_error_highlighted(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="comp", operation="op", error={"msg": "fail"}),
        ]
        trace = Trace(spans=spans)

        svg = render_mini_svg(trace)

        # Error messages should be colored red
        assert "#ef4444" in svg

    def test_render_mini_svg_empty_trace(self) -> None:
        trace = Trace(spans=[])

        svg = render_mini_svg(trace)

        assert "<svg" in svg
        assert "</svg>" in svg


# ============================================================================
# Test vendored libraries
# ============================================================================


class TestVendoredLibraries:
    """Tests for vendored JS library loading."""

    def test_load_svg_pan_zoom(self) -> None:
        js = _load_vendor_js("svg-pan-zoom.min.js")

        assert "svgPanZoom" in js
        assert "zoomIn" in js or "zoom" in js

    def test_load_fuse(self) -> None:
        js = _load_vendor_js("fuse.min.js")

        assert "Fuse" in js
        assert "search" in js

    def test_load_nonexistent_file(self) -> None:
        js = _load_vendor_js("nonexistent.js")

        assert "not found" in js


# ============================================================================
# Test ParticipantInfo dataclass
# ============================================================================


class TestParticipantInfo:
    """Tests for ParticipantInfo dataclass."""

    def test_auto_color_assignment(self) -> None:
        p = ParticipantInfo(id="p1", label="test", component_type="lambda", index=0)

        assert p.color == COMPONENT_COLORS["lambda"]

    def test_custom_color_preserved(self) -> None:
        custom_color = {"bg": "#123456", "text": "#fff", "icon": "X", "stroke": "#000"}
        p = ParticipantInfo(
            id="p1",
            label="test",
            component_type="lambda",
            index=0,
            color=custom_color,
        )

        assert p.color == custom_color

    def test_unknown_component_type_uses_default(self) -> None:
        p = ParticipantInfo(id="p1", label="test", component_type="unknown_type", index=0)

        assert p.color == COMPONENT_COLORS["default"]
