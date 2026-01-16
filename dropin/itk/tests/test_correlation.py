"""Tests for ID extraction and correlation stitching."""
from __future__ import annotations

import pytest

from itk.correlation.id_extractors import (
    ExtractedIds,
    extract_all_ids_from_text,
    extract_bedrock_session_id,
    extract_ids_from_event,
    extract_lambda_request_id,
    extract_sqs_message_id,
    extract_xray_trace_id,
)
from itk.correlation.stitch_graph import stitch_spans_by_id
from itk.trace.span_model import Span


class TestXrayExtraction:
    """Tests for X-Ray trace ID extraction."""

    def test_extract_from_header(self) -> None:
        """Extract X-Ray trace ID from standard header format."""
        header = "Root=1-67890abc-def0123456789;Parent=abcd1234;Sampled=1"
        result = extract_xray_trace_id(header)
        assert result == "1-67890abc-def0123456789"

    def test_extract_from_partial_header(self) -> None:
        """Extract X-Ray trace ID from partial header."""
        header = "Root=1-12345678-abcdef"
        result = extract_xray_trace_id(header)
        assert result == "1-12345678-abcdef"

    def test_no_match_returns_none(self) -> None:
        """Return None when no X-Ray ID present."""
        result = extract_xray_trace_id("no trace id here")
        assert result is None


class TestLambdaRequestIdExtraction:
    """Tests for Lambda request ID extraction."""

    def test_extract_from_log_format(self) -> None:
        """Extract Lambda request ID from standard log format."""
        log_line = "START RequestId: 12345678-1234-1234-1234-123456789012 Version: $LATEST"
        result = extract_lambda_request_id(log_line)
        assert result == "12345678-1234-1234-1234-123456789012"

    def test_extract_uuid_from_lambda_context(self) -> None:
        """Extract UUID when 'lambda' keyword present."""
        text = "lambda invocation abc12345-1234-1234-1234-123456789012"
        result = extract_lambda_request_id(text)
        assert result == "abc12345-1234-1234-1234-123456789012"


class TestEventExtraction:
    """Tests for extracting IDs from event dictionaries."""

    def test_extract_direct_fields(self) -> None:
        """Extract IDs from top-level event fields."""
        event = {
            "lambda_request_id": "req-123",
            "xray_trace_id": "xray-456",
            "sqs_message_id": "sqs-789",
        }
        result = extract_ids_from_event(event)
        assert result.lambda_request_id == "req-123"
        assert result.xray_trace_id == "xray-456"
        assert result.sqs_message_id == "sqs-789"

    def test_extract_from_sqs_records(self) -> None:
        """Extract SQS message ID from Records array."""
        event = {
            "Records": [
                {"messageId": "msg-abc123-def456-ghi789-jkl012-mno345"}
            ]
        }
        result = extract_ids_from_event(event)
        assert result.sqs_message_id == "msg-abc123-def456-ghi789-jkl012-mno345"

    def test_extract_from_nested_context(self) -> None:
        """Extract Lambda request ID from nested context."""
        event = {
            "context": {
                "aws_request_id": "ctx-req-123"
            }
        }
        result = extract_ids_from_event(event)
        assert result.lambda_request_id == "ctx-req-123"


class TestStitchGraph:
    """Tests for span stitching by correlation ID."""

    def test_stitch_by_common_id(self) -> None:
        """Spans with the same correlation ID are stitched together."""
        spans = [
            Span(
                span_id="s1",
                parent_span_id=None,
                component="a",
                operation="op1",
                lambda_request_id="req-shared",
            ),
            Span(
                span_id="s2",
                parent_span_id=None,
                component="b",
                operation="op2",
                lambda_request_id="req-shared",
            ),
            Span(
                span_id="s3",
                parent_span_id=None,
                component="c",
                operation="op3",
                lambda_request_id="req-other",
            ),
        ]

        result = stitch_spans_by_id(spans, seed_span_ids={"s1"})

        # s1 and s2 share lambda_request_id, so both should be included
        assert len(result.spans) == 2
        span_ids = {s.span_id for s in result.spans}
        assert "s1" in span_ids
        assert "s2" in span_ids
        assert "s3" not in span_ids

    def test_stitch_transitive(self) -> None:
        """Stitching works transitively through shared IDs."""
        spans = [
            Span(
                span_id="s1",
                parent_span_id=None,
                component="a",
                operation="op1",
                lambda_request_id="req-a",
            ),
            Span(
                span_id="s2",
                parent_span_id=None,
                component="b",
                operation="op2",
                lambda_request_id="req-a",
                bedrock_session_id="sess-b",
            ),
            Span(
                span_id="s3",
                parent_span_id=None,
                component="c",
                operation="op3",
                bedrock_session_id="sess-b",
            ),
        ]

        result = stitch_spans_by_id(spans, seed_span_ids={"s1"})

        # s1 -> s2 (via lambda_request_id) -> s3 (via bedrock_session_id)
        assert len(result.spans) == 3

    def test_stitch_all_spans_when_no_seed(self) -> None:
        """When no seed, use all spans with correlation IDs."""
        spans = [
            Span(
                span_id="s1",
                parent_span_id=None,
                component="a",
                operation="op1",
                lambda_request_id="req-1",
            ),
            Span(
                span_id="s2",
                parent_span_id=None,
                component="b",
                operation="op2",
                # No correlation IDs
            ),
        ]

        result = stitch_spans_by_id(spans)

        # s1 has ID and is its own group; s2 has no IDs
        assert len(result.spans) == 1
        assert result.spans[0].span_id == "s1"


class TestExtractedIds:
    """Tests for ExtractedIds helper methods."""

    def test_has_any_true(self) -> None:
        """has_any returns True when at least one ID present."""
        ids = ExtractedIds(lambda_request_id="req-123")
        assert ids.has_any() is True

    def test_has_any_false(self) -> None:
        """has_any returns False when no IDs present."""
        ids = ExtractedIds()
        assert ids.has_any() is False

    def test_all_ids_returns_dict(self) -> None:
        """all_ids returns dict of non-None IDs."""
        ids = ExtractedIds(
            lambda_request_id="req-123",
            bedrock_session_id="sess-456",
        )
        result = ids.all_ids()
        assert result == {
            "lambda_request_id": "req-123",
            "bedrock_session_id": "sess-456",
        }
