"""Trace model and ingestion utilities."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from itk.trace.span_model import Span


@dataclass(frozen=True)
class Trace:
    """An ordered list of spans for rendering and analysis."""

    spans: list[Span]


@dataclass
class BedrockTraceEvent:
    """A single event from Bedrock's enableTrace output.

    Bedrock traces have a nested structure with orchestrationTrace containing
    various event types: modelInvocationInput/Output, invocationInput, observation,
    rationale, etc.
    """

    session_id: str
    trace_id: str
    event_type: str
    timestamp: str
    raw_trace: dict[str, Any]

    @property
    def orchestration_trace(self) -> Optional[dict[str, Any]]:
        """Extract the orchestrationTrace from the raw trace."""
        return self.raw_trace.get("trace", {}).get("orchestrationTrace")


def parse_bedrock_trace_event(raw: dict[str, Any]) -> BedrockTraceEvent:
    """Parse a raw Bedrock trace event into a structured object."""
    return BedrockTraceEvent(
        session_id=raw.get("sessionId", ""),
        trace_id=raw.get("traceId", ""),
        event_type=raw.get("event", "unknown"),
        timestamp=raw.get("timestamp", ""),
        raw_trace=raw,
    )


def load_bedrock_trace_jsonl(path: Path) -> list[BedrockTraceEvent]:
    """Load Bedrock trace events from a JSONL file."""
    events: list[BedrockTraceEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        events.append(parse_bedrock_trace_event(raw))
    return events


def bedrock_traces_to_spans(
    events: list[BedrockTraceEvent],
    session_id: Optional[str] = None,
) -> list[Span]:
    """Convert Bedrock trace events into ITK spans.

    This creates spans for:
    - modelInvocationInput/Output pairs (agent model calls)
    - invocationInput/observation pairs (action group invocations)

    Args:
        events: List of Bedrock trace events
        session_id: Optional session ID to filter events

    Returns:
        List of Spans derived from the trace events
    """
    # Filter by session if specified
    if session_id:
        events = [e for e in events if e.session_id == session_id]

    # Sort by timestamp
    events.sort(key=lambda e: e.timestamp)

    spans: list[Span] = []
    span_counter = 0

    # Track open model invocations and action group calls
    model_input: Optional[BedrockTraceEvent] = None
    action_input: Optional[BedrockTraceEvent] = None

    for event in events:
        orch = event.orchestration_trace
        if not orch:
            continue

        # Model invocation input (start of model call)
        if "modelInvocationInput" in orch:
            model_input = event

        # Model invocation output (end of model call)
        elif "modelInvocationOutput" in orch and model_input:
            span_counter += 1
            inp = model_input.orchestration_trace.get("modelInvocationInput", {})
            out = orch.get("modelInvocationOutput", {})

            spans.append(
                Span(
                    span_id=f"bedrock-model-{span_counter:03d}",
                    parent_span_id=None,  # Would need parent tracking
                    component="agent:bedrock-model",
                    operation="InvokeModel",
                    ts_start=model_input.timestamp,
                    ts_end=event.timestamp,
                    bedrock_session_id=event.session_id,
                    request={
                        "text": inp.get("text"),
                        "inferenceConfiguration": inp.get("inferenceConfiguration"),
                        "type": inp.get("type"),
                    },
                    response={
                        "parsedResponse": out.get("parsedResponse"),
                    },
                )
            )
            model_input = None

        # Action group invocation input
        elif "invocationInput" in orch:
            inv_input = orch.get("invocationInput", {})
            if inv_input.get("invocationType") == "ACTION_GROUP":
                action_input = event

        # Action group observation (result)
        elif "observation" in orch:
            obs = orch.get("observation", {})
            if obs.get("type") == "ACTION_GROUP" and action_input:
                span_counter += 1
                inv_input = action_input.orchestration_trace.get("invocationInput", {})
                ag_input = inv_input.get("actionGroupInvocationInput", {})
                ag_output = obs.get("actionGroupInvocationOutput", {})

                action_group_name = ag_input.get("actionGroupName", "unknown")

                spans.append(
                    Span(
                        span_id=f"bedrock-action-{span_counter:03d}",
                        parent_span_id=None,
                        component=f"lambda:{action_group_name}",
                        operation="InvokeActionGroup",
                        ts_start=action_input.timestamp,
                        ts_end=event.timestamp,
                        bedrock_session_id=event.session_id,
                        request={
                            "actionGroupName": action_group_name,
                            "apiPath": ag_input.get("apiPath"),
                            "verb": ag_input.get("verb"),
                            "requestBody": ag_input.get("requestBody"),
                        },
                        response={
                            "text": ag_output.get("text"),
                        },
                    )
                )
                action_input = None

        # Rationale (agent's reasoning) - optional span
        elif "rationale" in orch:
            span_counter += 1
            rationale = orch.get("rationale", {})
            spans.append(
                Span(
                    span_id=f"bedrock-rationale-{span_counter:03d}",
                    parent_span_id=None,
                    component="agent:bedrock-rationale",
                    operation="Rationale",
                    ts_start=event.timestamp,
                    bedrock_session_id=event.session_id,
                    request={"reasoning": rationale.get("text")},
                )
            )

    return spans


def merge_trace_into_log_spans(
    log_spans: list[Span],
    trace_spans: list[Span],
) -> list[Span]:
    """Merge Bedrock trace spans with log-derived spans.

    Trace spans can fill in gaps where log spans are missing request/response
    payload detail. This uses session_id to correlate spans.

    Strategy:
    1. Index trace spans by session_id
    2. For each log span with a session_id, look for matching trace spans
    3. Enrich log span payloads from trace spans if log span is missing them
    4. Add remaining trace spans that have no corresponding log span
    """
    # Index trace spans by session_id
    trace_by_session: dict[str, list[Span]] = {}
    for ts in trace_spans:
        if ts.bedrock_session_id:
            if ts.bedrock_session_id not in trace_by_session:
                trace_by_session[ts.bedrock_session_id] = []
            trace_by_session[ts.bedrock_session_id].append(ts)

    # Track which trace spans are "consumed" by enrichment
    used_trace_span_ids: set[str] = set()

    # Enrich log spans
    enriched_spans: list[Span] = []
    for ls in log_spans:
        # Try to find matching trace spans
        matched_traces = trace_by_session.get(ls.bedrock_session_id or "", [])

        # If log span has no request but a trace span does, merge
        # This is a simplified merge - real implementation would be more sophisticated
        enriched = ls
        for ts in matched_traces:
            if ts.span_id not in used_trace_span_ids:
                # Match by operation type similarity
                if ls.operation == ts.operation or (
                    "Model" in ls.operation and "Model" in ts.operation
                ):
                    # Enrich missing fields
                    new_request = ls.request if ls.request else ts.request
                    new_response = ls.response if ls.response else ts.response

                    if new_request != ls.request or new_response != ls.response:
                        enriched = Span(
                            span_id=ls.span_id,
                            parent_span_id=ls.parent_span_id,
                            component=ls.component,
                            operation=ls.operation,
                            ts_start=ls.ts_start or ts.ts_start,
                            ts_end=ls.ts_end or ts.ts_end,
                            attempt=ls.attempt,
                            itk_trace_id=ls.itk_trace_id,
                            lambda_request_id=ls.lambda_request_id,
                            xray_trace_id=ls.xray_trace_id,
                            sqs_message_id=ls.sqs_message_id,
                            bedrock_session_id=ls.bedrock_session_id,
                            request=new_request,
                            response=new_response,
                            error=ls.error,
                        )
                        used_trace_span_ids.add(ts.span_id)
                        break

        enriched_spans.append(enriched)

    # Add remaining trace spans that weren't used for enrichment
    for session_traces in trace_by_session.values():
        for ts in session_traces:
            if ts.span_id not in used_trace_span_ids:
                enriched_spans.append(ts)

    return enriched_spans
