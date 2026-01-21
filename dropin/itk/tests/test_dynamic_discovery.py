"""Tests for dynamic correlation discovery."""
from __future__ import annotations

import pytest

from itk.correlation.dynamic_discovery import (
    CorrelationValue,
    LogEntry,
    build_correlation_chains,
    chain_to_spans,
    detect_component,
    discover_correlations,
    extract_correlation_values,
    parse_log_entry,
    parse_log_stream,
    summarize_chains,
)


class TestDetectComponent:
    """Test component auto-detection from log entries."""

    def test_detect_from_explicit_field(self) -> None:
        """Detect component from explicit component field."""
        assert detect_component({"component": "lambda"}) == "lambda"
        assert detect_component({"service": "bedrock"}) == "bedrock"
        assert detect_component({"source": "sqs"}) == "sqs"

    def test_detect_from_logger_name(self) -> None:
        """Detect component from logger_name field."""
        assert detect_component({"logger_name": "slack.webhook"}) == "slack"
        assert detect_component({"logger_name": "bedrock.agent"}) == "bedrock"

    def test_detect_from_appname(self) -> None:
        """Detect orchestrator as lambda."""
        obj = {"appname": "support-bot-orchestrator"}
        assert detect_component(obj) == "lambda"

    def test_detect_from_keywords(self) -> None:
        """Detect component from keyword matches."""
        assert detect_component({"message": "SQS message received"}) == "sqs"
        assert detect_component({"message": "Lambda handler invoked"}) == "lambda"
        assert detect_component({"message": "Bedrock model response"}) == "bedrock"
        assert detect_component({"message": "SlackMessage created"}) == "slack"

    def test_detect_unknown(self) -> None:
        """Return unknown when no component detected."""
        assert detect_component({"message": "Hello world"}) == "unknown"
        assert detect_component({}) == "unknown"


class TestExtractCorrelationValues:
    """Test extraction of correlation values from log entries."""

    def test_extract_uuid(self) -> None:
        """Extract UUID values."""
        obj = {"request_id": "12345678-1234-1234-1234-123456789012"}
        values = extract_correlation_values(obj)
        assert any(cv.value == "12345678-1234-1234-1234-123456789012" for cv in values)

    def test_extract_slack_timestamp(self) -> None:
        """Extract Slack timestamp values."""
        obj = {"thread_id": "1768927632.159269"}
        values = extract_correlation_values(obj)
        assert any(cv.value == "1768927632.159269" for cv in values)

    def test_extract_from_embedded_dict(self) -> None:
        """Extract values from Python dict repr in message."""
        obj = {"message": "Event_body is {'ts': '1768927632.159269', 'channel': 'C07GVLMH5EG'}"}
        values = extract_correlation_values(obj)
        value_strings = {cv.value for cv in values}
        assert "1768927632.159269" in value_strings
        assert "C07GVLMH5EG" in value_strings

    def test_extract_channel_id(self) -> None:
        """Extract Slack channel ID."""
        obj = {"channel": "C07GVLMH5EG"}
        values = extract_correlation_values(obj)
        assert any(cv.value == "C07GVLMH5EG" for cv in values)

    def test_extract_user_id(self) -> None:
        """Extract Slack user ID."""
        obj = {"user": "U08PS4EAM6M"}
        values = extract_correlation_values(obj)
        assert any(cv.value == "U08PS4EAM6M" for cv in values)

    def test_extract_from_nested_dict(self) -> None:
        """Extract from nested structures."""
        obj = {
            "context": {
                "session_id": "1768927632.159269",
                "data": {"channel_id": "C07GVLMH5EG"},
            }
        }
        values = extract_correlation_values(obj)
        value_strings = {cv.value for cv in values}
        assert "1768927632.159269" in value_strings
        assert "C07GVLMH5EG" in value_strings


class TestParseLogEntry:
    """Test parsing raw logs into LogEntry objects."""

    def test_parse_basic_entry(self) -> None:
        """Parse a basic log entry."""
        obj = {
            "component": "lambda",
            "timestamp": "2025-06-20T17:27:12Z",
            "request_id": "12345678-1234-1234-1234-123456789012",
        }
        entry = parse_log_entry(obj, index=5)
        assert entry.component == "lambda"
        assert entry.timestamp == "2025-06-20T17:27:12Z"
        assert entry.index == 5
        assert len(entry.correlation_values) > 0

    def test_parse_support_bot_log(self) -> None:
        """Parse actual support bot log format."""
        obj = {
            "appname": "support-bot-orchestrator",
            "level": "INFO",
            "logger_name": "main",
            "message": "Event_body is {'message': 'Hello', 'ts': '1768927632.159269', 'user': 'U08PS4EAM6M'}",
            "timestamp": "2025-06-20T17:27:12.268959",
        }
        entry = parse_log_entry(obj)
        assert entry.component == "lambda"  # orchestrator = lambda
        assert "1768927632.159269" in entry.value_strings()
        assert "U08PS4EAM6M" in entry.value_strings()


class TestBuildCorrelationChains:
    """Test building correlation chains from log entries."""

    def test_simple_chain(self) -> None:
        """Build chain from two entries sharing an ID."""
        entries = [
            LogEntry(
                raw={},
                component="lambda",
                correlation_values={
                    CorrelationValue("shared-123", "uuid"),
                },
            ),
            LogEntry(
                raw={},
                component="bedrock",
                correlation_values={
                    CorrelationValue("shared-123", "uuid"),
                },
            ),
        ]
        chains = build_correlation_chains(entries)
        assert len(chains) == 1
        assert chains[0].component_count == 2
        assert set(chains[0].components) == {"lambda", "bedrock"}

    def test_transitive_chain(self) -> None:
        """Build chain via transitive correlation (A-B, B-C -> A-B-C)."""
        entries = [
            LogEntry(
                raw={},
                component="sqs",
                index=0,
                correlation_values={
                    CorrelationValue("msg-abc", "uuid"),
                },
            ),
            LogEntry(
                raw={},
                component="lambda",
                index=1,
                correlation_values={
                    CorrelationValue("msg-abc", "uuid"),  # Links to SQS
                    CorrelationValue("1768.123", "slack_ts"),  # Links to Slack
                },
            ),
            LogEntry(
                raw={},
                component="slack",
                index=2,
                correlation_values={
                    CorrelationValue("1768.123", "slack_ts"),
                },
            ),
        ]
        chains = build_correlation_chains(entries)
        assert len(chains) == 1
        assert chains[0].component_count == 3
        assert chains[0].components == ["sqs", "lambda", "slack"]

    def test_separate_chains(self) -> None:
        """Unrelated entries form separate chains (or no chain if single)."""
        entries = [
            LogEntry(
                raw={},
                component="lambda",
                correlation_values={
                    CorrelationValue("id-a", "uuid"),
                },
            ),
            LogEntry(
                raw={},
                component="bedrock",
                correlation_values={
                    CorrelationValue("id-b", "uuid"),  # Different ID
                },
            ),
        ]
        chains = build_correlation_chains(entries)
        # Single entries don't form chains
        assert len(chains) == 0

    def test_bridge_values_identified(self) -> None:
        """Bridge values (shared across components) are identified."""
        entries = [
            LogEntry(
                raw={},
                component="lambda",
                correlation_values={
                    CorrelationValue("shared-val", "session"),
                    CorrelationValue("lambda-only", "uuid"),
                },
            ),
            LogEntry(
                raw={},
                component="bedrock",
                correlation_values={
                    CorrelationValue("shared-val", "session"),
                    CorrelationValue("bedrock-only", "uuid"),
                },
            ),
        ]
        chains = build_correlation_chains(entries)
        assert len(chains) == 1
        assert "shared-val" in chains[0].bridge_values
        # lambda-only and bedrock-only are NOT bridge values
        assert "lambda-only" not in chains[0].bridge_values
        assert "bedrock-only" not in chains[0].bridge_values


class TestDiscoverCorrelations:
    """End-to-end tests for correlation discovery."""

    def test_discover_from_raw_logs(self) -> None:
        """Discover chains from raw log dictionaries."""
        logs = [
            {
                "component": "sqs",
                "message_id": "msg-123",
                "timestamp": "2025-06-20T17:27:10Z",
            },
            {
                "component": "lambda",
                "message_id": "msg-123",  # Same as SQS
                "thread_id": "1768927632.159269",  # Links to Slack
                "timestamp": "2025-06-20T17:27:11Z",
            },
            {
                "appname": "support-bot-orchestrator",
                "message": "SlackMessage: {'thread_id': '1768927632.159269', 'channel': 'C07'}",
                "timestamp": "2025-06-20T17:27:12Z",
            },
        ]
        chains = discover_correlations(logs)
        assert len(chains) == 1
        assert chains[0].component_count >= 2

    def test_support_bot_full_flow(self) -> None:
        """Simulate full support bot flow: SQS -> Lambda -> Slack -> Bedrock."""
        logs = [
            # SQS event arrives
            {
                "component": "sqs",
                "messageId": "sqs-msg-001",
                "body": "{'ts': '1768927632.159269'}",
            },
            # Lambda receives SQS message
            {
                "appname": "support-bot-orchestrator",
                "logger_name": "main",
                "message": "Event_body is {'ts': '1768927632.159269', 'user': 'U08PS4EAM6M'}",
            },
            # SlackMessage created
            {
                "appname": "support-bot-orchestrator",
                "logger_name": "data_classes.slack_data",
                "message": "SlackMessage class finished creation with: {'thread_id': '1768927632.159269', 'channel': 'C07GVLMH5EG'}",
            },
            # Bedrock call with session_id = thread_id
            {
                "component": "bedrock",
                "session_id": "1768927632.159269",
                "message": "Agent invocation started",
            },
        ]
        chains = discover_correlations(logs)
        assert len(chains) >= 1
        
        # Main chain should span multiple components
        main_chain = max(chains, key=lambda c: c.component_count)
        assert main_chain.component_count >= 2
        
        # The thread_id/ts should be a bridge value
        assert any("1768927632.159269" in v for v in main_chain.bridge_values.keys())


class TestSummarizeChains:
    """Test human-readable chain summaries."""

    def test_empty_summary(self) -> None:
        """Summary for empty chains."""
        assert "No correlation chains" in summarize_chains([])

    def test_chain_summary(self) -> None:
        """Summary includes key information."""
        entries = [
            LogEntry(raw={}, component="lambda", correlation_values={CorrelationValue("x", "uuid")}),
            LogEntry(raw={}, component="bedrock", correlation_values={CorrelationValue("x", "uuid")}),
        ]
        chains = build_correlation_chains(entries)
        summary = summarize_chains(chains)
        assert "Chain 1" in summary
        assert "lambda" in summary
        assert "bedrock" in summary


class TestCloudWatchUnwrapping:
    """Test CloudWatch format unwrapping in parse_log_entry."""

    def test_unwrap_cloudwatch_json_message(self) -> None:
        """Unwrap CloudWatch event with JSON in message field."""
        import json
        inner = {
            "appname": "support-bot-orchestrator",
            "level": "INFO",
            "logger_name": "main",
            "message": "Event received",
        }
        cloudwatch_event = {
            "timestamp": 1750000000000,
            "message": json.dumps(inner),
        }
        entry = parse_log_entry(cloudwatch_event)
        # Should detect lambda from appname
        assert entry.component == "lambda"
        # Should have inner structure accessible
        assert entry.raw.get("appname") == "support-bot-orchestrator"

    def test_unwrap_cloudwatch_python_dict_repr(self) -> None:
        """Unwrap CloudWatch event with Python dict repr in message field."""
        cloudwatch_event = {
            "timestamp": 1750000000000,
            "message": "{'appname': 'support-bot-orchestrator', 'level': 'INFO', 'ts': '1768927632.159269'}",
        }
        entry = parse_log_entry(cloudwatch_event)
        # Should extract thread_id pattern
        assert "1768927632.159269" in entry.value_strings()

    def test_already_unwrapped_not_double_processed(self) -> None:
        """Already unwrapped logs (with appname) should not be re-processed."""
        direct_log = {
            "appname": "support-bot-orchestrator",
            "level": "INFO",
            "message": "{'ts': '1768927632.159269'}",
            "timestamp": "2025-06-20T17:27:12.268959",
        }
        entry = parse_log_entry(direct_log)
        assert entry.component == "lambda"
        assert "1768927632.159269" in entry.value_strings()

    def test_preserve_timestamp_from_cloudwatch(self) -> None:
        """CloudWatch timestamp should be preserved in unwrapped entry."""
        cloudwatch_event = {
            "timestamp": 1750000000000,
            "message": '{"level": "INFO", "msg": "hello"}',
        }
        entry = parse_log_entry(cloudwatch_event)
        assert entry.timestamp == 1750000000000


class TestChainToSpans:
    """Test converting CorrelationChain to Spans for diagram generation."""

    def test_chain_to_spans_basic(self) -> None:
        """Convert a chain with 2 entries to spans."""
        entries = [
            LogEntry(
                raw={"message": "request received"},
                component="lambda",
                timestamp="2025-06-20T17:27:12Z",
                correlation_values={CorrelationValue("1768927632.159269", "slack_ts")},
                index=0,
            ),
            LogEntry(
                raw={"message": "calling bedrock"},
                component="bedrock",
                timestamp="2025-06-20T17:27:13Z",
                correlation_values={CorrelationValue("1768927632.159269", "slack_ts")},
                index=1,
            ),
        ]
        chains = build_correlation_chains(entries)
        assert len(chains) == 1
        
        spans = chain_to_spans(chains[0], "test-chain-001")
        assert len(spans) == 2
        assert spans[0].component == "lambda"
        assert spans[1].component == "bedrock"
        assert spans[0].itk_trace_id == "test-chain-001"
        assert spans[1].itk_trace_id == "test-chain-001"
        # First span has no parent
        assert spans[0].parent_span_id is None
        # Second span's parent is first
        assert spans[1].parent_span_id == "test-chain-001-0"

    def test_chain_to_spans_uses_thread_id_as_session(self) -> None:
        """Chain with Slack thread_id should use it as session_id."""
        entries = [
            LogEntry(
                raw={},
                component="slack",
                correlation_values={CorrelationValue("1768927632.159269", "slack_ts")},
            ),
        ]
        chains = build_correlation_chains(entries)
        # Single entry won't form a chain, so build directly
        from itk.correlation.dynamic_discovery import CorrelationChain
        chain = CorrelationChain(
            entries=entries,
            bridge_values={"1768927632.159269": {"slack"}},
        )
        
        spans = chain_to_spans(chain, "test-001")
        assert len(spans) == 1
        assert spans[0].thread_id == "1768927632.159269"
        assert spans[0].session_id == "1768927632.159269"


class TestExtractInputData:
    """Test extraction of input/request data from log entries."""

    def test_extract_from_explicit_request_field(self) -> None:
        """Extract from explicit 'request' field."""
        from itk.correlation.dynamic_discovery import _extract_input_data
        entry = LogEntry(
            raw={"request": {"userMessage": "Hello"}},
            component="lambda",
        )
        result = _extract_input_data(entry)
        assert result == {"userMessage": "Hello"}

    def test_extract_from_embedded_dict_in_message(self) -> None:
        """Extract embedded dict from message field."""
        from itk.correlation.dynamic_discovery import _extract_input_data
        entry = LogEntry(
            raw={"message": "Event_body is {'message': 'What is CaaS 2.0?', 'ts': '123'}"},
            component="lambda",
        )
        result = _extract_input_data(entry)
        assert result is not None
        assert result.get("message") == "What is CaaS 2.0?"
        assert result.get("ts") == "123"

    def test_extract_log_metadata_as_fallback(self) -> None:
        """Include log metadata when no structured input data."""
        from itk.correlation.dynamic_discovery import _extract_input_data
        entry = LogEntry(
            raw={"level": "INFO", "message": "Simple log message", "logger_name": "main", "appname": "my-app"},
            component="lambda",
        )
        result = _extract_input_data(entry)
        assert result is not None
        assert result.get("_log_level") == "INFO"
        assert "_log_message" in result


class TestDetectError:
    """Test error detection from log entries."""

    def test_detect_from_explicit_error_field(self) -> None:
        """Detect error from explicit 'error' field."""
        from itk.correlation.dynamic_discovery import _detect_error
        entry = LogEntry(
            raw={"error": {"type": "ThrottlingException", "message": "Rate exceeded"}},
            component="lambda",
        )
        result = _detect_error(entry)
        assert result is not None
        assert result["type"] == "ThrottlingException"

    def test_detect_from_error_log_level(self) -> None:
        """Detect error from ERROR log level."""
        from itk.correlation.dynamic_discovery import _detect_error
        entry = LogEntry(
            raw={"level": "ERROR", "message": "Failed to invoke Bedrock agent"},
            component="lambda",
        )
        result = _detect_error(entry)
        assert result is not None
        assert result["level"] == "ERROR"
        assert "Failed to invoke" in result["message"]

    def test_no_error_for_info_log(self) -> None:
        """INFO log without error patterns should return None."""
        from itk.correlation.dynamic_discovery import _detect_error
        entry = LogEntry(
            raw={"level": "INFO", "message": "Request completed successfully"},
            component="lambda",
        )
        result = _detect_error(entry)
        assert result is None

    def test_detect_error_patterns_in_message(self) -> None:
        """Detect error from keywords in message even if level is not ERROR."""
        from itk.correlation.dynamic_discovery import _detect_error
        entry = LogEntry(
            raw={"level": "WARNING", "message": "Exception occurred: NullPointerException"},
            component="lambda",
        )
        result = _detect_error(entry)
        assert result is not None
        assert "Exception" in result["message"]


class TestChainToSpansWithExtractedData:
    """Test chain_to_spans properly extracts request/error data."""

    def test_chain_to_spans_extracts_error_from_log_level(self) -> None:
        """Spans should have error field when log level is ERROR."""
        entries = [
            LogEntry(
                raw={"level": "INFO", "message": "Request received"},
                component="lambda",
                timestamp="2025-06-20T17:27:12Z",
                correlation_values={CorrelationValue("123", "slack_ts")},
                index=0,
            ),
            LogEntry(
                raw={"level": "ERROR", "message": "ThrottlingException: Rate limit exceeded"},
                component="bedrock",
                timestamp="2025-06-20T17:27:13Z",
                correlation_values={CorrelationValue("123", "slack_ts")},
                index=1,
            ),
        ]
        chains = build_correlation_chains(entries)
        assert len(chains) == 1
        
        spans = chain_to_spans(chains[0], "test-chain")
        assert len(spans) == 2
        
        # First span should NOT have error
        assert spans[0].error is None
        
        # Second span SHOULD have error
        assert spans[1].error is not None
        assert spans[1].error["level"] == "ERROR"

    def test_chain_to_spans_has_ts_end(self) -> None:
        """Spans should have ts_end set for proper timeline rendering."""
        entries = [
            LogEntry(
                raw={"level": "INFO", "message": "Test"},
                component="lambda",
                timestamp="2025-06-20T17:27:12Z",
                correlation_values={CorrelationValue("123", "slack_ts")},
                index=0,
            ),
        ]
        from itk.correlation.dynamic_discovery import CorrelationChain
        chain = CorrelationChain(entries=entries, bridge_values={"123": {"lambda"}})
        
        spans = chain_to_spans(chain, "test-chain")
        assert len(spans) == 1
        assert spans[0].ts_start is not None
        assert spans[0].ts_end is not None
        assert spans[0].ts_start == spans[0].ts_end


class TestDetectAttempt:
    """Test retry attempt detection from log entries."""

    def test_detect_from_explicit_attempt_field(self) -> None:
        """Detect attempt from explicit 'attempt' field."""
        from itk.correlation.dynamic_discovery import _detect_attempt
        entry = LogEntry(
            raw={"attempt": 3, "message": "Processing request"},
            component="lambda",
        )
        result = _detect_attempt(entry)
        assert result == 3

    def test_detect_from_explicit_retry_field(self) -> None:
        """Detect attempt from explicit 'retry' field (retry + 1 = attempt)."""
        from itk.correlation.dynamic_discovery import _detect_attempt
        entry = LogEntry(
            raw={"retry": 2, "message": "Processing request"},
            component="lambda",
        )
        result = _detect_attempt(entry)
        assert result == 3  # retry 2 means attempt 3

    def test_detect_from_message_pattern(self) -> None:
        """Detect attempt from retry patterns in message."""
        from itk.correlation.dynamic_discovery import _detect_attempt
        entry = LogEntry(
            raw={"message": "Retrying Bedrock agent call, attempt 2"},
            component="bedrock",
        )
        result = _detect_attempt(entry)
        assert result == 2

    def test_detect_retry_without_number(self) -> None:
        """Retry keyword without number assumes attempt 2."""
        from itk.correlation.dynamic_discovery import _detect_attempt
        entry = LogEntry(
            raw={"message": "Retrying the request after backoff"},
            component="lambda",
        )
        result = _detect_attempt(entry)
        assert result == 2

    def test_no_retry_returns_1(self) -> None:
        """No retry indicators should return attempt 1."""
        from itk.correlation.dynamic_discovery import _detect_attempt
        entry = LogEntry(
            raw={"level": "INFO", "message": "Request completed successfully"},
            component="lambda",
        )
        result = _detect_attempt(entry)
        assert result == 1
