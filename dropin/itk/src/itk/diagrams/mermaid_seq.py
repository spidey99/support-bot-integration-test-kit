from __future__ import annotations

from collections import OrderedDict
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


def render_mermaid_sequence(trace: Trace) -> str:
    """Render a Mermaid sequence diagram from a trace.

    Features:
    - Participants derived from span components
    - Arrows from parent to child spans
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

    # Group spans for retry detection
    span_groups = _group_retry_spans(trace.spans)

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

    return "\n".join(lines) + "\n"
