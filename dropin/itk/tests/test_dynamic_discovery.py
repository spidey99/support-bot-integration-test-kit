"""Tests for dynamic correlation discovery."""
from __future__ import annotations

import pytest

from itk.correlation.dynamic_discovery import (
    CorrelationValue,
    LogEntry,
    build_correlation_chains,
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
