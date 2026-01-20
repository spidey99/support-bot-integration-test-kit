"""Extract correlation IDs from log events and spans."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class ExtractedIds:
    """Container for all extractable correlation IDs."""

    lambda_request_id: Optional[str] = None
    xray_trace_id: Optional[str] = None
    sqs_message_id: Optional[str] = None
    bedrock_session_id: Optional[str] = None
    itk_trace_id: Optional[str] = None
    thread_id: Optional[str] = None  # Slack thread_id / session correlation key
    session_id: Optional[str] = None  # Generic session ID (various formats)

    def has_any(self) -> bool:
        """Return True if any ID is present."""
        return any(
            [
                self.lambda_request_id,
                self.xray_trace_id,
                self.sqs_message_id,
                self.bedrock_session_id,
                self.itk_trace_id,
                self.thread_id,
                self.session_id,
            ]
        )

    def all_ids(self) -> dict[str, str]:
        """Return a dict of all non-None IDs."""
        result: dict[str, str] = {}
        if self.lambda_request_id:
            result["lambda_request_id"] = self.lambda_request_id
        if self.xray_trace_id:
            result["xray_trace_id"] = self.xray_trace_id
        if self.sqs_message_id:
            result["sqs_message_id"] = self.sqs_message_id
        if self.bedrock_session_id:
            result["bedrock_session_id"] = self.bedrock_session_id
        if self.itk_trace_id:
            result["itk_trace_id"] = self.itk_trace_id
        if self.thread_id:
            result["thread_id"] = self.thread_id
        if self.session_id:
            result["session_id"] = self.session_id
        return result


# Regex patterns for ID extraction
_XRAY_ROOT_RE = re.compile(r"Root=([0-9a-fA-F\-]+)")
_XRAY_TRACE_HEADER_RE = re.compile(
    r"Root=([0-9a-fA-F\-]+);(?:Parent=([0-9a-fA-F]+);)?(?:Sampled=(\d))?"
)
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_LAMBDA_REQUEST_ID_RE = re.compile(r"RequestId:\s*([0-9a-fA-F\-]{36})")

# Slack thread_id pattern: Unix timestamp with microseconds (e.g., 1768885845.305819)
_SLACK_THREAD_ID_RE = re.compile(r"thread_id['\"]?\s*[:=]\s*['\"]?(\d{10}\.\d{6})['\"]?")
_SLACK_TS_RE = re.compile(r"\b(\d{10}\.\d{6})\b")  # Bare Slack timestamp

# Session ID patterns - various formats
_SESSION_ID_FIELD_RE = re.compile(r"session[_-]?[iI]d['\"]?\s*[:=]\s*['\"]?([^'\"}\s,]+)['\"]?")
_BEDROCK_SESSION_HEADER_RE = re.compile(r"x-amz-bedrock-agent-session-id['\"]?\s*[:=]\s*['\"]?([^'\"}\s,]+)['\"]?")


def extract_xray_trace_id(text: str) -> Optional[str]:
    """Extract X-Ray trace ID from a string (e.g., _X_AMZN_TRACE_ID header)."""
    m = _XRAY_ROOT_RE.search(text)
    return m.group(1) if m else None


def extract_lambda_request_id(text: str) -> Optional[str]:
    """Extract Lambda request ID from log line or context."""
    # Try explicit pattern first
    m = _LAMBDA_REQUEST_ID_RE.search(text)
    if m:
        return m.group(1)

    # Fall back to UUID pattern if in Lambda-looking context
    if "lambda" in text.lower() or "request" in text.lower():
        m = _UUID_RE.search(text)
        if m:
            return m.group(0)

    return None


def extract_sqs_message_id(text: str) -> Optional[str]:
    """Extract SQS message ID from text."""
    # SQS message IDs are UUIDs
    if "messageid" in text.lower() or "sqs" in text.lower():
        m = _UUID_RE.search(text)
        if m:
            return m.group(0)
    return None


def extract_bedrock_session_id(text: str) -> Optional[str]:
    """Extract Bedrock session ID from text.

    Bedrock session IDs can be:
    - UUIDs
    - Custom session strings passed by the caller
    - x-amz-bedrock-agent-session-id header values
    """
    # Try explicit header pattern first
    m = _BEDROCK_SESSION_HEADER_RE.search(text)
    if m:
        return m.group(1)
    
    if "session" in text.lower() or "bedrock" in text.lower():
        m = _UUID_RE.search(text)
        if m:
            return m.group(0)
    return None


def extract_thread_id(text: str) -> Optional[str]:
    """Extract Slack thread_id from text.
    
    Slack thread IDs are Unix timestamps with microseconds: 1768885845.305819
    """
    # Try explicit thread_id field pattern
    m = _SLACK_THREAD_ID_RE.search(text)
    if m:
        return m.group(1)
    
    # Look for bare timestamp if "thread" or "slack" is mentioned
    if "thread" in text.lower() or "slack" in text.lower() or "ts" in text.lower():
        m = _SLACK_TS_RE.search(text)
        if m:
            return m.group(1)
    
    return None


def extract_session_id(text: str) -> Optional[str]:
    """Extract generic session ID from text.
    
    Session IDs can be various formats:
    - Slack timestamps (1768885845.305819)
    - UUIDs
    - Custom strings
    """
    # Try explicit sessionId field pattern
    m = _SESSION_ID_FIELD_RE.search(text)
    if m:
        return m.group(1)
    
    return None


def extract_all_ids_from_text(text: str) -> ExtractedIds:
    """Extract all possible IDs from a text string."""
    return ExtractedIds(
        lambda_request_id=extract_lambda_request_id(text),
        xray_trace_id=extract_xray_trace_id(text),
        sqs_message_id=extract_sqs_message_id(text),
        bedrock_session_id=extract_bedrock_session_id(text),
        # ITK trace ID requires explicit field, not text extraction
        itk_trace_id=None,
        thread_id=extract_thread_id(text),
        session_id=extract_session_id(text),
    )


def extract_ids_from_event(event: dict[str, Any]) -> ExtractedIds:
    """Extract all correlation IDs from a log event dictionary.

    Looks in common field locations:
    - Top-level fields (lambda_request_id, thread_id, sessionId, etc.)
    - Nested in context/meta
    - In message text
    """
    # Direct field extraction
    lambda_req_id = event.get("lambda_request_id")
    xray_trace_id = event.get("xray_trace_id")
    sqs_message_id = event.get("sqs_message_id")
    bedrock_session_id = event.get("bedrock_session_id")
    itk_trace_id = event.get("itk_trace_id")
    
    # Thread ID - key correlation field for Slack-based systems
    thread_id = event.get("thread_id")
    thread_id = thread_id or event.get("thread_ts")  # Slack alias
    
    # Session ID - various field names used
    session_id = event.get("session_id")
    session_id = session_id or event.get("sessionId")  # camelCase
    session_id = session_id or event.get("x-amz-bedrock-agent-session-id")
    
    # If session_id matches thread_id pattern, they're probably the same concept
    # The correlation engine will unify them

    # Try nested context
    context = event.get("context", {})
    if isinstance(context, dict):
        lambda_req_id = lambda_req_id or context.get("aws_request_id")
        lambda_req_id = lambda_req_id or context.get("lambda_request_id")
        thread_id = thread_id or context.get("thread_id")
        session_id = session_id or context.get("session_id")
        session_id = session_id or context.get("sessionId")

    # Try message text extraction if fields not found
    message = event.get("message", "")
    if isinstance(message, str):
        text_ids = extract_all_ids_from_text(message)
        lambda_req_id = lambda_req_id or text_ids.lambda_request_id
        xray_trace_id = xray_trace_id or text_ids.xray_trace_id
        thread_id = thread_id or text_ids.thread_id
        session_id = session_id or text_ids.session_id
        bedrock_session_id = bedrock_session_id or text_ids.bedrock_session_id

    # Try X-Ray header if present
    xray_header = event.get("_X_AMZN_TRACE_ID") or event.get("x_amzn_trace_id")
    if xray_header and not xray_trace_id:
        xray_trace_id = extract_xray_trace_id(str(xray_header))

    # Try SQS Records
    records = event.get("Records", [])
    if records and isinstance(records, list) and not sqs_message_id:
        for rec in records:
            if isinstance(rec, dict) and "messageId" in rec:
                sqs_message_id = rec["messageId"]
                break

    return ExtractedIds(
        lambda_request_id=lambda_req_id,
        xray_trace_id=xray_trace_id,
        sqs_message_id=sqs_message_id,
        bedrock_session_id=bedrock_session_id,
        itk_trace_id=itk_trace_id,
        thread_id=thread_id,
        session_id=session_id,
    )
