from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Sequence

from itk.trace.span_model import Span
from itk.trace.trace_model import Trace


def _participant_key(component: str) -> str:
    """Convert component name to valid Mermaid participant ID.

    Mermaid participant IDs must be simple alphanumeric tokens.
    Examples:
        lambda:foo-bar -> lambda_foo_bar
        agent:supervisor -> agent_supervisor
    """
    return (
        component.replace(":", "_")
        .replace("-", "_")
        .replace("/", "_")
        .replace(".", "_")
    )


@dataclass
class _DiagramEvent:
    """A single event (request or response) for timeline ordering."""

    timestamp: str
    span: Span
    is_response: bool  # False = request, True = response
    src_component: str
    dst_component: str

    @property
    def sort_key(self) -> tuple[str, int]:
        """Sort by timestamp, then responses after requests at same time."""
        return (self.timestamp, 1 if self.is_response else 0)


def _build_timeline_events(
    spans: Sequence[Span],
    span_by_id: dict[str, Span],
) -> list[_DiagramEvent]:
    """Build a list of diagram events sorted by timestamp.

    Each span produces up to two events:
    - Request event at ts_start (arrow from parent to child)
    - Response event at ts_end (arrow from child back to parent)

    Events are sorted by timestamp to produce correct temporal ordering.
    """
    events: list[_DiagramEvent] = []

    for s in spans:
        # Determine source (caller) and destination (callee)
        if s.parent_span_id and s.parent_span_id in span_by_id:
            caller_comp = span_by_id[s.parent_span_id].component
        else:
            caller_comp = s.component

        callee_comp = s.component

        # Request event at ts_start
        if s.ts_start:
            events.append(
                _DiagramEvent(
                    timestamp=s.ts_start,
                    span=s,
                    is_response=False,
                    src_component=caller_comp,
                    dst_component=callee_comp,
                )
            )

        # Response event at ts_end (only if we have a response or error)
        if s.ts_end and (s.response is not None or s.error is not None):
            events.append(
                _DiagramEvent(
                    timestamp=s.ts_end,
                    span=s,
                    is_response=True,
                    src_component=callee_comp,  # Response flows back
                    dst_component=caller_comp,
                )
            )

    # Sort by timestamp, with responses after requests at same timestamp
    events.sort(key=lambda e: e.sort_key)
    return events


def _group_retry_spans(spans: Sequence[Span]) -> list[list[Span]]:
    """Group spans by operation for retry detection.

    Returns groups where each group contains spans that represent
    retry attempts of the same operation.
    """
    # Group by (component, operation, parent_span_id) to detect retries
    groups: dict[tuple[str, str, str | None], list[Span]] = {}
    for s in spans:
        key = (s.component, s.operation, s.parent_span_id)
        if key not in groups:
            groups[key] = []
        groups[key].append(s)

    # Convert to list of groups, preserving original order
    result: list[list[Span]] = []
    seen_keys: set[tuple[str, str, str | None]] = set()
    for s in spans:
        key = (s.component, s.operation, s.parent_span_id)
        if key not in seen_keys:
            seen_keys.add(key)
            result.append(groups[key])

    return result


def _detect_retry_spans(spans: Sequence[Span]) -> set[str]:
    """Detect which spans are part of retry sequences.

    Returns span_ids that should be wrapped in retry loops.
    """
    groups = _group_retry_spans(spans)
    retry_span_ids: set[str] = set()

    for group in groups:
        has_retries = len(group) > 1 or any(
            s.attempt is not None and s.attempt > 1 for s in group
        )
        if has_retries:
            for s in group:
                retry_span_ids.add(s.span_id)

    return retry_span_ids


def render_mermaid_sequence(trace: Trace) -> str:
    """Render a Mermaid sequence diagram from a trace.

    Features:
    - Participants derived from span components
    - Arrows ordered by timestamp (ts_start for requests, ts_end for responses)
    - Request arrows flow from caller to callee
    - Response arrows flow from callee back to caller
    - Loop blocks for retry attempts (attempt > 1)
    - Notes with payload file references
    """
    # Collect participants in first-seen order
    participants: OrderedDict[str, str] = OrderedDict()
    for s in trace.spans:
        if s.component not in participants:
            participants[s.component] = _participant_key(s.component)

    lines: list[str] = ["sequenceDiagram"]

    # Participant declarations
    for label, pid in participants.items():
        lines.append(f"    participant {pid} as {label}")

    lines.append("")

    # Build span lookup for parent resolution
    span_by_id = {s.span_id: s for s in trace.spans}

    # Check if we have timestamps for proper ordering
    has_timestamps = any(s.ts_start for s in trace.spans)

    if has_timestamps:
        # Use timeline-based rendering for proper temporal ordering
        _render_timeline_based(lines, trace.spans, span_by_id, participants)
    else:
        # Fall back to span-order rendering (legacy behavior)
        _render_span_order(lines, trace.spans, span_by_id, participants)

    return "\n".join(lines) + "\n"


def _render_timeline_based(
    lines: list[str],
    spans: Sequence[Span],
    span_by_id: dict[str, Span],
    participants: OrderedDict[str, str],
) -> None:
    """Render diagram events in timestamp order.

    This produces correct temporal ordering where:
    1. Request arrows appear at ts_start
    2. Nested calls appear in order
    3. Response arrows appear at ts_end (unwinding the call stack)
    """
    events = _build_timeline_events(spans, span_by_id)
    retry_span_ids = _detect_retry_spans(spans)

    # Track which retry loops are open
    open_retry_loops: dict[str, int] = {}  # span_id -> max_attempt

    for event in events:
        s = event.span
        src = participants[event.src_component]
        dst = participants[event.dst_component]

        # Handle retry loop opening (on request events only)
        if not event.is_response and s.span_id in retry_span_ids:
            if s.span_id not in open_retry_loops:
                max_attempt = s.attempt or 1
                open_retry_loops[s.span_id] = max_attempt
                lines.append(f"    loop Retries (up to {max_attempt} attempts)")

        if event.is_response:
            # Response arrow (dashed, going back)
            label = f"{s.operation} response"
            if s.error is not None:
                label += " [ERROR]"
            lines.append(f"    {src}-->>{dst}: {label}")

            # Notes for response
            notes: list[str] = []
            if s.response is not None:
                notes.append(f"res=payloads/{s.span_id}.response.json")
            if s.error is not None:
                notes.append(f"err=payloads/{s.span_id}.error.json")
            if notes:
                lines.append(f"    Note over {dst},{src}: {', '.join(notes)}")

            # Close retry loop after response
            if s.span_id in open_retry_loops:
                lines.append("    end")
                del open_retry_loops[s.span_id]
        else:
            # Request arrow (solid, going forward)
            label = s.operation
            if s.attempt is not None and s.attempt > 1:
                label += f" [attempt {s.attempt}]"
            lines.append(f"    {src}->>{dst}: {label}")

            # Notes for request
            notes = []
            if s.request is not None:
                notes.append(f"req=payloads/{s.span_id}.request.json")

            # Add correlation IDs
            ids: list[str] = []
            if s.itk_trace_id:
                ids.append(f"itk:{s.itk_trace_id[:8]}")
            if s.lambda_request_id:
                ids.append(f"λ:{s.lambda_request_id[:8]}")
            if s.bedrock_session_id:
                ids.append(f"br:{s.bedrock_session_id[:8]}")

            if notes or ids:
                note_text = ", ".join(notes + ids)
                lines.append(f"    Note over {src},{dst}: {note_text}")

        lines.append("")


def _render_span_order(
    lines: list[str],
    spans: Sequence[Span],
    span_by_id: dict[str, Span],
    participants: OrderedDict[str, str],
) -> None:
    """Render in span order (legacy behavior when no timestamps available).

    This is the original rendering approach that processes spans sequentially.
    """
    span_groups = _group_retry_spans(spans)

    for group in span_groups:
        has_retries = len(group) > 1 or any(
            s.attempt is not None and s.attempt > 1 for s in group
        )

        if has_retries:
            # Open loop block
            max_attempt = max(s.attempt or 1 for s in group)
            lines.append(f"    loop Retries (up to {max_attempt} attempts)")

        for s in group:
            # Determine source and destination
            if s.parent_span_id and s.parent_span_id in span_by_id:
                src_comp = span_by_id[s.parent_span_id].component
            else:
                src_comp = s.component

            dst_comp = s.component
            src = participants[src_comp]
            dst = participants[dst_comp]

            # Build message label
            label = s.operation
            if s.attempt is not None:
                label += f" [attempt {s.attempt}]"

            # Arrow
            lines.append(f"    {src}->>{dst}: {label}")

            # Notes with payload references
            notes: list[str] = []
            if s.request is not None:
                notes.append(f"req=payloads/{s.span_id}.request.json")
            if s.response is not None:
                notes.append(f"res=payloads/{s.span_id}.response.json")
            if s.error is not None:
                notes.append("ERROR")

            # Add trace/span IDs to notes for debugging
            ids: list[str] = []
            if s.itk_trace_id:
                ids.append(f"itk:{s.itk_trace_id[:8]}")
            if s.lambda_request_id:
                ids.append(f"λ:{s.lambda_request_id[:8]}")
            if s.bedrock_session_id:
                ids.append(f"br:{s.bedrock_session_id[:8]}")

            if notes or ids:
                note_parts = notes + ids
                note_text = ", ".join(note_parts)
                lines.append(f"    Note over {src},{dst}: {note_text}")

        if has_retries:
            # Close loop block
            lines.append("    end")

        lines.append("")
