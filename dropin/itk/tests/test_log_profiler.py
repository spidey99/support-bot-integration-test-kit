"""Tests for the log profiler module."""
from __future__ import annotations

import pytest

from itk.correlation.log_profiler import (
    FactSheet,
    LogProfiler,
    CorpusProfile,
    profile_corpus,
)


class TestLogProfilerBasics:
    """Test basic profiler functionality."""

    def test_profile_simple_log(self) -> None:
        """Test profiling a simple log entry."""
        profiler = LogProfiler()
        
        entry = {
            "timestamp": "2025-01-20T10:00:00Z",
            "level": "INFO",
            "message": "Hello world",
        }
        
        facts = profiler.profile(entry)
        
        assert facts.timestamp == "2025-01-20T10:00:00Z"
        assert facts.level == "INFO"
        assert facts.message == "Hello world"

    def test_profile_with_agent_id_in_message(self) -> None:
        """Test extracting agent ID from message string."""
        profiler = LogProfiler()
        
        entry = {
            "message": "Agent 1YRLEPE1LQ response: some data here",
        }
        
        facts = profiler.profile(entry)
        
        assert "1YRLEPE1LQ" in facts.agent_ids
        assert facts.component == "bedrock"

    def test_profile_with_embedded_json(self) -> None:
        """Test extracting data from embedded JSON in message."""
        profiler = LogProfiler()
        
        entry = {
            "message": '{"sessionId": "abc123", "status": "complete"}',
        }
        
        facts = profiler.profile(entry)
        
        assert "abc123" in facts.session_ids

    def test_profile_with_python_dict_repr(self) -> None:
        """Test extracting data from Python dict repr in message."""
        profiler = LogProfiler()
        
        entry = {
            "message": "Event_body is {'ts': '1768927632.159269', 'user': 'U08PS4EAM6M'}",
        }
        
        facts = profiler.profile(entry)
        
        # Should extract Slack thread timestamp and user
        assert "1768927632.159269" in facts.slack_thread_ts
        assert "U08PS4EAM6M" in facts.slack_users

    def test_profile_deeply_nested(self) -> None:
        """Test extracting from deeply nested structures."""
        profiler = LogProfiler()
        
        entry = {
            "message": '{"wrapper": "{\\"inner\\": {\\"sessionId\\": \\"deep-session\\"}}"}',
        }
        
        facts = profiler.profile(entry)
        
        # Should find the deeply nested session ID
        assert "deep-session" in facts.session_ids


class TestPatternExtraction:
    """Test specific pattern extraction."""

    def test_extract_slack_patterns(self) -> None:
        """Test extraction of Slack-specific patterns."""
        profiler = LogProfiler()
        
        entry = {
            "message": "SlackMessage: thread_id='1768927632.159269', channel='C07GVLMH5EG'",
        }
        
        facts = profiler.profile(entry)
        
        assert "1768927632.159269" in facts.slack_thread_ts
        assert "C07GVLMH5EG" in facts.slack_channels
        assert facts.component == "slack"

    def test_extract_aws_request_id(self) -> None:
        """Test extraction of AWS request IDs."""
        profiler = LogProfiler()
        
        entry = {
            "message": "RequestId: 12345678-1234-1234-1234-123456789abc",
        }
        
        facts = profiler.profile(entry)
        
        assert "12345678-1234-1234-1234-123456789abc" in facts.request_ids

    def test_extract_arns(self) -> None:
        """Test extraction of ARNs."""
        profiler = LogProfiler()
        
        entry = {
            "message": "Invoking arn:aws:lambda:us-east-1:123456789012:function:MyFunc",
        }
        
        facts = profiler.profile(entry)
        
        assert "arn:aws:lambda:us-east-1:123456789012:function:MyFunc" in facts.arns

    def test_extract_uuids(self) -> None:
        """Test extraction of UUIDs."""
        profiler = LogProfiler()
        
        entry = {
            "message": "Processing item abc12345-def6-7890-abcd-ef1234567890",
        }
        
        facts = profiler.profile(entry)
        
        assert "abc12345-def6-7890-abcd-ef1234567890" in facts.uuids


class TestComponentInference:
    """Test component/system inference."""

    def test_infer_bedrock_from_agent_id(self) -> None:
        """Test inferring Bedrock from agent ID presence."""
        profiler = LogProfiler()
        
        entry = {
            "message": "Agent ABCDEF1234 invoked",
        }
        
        facts = profiler.profile(entry)
        
        assert facts.component == "bedrock"
        assert facts.component_confidence > 0

    def test_infer_slack_from_channel(self) -> None:
        """Test inferring Slack from channel presence."""
        profiler = LogProfiler()
        
        entry = {
            "message": "Posted to channel C12345678",
        }
        
        facts = profiler.profile(entry)
        
        assert facts.component == "slack"

    def test_infer_lambda_from_handler(self) -> None:
        """Test inferring Lambda from handler mention."""
        profiler = LogProfiler()
        
        entry = {
            "message": "Lambda handler starting",
            "logger_name": "lambda.handler",
        }
        
        facts = profiler.profile(entry)
        
        assert facts.component == "lambda"


class TestCorpusProfile:
    """Test corpus-level profiling."""

    def test_profile_corpus(self) -> None:
        """Test profiling multiple log entries."""
        entries = [
            {"message": "Agent ABCDEF1234 started", "level": "INFO"},
            {"message": "Slack channel C12345678", "level": "DEBUG"},
            {"message": "Agent ABCDEF1234 completed", "level": "INFO"},
        ]
        
        profile = profile_corpus(entries)
        
        assert profile.total_entries == 3
        assert "ABCDEF1234" in profile.all_agent_ids
        assert "C12345678" in profile.all_slack_channels
        assert profile.levels.get("INFO") == 2
        assert profile.levels.get("DEBUG") == 1

    def test_corpus_time_range(self) -> None:
        """Test corpus time range tracking."""
        entries = [
            {"timestamp": "2025-01-20T10:00:00Z", "message": "first"},
            {"timestamp": "2025-01-20T10:05:00Z", "message": "middle"},
            {"timestamp": "2025-01-20T10:10:00Z", "message": "last"},
        ]
        
        profile = profile_corpus(entries)
        
        assert profile.earliest is not None
        assert profile.latest is not None
        assert profile.earliest < profile.latest


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_entry(self) -> None:
        """Test profiling an empty entry."""
        profiler = LogProfiler()
        
        facts = profiler.profile({})
        
        assert facts.raw == {}
        assert facts.component is None

    def test_malformed_json_in_message(self) -> None:
        """Test handling malformed JSON gracefully."""
        profiler = LogProfiler()
        
        entry = {
            "message": '{"broken": json here}',
        }
        
        # Should not raise
        facts = profiler.profile(entry)
        assert facts.message == '{"broken": json here}'

    def test_very_long_message(self) -> None:
        """Test handling very long messages."""
        profiler = LogProfiler()
        
        long_message = "x" * 10000 + " sessionId=test123 " + "y" * 10000
        entry = {"message": long_message}
        
        facts = profiler.profile(entry)
        
        # Should still extract the session ID
        assert "test123" in facts.session_ids

    def test_nested_depth_limit(self) -> None:
        """Test that deeply nested structures don't cause infinite recursion."""
        profiler = LogProfiler()
        
        # Create deeply nested structure
        nested = "test"
        for _ in range(20):
            nested = f'{{"level": "{nested}"}}'
        
        entry = {"message": nested}
        
        # Should not raise or hang
        facts = profiler.profile(entry)
        assert facts is not None


class TestAllCorrelationKeys:
    """Test the correlation key collection."""

    def test_all_correlation_keys(self) -> None:
        """Test collecting all correlation keys from a fact sheet."""
        profiler = LogProfiler()
        
        entry = {
            "message": "Agent ABCDEF1234 session=sess123 thread_ts=1768927632.159269",
        }
        
        facts = profiler.profile(entry)
        keys = facts.all_correlation_keys()
        
        assert "ABCDEF1234" in keys
        assert "sess123" in keys
        assert "1768927632.159269" in keys
