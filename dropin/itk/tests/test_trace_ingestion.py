"""Tests for Bedrock trace ingestion and span conversion."""
from __future__ import annotations

from pathlib import Path

import pytest

from itk.trace.span_model import Span
from itk.trace.trace_model import (
    BedrockTraceEvent,
    bedrock_traces_to_spans,
    load_bedrock_trace_jsonl,
    merge_trace_into_log_spans,
    parse_bedrock_trace_event,
)


class TestBedrockTraceEvent:
    """Tests for parsing Bedrock trace events."""

    def test_parse_basic_event(self) -> None:
        """Parse a basic Bedrock trace event."""
        raw = {
            "sessionId": "sess-123",
            "traceId": "trace-456",
            "event": "orchestrationTrace",
            "timestamp": "2026-01-15T12:00:00Z",
            "trace": {
                "orchestrationTrace": {
                    "modelInvocationInput": {"text": "hello"}
                }
            },
        }

        event = parse_bedrock_trace_event(raw)

        assert event.session_id == "sess-123"
        assert event.trace_id == "trace-456"
        assert event.event_type == "orchestrationTrace"
        assert event.timestamp == "2026-01-15T12:00:00Z"

    def test_orchestration_trace_extraction(self) -> None:
        """Extract orchestrationTrace from event."""
        raw = {
            "sessionId": "sess-123",
            "traceId": "trace-456",
            "event": "orchestrationTrace",
            "timestamp": "2026-01-15T12:00:00Z",
            "trace": {
                "orchestrationTrace": {
                    "modelInvocationInput": {"text": "hello"}
                }
            },
        }

        event = parse_bedrock_trace_event(raw)
        orch = event.orchestration_trace

        assert orch is not None
        assert "modelInvocationInput" in orch


class TestLoadBedrockTrace:
    """Tests for loading Bedrock trace files."""

    def test_load_sample_trace(self, fixtures_dir: Path) -> None:
        """Load the sample Bedrock trace fixture."""
        trace_path = fixtures_dir / "traces" / "bedrock_trace_sample_001.jsonl"

        events = load_bedrock_trace_jsonl(trace_path)

        assert len(events) == 5  # 5 events in sample
        assert all(e.session_id == "sess-111" for e in events)
        assert all(e.event_type == "orchestrationTrace" for e in events)


class TestBedrockTracesToSpans:
    """Tests for converting Bedrock traces to spans."""

    def test_model_invocation_span(self, fixtures_dir: Path) -> None:
        """Convert model invocation input/output to a span."""
        trace_path = fixtures_dir / "traces" / "bedrock_trace_sample_001.jsonl"
        events = load_bedrock_trace_jsonl(trace_path)

        spans = bedrock_traces_to_spans(events)

        # Should have model invocation span
        model_spans = [s for s in spans if "InvokeModel" in s.operation]
        assert len(model_spans) >= 1

        span = model_spans[0]
        assert span.component == "agent:bedrock-model"
        assert span.bedrock_session_id == "sess-111"
        assert span.request is not None
        assert span.response is not None

    def test_action_group_span(self, fixtures_dir: Path) -> None:
        """Convert action group invocation to a span."""
        trace_path = fixtures_dir / "traces" / "bedrock_trace_sample_001.jsonl"
        events = load_bedrock_trace_jsonl(trace_path)

        spans = bedrock_traces_to_spans(events)

        # Should have action group span
        action_spans = [s for s in spans if "InvokeActionGroup" in s.operation]
        assert len(action_spans) >= 1

        span = action_spans[0]
        assert "actionGroupFoo" in span.component
        assert span.request is not None
        assert "actionGroupName" in span.request

    def test_rationale_span(self, fixtures_dir: Path) -> None:
        """Convert rationale to a span."""
        trace_path = fixtures_dir / "traces" / "bedrock_trace_sample_001.jsonl"
        events = load_bedrock_trace_jsonl(trace_path)

        spans = bedrock_traces_to_spans(events)

        # Should have rationale span
        rationale_spans = [s for s in spans if "Rationale" in s.operation]
        assert len(rationale_spans) >= 1

        span = rationale_spans[0]
        assert span.request is not None
        assert "reasoning" in span.request


class TestMergeTraceIntoLogSpans:
    """Tests for merging trace spans with log spans."""

    def test_enrich_log_span_with_trace(self) -> None:
        """Trace span enriches log span with missing payload."""
        log_spans = [
            Span(
                span_id="log-001",
                parent_span_id=None,
                component="agent:bedrock",
                operation="InvokeModel",
                ts_start="2026-01-15T12:00:00Z",
                bedrock_session_id="sess-123",
                request=None,  # Missing
                response=None,  # Missing
            )
        ]

        trace_spans = [
            Span(
                span_id="trace-001",
                parent_span_id=None,
                component="agent:bedrock-model",
                operation="InvokeModel",
                ts_start="2026-01-15T12:00:00Z",
                bedrock_session_id="sess-123",
                request={"text": "hello"},
                response={"text": "world"},
            )
        ]

        merged = merge_trace_into_log_spans(log_spans, trace_spans)

        # Log span should be enriched
        enriched = next(s for s in merged if s.span_id == "log-001")
        assert enriched.request == {"text": "hello"}
        assert enriched.response == {"text": "world"}

    def test_preserve_log_span_payloads(self) -> None:
        """Log span payloads are preserved when present."""
        log_spans = [
            Span(
                span_id="log-001",
                parent_span_id=None,
                component="agent:bedrock",
                operation="InvokeModel",
                ts_start="2026-01-15T12:00:00Z",
                bedrock_session_id="sess-123",
                request={"original": True},  # Already has payload
                response={"original": True},
            )
        ]

        trace_spans = [
            Span(
                span_id="trace-001",
                parent_span_id=None,
                component="agent:bedrock-model",
                operation="InvokeModel",
                ts_start="2026-01-15T12:00:00Z",
                bedrock_session_id="sess-123",
                request={"from_trace": True},
                response={"from_trace": True},
            )
        ]

        merged = merge_trace_into_log_spans(log_spans, trace_spans)

        enriched = next(s for s in merged if s.span_id == "log-001")
        assert enriched.request == {"original": True}  # Preserved
        assert enriched.response == {"original": True}  # Preserved

    def test_add_unmatched_trace_spans(self) -> None:
        """Trace spans without matching log spans are added."""
        log_spans = [
            Span(
                span_id="log-001",
                parent_span_id=None,
                component="entrypoint:sqs",
                operation="Start",
                # No session ID - won't match
            )
        ]

        trace_spans = [
            Span(
                span_id="trace-001",
                parent_span_id=None,
                component="agent:bedrock-model",
                operation="InvokeModel",
                bedrock_session_id="sess-123",
                request={"text": "hello"},
            )
        ]

        merged = merge_trace_into_log_spans(log_spans, trace_spans)

        # Should have both spans
        assert len(merged) == 2
        span_ids = {s.span_id for s in merged}
        assert "log-001" in span_ids
        assert "trace-001" in span_ids
