"""Tests for HTML sequence diagram renderer."""
from __future__ import annotations

import pytest

from itk.diagrams.html_renderer import (
    render_html_sequence,
    _extract_participants,
    _extract_messages,
    _get_component_type,
    _safe_id,
    _compute_latency,
    ParticipantInfo,
    COMPONENT_COLORS,
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

    def test_safe_id(self) -> None:
        assert _safe_id("lambda:handler") == "lambda_handler"
        assert _safe_id("span-001") == "span_001"
        assert _safe_id("my.component") == "my_component"

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

    def test_compute_latency_no_timestamps(self) -> None:
        span = Span(span_id="s1", parent_span_id=None, component="test", operation="op")
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
            Span(span_id="s3", parent_span_id=None, component="lambda:handler", operation="invoke"),  # duplicate
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
        unknown_p = next(p for p in participants if "unknown" in p.label)
        
        assert lambda_p.color == COMPONENT_COLORS["lambda"]
        assert unknown_p.color == COMPONENT_COLORS["default"]


# ============================================================================
# Test message extraction
# ============================================================================


class TestMessageExtraction:
    """Tests for message extraction."""

    def test_extract_messages_basic(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="lambda:handler", operation="invoke"),
            Span(
                span_id="s2",
                parent_span_id="s1",
                component="agent:supervisor",
                operation="process",
            ),
        ]
        trace = Trace(spans=spans)
        participants = _extract_participants(trace)
        
        messages = _extract_messages(trace, participants)
        
        assert len(messages) == 2
        assert messages[0].operation == "invoke"
        assert messages[1].operation == "process"

    def test_message_error_detection(self) -> None:
        spans = [
            Span(
                span_id="s1",
                parent_span_id=None,
                component="lambda:handler",
                operation="invoke",
                error={"message": "failed"},
            ),
        ]
        trace = Trace(spans=spans)
        participants = _extract_participants(trace)
        
        messages = _extract_messages(trace, participants)
        
        assert messages[0].has_error is True

    def test_message_attempt_number(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="lambda:handler", operation="invoke", attempt=3),
        ]
        trace = Trace(spans=spans)
        participants = _extract_participants(trace)
        
        messages = _extract_messages(trace, participants)
        
        assert messages[0].attempt == 3


# ============================================================================
# Test HTML rendering
# ============================================================================


class TestHtmlRendering:
    """Tests for HTML rendering."""

    def test_render_basic_diagram(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="lambda:handler", operation="invoke"),
        ]
        trace = Trace(spans=spans)
        
        html = render_html_sequence(trace)
        
        assert "<!DOCTYPE html>" in html
        assert "lambda:handler" in html
        assert "invoke" in html

    def test_render_with_title(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="lambda:handler", operation="invoke"),
        ]
        trace = Trace(spans=spans)
        
        html = render_html_sequence(trace, title="My Test Diagram")
        
        assert "My Test Diagram" in html

    def test_render_includes_dark_mode_toggle(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="lambda:handler", operation="invoke"),
        ]
        trace = Trace(spans=spans)
        
        html = render_html_sequence(trace)
        
        assert "Dark Mode" in html
        assert "toggleTheme" in html

    def test_render_includes_zoom_controls(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="lambda:handler", operation="invoke"),
        ]
        trace = Trace(spans=spans)
        
        html = render_html_sequence(trace)
        
        assert "zoom" in html.lower()
        assert "resetZoom" in html

    def test_render_with_payloads(self) -> None:
        spans = [
            Span(
                span_id="s1",
                parent_span_id=None,
                component="lambda:handler",
                operation="invoke",
                request={"key": "value"},
                response={"status": "ok"},
            ),
        ]
        trace = Trace(spans=spans)
        
        html = render_html_sequence(trace, include_payloads=True)
        
        assert "View Payloads" in html
        # JSON keys are escaped in HTML
        assert "key" in html
        assert "value" in html

    def test_render_without_payloads(self) -> None:
        spans = [
            Span(
                span_id="s1",
                parent_span_id=None,
                component="lambda:handler",
                operation="invoke",
                request={"key": "value"},
            ),
        ]
        trace = Trace(spans=spans)
        
        html = render_html_sequence(trace, include_payloads=False)
        
        assert "View Payloads" not in html

    def test_render_error_styling(self) -> None:
        spans = [
            Span(
                span_id="s1",
                parent_span_id=None,
                component="lambda:handler",
                operation="invoke",
                error={"message": "Something went wrong"},
            ),
        ]
        trace = Trace(spans=spans)
        
        html = render_html_sequence(trace)
        
        assert "error" in html  # error class applied
        assert "Something went wrong" in html

    def test_render_retry_badge(self) -> None:
        spans = [
            Span(
                span_id="s1",
                parent_span_id=None,
                component="lambda:handler",
                operation="invoke",
                attempt=2,
            ),
        ]
        trace = Trace(spans=spans)
        
        html = render_html_sequence(trace)
        
        # attempt=2 means first retry, so badge shows "retry 1"
        assert "retry 1" in html
        assert "retry-badge" in html

    def test_render_latency_display(self) -> None:
        spans = [
            Span(
                span_id="s1",
                parent_span_id=None,
                component="lambda:handler",
                operation="invoke",
                ts_start="2024-01-01T00:00:00Z",
                ts_end="2024-01-01T00:00:00.500Z",
            ),
        ]
        trace = Trace(spans=spans)
        
        html = render_html_sequence(trace)
        
        assert "500ms" in html

    def test_render_stats_section(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="lambda:handler", operation="invoke"),
            Span(span_id="s2", parent_span_id="s1", component="agent:supervisor", operation="process"),
        ]
        trace = Trace(spans=spans)
        
        html = render_html_sequence(trace)
        
        assert "Spans:" in html
        assert "Participants:" in html
        assert "Errors:" in html

    def test_render_multiple_participants(self) -> None:
        spans = [
            Span(span_id="s1", parent_span_id=None, component="entrypoint:sqs", operation="receive"),
            Span(span_id="s2", parent_span_id="s1", component="lambda:handler", operation="invoke"),
            Span(span_id="s3", parent_span_id="s2", component="agent:supervisor", operation="process"),
            Span(span_id="s4", parent_span_id="s3", component="model:claude", operation="generate"),
        ]
        trace = Trace(spans=spans)
        
        html = render_html_sequence(trace)
        
        assert "entrypoint:sqs" in html
        assert "lambda:handler" in html
        assert "agent:supervisor" in html
        assert "model:claude" in html

    def test_render_escapes_html(self) -> None:
        spans = [
            Span(
                span_id="s1",
                parent_span_id=None,
                component="test<script>",
                operation="<alert>",
            ),
        ]
        trace = Trace(spans=spans)
        
        html = render_html_sequence(trace)
        
        # The component/operation names should be escaped
        assert "test&lt;script&gt;" in html
        assert "&lt;alert&gt;" in html
