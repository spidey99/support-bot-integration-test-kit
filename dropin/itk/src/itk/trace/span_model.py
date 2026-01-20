from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class Span:
    """A normalized boundary event used to build a sequence diagram."""

    span_id: str
    parent_span_id: Optional[str]

    # Identity
    component: str  # e.g. lambda:action-foo, agent:supervisor, model:claude
    operation: str  # e.g. InvokeAgent, InvokeModel, InvokeLambda

    # Timing
    ts_start: Optional[str] = None
    ts_end: Optional[str] = None

    # Retry
    attempt: Optional[int] = None

    # Correlation (any/all may exist)
    itk_trace_id: Optional[str] = None
    lambda_request_id: Optional[str] = None
    xray_trace_id: Optional[str] = None
    sqs_message_id: Optional[str] = None
    bedrock_session_id: Optional[str] = None
    thread_id: Optional[str] = None  # Slack thread_id - primary correlation key
    session_id: Optional[str] = None  # Generic session ID (e.g., x-amz-bedrock-agent-session-id)

    # Payloads
    request: Optional[dict[str, Any]] = None
    response: Optional[dict[str, Any]] = None

    # Error
    error: Optional[dict[str, Any]] = None

    # Flow semantics
    is_async: bool = False  # True for fire-and-forget, no return expected
    is_one_way: bool = False  # Alias for is_async (backwards compat)
