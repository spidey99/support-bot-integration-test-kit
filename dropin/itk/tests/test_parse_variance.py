"""Test parse.py handles realistic log format variance."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from itk.logs.parse import (
    extract_field,
    extract_thread_id_from_message,
    flatten_nested_log,
    load_realistic_logs_as_spans,
    normalize_log_to_span,
    parse_cloudwatch_logs,
    try_parse_python_dict_repr,
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


class TestStringifiedJsonParsing:
    """Test handling of stringified JSON within log fields."""

    def test_parse_stringified_json_in_message(self) -> None:
        """Parse stringified JSON inside a message field."""
        from itk.logs.parse import try_parse_stringified_json

        value = '{"component": "lambda", "operation": "invoke"}'
        parsed = try_parse_stringified_json(value)
        assert isinstance(parsed, dict)
        assert parsed["component"] == "lambda"
        assert parsed["operation"] == "invoke"

    def test_parse_double_stringified_json(self) -> None:
        """Parse double-stringified JSON (escaped quotes)."""
        from itk.logs.parse import try_parse_stringified_json

        # Double-stringify: first json.dumps produces '{"component": "lambda"}'
        # second json.dumps wraps it in quotes producing '"{\"component\": \"lambda\"}"'
        inner = json.dumps({"component": "lambda"})
        value = json.dumps(inner)
        parsed = try_parse_stringified_json(value)
        assert isinstance(parsed, dict)
        assert parsed["component"] == "lambda"

    def test_parse_triple_stringified_json(self) -> None:
        """Parse triple-stringified JSON (deeply escaped)."""
        from itk.logs.parse import try_parse_stringified_json

        inner = {"component": "lambda", "operation": "invoke"}
        value = json.dumps(json.dumps(json.dumps(inner)))
        parsed = try_parse_stringified_json(value)
        assert isinstance(parsed, dict)
        assert parsed["component"] == "lambda"

    def test_parse_stringified_json_in_dict(self) -> None:
        """Parse stringified JSON within dict values."""
        from itk.logs.parse import parse_stringified_json_in_dict

        obj = {
            "level": "INFO",
            "message": '{"component": "lambda", "operation": "start"}',
            "normal_field": "just a string",
        }
        parsed = parse_stringified_json_in_dict(obj)
        assert parsed["level"] == "INFO"
        assert parsed["normal_field"] == "just a string"
        assert isinstance(parsed["message"], dict)
        assert parsed["message"]["component"] == "lambda"

    def test_normalize_log_with_stringified_data(self) -> None:
        """Normalize log with stringified JSON in data field."""
        log = {
            "level": "INFO",
            "data": '{"component": "lambda", "operation": "invoke", "requestId": "req-123"}',
            "timestamp": "2025-01-19T00:00:00Z",
        }
        span = normalize_log_to_span(log)
        assert span is not None
        assert span.component == "lambda"
        assert span.operation == "invoke"
        assert span.lambda_request_id == "req-123"

    def test_normalize_log_with_stringified_message(self) -> None:
        """Normalize log where message field contains stringified JSON."""
        log = {
            "level": "INFO",
            "message": '{"component": "bedrock", "operation": "model_invoke", "traceId": "trace-456"}',
        }
        span = normalize_log_to_span(log)
        assert span is not None
        assert span.component == "bedrock"
        assert span.operation == "model_invoke"
        assert span.itk_trace_id == "trace-456"

    def test_normalize_log_with_double_stringified(self) -> None:
        """Normalize log with double-stringified JSON."""
        # First stringify: dict -> JSON string
        inner = json.dumps({"component": "sqs", "operation": "sendMessage"})
        log = {
            "level": "INFO",
            "data": inner,  # data is now a JSON string like '{"component": "sqs", ...}'
            "timestamp": "2025-01-19T00:00:00Z",
        }
        # Second stringify: wrap JSON string in quotes, adding escape sequences
        log["data"] = json.dumps(log["data"])
        span = normalize_log_to_span(log)
        assert span is not None
        assert span.component == "sqs"
        assert span.operation == "sendMessage"

    def test_flatten_nested_log_parses_stringified(self) -> None:
        """Flatten log with stringified nested structure."""
        log = {
            "level": "INFO",
            "data": '{"component": "lambda", "traceId": "trace-001"}',
            "timestamp": "2025-01-19T00:00:00Z",
        }
        flat = flatten_nested_log(log)
        assert flat["timestamp"] == "2025-01-19T00:00:00Z"
        assert flat["component"] == "lambda"
        assert flat["traceId"] == "trace-001"

    def test_skip_non_json_strings(self) -> None:
        """Leave non-JSON strings unchanged."""
        from itk.logs.parse import try_parse_stringified_json

        assert try_parse_stringified_json("just a plain string") == "just a plain string"
        assert try_parse_stringified_json("not json: {missing quotes}") == "not json: {missing quotes}"
        assert try_parse_stringified_json("") == ""
        assert try_parse_stringified_json(123) == 123  # Non-string values

    def test_nested_arrays_in_stringified(self) -> None:
        """Parse stringified JSON containing arrays."""
        from itk.logs.parse import try_parse_stringified_json

        value = json.dumps({"items": [1, 2, {"nested": "value"}]})
        parsed = try_parse_stringified_json(value)
        assert isinstance(parsed, dict)
        assert parsed["items"] == [1, 2, {"nested": "value"}]

    def test_cloudwatch_with_stringified_inner_json(self) -> None:
        """Parse CloudWatch events with stringified JSON in message."""
        # Simulates CloudWatch putting JSON log as a string in message field
        events = [
            {
                "timestamp": 1705622400000,
                "message": '{"component": "lambda", "operation": "invoke", "data": "{\\"requestId\\": \\"req-nested\\"}"}',
            },
        ]
        spans = parse_cloudwatch_logs(events)
        assert len(spans) == 1
        assert spans[0].component == "lambda"
        assert spans[0].operation == "invoke"

    def test_load_realistic_logs_with_stringified(self) -> None:
        """Load JSONL logs containing stringified JSON."""
        logs = [
            {"level": "INFO", "message": '{"component": "lambda", "operation": "start"}'},
            {"level": "INFO", "data": '{"component": "bedrock", "op": "invoke"}'},
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for log in logs:
                f.write(json.dumps(log) + "\n")
            f.flush()
            path = Path(f.name)

        try:
            spans = load_realistic_logs_as_spans(path)
            assert len(spans) == 2
            assert spans[0].component == "lambda"
            assert spans[1].component == "bedrock"
        finally:
            path.unlink()


class TestPythonDictReprParsing:
    """Test parsing Python dict repr from log messages (single-quoted dicts)."""

    def test_parse_simple_dict(self) -> None:
        """Parse simple Python dict repr."""
        result = try_parse_python_dict_repr("{'key': 'value', 'number': 123}")
        assert result == {"key": "value", "number": 123}

    def test_parse_embedded_dict(self) -> None:
        """Parse dict embedded in surrounding text."""
        result = try_parse_python_dict_repr("Event_body is {'message': 'hello', 'ts': '123.456'}")
        assert result == {"message": "hello", "ts": "123.456"}

    def test_parse_slack_message_dict(self) -> None:
        """Parse SlackMessage log format."""
        msg = "SlackMessage class finished creation with: {'thread_id': '1768927632.159269', 'channel': 'C07GVLMH5EG'}"
        result = try_parse_python_dict_repr(msg)
        assert result["thread_id"] == "1768927632.159269"
        assert result["channel"] == "C07GVLMH5EG"

    def test_returns_none_for_no_dict(self) -> None:
        """Return None when no dict found."""
        assert try_parse_python_dict_repr("no dict here") is None
        assert try_parse_python_dict_repr("") is None

    def test_returns_none_for_invalid_syntax(self) -> None:
        """Return None for invalid Python syntax."""
        assert try_parse_python_dict_repr("{'incomplete': ") is None

    def test_extract_thread_id_from_ts(self) -> None:
        """Extract thread_id from ts field in embedded dict."""
        msg = "Event_body is {'message': 'What is CaaS 2.0?', 'ts': '1768927632.159269', 'channel': 'C07'}"
        result = extract_thread_id_from_message(msg)
        assert result == "1768927632.159269"

    def test_extract_thread_id_direct(self) -> None:
        """Extract thread_id directly from embedded dict."""
        msg = "SlackMessage created: {'thread_id': '1768927632.159269', 'user': 'U123'}"
        result = extract_thread_id_from_message(msg)
        assert result == "1768927632.159269"

    def test_thread_id_preferred_over_ts(self) -> None:
        """thread_id takes precedence over ts if both present."""
        msg = "Data: {'ts': '111.111', 'thread_id': '222.222'}"
        result = extract_thread_id_from_message(msg)
        assert result == "222.222"

    def test_normalize_log_extracts_embedded_thread_id(self) -> None:
        """normalize_log_to_span extracts thread_id from Python dict in message."""
        obj = {
            "level": "INFO",
            "logger_name": "data_classes.slack_data",
            "message": "SlackMessage class finished creation with: {'thread_id': '1768927632.159269', 'channel': 'C07'}",
            "timestamp": "2025-06-20T17:27:12.000Z",
            "component": "lambda",
        }
        span = normalize_log_to_span(obj)
        assert span is not None
        assert span.thread_id == "1768927632.159269"

    def test_normalize_log_direct_thread_id_preferred(self) -> None:
        """Direct thread_id field takes precedence over embedded."""
        obj = {
            "component": "lambda",
            "thread_id": "direct-123.456",
            "message": "Data: {'thread_id': 'embedded-789.012'}",
        }
        span = normalize_log_to_span(obj)
        assert span is not None
        assert span.thread_id == "direct-123.456"

    def test_real_support_bot_log_format(self) -> None:
        """Test with actual support bot log format."""
        obj = {
            "appname": "support-bot-orchestrator",
            "level": "INFO",
            "logger_name": "main",
            "message": "Event_body is {'message': 'What is CaaS 2.0?', 'ts': '1768927632.159269', 'user': 'U08PS4EAM6M', 'channel': 'C07GVLMH5EG'}",
            "timestamp": "2025-06-20T17:27:12.268959",
        }
        # Add component so it becomes a valid span
        obj["component"] = "lambda"
        span = normalize_log_to_span(obj)
        assert span is not None
        assert span.thread_id == "1768927632.159269"

    def test_cloudwatch_with_python_dict_repr_message(self) -> None:
        """Parse CloudWatch events where message is Python dict repr (single quotes)."""
        events = [
            {
                "timestamp": 1705622400000,
                "message": "{'component': 'lambda', 'operation': 'invoke', 'thread_id': '1768927632.159269'}",
            },
        ]
        spans = parse_cloudwatch_logs(events)
        assert len(spans) == 1
        assert spans[0].component == "lambda"
        assert spans[0].operation == "invoke"
        assert spans[0].thread_id == "1768927632.159269"

    def test_cloudwatch_with_embedded_dict_in_text(self) -> None:
        """Parse CloudWatch events with embedded Python dict in plain text."""
        events = [
            {
                "timestamp": 1705622400000,
                "message": "Event_body is {'message': 'Hello', 'ts': '1768927632.159269', 'channel': 'C07GVLMH5EG'}",
            },
        ]
        spans = parse_cloudwatch_logs(events)
        # Should create a span with thread_id extracted from embedded dict
        assert len(spans) == 1
        assert spans[0].thread_id == "1768927632.159269"

    def test_cloudwatch_support_bot_full_flow(self) -> None:
        """Parse CloudWatch events matching support bot log format."""
        events = [
            {
                "timestamp": 1705622400000,
                "message": '{"appname": "support-bot-orchestrator", "level": "INFO", "logger_name": "main", "message": "Event_body is {\'ts\': \'1768927632.159269\'}", "timestamp": "2025-06-20T17:27:12Z"}',
            },
            {
                "timestamp": 1705622401000,
                "message": '{"appname": "support-bot-orchestrator", "level": "INFO", "logger_name": "data_classes.slack_data", "message": "SlackMessage class finished creation with: {\'thread_id\': \'1768927632.159269\'}", "timestamp": "2025-06-20T17:27:13Z"}',
            },
        ]
        spans = parse_cloudwatch_logs(events)
        # Both should have thread_id extracted
        assert len(spans) >= 1
        thread_ids = [s.thread_id for s in spans if s.thread_id]
        assert "1768927632.159269" in thread_ids

