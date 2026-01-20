from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from itk.trace.span_model import Span


# Field name mappings: ITK canonical name -> list of common alternatives
FIELD_MAPPINGS = {
    "span_id": ["span_id", "spanId", "id", "eventId", "event_id"],
    "component": ["component", "span_type", "spanType", "type", "source", "service"],
    "operation": ["operation", "op", "action", "method", "function", "handler"],
    "ts_start": ["ts_start", "tsStart", "timestamp", "time", "startTime", "start_time", "@timestamp"],
    "ts_end": ["ts_end", "tsEnd", "endTime", "end_time"],
    "itk_trace_id": ["itk_trace_id", "itkTraceId", "trace_id", "traceId", "correlationId", "correlation_id"],
    "lambda_request_id": ["lambda_request_id", "lambdaRequestId", "request_id", "requestId", "reqId", "awsRequestId"],
    "xray_trace_id": ["xray_trace_id", "xrayTraceId", "x_ray_trace_id"],
    "sqs_message_id": ["sqs_message_id", "sqsMessageId", "messageId", "message_id"],
    "bedrock_session_id": ["bedrock_session_id", "bedrockSessionId"],
    "thread_id": ["thread_id", "threadId", "thread_ts", "threadTs", "ts"],
    "session_id": ["session_id", "sessionId", "x-amz-bedrock-agent-session-id", "bedrockSessionId"],
    "request": ["request", "req", "input", "payload", "body"],
    "response": ["response", "res", "output", "result"],
    "error": ["error", "err", "exception", "failure"],
    "attempt": ["attempt", "retry_attempt", "retryAttempt", "retry", "retryCount"],
    "parent_span_id": ["parent_span_id", "parentSpanId", "parent_id", "parentId"],
}

# Common parent keys that may wrap log data
NESTED_PARENT_KEYS = ["data", "log", "record", "event", "span", "context", "detail", "body", "payload", "attributes", "message"]

# Maximum depth for parsing stringified JSON to prevent infinite recursion
MAX_STRINGIFY_DEPTH = 5


def try_parse_stringified_json(value: Any, depth: int = 0) -> Any:
    """
    Attempt to parse stringified JSON from a string value, recursively.
    
    Handles cases where JSON is stringified (potentially multiple times):
    - '{"component": "lambda"}' -> {"component": "lambda"}
    - '"{\"component\": \"lambda\"}"' -> {"component": "lambda"}
    
    Args:
        value: The value to attempt parsing (only strings are parsed)
        depth: Current recursion depth to prevent infinite loops
        
    Returns:
        Parsed object if value was valid JSON, otherwise original value
    """
    if depth > MAX_STRINGIFY_DEPTH:
        return value
    
    if not isinstance(value, str):
        return value
    
    stripped = value.strip()
    if not stripped:
        return value
    
    # Only try to parse if it looks like JSON (starts with { or [, or is a quoted string)
    if not (stripped.startswith(("{", "[", '"'))):
        return value
    
    try:
        parsed = json.loads(stripped)
        # If parsed result is also a string, try parsing again (double-stringified JSON)
        if isinstance(parsed, str):
            return try_parse_stringified_json(parsed, depth + 1)
        # If parsed result is a dict, recursively parse any string values
        if isinstance(parsed, dict):
            return parse_stringified_json_in_dict(parsed, depth + 1)
        # If parsed result is a list, recursively parse items
        if isinstance(parsed, list):
            return [try_parse_stringified_json(item, depth + 1) for item in parsed]
        return parsed
    except (json.JSONDecodeError, TypeError):
        return value


def parse_stringified_json_in_dict(obj: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    """
    Recursively parse any stringified JSON within dictionary values.
    
    Handles nested stringified JSON in any string field:
    - {"message": '{"component": "lambda"}'} -> {"message": {"component": "lambda"}}
    - {"data": '{"nested": "{\\"deep\\": true}"}'} -> {"data": {"nested": {"deep": true}}}
    
    Args:
        obj: Dictionary to process
        depth: Current recursion depth
        
    Returns:
        Dictionary with any stringified JSON values parsed
    """
    if depth > MAX_STRINGIFY_DEPTH:
        return obj
    
    result: dict[str, Any] = {}
    for key, value in obj.items():
        if isinstance(value, str):
            result[key] = try_parse_stringified_json(value, depth)
        elif isinstance(value, dict):
            result[key] = parse_stringified_json_in_dict(value, depth + 1)
        elif isinstance(value, list):
            result[key] = [
                try_parse_stringified_json(item, depth + 1) if isinstance(item, str)
                else parse_stringified_json_in_dict(item, depth + 1) if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def extract_field(obj: dict[str, Any], canonical_name: str, default: Any = None) -> Any:
    """Extract a field using multiple possible names, searching nested structures."""
    alternatives = FIELD_MAPPINGS.get(canonical_name, [canonical_name])
    
    # First, search at root level
    for name in alternatives:
        if name in obj:
            return obj[name]
    
    # Then, search in common nested parent keys
    for parent_key in NESTED_PARENT_KEYS:
        if parent_key in obj and isinstance(obj[parent_key], dict):
            nested = obj[parent_key]
            for name in alternatives:
                if name in nested:
                    return nested[name]
    
    return default


def flatten_nested_log(obj: dict[str, Any], parse_stringified: bool = True) -> dict[str, Any]:
    """
    Flatten a nested log structure by merging common wrapper keys into root.
    
    Handles patterns like:
    - {"data": {"component": "lambda", ...}, "timestamp": "..."}
    - {"log": {"span_type": "sqs", ...}, "metadata": {...}}
    - {"record": {"operation": "invoke"}, "level": "INFO"}
    - {"message": '{"component": "lambda", ...}'} (stringified JSON)
    
    Args:
        obj: Log object to flatten
        parse_stringified: Whether to parse stringified JSON in string fields
    """
    # First, parse any stringified JSON values
    if parse_stringified:
        obj = parse_stringified_json_in_dict(obj)
    
    result = dict(obj)  # Start with root fields
    
    for parent_key in NESTED_PARENT_KEYS:
        if parent_key in obj and isinstance(obj[parent_key], dict):
            # Merge nested fields into result, but don't overwrite existing root fields
            for key, value in obj[parent_key].items():
                if key not in result:
                    result[key] = value
    
    return result


def normalize_log_to_span(obj: dict[str, Any]) -> Span | None:
    """
    Normalize a realistic log entry into an ITK Span.
    
    Handles:
    - Field name variance (requestId vs request_id vs reqId)
    - Missing span_id (auto-generate)
    - Different timestamp formats
    - Nested structures
    - Stringified JSON in string fields (potentially nested multiple times)
    """
    # First, parse any stringified JSON in the object
    obj = parse_stringified_json_in_dict(obj)
    
    # Skip non-span log entries (debug, plain messages, etc.)
    # A span needs at least component/operation or recognizable structure
    component = extract_field(obj, "component")
    operation = extract_field(obj, "operation")
    
    # If no component, try to infer from message
    if not component:
        message = obj.get("message", "")
        # Message could be a string or parsed dict; only infer from strings
        if isinstance(message, str):
            if "lambda" in message.lower() or "handler" in message.lower():
                component = "lambda"
            elif "bedrock" in message.lower() or "model" in message.lower():
                component = "bedrock"
            elif "sqs" in message.lower() or "queue" in message.lower():
                component = "sqs"
    
    # Must have at least component or operation to be a span
    if not component and not operation:
        return None
    
    # Generate span_id if missing
    span_id = extract_field(obj, "span_id")
    if not span_id:
        # Create deterministic ID from trace_id + operation + timestamp
        trace_id = extract_field(obj, "itk_trace_id", "")
        ts = extract_field(obj, "ts_start", "")
        span_id = f"auto-{uuid.uuid5(uuid.NAMESPACE_DNS, f'{trace_id}:{operation}:{ts}').hex[:12]}"
    
    # Determine operation fallback (message can be string or dict after parsing)
    message_val = obj.get("message", "unknown")
    operation_fallback = message_val if isinstance(message_val, str) else "unknown"
    
    return Span(
        span_id=span_id,
        parent_span_id=extract_field(obj, "parent_span_id"),
        component=component or "unknown",
        operation=operation or operation_fallback,
        ts_start=extract_field(obj, "ts_start"),
        ts_end=extract_field(obj, "ts_end"),
        attempt=extract_field(obj, "attempt"),
        itk_trace_id=extract_field(obj, "itk_trace_id"),
        lambda_request_id=extract_field(obj, "lambda_request_id"),
        xray_trace_id=extract_field(obj, "xray_trace_id"),
        sqs_message_id=extract_field(obj, "sqs_message_id"),
        bedrock_session_id=extract_field(obj, "bedrock_session_id"),
        thread_id=extract_field(obj, "thread_id"),
        session_id=extract_field(obj, "session_id"),
        request=extract_field(obj, "request"),
        response=extract_field(obj, "response"),
        error=extract_field(obj, "error"),
    )


def load_fixture_jsonl_as_spans(path: Path) -> list[Span]:
    """Load JSONL fixture lines that already resemble the Span model.

    This is intentionally simple so Tier 2 can build deterministic tests.
    Tier 3 will add CloudWatch parsing and heuristics.
    """
    spans: list[Span] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        spans.append(
            Span(
                span_id=obj["span_id"],
                parent_span_id=obj.get("parent_span_id"),
                component=obj["component"],
                operation=obj["operation"],
                ts_start=obj.get("ts_start"),
                ts_end=obj.get("ts_end"),
                attempt=obj.get("attempt"),
                itk_trace_id=obj.get("itk_trace_id"),
                lambda_request_id=obj.get("lambda_request_id"),
                xray_trace_id=obj.get("xray_trace_id"),
                sqs_message_id=obj.get("sqs_message_id"),
                bedrock_session_id=obj.get("bedrock_session_id"),
                thread_id=obj.get("thread_id"),
                session_id=obj.get("session_id"),
                request=obj.get("request"),
                response=obj.get("response"),
                error=obj.get("error"),
            )
        )
    return spans


def load_realistic_logs_as_spans(path: Path) -> list[Span]:
    """
    Load JSONL logs with realistic/varied field names and normalize to Spans.
    
    This handles logs from real systems that don't follow the ITK schema exactly.
    It auto-detects field mappings, generates missing span_ids, and filters
    non-span log entries (debug messages, etc.).
    """
    spans: list[Span] = []
    parse_stats = {"total": 0, "json_errors": 0, "skipped": 0, "spans": 0}
    
    for line_num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        
        parse_stats["total"] += 1
        
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            # Skip non-JSON lines (e.g., Lambda START/END/REPORT)
            parse_stats["json_errors"] += 1
            # Only log for unexpected failures (not Lambda runtime messages)
            if not any(line.startswith(prefix) for prefix in ("START ", "END ", "REPORT ", "INIT_")):
                import sys
                print(f"Warning: Line {line_num} is not valid JSON: {str(e)[:50]}", file=sys.stderr)
            continue
        
        span = normalize_log_to_span(obj)
        if span:
            spans.append(span)
            parse_stats["spans"] += 1
        else:
            parse_stats["skipped"] += 1
    
    # Warn if no spans were parsed
    if parse_stats["total"] > 0 and parse_stats["spans"] == 0:
        import sys
        print(f"Warning: Parsed 0 spans from {parse_stats['total']} log lines", file=sys.stderr)
        print(f"  JSON errors: {parse_stats['json_errors']}, Skipped (not span-like): {parse_stats['skipped']}", file=sys.stderr)
        print(f"  Hint: Logs may not have 'component' or 'operation' fields", file=sys.stderr)
    
    return spans


def parse_cloudwatch_logs(log_events: list[dict[str, Any]]) -> list[Span]:
    """
    Parse CloudWatch log events into Spans.
    
    CloudWatch events have structure: {timestamp, message, ...}
    The message field contains our JSON log entry.
    """
    spans: list[Span] = []
    stats = {"total": 0, "runtime_msgs": 0, "json_errors": 0, "no_span": 0, "spans": 0}
    
    for event in log_events:
        message = event.get("message", "") or event.get("@message", "")
        stats["total"] += 1
        
        # Skip Lambda runtime messages
        if message.startswith(("START ", "END ", "REPORT ", "INIT_START", "EXTENSION")):
            stats["runtime_msgs"] += 1
            continue
        
        try:
            obj = json.loads(message)
        except json.JSONDecodeError:
            # Not a JSON log, skip
            stats["json_errors"] += 1
            continue
        
        span = normalize_log_to_span(obj)
        if span:
            spans.append(span)
            stats["spans"] += 1
        else:
            stats["no_span"] += 1
    
    # Provide diagnostics if no spans found
    if stats["total"] > 0 and stats["spans"] == 0:
        import sys
        print(f"Warning: 0 spans from {stats['total']} CloudWatch events", file=sys.stderr)
        print(f"  Runtime messages: {stats['runtime_msgs']}", file=sys.stderr)
        print(f"  Non-JSON: {stats['json_errors']}", file=sys.stderr)
        print(f"  JSON but not span-like: {stats['no_span']}", file=sys.stderr)
        if stats["no_span"] > 0:
            print(f"  Hint: Your logs may need 'component' or 'operation' fields", file=sys.stderr)
            print(f"  Supported field names: {list(FIELD_MAPPINGS.get('component', []))}", file=sys.stderr)
    
    return spans

