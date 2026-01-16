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

    def has_any(self) -> bool:
        """Return True if any ID is present."""
        return any(
            [
                self.lambda_request_id,
                self.xray_trace_id,
                self.sqs_message_id,
                self.bedrock_session_id,
                self.itk_trace_id,
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
        return result


# Regex patterns for ID extraction
_XRAY_ROOT_RE = re.compile(r"Root=([0-9a-fA-F\-]+)")
_XRAY_TRACE_HEADER_RE = re.compile(
    r"Root=([0-9a-fA-F\-]+);(?:Parent=([0-9a-fA-F]+);)?(?:Sampled=(\d))?"
)
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_LAMBDA_REQUEST_ID_RE = re.compile(r"RequestId:\s*([0-9a-fA-F\-]{36})")


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
    """
    if "session" in text.lower() or "bedrock" in text.lower():
        m = _UUID_RE.search(text)
        if m:
            return m.group(0)
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
    )


def extract_ids_from_event(event: dict[str, Any]) -> ExtractedIds:
    """Extract all correlation IDs from a log event dictionary.

    Looks in common field locations:
    - Top-level fields (lambda_request_id, etc.)
    - Nested in context/meta
    - In message text
    """
    # Direct field extraction
    lambda_req_id = event.get("lambda_request_id")
    xray_trace_id = event.get("xray_trace_id")
    sqs_message_id = event.get("sqs_message_id")
    bedrock_session_id = event.get("bedrock_session_id")
    itk_trace_id = event.get("itk_trace_id")

    # Try nested context
    context = event.get("context", {})
    if isinstance(context, dict):
        lambda_req_id = lambda_req_id or context.get("aws_request_id")
        lambda_req_id = lambda_req_id or context.get("lambda_request_id")

    # Try message text extraction if fields not found
    message = event.get("message", "")
    if isinstance(message, str):
        text_ids = extract_all_ids_from_text(message)
        lambda_req_id = lambda_req_id or text_ids.lambda_request_id
        xray_trace_id = xray_trace_id or text_ids.xray_trace_id

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
    )
