"""Test parse.py handles realistic log format variance."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from itk.logs.parse import (
    extract_field,
    flatten_nested_log,
    load_realistic_logs_as_spans,
    normalize_log_to_span,
    parse_cloudwatch_logs,
)


class TestExtractField:
    """Test field extraction with multiple name variants."""

    def test_canonical_name(self) -> None:
        """Extract using canonical field name."""
        obj = {"span_id": "abc123"}
        assert extract_field(obj, "span_id") == "abc123"

    def test_alternative_name(self) -> None:
        """Extract using alternative field name."""
        obj = {"requestId": "req-123"}
        assert extract_field(obj, "lambda_request_id") == "req-123"

    def test_camel_case_variant(self) -> None:
        """Extract using camelCase variant."""
        obj = {"traceId": "trace-456"}
        assert extract_field(obj, "itk_trace_id") == "trace-456"

    def test_timestamp_variants(self) -> None:
        """Extract timestamp from various field names."""
        for name in ["timestamp", "ts_start", "time", "@timestamp"]:
            obj = {name: "2025-01-19T00:00:00Z"}
            assert extract_field(obj, "ts_start") == "2025-01-19T00:00:00Z"

    def test_default_when_missing(self) -> None:
        """Return default when field not found."""
        obj = {"other_field": "value"}
        assert extract_field(obj, "span_id") is None
        assert extract_field(obj, "span_id", "default") == "default"

    def test_nested_in_data(self) -> None:
        """Extract field nested under 'data' key."""
        obj = {"level": "INFO", "data": {"component": "lambda", "operation": "invoke"}}
        assert extract_field(obj, "component") == "lambda"
        assert extract_field(obj, "operation") == "invoke"

    def test_nested_in_record(self) -> None:
        """Extract field nested under 'record' key."""
        obj = {"timestamp": "2025-01-19T00:00:00Z", "record": {"span_type": "sqs"}}
        assert extract_field(obj, "component") == "sqs"  # span_type maps to component

    def test_nested_in_event(self) -> None:
        """Extract field nested under 'event' key."""
        obj = {"event": {"requestId": "req-123", "traceId": "trace-456"}}
        assert extract_field(obj, "lambda_request_id") == "req-123"
        assert extract_field(obj, "itk_trace_id") == "trace-456"

    def test_root_takes_precedence_over_nested(self) -> None:
        """Root-level field takes precedence over nested."""
        obj = {"component": "lambda", "data": {"component": "bedrock"}}
        assert extract_field(obj, "component") == "lambda"


class TestFlattenNestedLog:
    """Test flattening nested log structures."""

    def test_flatten_data_wrapper(self) -> None:
        """Flatten log with data wrapper."""
        obj = {
            "timestamp": "2025-01-19T00:00:00Z",
            "level": "INFO",
            "data": {"component": "lambda", "operation": "invoke"},
        }
        flat = flatten_nested_log(obj)
        assert flat["timestamp"] == "2025-01-19T00:00:00Z"
        assert flat["component"] == "lambda"
        assert flat["operation"] == "invoke"

    def test_flatten_preserves_root(self) -> None:
        """Root fields are not overwritten by nested."""
        obj = {
            "component": "root-component",
            "data": {"component": "nested-component", "extra": "value"},
        }
        flat = flatten_nested_log(obj)
        assert flat["component"] == "root-component"
        assert flat["extra"] == "value"

    def test_flatten_multiple_wrappers(self) -> None:
        """Flatten log with multiple wrapper keys."""
        obj = {
            "log": {"operation": "op1"},
            "context": {"traceId": "trace-123"},
        }
        flat = flatten_nested_log(obj)
        assert flat["operation"] == "op1"
        assert flat["traceId"] == "trace-123"


class TestNormalizeLogToSpan:
    """Test normalization of realistic logs to Span objects."""

    def test_realistic_lambda_log(self) -> None:
        """Normalize a realistic Lambda log entry."""
        log = {
            "level": "INFO",
            "message": "Request processed",
            "timestamp": "2025-01-19T00:00:00Z",
            "requestId": "req-123",
            "traceId": "trace-456",
            "component": "lambda",
            "operation": "invoke",
        }
        span = normalize_log_to_span(log)
        assert span is not None
        assert span.component == "lambda"
        assert span.operation == "invoke"
        assert span.ts_start == "2025-01-19T00:00:00Z"
        assert span.lambda_request_id == "req-123"
        assert span.itk_trace_id == "trace-456"

    def test_auto_generate_span_id(self) -> None:
        """Generate span_id when not present."""
        log = {
            "component": "lambda",
            "operation": "invoke",
            "traceId": "trace-123",
            "timestamp": "2025-01-19T00:00:00Z",
        }
        span = normalize_log_to_span(log)
        assert span is not None
        assert span.span_id.startswith("auto-")
        assert len(span.span_id) == 17  # "auto-" + 12 hex chars

    def test_infer_component_from_message(self) -> None:
        """Infer component when not explicitly provided."""
        log = {
            "message": "Lambda handler starting",
            "operation": "start",
        }
        span = normalize_log_to_span(log)
        assert span is not None
        assert span.component == "lambda"

    def test_skip_plain_debug_log(self) -> None:
        """Skip logs that aren't spans (no component/operation)."""
        log = {
            "level": "DEBUG",
            "message": "Just a debug message",
        }
        span = normalize_log_to_span(log)
        assert span is None

    def test_nested_span_data(self) -> None:
        """Normalize log with span data nested under wrapper key."""
        log = {
            "level": "INFO",
            "timestamp": "2025-01-19T00:00:00Z",
            "data": {
                "component": "lambda",
                "operation": "invoke",
                "requestId": "req-nested",
            },
        }
        span = normalize_log_to_span(log)
        assert span is not None
        assert span.component == "lambda"
        assert span.operation == "invoke"
        assert span.lambda_request_id == "req-nested"
        assert span.ts_start == "2025-01-19T00:00:00Z"


class TestLoadRealisticLogs:
    """Test loading JSONL files with realistic log formats."""

    def test_load_mixed_format_logs(self) -> None:
        """Load logs with mixed field naming conventions."""
        logs = [
            {"component": "lambda", "operation": "start", "timestamp": "2025-01-19T00:00:00Z"},
            {"span_type": "bedrock", "op": "invoke", "ts_start": "2025-01-19T00:00:01Z"},
            {"level": "DEBUG", "message": "ignored debug line"},  # Should be skipped
            {"component": "sqs", "action": "sendMessage", "time": "2025-01-19T00:00:02Z"},
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for log in logs:
                f.write(json.dumps(log) + "\n")
            f.flush()
            path = Path(f.name)

        try:
            spans = load_realistic_logs_as_spans(path)
            assert len(spans) == 3  # Debug line skipped
            assert spans[0].component == "lambda"
            assert spans[1].component == "bedrock"
            assert spans[2].component == "sqs"
        finally:
            path.unlink()

    def test_skip_non_json_lines(self) -> None:
        """Skip Lambda runtime messages and non-JSON lines."""
        content = """START RequestId: abc-123 Version: $LATEST
{"component": "lambda", "operation": "invoke"}
END RequestId: abc-123
REPORT RequestId: abc-123 Duration: 100 ms
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(content)
            f.flush()
            path = Path(f.name)

        try:
            spans = load_realistic_logs_as_spans(path)
            assert len(spans) == 1
            assert spans[0].component == "lambda"
        finally:
            path.unlink()


class TestParseCloudWatchLogs:
    """Test parsing CloudWatch log events."""

    def test_parse_events(self) -> None:
        """Parse structured CloudWatch events."""
        events = [
            {
                "timestamp": 1705622400000,
                "message": "START RequestId: abc-123 Version: $LATEST",
            },
            {
                "timestamp": 1705622400100,
                "message": '{"component": "lambda", "operation": "invoke", "requestId": "abc-123"}',
            },
            {
                "timestamp": 1705622400200,
                "message": "END RequestId: abc-123",
            },
        ]

        spans = parse_cloudwatch_logs(events)
        assert len(spans) == 1
        assert spans[0].component == "lambda"
        assert spans[0].lambda_request_id == "abc-123"

    def test_handle_non_json_messages(self) -> None:
        """Gracefully handle non-JSON messages."""
        events = [
            {"message": "Plain text log"},
            {"message": '{"component": "test", "operation": "op"}'},
        ]

        spans = parse_cloudwatch_logs(events)
        assert len(spans) == 1
