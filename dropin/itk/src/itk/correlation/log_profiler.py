"""Log Profiler - Deep extraction of structured data from messy logs.

The problem: Logs contain valuable identifiers but they're buried in:
- Stringified JSON
- Python dict repr format  
- Embedded in message strings like "Agent 1YRLEPE1LQ response: {...}"
- Nested multiple levels deep

This module combs through the mess and extracts EVERYTHING identifiable
into a structured "fact sheet" for each log line.

Example input:
    {"message": "Agent 1YRLEPE1LQ response: {'sessionId': 'abc123', ...}"}

Example output (FactSheet):
    - agent_ids: ["1YRLEPE1LQ"]
    - session_ids: ["abc123"]
    - component: "bedrock" (inferred from agent pattern)
    - all extracted key-value pairs
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterator

# ============================================================================
# Pattern Registry - Known identifier patterns
# ============================================================================

# AWS patterns
PATTERN_AWS_REQUEST_ID = re.compile(
    r"(?:request[_-]?id|RequestId)[\"':\s]*([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})",
    re.IGNORECASE,
)
PATTERN_AWS_ARN = re.compile(
    r"arn:aws:[a-z0-9-]+:[a-z0-9-]*:\d{12}:[a-zA-Z0-9/:_-]+",
)
PATTERN_LAMBDA_REQUEST_ID = re.compile(
    r"(?:RequestId|request_id)[:\s\"']*([a-f0-9-]{36})",
    re.IGNORECASE,
)

# Bedrock Agent patterns
PATTERN_AGENT_ID = re.compile(
    r"(?:agent[_\s]?(?:id)?|Agent)[\"':\s]*([A-Z0-9]{10})",
    re.IGNORECASE,
)
PATTERN_AGENT_ALIAS_ID = re.compile(
    r"(?:alias[_\s]?id|aliasId)[\"':\s]*([A-Z0-9]{10})",
    re.IGNORECASE,
)
PATTERN_SESSION_ID = re.compile(
    r"(?:session[_\s]?(?:id)?|sessionId)[\"':=\s]*['\"]?([a-zA-Z0-9._-]+)['\"]?",
    re.IGNORECASE,
)
PATTERN_TRACE_ID = re.compile(
    r"(?:trace[_\s]?id|traceId)[\"':\s]*['\"]?([a-zA-Z0-9._-]+)['\"]?",
    re.IGNORECASE,
)

# Slack patterns
PATTERN_SLACK_CHANNEL = re.compile(
    r"(?:channel[_\s]?(?:id)?|channel)[\"':=\s]*['\"]?([CGD][A-Z0-9]{8,})['\"]?",
    re.IGNORECASE,
)
PATTERN_SLACK_THREAD_TS = re.compile(
    r"(?:thread[_\s]?(?:ts|id)|ts)[\"':=\s]*['\"]?(\d{10}\.\d{6})['\"]?",
    re.IGNORECASE,
)
PATTERN_SLACK_USER = re.compile(
    r"(?:user[_\s]?(?:id)?|user)[\"':\s]*['\"]?([UW][A-Z0-9]{8,})['\"]?",
    re.IGNORECASE,
)
PATTERN_SLACK_MESSAGE_TS = re.compile(
    r"(?:message[_\s]?ts|ts)[\"':\s]*['\"]?(\d{10}\.\d{6})['\"]?",
)

# SQS / message patterns
PATTERN_MESSAGE_ID = re.compile(
    r"(?:message[_\s]?id|messageId)[\"':=\s]*['\"]?([a-zA-Z0-9._-]+)['\"]?",
    re.IGNORECASE,
)

# Generic ID patterns
PATTERN_UUID = re.compile(
    r"\b([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})\b",
    re.IGNORECASE,
)
PATTERN_CORRELATION_ID = re.compile(
    r"(?:correlation[_\s]?id|correlationId|x-correlation-id)[\"':\s]*['\"]?([a-zA-Z0-9._-]+)['\"]?",
    re.IGNORECASE,
)

# Timestamp patterns
PATTERN_ISO_TIMESTAMP = re.compile(
    r"(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)",
)
PATTERN_EPOCH_MS = re.compile(
    r"(?:timestamp|time|eventTime)[\"':\s]*(\d{13})",
    re.IGNORECASE,
)

# Component inference patterns (for identifying what system a log is from)
COMPONENT_PATTERNS = {
    "bedrock": [
        re.compile(r"bedrock", re.IGNORECASE),
        re.compile(r"agent[_\s]?(?:id|response|invoke)", re.IGNORECASE),
        re.compile(r"InvokeAgent", re.IGNORECASE),
        re.compile(r"orchestrationTrace"),
        re.compile(r"knowledgeBase", re.IGNORECASE),
    ],
    "slack": [
        re.compile(r"slack", re.IGNORECASE),
        re.compile(r"SlackMessage"),
        re.compile(r"thread_ts"),
        re.compile(r"channel[\"':\s]*['\"]?[CGD][A-Z0-9]"),
    ],
    "lambda": [
        re.compile(r"lambda", re.IGNORECASE),
        re.compile(r"handler"),
        re.compile(r"LAMBDA_"),
        re.compile(r"aws[_\s]?request[_\s]?id", re.IGNORECASE),
    ],
    "sqs": [
        re.compile(r"sqs", re.IGNORECASE),
        re.compile(r"message[_\s]?id", re.IGNORECASE),
        re.compile(r"receipt[_\s]?handle", re.IGNORECASE),
    ],
    "dynamodb": [
        re.compile(r"dynamodb", re.IGNORECASE),
        re.compile(r"table[_\s]?name", re.IGNORECASE),
        re.compile(r"PutItem|GetItem|UpdateItem|DeleteItem"),
    ],
    "s3": [
        re.compile(r"s3://"),
        re.compile(r"bucket[_\s]?name", re.IGNORECASE),
    ],
}


@dataclass
class FactSheet:
    """Extracted facts from a single log entry."""
    
    # Original data
    raw: dict[str, Any]
    raw_text: str  # Full text representation for pattern matching
    
    # Timestamps
    timestamp: str | None = None
    timestamp_parsed: datetime | None = None
    
    # Log metadata
    level: str | None = None
    logger_name: str | None = None
    appname: str | None = None
    
    # Inferred component
    component: str | None = None
    component_confidence: float = 0.0
    
    # Extracted identifiers
    agent_ids: list[str] = field(default_factory=list)
    alias_ids: list[str] = field(default_factory=list)
    session_ids: list[str] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)
    request_ids: list[str] = field(default_factory=list)
    correlation_ids: list[str] = field(default_factory=list)
    message_ids: list[str] = field(default_factory=list)  # SQS/SNS message IDs
    
    # Slack-specific
    slack_channels: list[str] = field(default_factory=list)
    slack_thread_ts: list[str] = field(default_factory=list)
    slack_users: list[str] = field(default_factory=list)
    
    # AWS resources
    arns: list[str] = field(default_factory=list)
    
    # All UUIDs found
    uuids: list[str] = field(default_factory=list)
    
    # All key-value pairs extracted (flattened)
    extracted_kvs: dict[str, Any] = field(default_factory=dict)
    
    # The message content (if extractable)
    message: str | None = None
    
    # Nested data found (parsed from message strings)
    nested_data: list[dict[str, Any]] = field(default_factory=list)

    def all_correlation_keys(self) -> set[str]:
        """Return all values that could be used for correlation."""
        keys: set[str] = set()
        keys.update(self.agent_ids)
        keys.update(self.session_ids)
        keys.update(self.trace_ids)
        keys.update(self.request_ids)
        keys.update(self.correlation_ids)
        keys.update(self.message_ids)  # SQS/SNS message IDs
        keys.update(self.slack_thread_ts)
        keys.update(self.slack_channels)
        # Don't include UUIDs by default - too noisy
        return keys

    def summary(self) -> str:
        """One-line summary of the fact sheet."""
        parts = []
        if self.component:
            parts.append(f"[{self.component}]")
        if self.level:
            parts.append(f"{self.level}")
        if self.agent_ids:
            parts.append(f"agent={self.agent_ids[0]}")
        if self.session_ids:
            parts.append(f"session={self.session_ids[0][:12]}...")
        if self.slack_thread_ts:
            parts.append(f"thread={self.slack_thread_ts[0]}")
        return " ".join(parts) if parts else "(no facts extracted)"


class LogProfiler:
    """Deep extraction of structured data from messy logs."""

    def __init__(self, debug: bool = False):
        self._debug = debug

    def profile(self, log_entry: dict[str, Any]) -> FactSheet:
        """Extract all facts from a single log entry."""
        # Build raw text representation for pattern matching
        raw_text = self._to_searchable_text(log_entry)
        
        facts = FactSheet(
            raw=log_entry,
            raw_text=raw_text,
        )
        
        # Extract basic metadata
        facts.timestamp = self._extract_timestamp(log_entry)
        facts.level = self._extract_level(log_entry)
        facts.logger_name = log_entry.get("logger_name") or log_entry.get("logger")
        facts.appname = log_entry.get("appname") or log_entry.get("app")
        facts.message = log_entry.get("message")
        
        # Parse timestamp
        if facts.timestamp:
            facts.timestamp_parsed = self._parse_timestamp(facts.timestamp)
        
        # Flatten and extract all nested data
        self._extract_nested_data(log_entry, facts)
        
        # Run pattern extractors on full text
        self._extract_patterns(raw_text, facts)
        
        # Infer component
        facts.component, facts.component_confidence = self._infer_component(raw_text, facts)
        
        return facts

    def profile_many(self, log_entries: list[dict[str, Any]]) -> list[FactSheet]:
        """Profile multiple log entries."""
        return [self.profile(entry) for entry in log_entries]

    def _to_searchable_text(self, obj: Any, depth: int = 0) -> str:
        """Convert any object to searchable text, unwrapping nested structures."""
        if depth > 10:
            return str(obj)
        
        if isinstance(obj, str):
            # Try to parse as JSON
            parsed = self._try_parse_json(obj)
            if parsed is not None and parsed != obj:
                return obj + " " + self._to_searchable_text(parsed, depth + 1)
            # Try to parse as Python dict repr
            parsed = self._try_parse_python_repr(obj)
            if parsed is not None:
                return obj + " " + self._to_searchable_text(parsed, depth + 1)
            return obj
        
        if isinstance(obj, dict):
            parts = []
            for k, v in obj.items():
                parts.append(f"{k}={self._to_searchable_text(v, depth + 1)}")
            return " ".join(parts)
        
        if isinstance(obj, (list, tuple)):
            return " ".join(self._to_searchable_text(item, depth + 1) for item in obj)
        
        return str(obj)

    def _try_parse_json(self, text: str) -> Any | None:
        """Try to parse text as JSON."""
        text = text.strip()
        if not text:
            return None
        
        # Quick check for JSON-like content
        if not (text.startswith("{") or text.startswith("[")):
            # Look for embedded JSON
            match = re.search(r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})', text)
            if match:
                text = match.group(1)
            else:
                return None
        
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None

    def _try_parse_python_repr(self, text: str) -> Any | None:
        """Try to parse text as Python dict/list repr."""
        text = text.strip()
        if not text:
            return None
        
        # Quick check for dict-like content
        if not (text.startswith("{") or text.startswith("[")):
            # Look for embedded dict
            match = re.search(r"(\{['\"][^{}]*(?:\{[^{}]*\}[^{}]*)*\})", text)
            if match:
                text = match.group(1)
            else:
                return None
        
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return None

    def _extract_timestamp(self, log_entry: dict[str, Any]) -> str | None:
        """Extract timestamp from various possible fields."""
        for key in ["timestamp", "@timestamp", "time", "eventTime", "ts"]:
            if key in log_entry:
                val = log_entry[key]
                if isinstance(val, str):
                    return val
                if isinstance(val, (int, float)):
                    # Assume epoch ms
                    return datetime.fromtimestamp(val / 1000).isoformat()
        return None

    def _parse_timestamp(self, ts: str) -> datetime | None:
        """Parse a timestamp string to datetime."""
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(ts.replace("+00:00", "Z").rstrip("Z") + "Z", fmt.replace("Z", "") + "Z" if "Z" in fmt else fmt)
            except ValueError:
                continue
        
        # Try with timezone offset
        try:
            # Handle +00:00 style
            if "+" in ts or (ts.count("-") > 2):
                # Remove timezone for simple parsing
                ts_clean = re.sub(r'[+-]\d{2}:\d{2}$', '', ts)
                return datetime.fromisoformat(ts_clean)
        except ValueError:
            pass
        
        return None

    def _extract_level(self, log_entry: dict[str, Any]) -> str | None:
        """Extract log level."""
        for key in ["level", "severity", "log_level", "@level"]:
            if key in log_entry:
                return str(log_entry[key]).upper()
        return None

    def _extract_nested_data(self, obj: Any, facts: FactSheet, path: str = "") -> None:
        """Recursively extract all nested data."""
        if isinstance(obj, str):
            # Try to parse embedded data
            parsed = self._try_parse_json(obj)
            if parsed is not None and isinstance(parsed, dict):
                facts.nested_data.append(parsed)
                self._extract_nested_data(parsed, facts, path + ".json")
                return
            
            parsed = self._try_parse_python_repr(obj)
            if parsed is not None and isinstance(parsed, dict):
                facts.nested_data.append(parsed)
                self._extract_nested_data(parsed, facts, path + ".repr")
                return
        
        if isinstance(obj, dict):
            for k, v in obj.items():
                full_path = f"{path}.{k}" if path else k
                
                # Store flattened key-value
                if not isinstance(v, (dict, list)):
                    facts.extracted_kvs[full_path] = v
                
                # Recurse
                self._extract_nested_data(v, facts, full_path)
        
        elif isinstance(obj, (list, tuple)):
            for i, item in enumerate(obj):
                self._extract_nested_data(item, facts, f"{path}[{i}]")

    def _extract_patterns(self, text: str, facts: FactSheet) -> None:
        """Extract all known patterns from text."""
        # Agent IDs
        for match in PATTERN_AGENT_ID.finditer(text):
            agent_id = match.group(1)
            if agent_id not in facts.agent_ids and len(agent_id) == 10:
                facts.agent_ids.append(agent_id)
        
        # Alias IDs
        for match in PATTERN_AGENT_ALIAS_ID.finditer(text):
            alias_id = match.group(1)
            if alias_id not in facts.alias_ids:
                facts.alias_ids.append(alias_id)
        
        # Session IDs
        for match in PATTERN_SESSION_ID.finditer(text):
            session_id = match.group(1)
            if session_id not in facts.session_ids and len(session_id) > 5:
                facts.session_ids.append(session_id)
        
        # Trace IDs
        for match in PATTERN_TRACE_ID.finditer(text):
            trace_id = match.group(1)
            if trace_id not in facts.trace_ids:
                facts.trace_ids.append(trace_id)
        
        # Request IDs
        for match in PATTERN_AWS_REQUEST_ID.finditer(text):
            request_id = match.group(1)
            if request_id not in facts.request_ids:
                facts.request_ids.append(request_id)
        
        for match in PATTERN_LAMBDA_REQUEST_ID.finditer(text):
            request_id = match.group(1)
            if request_id not in facts.request_ids:
                facts.request_ids.append(request_id)
        
        # Correlation IDs
        for match in PATTERN_CORRELATION_ID.finditer(text):
            corr_id = match.group(1)
            if corr_id not in facts.correlation_ids:
                facts.correlation_ids.append(corr_id)
        
        # Message IDs (SQS, SNS, etc.)
        for match in PATTERN_MESSAGE_ID.finditer(text):
            message_id = match.group(1)
            if message_id not in facts.message_ids and len(message_id) > 3:
                facts.message_ids.append(message_id)
        
        # Slack channels
        for match in PATTERN_SLACK_CHANNEL.finditer(text):
            channel = match.group(1)
            if channel not in facts.slack_channels:
                facts.slack_channels.append(channel)
        
        # Slack thread timestamps
        for match in PATTERN_SLACK_THREAD_TS.finditer(text):
            thread_ts = match.group(1)
            if thread_ts not in facts.slack_thread_ts:
                facts.slack_thread_ts.append(thread_ts)
        
        # Slack users
        for match in PATTERN_SLACK_USER.finditer(text):
            user = match.group(1)
            if user not in facts.slack_users:
                facts.slack_users.append(user)
        
        # ARNs
        for match in PATTERN_AWS_ARN.finditer(text):
            arn = match.group(0)
            if arn not in facts.arns:
                facts.arns.append(arn)
        
        # UUIDs
        for match in PATTERN_UUID.finditer(text):
            uuid_val = match.group(1).lower()
            if uuid_val not in facts.uuids:
                facts.uuids.append(uuid_val)

    def _infer_component(self, text: str, facts: FactSheet) -> tuple[str | None, float]:
        """Infer what component/system this log is from."""
        scores: dict[str, float] = {}
        
        for component, patterns in COMPONENT_PATTERNS.items():
            score = 0.0
            for pattern in patterns:
                if pattern.search(text):
                    score += 1.0
            if score > 0:
                scores[component] = score / len(patterns)
        
        # Boost based on extracted data
        if facts.agent_ids:
            scores["bedrock"] = scores.get("bedrock", 0) + 0.5
        if facts.slack_channels or facts.slack_thread_ts:
            scores["slack"] = scores.get("slack", 0) + 0.5
        
        # Also check logger name
        if facts.logger_name:
            logger_lower = facts.logger_name.lower()
            for component in COMPONENT_PATTERNS:
                if component in logger_lower:
                    scores[component] = scores.get(component, 0) + 0.3
        
        if not scores:
            return None, 0.0
        
        best = max(scores.items(), key=lambda x: x[1])
        return best[0], min(best[1], 1.0)


@dataclass
class CorpusProfile:
    """Summary profile of an entire log corpus."""
    
    total_entries: int = 0
    
    # Component breakdown
    components: dict[str, int] = field(default_factory=dict)
    
    # All unique identifiers found
    all_agent_ids: set[str] = field(default_factory=set)
    all_session_ids: set[str] = field(default_factory=set)
    all_slack_channels: set[str] = field(default_factory=set)
    all_slack_threads: set[str] = field(default_factory=set)
    all_request_ids: set[str] = field(default_factory=set)
    
    # Log levels
    levels: dict[str, int] = field(default_factory=dict)
    
    # Time range
    earliest: datetime | None = None
    latest: datetime | None = None
    
    # Fact sheets
    fact_sheets: list[FactSheet] = field(default_factory=list)

    def summary(self) -> str:
        """Multi-line summary of the corpus."""
        lines = [
            f"=== Corpus Profile: {self.total_entries} entries ===",
            "",
        ]
        
        if self.earliest and self.latest:
            lines.append(f"Time range: {self.earliest} → {self.latest}")
            lines.append("")
        
        if self.components:
            lines.append("Components:")
            for comp, count in sorted(self.components.items(), key=lambda x: -x[1]):
                lines.append(f"  {comp}: {count}")
            lines.append("")
        
        if self.levels:
            lines.append("Log levels:")
            for level, count in sorted(self.levels.items(), key=lambda x: -x[1]):
                lines.append(f"  {level}: {count}")
            lines.append("")
        
        if self.all_agent_ids:
            lines.append(f"Agent IDs: {', '.join(sorted(self.all_agent_ids))}")
        if self.all_session_ids:
            lines.append(f"Session IDs: {len(self.all_session_ids)} unique")
        if self.all_slack_channels:
            lines.append(f"Slack channels: {', '.join(sorted(self.all_slack_channels))}")
        if self.all_slack_threads:
            lines.append(f"Slack threads: {len(self.all_slack_threads)} unique")
        
        return "\n".join(lines)


def profile_corpus(log_entries: list[dict[str, Any]], debug: bool = False) -> CorpusProfile:
    """Profile an entire log corpus."""
    profiler = LogProfiler(debug=debug)
    profile = CorpusProfile()
    
    for entry in log_entries:
        facts = profiler.profile(entry)
        profile.fact_sheets.append(facts)
        profile.total_entries += 1
        
        # Aggregate component
        if facts.component:
            profile.components[facts.component] = profile.components.get(facts.component, 0) + 1
        
        # Aggregate levels
        if facts.level:
            profile.levels[facts.level] = profile.levels.get(facts.level, 0) + 1
        
        # Collect identifiers
        profile.all_agent_ids.update(facts.agent_ids)
        profile.all_session_ids.update(facts.session_ids)
        profile.all_slack_channels.update(facts.slack_channels)
        profile.all_slack_threads.update(facts.slack_thread_ts)
        profile.all_request_ids.update(facts.request_ids)
        
        # Track time range
        if facts.timestamp_parsed:
            if profile.earliest is None or facts.timestamp_parsed < profile.earliest:
                profile.earliest = facts.timestamp_parsed
            if profile.latest is None or facts.timestamp_parsed > profile.latest:
                profile.latest = facts.timestamp_parsed
    
    return profile
