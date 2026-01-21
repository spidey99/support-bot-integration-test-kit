"""Dynamic correlation discovery for logs without uniform trace IDs.

This module builds transitive correlation chains by:
1. Auto-detecting components from log entries
2. Extracting ALL potential correlation values (not just known ID fields)
3. Discovering "bridge values" that appear in multiple components
4. Building chains even without a single ID spanning the full trace

Example: SQS → Lambda → Slack → Bedrock
- SQS has message_id: "abc123"
- Lambda has request_id and receives message_id "abc123", logs thread_id: "1768.123"
- Slack entry has thread_id: "1768.123", sends to Bedrock with session_id: "1768.123"
- Bedrock has session_id: "1768.123"

Even though there's no single ID through all 4, we can chain:
SQS.message_id → Lambda.message_id, Lambda.thread_id → Slack.thread_id,
Slack.session_id → Bedrock.session_id
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

from itk.logs.parse import try_parse_python_dict_repr


# Patterns for extracting potential correlation values
# These are intentionally broad to catch values that might correlate

# UUID pattern (SQS message IDs, Lambda request IDs, etc.)
_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

# Slack timestamp pattern (thread_id, ts, session_id for Bedrock)
_SLACK_TS_PATTERN = re.compile(r"\b(\d{10}\.\d{6})\b")

# X-Ray trace ID pattern
_XRAY_PATTERN = re.compile(r"1-[0-9a-fA-F]{8}-[0-9a-fA-F]{24}")

# AWS request ID in log prefix: "RequestId: <uuid>"
_AWS_REQUEST_ID_PATTERN = re.compile(r"RequestId:\s*([0-9a-fA-F\-]{36})")

# Channel ID pattern (Slack channel IDs start with C, D, or G)
_CHANNEL_ID_PATTERN = re.compile(r"\b([CDG][0-9A-Z]{8,})\b")

# User ID pattern (Slack user IDs start with U or W)
_USER_ID_PATTERN = re.compile(r"\b([UW][0-9A-Z]{8,})\b")


# Component detection keywords and patterns
COMPONENT_PATTERNS: dict[str, list[str]] = {
    "sqs": ["sqs", "queue", "messageId", "receiptHandle"],
    "lambda": ["lambda", "handler", "invoke", "RequestId", "awsRequestId"],
    "bedrock": ["bedrock", "anthropic", "claude", "model", "agent-runtime", "x-amz-bedrock"],
    "slack": ["slack", "thread_id", "channel", "user", "SlackMessage", "thread_ts"],
    "dynamodb": ["dynamodb", "ddb", "table", "item", "putItem", "getItem"],
    "s3": ["s3", "bucket", "object", "key", "getObject", "putObject"],
    "api_gateway": ["apigateway", "api-gateway", "httpMethod", "resource", "path"],
    "eventbridge": ["eventbridge", "events", "detail-type", "source"],
    "step_functions": ["stepfunctions", "states", "execution", "stateMachine"],
    "sns": ["sns", "topic", "subscription", "publish"],
}


@dataclass
class CorrelationValue:
    """A potential correlation value extracted from a log entry."""
    
    value: str
    value_type: str  # uuid, slack_ts, xray, channel, user, etc.
    field_name: Optional[str] = None  # Original field name if from a field
    context: Optional[str] = None  # Text context where found
    
    def __hash__(self) -> int:
        return hash((self.value, self.value_type))
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CorrelationValue):
            return False
        return self.value == other.value and self.value_type == other.value_type


@dataclass
class LogEntry:
    """Parsed log entry with component and correlation values."""
    
    raw: dict[str, Any]
    component: str
    timestamp: Optional[str] = None
    correlation_values: set[CorrelationValue] = field(default_factory=set)
    index: int = 0  # Position in log stream
    
    def value_strings(self) -> set[str]:
        """Get just the value strings for quick matching."""
        return {cv.value for cv in self.correlation_values}


@dataclass
class CorrelationChain:
    """A chain of correlated log entries across components."""
    
    entries: list[LogEntry] = field(default_factory=list)
    bridge_values: dict[str, set[str]] = field(default_factory=dict)
    # Maps value -> set of components that share it
    
    @property
    def components(self) -> list[str]:
        """Unique components in order of appearance."""
        seen: set[str] = set()
        result: list[str] = []
        for entry in self.entries:
            if entry.component not in seen:
                seen.add(entry.component)
                result.append(entry.component)
        return result
    
    @property
    def component_count(self) -> int:
        return len(set(e.component for e in self.entries))


def detect_component(obj: dict[str, Any]) -> str:
    """
    Detect the component/service from a log entry.
    
    Uses keywords in field names, values, and logger names.
    Returns best-matching component or 'unknown'.
    """
    # Flatten to searchable text
    searchable = _flatten_to_text(obj).lower()
    
    # Check for explicit component field first
    component = obj.get("component") or obj.get("service") or obj.get("source")
    if component:
        return str(component).lower()
    
    # Check logger_name for hints
    logger = obj.get("logger_name", "")
    if isinstance(logger, str):
        if "slack" in logger.lower():
            return "slack"
        if "bedrock" in logger.lower():
            return "bedrock"
    
    # Check appname for hints
    appname = obj.get("appname", "")
    if isinstance(appname, str):
        if "orchestrator" in appname.lower():
            return "lambda"  # Orchestrator is typically a Lambda
    
    # Score each component by keyword matches
    scores: dict[str, int] = defaultdict(int)
    for component_name, keywords in COMPONENT_PATTERNS.items():
        for keyword in keywords:
            if keyword.lower() in searchable:
                scores[component_name] += 1
    
    if scores:
        return max(scores, key=scores.get)  # type: ignore
    
    return "unknown"


def _flatten_to_text(obj: Any, depth: int = 0) -> str:
    """Flatten an object to searchable text."""
    if depth > 5:
        return ""
    
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if isinstance(obj, dict):
        parts = []
        for k, v in obj.items():
            parts.append(str(k))
            parts.append(_flatten_to_text(v, depth + 1))
        return " ".join(parts)
    if isinstance(obj, (list, tuple)):
        return " ".join(_flatten_to_text(item, depth + 1) for item in obj)
    
    return ""


def extract_correlation_values(obj: dict[str, Any]) -> set[CorrelationValue]:
    """
    Extract ALL potential correlation values from a log entry.
    
    This is intentionally aggressive - we extract anything that MIGHT
    be a correlation ID, then let the graph analysis determine which
    values actually correlate entries.
    """
    values: set[CorrelationValue] = set()
    
    # Get all text to search
    text = _flatten_to_text(obj)
    
    # Extract from embedded Python dicts in message
    message = obj.get("message", "")
    if isinstance(message, str):
        embedded = try_parse_python_dict_repr(message)
        if embedded:
            _extract_from_dict(embedded, values, "embedded")
    
    # Extract from the main object
    _extract_from_dict(obj, values, "root")
    
    # Pattern-based extraction from text
    _extract_patterns_from_text(text, values)
    
    return values


def _extract_from_dict(
    obj: dict[str, Any],
    values: set[CorrelationValue],
    context: str,
    depth: int = 0,
) -> None:
    """Recursively extract correlation values from dict fields."""
    if depth > 5:
        return
    
    # Field names that likely contain correlation values
    correlation_fields = {
        "thread_id", "threadId", "thread_ts", "ts",
        "session_id", "sessionId", 
        "request_id", "requestId", "reqId", "awsRequestId",
        "message_id", "messageId",
        "trace_id", "traceId", "correlationId", "correlation_id",
        "channel", "channel_id", "channelId",
        "user", "user_id", "userId",
        "x-amz-bedrock-agent-session-id",
    }
    
    for key, val in obj.items():
        if isinstance(val, str) and val.strip():
            # Check if this is a known correlation field
            if key.lower().replace("-", "_").replace(" ", "_") in {f.lower() for f in correlation_fields}:
                value_type = _infer_value_type(val, key)
                values.add(CorrelationValue(
                    value=val,
                    value_type=value_type,
                    field_name=key,
                    context=context,
                ))
            
            # Also extract patterns from string values
            _extract_patterns_from_text(val, values)
        
        elif isinstance(val, dict):
            _extract_from_dict(val, values, f"{context}.{key}", depth + 1)
        
        elif isinstance(val, list):
            for i, item in enumerate(val):
                if isinstance(item, dict):
                    _extract_from_dict(item, values, f"{context}.{key}[{i}]", depth + 1)


def _infer_value_type(value: str, field_name: str) -> str:
    """Infer the type of a correlation value from its format and field name."""
    # Check patterns first
    if _UUID_PATTERN.fullmatch(value):
        return "uuid"
    if _SLACK_TS_PATTERN.fullmatch(value):
        return "slack_ts"
    if _XRAY_PATTERN.fullmatch(value):
        return "xray"
    if _CHANNEL_ID_PATTERN.fullmatch(value):
        return "channel"
    if _USER_ID_PATTERN.fullmatch(value):
        return "user"
    
    # Infer from field name
    field_lower = field_name.lower()
    if "thread" in field_lower or field_lower == "ts":
        return "thread"
    if "session" in field_lower:
        return "session"
    if "request" in field_lower or "req" in field_lower:
        return "request"
    if "message" in field_lower and "id" in field_lower:
        return "message"
    if "trace" in field_lower:
        return "trace"
    if "channel" in field_lower:
        return "channel"
    if "user" in field_lower:
        return "user"
    
    return "unknown"


def _extract_patterns_from_text(text: str, values: set[CorrelationValue]) -> None:
    """Extract correlation values using regex patterns."""
    # UUIDs
    for match in _UUID_PATTERN.finditer(text):
        values.add(CorrelationValue(
            value=match.group(0),
            value_type="uuid",
        ))
    
    # Slack timestamps
    for match in _SLACK_TS_PATTERN.finditer(text):
        values.add(CorrelationValue(
            value=match.group(1),
            value_type="slack_ts",
        ))
    
    # X-Ray trace IDs
    for match in _XRAY_PATTERN.finditer(text):
        values.add(CorrelationValue(
            value=match.group(0),
            value_type="xray",
        ))
    
    # AWS Request IDs from log prefix
    for match in _AWS_REQUEST_ID_PATTERN.finditer(text):
        values.add(CorrelationValue(
            value=match.group(1),
            value_type="lambda_request",
            context="aws_log_prefix",
        ))
    
    # Slack channel IDs
    for match in _CHANNEL_ID_PATTERN.finditer(text):
        values.add(CorrelationValue(
            value=match.group(1),
            value_type="channel",
        ))
    
    # Slack user IDs
    for match in _USER_ID_PATTERN.finditer(text):
        values.add(CorrelationValue(
            value=match.group(1),
            value_type="user",
        ))


def _unwrap_cloudwatch_format(obj: dict[str, Any]) -> dict[str, Any]:
    """
    Unwrap CloudWatch log format if detected.
    
    CloudWatch format: {"timestamp": ..., "message": "<stringified JSON or dict>"}
    Returns the unwrapped object or the original if not CloudWatch format.
    """
    # Check if this looks like CloudWatch format
    # CloudWatch events typically have: timestamp (int), message (str), other metadata
    message = obj.get("message")
    if not isinstance(message, str):
        return obj
    
    # Check if 'message' looks like it contains another structured log
    # NOT CloudWatch format: {"message": "Some text", "level": "INFO", ...}
    # IS CloudWatch format: {"timestamp": 123, "message": "{\"appname\":...}"}
    
    # If the object has fields like appname, level, logger_name - it's already unwrapped
    if any(k in obj for k in ("appname", "level", "logger_name", "component")):
        return obj
    
    # Try to parse the message as JSON or Python dict repr
    import json as json_module
    
    inner: dict[str, Any] | None = None
    
    # Try JSON first
    try:
        parsed = json_module.loads(message)
        if isinstance(parsed, dict):
            inner = parsed
    except json_module.JSONDecodeError:
        pass
    
    # Try Python dict repr (single quotes)
    if inner is None:
        inner = try_parse_python_dict_repr(message)
    
    if inner:
        # Merge with CloudWatch metadata
        result = dict(inner)
        if "timestamp" not in result and "timestamp" in obj:
            result["timestamp"] = obj["timestamp"]
        if "@timestamp" not in result and "@timestamp" in obj:
            result["@timestamp"] = obj["@timestamp"]
        return result
    
    return obj


def parse_log_entry(obj: dict[str, Any], index: int = 0) -> LogEntry:
    """Parse a raw log object into a LogEntry with component and correlation values."""
    # Unwrap CloudWatch format if needed
    unwrapped = _unwrap_cloudwatch_format(obj)
    
    return LogEntry(
        raw=unwrapped,
        component=detect_component(unwrapped),
        timestamp=unwrapped.get("timestamp") or unwrapped.get("time") or unwrapped.get("@timestamp"),
        correlation_values=extract_correlation_values(unwrapped),
        index=index,
    )


def parse_log_stream(logs: list[dict[str, Any]]) -> list[LogEntry]:
    """Parse a stream of log objects into LogEntries."""
    return [parse_log_entry(obj, i) for i, obj in enumerate(logs)]


def build_correlation_chains(entries: list[LogEntry]) -> list[CorrelationChain]:
    """
    Build correlation chains from log entries.
    
    Uses Union-Find with transitive closure to group entries that share
    any correlation value, even indirectly.
    
    Algorithm:
    1. Build index: value -> list of entry indices
    2. Use Union-Find to group entries that share any value
    3. For each group, identify bridge values (values shared by 2+ components)
    4. Return chains sorted by first entry timestamp
    """
    if not entries:
        return []
    
    # Build value -> entries index
    value_to_entries: dict[str, list[int]] = defaultdict(list)
    for i, entry in enumerate(entries):
        for cv in entry.correlation_values:
            value_to_entries[cv.value].append(i)
    
    # Union-Find
    parent = list(range(len(entries)))
    
    def find(x: int) -> int:
        if parent[x] != x:
            parent[x] = find(parent[x])  # Path compression
        return parent[x]
    
    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py
    
    # Union entries that share any value
    for value, entry_indices in value_to_entries.items():
        if len(entry_indices) > 1:
            first = entry_indices[0]
            for other in entry_indices[1:]:
                union(first, other)
    
    # Group entries by root
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(entries)):
        groups[find(i)].append(i)
    
    # Build chains
    chains: list[CorrelationChain] = []
    for group_indices in groups.values():
        if len(group_indices) < 2:
            # Single entry - not interesting as a chain
            continue
        
        chain_entries = [entries[i] for i in sorted(group_indices)]
        
        # Find bridge values (shared across components)
        bridge_values: dict[str, set[str]] = defaultdict(set)
        for entry in chain_entries:
            for cv in entry.correlation_values:
                bridge_values[cv.value].add(entry.component)
        
        # Filter to only values shared by 2+ components
        bridge_values = {
            v: comps for v, comps in bridge_values.items()
            if len(comps) > 1
        }
        
        chains.append(CorrelationChain(
            entries=chain_entries,
            bridge_values=bridge_values,
        ))
    
    # Sort chains by first entry index (chronological order)
    chains.sort(key=lambda c: c.entries[0].index if c.entries else 0)
    
    return chains


def discover_correlations(logs: list[dict[str, Any]]) -> list[CorrelationChain]:
    """
    Main entry point: discover correlation chains from raw logs.
    
    Args:
        logs: List of raw log dictionaries
        
    Returns:
        List of CorrelationChain objects, each representing a set of
        correlated log entries across components.
    """
    entries = parse_log_stream(logs)
    return build_correlation_chains(entries)


def summarize_chains(chains: list[CorrelationChain]) -> str:
    """Generate a human-readable summary of discovered chains."""
    if not chains:
        return "No correlation chains discovered."
    
    lines = [f"Discovered {len(chains)} correlation chain(s):\n"]
    
    for i, chain in enumerate(chains, 1):
        lines.append(f"Chain {i}: {' → '.join(chain.components)}")
        lines.append(f"  Entries: {len(chain.entries)}")
        lines.append(f"  Components: {chain.component_count}")
        
        if chain.bridge_values:
            lines.append("  Bridge values:")
            for value, components in list(chain.bridge_values.items())[:5]:
                lines.append(f"    {value[:30]}... → {', '.join(components)}")
        
        lines.append("")
    
    return "\n".join(lines)


def _extract_input_data(entry: LogEntry) -> dict[str, Any] | None:
    """
    Extract input/request data from a log entry.
    
    Looks for input data in:
    1. Explicit 'request' or 'input' fields
    2. Embedded dicts in the 'message' field
    3. Structured fields that represent input (body, payload, etc.)
    """
    raw = entry.raw
    
    # Check explicit fields first
    if raw.get("request"):
        return raw["request"]
    if raw.get("input"):
        return raw["input"]
    if raw.get("body"):
        return raw["body"]
    if raw.get("payload"):
        return raw["payload"]
    
    # Try to extract embedded dict from message
    message = raw.get("message", "")
    if isinstance(message, str):
        embedded = try_parse_python_dict_repr(message)
        if embedded:
            return embedded
    
    # Build input summary from relevant fields
    input_fields = {}
    for key in ("text", "userMessage", "inputText", "query", "prompt"):
        if key in raw:
            input_fields[key] = raw[key]
    
    # Include log metadata as context
    input_fields["_log_level"] = raw.get("level", "INFO")
    input_fields["_log_message"] = message[:500] if isinstance(message, str) else str(message)[:500]
    if raw.get("logger_name"):
        input_fields["_logger"] = raw["logger_name"]
    if raw.get("appname"):
        input_fields["_appname"] = raw["appname"]
    
    return input_fields if input_fields else None


def _extract_response_data(entry: LogEntry) -> dict[str, Any] | None:
    """
    Extract response/output data from a log entry.
    
    Looks for response patterns in message content.
    """
    raw = entry.raw
    
    # Check explicit fields first
    if raw.get("response"):
        return raw["response"]
    if raw.get("output"):
        return raw["output"]
    if raw.get("result"):
        return raw["result"]
    
    # Check for response patterns in message
    message = raw.get("message", "")
    if isinstance(message, str):
        message_lower = message.lower()
        
        # Look for response indicators
        if any(pattern in message_lower for pattern in 
               ("response", "replied", "posted", "returned", "result")):
            # Try to extract embedded dict
            embedded = try_parse_python_dict_repr(message)
            if embedded:
                return embedded
            
            # Return message as response summary
            return {"_response_message": message[:500]}
    
    return None


def _detect_error(entry: LogEntry) -> dict[str, Any] | None:
    """
    Detect error status from a log entry.
    
    Checks:
    1. Explicit 'error' field
    2. Log level (ERROR, CRITICAL, FATAL)
    3. Error patterns in message
    """
    raw = entry.raw
    
    # Check explicit error field
    if raw.get("error"):
        error_data = raw["error"]
        if isinstance(error_data, dict):
            return error_data
        return {"message": str(error_data)}
    
    # Check log level
    level = str(raw.get("level", "")).upper()
    if level in ("ERROR", "CRITICAL", "FATAL", "SEVERE"):
        error_info: dict[str, Any] = {
            "level": level,
        }
        
        message = raw.get("message", "")
        if isinstance(message, str):
            error_info["message"] = message[:500]
            
            # Try to extract exception details from message
            embedded = try_parse_python_dict_repr(message)
            if embedded:
                error_info["details"] = embedded
        
        return error_info
    
    # Check for error patterns in message (even if level is INFO/WARNING)
    message = raw.get("message", "")
    if isinstance(message, str):
        message_lower = message.lower()
        error_patterns = ("exception", "traceback", "failed", "failure", "error:")
        if any(pattern in message_lower for pattern in error_patterns):
            return {
                "level": level or "UNKNOWN",
                "message": message[:500],
            }
    
    return None


def chain_to_spans(chain: CorrelationChain, chain_id: str) -> list["Span"]:
    """
    Convert a CorrelationChain to a list of Spans.
    
    Uses the chain's primary bridge value as the correlation ID,
    allowing the chain to be treated as a single execution/trace.
    
    Args:
        chain: The correlation chain to convert
        chain_id: Unique identifier for this chain (used as trace ID)
        
    Returns:
        List of Span objects that can be used for diagram generation.
    """
    from itk.trace.span_model import Span
    
    spans: list[Span] = []
    
    # Find primary bridge value (appears in most components)
    primary_bridge: str | None = None
    if chain.bridge_values:
        # Sort by number of components, pick the one spanning the most
        sorted_bridges = sorted(
            chain.bridge_values.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )
        if sorted_bridges:
            primary_bridge = sorted_bridges[0][0]
    
    for i, entry in enumerate(chain.entries):
        # Extract operation from log entry
        operation = _infer_operation(entry.raw)
        
        # Get timestamp
        ts = entry.timestamp
        if isinstance(ts, (int, float)):
            # Convert epoch ms to ISO format
            from datetime import datetime, timezone
            try:
                ts = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
            except (OSError, ValueError):
                ts = str(ts)
        
        # Extract any thread_id/session_id from correlation values
        thread_id = None
        session_id = None
        for cv in entry.correlation_values:
            if cv.value_type == "slack_ts":
                thread_id = cv.value
                session_id = cv.value  # Also use as session_id
                break
        
        # Extract input, response, and error data from log entry
        request_data = _extract_input_data(entry)
        response_data = _extract_response_data(entry)
        error_data = _detect_error(entry)
        
        span = Span(
            span_id=f"{chain_id}-{i}",
            parent_span_id=f"{chain_id}-{i-1}" if i > 0 else None,
            component=entry.component,
            operation=operation,
            ts_start=ts,
            ts_end=ts,  # Use same timestamp to enable response event rendering
            itk_trace_id=chain_id,
            thread_id=thread_id or primary_bridge,
            session_id=session_id or primary_bridge,
            request=request_data,
            response=response_data,
            error=error_data,
        )
        spans.append(span)
    
    return spans


def _infer_operation(obj: dict[str, Any]) -> str:
    """Infer operation name from log entry."""
    # Check explicit fields
    for field in ("operation", "op", "action", "event", "method"):
        if field in obj:
            return str(obj[field])
    
    # Check logger_name for hints
    logger = obj.get("logger_name", "")
    if logger:
        parts = logger.split(".")
        if len(parts) > 1:
            return parts[-1]
    
    # Check message for operation hints
    message = obj.get("message", "")
    if isinstance(message, str):
        # Look for common patterns
        if "received" in message.lower():
            return "receive"
        if "sending" in message.lower() or "sent" in message.lower():
            return "send"
        if "invoking" in message.lower() or "invoked" in message.lower():
            return "invoke"
        if "response" in message.lower():
            return "response"
        if "error" in message.lower():
            return "error"
    
    return "log"

