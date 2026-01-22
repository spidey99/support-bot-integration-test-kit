"""Enhanced interactive trace viewer with SVG pan/zoom and search.

This module generates a feature-rich trace viewer with:
- SVG-based sequence diagram with pan/zoom (via svg-pan-zoom)
- Search with fuzzy matching (via Fuse.js)
- Filters: participants, errors-only, retries-only
- Click-to-select with ancestor/descendant highlighting
- Keyboard navigation (/, Esc, arrows)
- Right panel with full span details
- Dark mode support
"""
from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from itk.trace.trace_model import Trace
from itk.trace.span_model import Span


# Load vendored JS libraries
_VENDOR_DIR = Path(__file__).parent / "vendor"


def _load_vendor_js(name: str) -> str:
    """Load vendored JavaScript file contents."""
    path = _VENDOR_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"// {name} not found"


# Component type → color scheme (AWS-inspired palette)
COMPONENT_COLORS: dict[str, dict[str, str]] = {
    "lambda": {"bg": "#ff9900", "text": "#000", "icon": "λ", "stroke": "#cc7a00"},
    "agent": {"bg": "#00a4ef", "text": "#fff", "icon": "🤖", "stroke": "#0082c4"},
    "model": {"bg": "#8b5cf6", "text": "#fff", "icon": "🧠", "stroke": "#6d43d8"},
    "sqs": {"bg": "#ff4f8b", "text": "#fff", "icon": "📨", "stroke": "#d93d73"},
    "entrypoint": {"bg": "#10b981", "text": "#fff", "icon": "▶", "stroke": "#0d9668"},
    "bedrock": {"bg": "#8b5cf6", "text": "#fff", "icon": "🪨", "stroke": "#6d43d8"},
    "dynamodb": {"bg": "#3b82f6", "text": "#fff", "icon": "📊", "stroke": "#2563eb"},
    "s3": {"bg": "#22c55e", "text": "#fff", "icon": "📦", "stroke": "#16a34a"},
    "default": {"bg": "#6b7280", "text": "#fff", "icon": "●", "stroke": "#4b5563"},
}

# SVG layout constants
PARTICIPANT_WIDTH = 150
PARTICIPANT_GAP = 50
PARTICIPANT_HEADER_HEIGHT = 80
MESSAGE_HEIGHT = 80  # Increased to accommodate call + return arrows
PADDING = 40


@dataclass
class ParticipantInfo:
    """Info about a participant in the sequence diagram."""

    id: str
    label: str
    component_type: str
    index: int
    color: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.color:
            self.color = COMPONENT_COLORS.get(
                self.component_type.lower(), COMPONENT_COLORS["default"]
            )

    @property
    def x_center(self) -> int:
        """X coordinate of participant's center line."""
        return PADDING + self.index * (PARTICIPANT_WIDTH + PARTICIPANT_GAP) + PARTICIPANT_WIDTH // 2


@dataclass
class MessageInfo:
    """Info about a message/arrow in the sequence diagram."""

    span_id: str
    span: Span
    from_participant: ParticipantInfo
    to_participant: ParticipantInfo
    operation: str
    attempt: int
    latency_ms: float | None
    has_error: bool
    y_position: int
    request: dict[str, Any] | None
    response: dict[str, Any] | None
    error: dict[str, Any] | None
    is_response: bool = False  # True for return arrows, False for call arrows
    timestamp: str | None = None  # For timeline ordering


def _get_component_type(component: str) -> str:
    """Extract component type from component string like 'lambda:handler'."""
    if ":" in component:
        return component.split(":")[0].lower()
    return component.lower()


def _safe_id(s: str) -> str:
    """Convert string to safe HTML/SVG id."""
    import re
    # Replace non-alphanumeric with underscore
    safe = re.sub(r"[^a-zA-Z0-9]", "_", s)
    # Ensure starts with letter
    if safe and safe[0].isdigit():
        safe = "id_" + safe
    return safe or "unknown"


def _compute_latency(span: Span) -> float | None:
    """Compute latency in ms from span timestamps."""
    if not span.ts_start or not span.ts_end:
        return None
    try:
        from datetime import datetime

        def parse_ts(ts: str) -> datetime:
            ts = ts.replace("Z", "+00:00")
            if "+" not in ts and "-" not in ts[10:]:
                ts += "+00:00"
            return datetime.fromisoformat(ts)

        start = parse_ts(span.ts_start)
        end = parse_ts(span.ts_end)
        return (end - start).total_seconds() * 1000
    except Exception:
        return None


def _extract_participants(trace: Trace) -> list[ParticipantInfo]:
    """Extract unique participants from trace spans in order of appearance."""
    seen: dict[str, ParticipantInfo] = {}
    index = 0

    for span in trace.spans:
        comp = span.component
        if comp not in seen:
            comp_type = _get_component_type(comp)
            seen[comp] = ParticipantInfo(
                id=_safe_id(comp),
                label=comp,
                component_type=comp_type,
                index=index,
            )
            index += 1

    return list(seen.values())



def _extract_messages(
    trace: Trace, participants: list[ParticipantInfo]
) -> list[MessageInfo]:
    """Extract messages from trace spans using timeline-based ordering.

    If timestamps are available, produces separate request and response arrows
    in chronological order. Otherwise, falls back to span-order processing.
    """
    span_map = {s.span_id: s for s in trace.spans}
    participant_map = {p.label: p for p in participants}

    # Check if we have timestamps for timeline-based rendering
    has_timestamps = any(s.ts_start for s in trace.spans)

    if has_timestamps:
        return _extract_messages_timeline(trace, span_map, participant_map)
    else:
        return _extract_messages_legacy(trace, span_map, participant_map)


def _extract_messages_timeline(
    trace: Trace,
    span_map: dict[str, Span],
    participant_map: dict[str, ParticipantInfo],
) -> list[MessageInfo]:
    """Extract messages using timestamp ordering (request + response arrows)."""
    # Build list of events (request at ts_start, response at ts_end)
    events: list[tuple[str, bool, Span]] = []  # (timestamp, is_response, span)

    for span in trace.spans:
        # Request event at ts_start
        if span.ts_start:
            events.append((span.ts_start, False, span))

        # Response event at ts_end (always create to show success/error indicators)
        if span.ts_end:
            events.append((span.ts_end, True, span))

    # Sort by timestamp, then responses after requests at same time
    events.sort(key=lambda e: (e[0], 1 if e[1] else 0))

    # Convert to MessageInfo objects
    messages: list[MessageInfo] = []
    y_pos = PARTICIPANT_HEADER_HEIGHT + 40

    for timestamp, is_response, span in events:
        # Determine caller (parent) and callee (this span)
        if span.parent_span_id and span.parent_span_id in span_map:
            caller_comp = span_map[span.parent_span_id].component
        else:
            caller_comp = span.component

        callee_comp = span.component

        caller = participant_map.get(caller_comp)
        callee = participant_map.get(callee_comp)

        if not caller or not callee:
            continue

        if is_response:
            # Response: arrow goes from callee back to caller
            messages.append(
                MessageInfo(
                    span_id=span.span_id,
                    span=span,
                    from_participant=callee,
                    to_participant=caller,
                    operation=f"{span.operation} response",
                    attempt=span.attempt or 1,
                    latency_ms=_compute_latency(span),
                    has_error=span.error is not None,
                    y_position=y_pos,
                    request=None,
                    response=span.response,
                    error=span.error,
                    is_response=True,
                    timestamp=timestamp,
                )
            )
        else:
            # Request: arrow goes from caller to callee
            messages.append(
                MessageInfo(
                    span_id=span.span_id,
                    span=span,
                    from_participant=caller,
                    to_participant=callee,
                    operation=span.operation,
                    attempt=span.attempt or 1,
                    latency_ms=None,  # Latency shown on response
                    has_error=False,  # Error shown on response
                    y_position=y_pos,
                    request=span.request,
                    response=None,
                    error=None,
                    is_response=False,
                    timestamp=timestamp,
                )
            )

        y_pos += MESSAGE_HEIGHT

    return messages


def _extract_messages_legacy(
    trace: Trace,
    span_map: dict[str, Span],
    participant_map: dict[str, ParticipantInfo],
) -> list[MessageInfo]:
    """Extract messages in span order (legacy, no timestamps)."""
    messages: list[MessageInfo] = []
    y_pos = PARTICIPANT_HEADER_HEIGHT + 40

    for span in trace.spans:
        from_comp = span.component
        from_participant = participant_map.get(from_comp)

        if not from_participant:
            continue

        # Determine target participant
        if span.parent_span_id and span.parent_span_id in span_map:
            parent = span_map[span.parent_span_id]
            to_comp = parent.component
        else:
            to_comp = from_comp  # Self-call for root spans

        to_participant = participant_map.get(to_comp, from_participant)

        messages.append(
            MessageInfo(
                span_id=span.span_id,
                span=span,
                from_participant=from_participant,
                to_participant=to_participant,
                operation=span.operation,
                attempt=span.attempt or 1,
                latency_ms=_compute_latency(span),
                has_error=span.error is not None,
                y_position=y_pos,
                request=span.request,
                response=span.response,
                error=span.error,
            )
        )
        y_pos += MESSAGE_HEIGHT

    return messages


def _build_span_tree(trace: Trace) -> dict[str, list[str]]:
    """Build parent → children mapping."""
    tree: dict[str, list[str]] = {}
    for span in trace.spans:
        if span.parent_span_id:
            if span.parent_span_id not in tree:
                tree[span.parent_span_id] = []
            tree[span.parent_span_id].append(span.span_id)
    return tree


def _get_ancestors(span_id: str, trace: Trace) -> list[str]:
    """Get all ancestor span IDs."""
    span_map = {s.span_id: s for s in trace.spans}
    ancestors = []
    current = span_map.get(span_id)
    while current and current.parent_span_id:
        ancestors.append(current.parent_span_id)
        current = span_map.get(current.parent_span_id)
    return ancestors


def _get_descendants(span_id: str, tree: dict[str, list[str]]) -> list[str]:
    """Get all descendant span IDs."""
    descendants = []
    to_visit = tree.get(span_id, [])[:]
    while to_visit:
        child = to_visit.pop(0)
        descendants.append(child)
        to_visit.extend(tree.get(child, []))
    return descendants


def _render_svg_participant(p: ParticipantInfo, height: int) -> str:
    """Render SVG for a single participant header and lifeline."""
    x = p.x_center
    return f'''
    <g class="participant" data-participant="{p.id}">
        <!-- Lifeline -->
        <line x1="{x}" y1="{PARTICIPANT_HEADER_HEIGHT}" x2="{x}" y2="{height - 20}"
              class="lifeline" stroke="{p.color['stroke']}" stroke-width="2" stroke-dasharray="5,5"/>
        <!-- Header box -->
        <rect x="{x - PARTICIPANT_WIDTH//2 + 10}" y="10" width="{PARTICIPANT_WIDTH - 20}" height="{PARTICIPANT_HEADER_HEIGHT - 20}"
              rx="8" fill="{p.color['bg']}" class="participant-box"/>
        <!-- Icon -->
        <text x="{x}" y="35" text-anchor="middle" class="participant-icon" fill="{p.color['text']}">{p.color['icon']}</text>
        <!-- Label -->
        <text x="{x}" y="60" text-anchor="middle" class="participant-label" fill="{p.color['text']}">{html.escape(p.label)}</text>
    </g>'''


def _render_svg_message(msg: MessageInfo, span_tree: dict[str, list[str]]) -> str:
    """Render SVG for a message arrow.

    With timeline-based ordering, each message is either:
    - A request arrow (solid): caller → callee
    - A response arrow (dashed): callee → caller

    Legacy mode (no timestamps): renders both call and return in one message.
    """
    from_x = msg.from_participant.x_center
    to_x = msg.to_participant.x_center
    y = msg.y_position

    is_self = from_x == to_x
    is_error = msg.has_error
    is_retry = msg.attempt > 1
    is_response = getattr(msg, 'is_response', False)
    is_async = getattr(msg.span, 'is_async', False) or getattr(msg.span, 'is_one_way', False)

    error_class = "error" if is_error else ""
    # Position retry badge on the left side, only show on request arrows (not response)
    # Place it at x=30 (left margin) at the message's y position
    retry_badge = f'<text x="30" y="{y + 4}" class="retry-badge">🔄 retry {msg.attempt - 1}</text>' if is_retry and not is_response else ""

    latency_text = f"{msg.latency_ms:.0f}ms" if msg.latency_ms else ""

    # Status indicator (only on response arrows or legacy mode)
    status_icon = "❌" if is_error else "✅" if is_response or not msg.timestamp else ""
    status_class = "status-error" if is_error else "status-success"

    span_data = html.escape(json.dumps({
        "span_id": msg.span_id,
        "operation": msg.operation,
        "component": msg.from_participant.label,
        "target": msg.to_participant.label,
        "latency_ms": msg.latency_ms,
        "attempt": msg.attempt,
        "has_error": is_error,
        "is_async": is_async,
        "is_response": is_response,
        "request": msg.request,
        "response": msg.response,
        "error": msg.error,
    }))

    # Timeline mode: separate request and response arrows
    if msg.timestamp is not None:
        return _render_svg_message_timeline(
            msg, from_x, to_x, y, is_self, is_error, is_response,
            retry_badge, latency_text, status_icon, status_class, span_data
        )

    # Legacy mode: combined call + return arrows
    return _render_svg_message_legacy(
        msg, from_x, to_x, y, is_self, is_error, is_async,
        retry_badge, latency_text, status_icon, status_class, span_data
    )


def _render_svg_message_timeline(
    msg: MessageInfo,
    from_x: int,
    to_x: int,
    y: int,
    is_self: bool,
    is_error: bool,
    is_response: bool,
    retry_badge: str,
    latency_text: str,
    status_icon: str,
    status_class: str,
    span_data: str,
) -> str:
    """Render a single arrow (request or response) in timeline mode."""
    error_class = "error" if is_error else ""
    response_class = "response-message" if is_response else "request-message"
    arrow_marker = "url(#arrowhead-return)" if is_response else "url(#arrowhead)"
    dash_array = 'stroke-dasharray="4,2"' if is_response else ""

    if is_self:
        # Self-call: use entry/exit indicators instead of curved arrows
        # Entry: downward arrow into activation bar
        # Exit: checkmark or X status indicator
        if is_response:
            # Exit/return - arrow from lifeline extending LEFT (mirror of entry)
            return f'''
        <g class="message self-message {error_class} {response_class}" data-span-id="{msg.span_id}" data-span='{span_data}'>
            <!-- Exit indicator - arrow from lifeline to left -->
            <line x1="{from_x - 4}" y1="{y}" x2="{from_x - 50}" y2="{y}"
                  stroke="currentColor" stroke-width="2" {dash_array} marker-end="{arrow_marker}"/>
            <!-- Status indicator and latency on left -->
            <text x="{from_x - 58}" y="{y + 4}" text-anchor="end" class="status-indicator {status_class}">{status_icon} {latency_text}</text>
        </g>'''
        else:
            # Entry/request - show operation label with entry arrow
            return f'''
        <g class="message self-message {error_class} {response_class}" data-span-id="{msg.span_id}" data-span='{span_data}'>
            <!-- Entry indicator - short horizontal line with downward arrow -->
            <line x1="{from_x - 50}" y1="{y}" x2="{from_x - 4}" y2="{y}"
                  stroke="currentColor" stroke-width="2" marker-end="{arrow_marker}"/>
            <!-- Entry marker -->
            <text x="{from_x - 58}" y="{y + 4}" text-anchor="end" class="message-label">▶ {html.escape(msg.operation)}</text>
            {retry_badge}
        </g>'''
    else:
        # Normal arrow between participants
        direction = 1 if to_x > from_x else -1
        mid_x = (from_x + to_x) // 2
        arrow_offset = 4 * direction  # Reduced offset for closer connection to lifelines

        return f'''
        <g class="message {error_class} {response_class}" data-span-id="{msg.span_id}" data-span='{span_data}'>
            <line x1="{from_x + arrow_offset}" y1="{y}" x2="{to_x - arrow_offset}" y2="{y}"
                  stroke="currentColor" stroke-width="2" {dash_array} marker-end="{arrow_marker}"/>
            <text x="{mid_x}" y="{y - 8}" text-anchor="middle" class="message-label">{html.escape(msg.operation)}</text>
            {f'<text x="{mid_x}" y="{y + 15}" text-anchor="middle" class="message-latency">{latency_text}</text>' if latency_text else ''}
            {f'<text x="{to_x}" y="{y + 4}" text-anchor="middle" class="status-indicator {status_class}">{status_icon}</text>' if status_icon else ''}
            {retry_badge}
        </g>'''


def _render_svg_message_legacy(
    msg: MessageInfo,
    from_x: int,
    to_x: int,
    y: int,
    is_self: bool,
    is_error: bool,
    is_async: bool,
    retry_badge: str,
    latency_text: str,
    status_icon: str,
    status_class: str,
    span_data: str,
) -> str:
    """Render combined call + return arrows (legacy mode, no timestamps)."""
    error_class = "error" if is_error else ""

    if is_self:
        # Self-call: entry/exit with activation bar instead of curved arrows
        activation_height = 30
        return f'''
        <g class="message self-message {error_class}" data-span-id="{msg.span_id}" data-span='{span_data}'>
            <!-- Entry arrow from left -->
            <line x1="{from_x - 50}" y1="{y}" x2="{from_x - 4}" y2="{y}"
                  stroke="currentColor" stroke-width="2" marker-end="url(#arrowhead)"/>
            <!-- Entry label -->
            <text x="{from_x - 58}" y="{y + 4}" text-anchor="end" class="message-label">▶ {html.escape(msg.operation)}</text>
            <!-- Activation box -->
            <rect x="{from_x - 8}" y="{y}" width="16" height="{activation_height}" 
                  fill="var(--panel-bg)" stroke="currentColor" stroke-width="1" class="activation-box"/>
            <!-- Status indicator inside box -->
            <text x="{from_x}" y="{y + activation_height // 2 + 4}" text-anchor="middle" class="status-indicator {status_class}">{status_icon}</text>
            <!-- Exit arrow to left (mirror of entry) -->
            <line x1="{from_x - 4}" y1="{y + activation_height}" x2="{from_x - 50}" y2="{y + activation_height}"
                  stroke="currentColor" stroke-width="2" stroke-dasharray="4,2" marker-end="url(#arrowhead-return)"/>
            <!-- Latency on exit -->
            <text x="{from_x - 58}" y="{y + activation_height + 4}" text-anchor="end" class="message-latency">◀ {latency_text}</text>
            {retry_badge}
        </g>'''
    else:
        # Normal arrow with call/return pair
        direction = 1 if to_x > from_x else -1
        mid_x = (from_x + to_x) // 2
        arrow_offset = 4 * direction  # Reduced offset for closer connection to lifelines
        activation_height = 25
        return_y = y + activation_height

        # Return arrow (unless async)
        return_arrow = "" if is_async else f'''
            <!-- Return arrow -->
            <line x1="{to_x}" y1="{return_y}" x2="{from_x + arrow_offset}" y2="{return_y}"
                  stroke="currentColor" stroke-width="2" stroke-dasharray="4,2" marker-end="url(#arrowhead-return)"/>'''

        return f'''
        <g class="message {error_class}" data-span-id="{msg.span_id}" data-span='{span_data}'>
            <!-- Call arrow -->
            <line x1="{from_x}" y1="{y}" x2="{to_x - arrow_offset}" y2="{y}"
                  stroke="currentColor" stroke-width="2" marker-end="url(#arrowhead)"/>
            <!-- Activation box on callee -->
            <rect x="{to_x - 8}" y="{y - 2}" width="16" height="{activation_height + 4}" 
                  fill="var(--panel-bg)" stroke="currentColor" stroke-width="1" class="activation-box"/>
            <!-- Status indicator -->
            <text x="{to_x}" y="{y + activation_height // 2 + 4}" text-anchor="middle" class="status-indicator {status_class}">{status_icon}</text>
            {return_arrow}
            <!-- Labels -->
            <text x="{mid_x}" y="{y - 8}" text-anchor="middle" class="message-label">{html.escape(msg.operation)}</text>
            <text x="{mid_x}" y="{return_y + 15}" text-anchor="middle" class="message-latency">{latency_text}</text>
            {retry_badge}
        </g>'''


def render_trace_viewer(
    trace: Trace,
    title: str = "Trace Viewer",
) -> str:
    """Render enhanced interactive trace viewer.

    Args:
        trace: The trace to render.
        title: Title for the viewer.

    Returns:
        Complete HTML document as string.
    """
    participants = _extract_participants(trace)
    messages = _extract_messages(trace, participants)
    span_tree = _build_span_tree(trace)

    # Calculate SVG dimensions
    svg_width = PADDING * 2 + len(participants) * (PARTICIPANT_WIDTH + PARTICIPANT_GAP)
    svg_height = PARTICIPANT_HEADER_HEIGHT + len(messages) * MESSAGE_HEIGHT + 100

    # Render SVG elements
    participant_svg = "\n".join(_render_svg_participant(p, svg_height) for p in participants)
    message_svg = "\n".join(_render_svg_message(m, span_tree) for m in messages)

    # Build spans data for search/filter AND details panel display
    spans_json = json.dumps([
        {
            "span_id": m.span_id,
            "operation": m.operation,
            "component": m.from_participant.label,
            "target": m.to_participant.label,
            "latency_ms": m.latency_ms,
            "attempt": m.attempt,
            "has_error": m.has_error,
            "request": m.request,
            "response": m.response,
            "error": m.error,
        }
        for m in messages
    ])

    # Load vendored JS
    svg_pan_zoom_js = _load_vendor_js("svg-pan-zoom.min.js")
    fuse_js = _load_vendor_js("fuse.min.js")

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <style>
        :root {{
            --bg-color: #ffffff;
            --text-color: #1f2937;
            --border-color: #e5e7eb;
            --panel-bg: #f9fafb;
            --accent-color: #3b82f6;
            --error-color: #ef4444;
            --success-color: #10b981;
            --muted-color: #6b7280;
        }}
        
        [data-theme="dark"] {{
            --bg-color: #1f2937;
            --text-color: #f9fafb;
            --border-color: #374151;
            --panel-bg: #111827;
            --accent-color: #60a5fa;
            --error-color: #f87171;
            --success-color: #34d399;
            --muted-color: #9ca3af;
        }}
        
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-color);
            color: var(--text-color);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}
        
        /* Header */
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border-color);
            background: var(--panel-bg);
            flex-shrink: 0;
        }}
        
        .header h1 {{
            font-size: 1.25rem;
            font-weight: 600;
        }}
        
        .header-controls {{
            display: flex;
            gap: 0.5rem;
            align-items: center;
        }}
        
        /* Search */
        .search-container {{
            position: relative;
        }}
        
        .search-input {{
            padding: 0.5rem 2rem 0.5rem 0.75rem;
            border: 1px solid var(--border-color);
            border-radius: 0.375rem;
            background: var(--bg-color);
            color: var(--text-color);
            width: 250px;
            font-size: 0.875rem;
        }}
        
        .search-input:focus {{
            outline: none;
            border-color: var(--accent-color);
            box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
        }}
        
        .search-shortcut {{
            position: absolute;
            right: 0.5rem;
            top: 50%;
            transform: translateY(-50%);
            font-size: 0.75rem;
            color: var(--muted-color);
            background: var(--panel-bg);
            padding: 0.125rem 0.25rem;
            border-radius: 0.25rem;
            border: 1px solid var(--border-color);
        }}
        
        /* Filters */
        .filters {{
            display: flex;
            gap: 0.5rem;
        }}
        
        .filter-btn {{
            padding: 0.375rem 0.75rem;
            border: 1px solid var(--border-color);
            border-radius: 0.375rem;
            background: var(--bg-color);
            color: var(--text-color);
            font-size: 0.75rem;
            cursor: pointer;
            transition: all 0.15s;
        }}
        
        .filter-btn:hover {{
            border-color: var(--accent-color);
        }}
        
        .filter-btn.active {{
            background: var(--accent-color);
            color: white;
            border-color: var(--accent-color);
        }}
        
        .theme-btn {{
            padding: 0.375rem 0.75rem;
            border: 1px solid var(--border-color);
            border-radius: 0.375rem;
            background: var(--bg-color);
            color: var(--text-color);
            font-size: 0.875rem;
            cursor: pointer;
        }}
        
        /* Main content */
        .main-content {{
            display: flex;
            flex: 1;
            overflow: hidden;
        }}
        
        /* SVG container */
        .svg-container {{
            flex: 1;
            overflow: hidden;
            background: var(--bg-color);
            position: relative;
        }}
        
        .svg-container svg {{
            width: 100%;
            height: 100%;
            cursor: grab;
        }}
        
        .svg-container svg:active {{
            cursor: grabbing;
        }}
        
        /* Allow pointer events on interactive SVG children */
        .svg-container svg .message {{
            pointer-events: all;
            cursor: pointer;
        }}
        
        /* SVG styles */
        .lifeline {{
            opacity: 0.5;
            pointer-events: none;
        }}
        
        .participant-box {{
            filter: drop-shadow(0 1px 2px rgba(0,0,0,0.1));
        }}
        
        .participant-icon {{
            font-size: 1.25rem;
        }}
        
        .participant-label {{
            font-size: 0.75rem;
            font-weight: 500;
        }}
        
        .message {{
            cursor: pointer;
            color: var(--text-color);
            transition: opacity 0.15s;
        }}
        
        .message:hover {{
            opacity: 0.8;
        }}
        
        .message.selected {{
            color: var(--accent-color);
        }}
        
        .message.dimmed {{
            opacity: 0.15;
            filter: grayscale(100%);
        }}
        
        .message.highlighted {{
            color: var(--accent-color);
        }}
        
        .message.error {{
            color: var(--error-color);
        }}
        
        .message-label {{
            font-size: 0.75rem;
            font-weight: 500;
        }}
        
        .message-latency {{
            font-size: 0.625rem;
            fill: var(--muted-color);
        }}
        
        .retry-badge {{
            font-size: 0.625rem;
            fill: #f59e0b;
            font-weight: 600;
        }}
        
        /* Activation box and status indicators */
        .activation-box {{
            fill: var(--panel-bg);
            stroke: var(--text-color);
        }}
        
        .status-indicator {{
            font-size: 0.75rem;
        }}
        
        .status-success {{
            fill: var(--success-color);
        }}
        
        .status-error {{
            fill: var(--error-color);
        }}
        
        .hidden {{
            display: none !important;
        }}
        
        .search-match {{
            filter: drop-shadow(0 0 4px var(--accent-color));
        }}
        
        .search-match .message-arrow {{
            stroke-width: 3;
            stroke: var(--accent-color) !important;
        }}
        
        .search-match .message-label {{
            font-weight: bold;
            fill: var(--accent-color);
            font-size: 0.85rem;
        }}
        
        /* No results indicator */
        #no-results {{
            display: none;
            position: absolute;
            top: 50%;
            left: calc(50% - 200px);  /* Account for potential details panel */
            transform: translate(-50%, -50%);
            background: var(--panel-bg);
            border: 2px solid var(--accent-color);
            border-radius: 12px;
            padding: 24px 40px;
            flex-direction: column;
            align-items: center;
            gap: 12px;
            z-index: 1000;
            box-shadow: 0 8px 24px rgba(0,0,0,0.25);
            pointer-events: none;
        }}
        
        .no-results-icon {{
            font-size: 3rem;
            opacity: 0.8;
        }}
        
        .no-results-text {{
            color: var(--text-color);
            font-size: 1.1rem;
            font-weight: 500;
        }}
        
        /* Details panel */
        .details-panel {{
            width: 400px;
            border-left: 1px solid var(--border-color);
            background: var(--panel-bg);
            overflow-y: auto;
            flex-shrink: 0;
            transition: width 0.2s;
        }}
        
        .details-panel.collapsed {{
            width: 0;
            border-left: none;
        }}
        
        .details-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border-color);
            position: sticky;
            top: 0;
            background: var(--panel-bg);
        }}
        
        .details-title {{
            font-weight: 600;
            font-size: 0.875rem;
        }}
        
        .details-close {{
            background: none;
            border: none;
            color: var(--muted-color);
            cursor: pointer;
            font-size: 1.25rem;
            padding: 0.25rem;
        }}
        
        .details-content {{
            padding: 1rem;
        }}
        
        .detail-section {{
            margin-bottom: 1rem;
        }}
        
        .detail-label {{
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--muted-color);
            text-transform: uppercase;
            margin-bottom: 0.25rem;
        }}
        
        .detail-value {{
            font-size: 0.875rem;
        }}
        
        .detail-value.error {{
            color: var(--error-color);
        }}
        
        .detail-value.success {{
            color: var(--success-color);
        }}
        
        .json-viewer {{
            background: var(--bg-color);
            border: 1px solid var(--border-color);
            border-radius: 0.375rem;
            padding: 0.75rem;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.75rem;
            overflow-x: auto;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 300px;
            overflow-y: auto;
            margin: 0;
        }}
        
        /* Payload container */
        .payload-container {{
            position: relative;
        }}
        
        .payload-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.5rem;
        }}
        
        .payload-meta {{
            font-size: 0.625rem;
            color: var(--muted-color);
        }}
        
        .payload-size {{
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 0.25rem;
            padding: 0.125rem 0.375rem;
        }}
        
        .payload-truncated {{
            color: var(--error-color);
            font-weight: 600;
        }}
        
        .copy-btn {{
            background: var(--accent-color);
            color: white;
            border: none;
            border-radius: 0.25rem;
            padding: 0.25rem 0.5rem;
            font-size: 0.625rem;
            cursor: pointer;
            transition: opacity 0.15s;
        }}
        
        .copy-btn:hover {{
            opacity: 0.8;
        }}
        
        .copy-btn.copied {{
            background: var(--success-color);
        }}
        
        /* Stats bar */
        .stats-bar {{
            display: flex;
            gap: 1.5rem;
            padding: 0.5rem 1rem;
            border-top: 1px solid var(--border-color);
            background: var(--panel-bg);
            font-size: 0.75rem;
            flex-shrink: 0;
        }}
        
        .stat {{
            display: flex;
            gap: 0.25rem;
        }}
        
        .stat-label {{
            color: var(--muted-color);
        }}
        
        .stat-value {{
            font-weight: 600;
        }}
        
        /* Zoom controls */
        .zoom-controls {{
            position: absolute;
            bottom: 1rem;
            left: 1rem;
            display: flex;
            gap: 0.25rem;
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 0.375rem;
            padding: 0.25rem;
        }}
        
        .zoom-btn {{
            width: 2rem;
            height: 2rem;
            border: none;
            background: transparent;
            color: var(--text-color);
            cursor: pointer;
            border-radius: 0.25rem;
            font-size: 1rem;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .zoom-btn:hover {{
            background: var(--border-color);
        }}
        
        /* Keyboard hint */
        .keyboard-hint {{
            position: absolute;
            bottom: 1rem;
            right: 1rem;
            font-size: 0.625rem;
            color: var(--muted-color);
            background: var(--panel-bg);
            padding: 0.25rem 0.5rem;
            border-radius: 0.25rem;
            border: 1px solid var(--border-color);
        }}
        
        kbd {{
            background: var(--bg-color);
            border: 1px solid var(--border-color);
            border-radius: 0.25rem;
            padding: 0 0.25rem;
            font-family: inherit;
        }}
    </style>
</head>
<body>
    <header class="header">
        <h1>{html.escape(title)}</h1>
        <div class="header-controls">
            <div class="search-container">
                <input type="text" class="search-input" id="search" placeholder="Search spans...">
                <span class="search-shortcut">/</span>
            </div>
            <div class="filters">
                <button class="filter-btn" data-filter="errors" title="Show only errors">🔴 Errors</button>
                <button class="filter-btn" data-filter="retries" title="Show only retries">🔄 Retries</button>
            </div>
            <button class="theme-btn" onclick="toggleTheme()">🌙</button>
        </div>
    </header>
    
    <main class="main-content">
        <div class="svg-container">
            <div id="no-results">
                <span class="no-results-icon">🔍</span>
                <span class="no-results-text">No spans match the current filters</span>
            </div>
            <svg id="diagram" viewBox="0 0 {svg_width} {svg_height}" preserveAspectRatio="xMidYMid meet">
                <defs>
                    <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                        <polygon points="0 0, 10 3.5, 0 7" fill="currentColor"/>
                    </marker>
                    <marker id="arrowhead-return" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                        <polygon points="0 0, 10 3.5, 0 7" fill="currentColor"/>
                    </marker>
                </defs>
                <g class="svg-pan-zoom_viewport">
                    <g class="participants">
                        {participant_svg}
                    </g>
                    <g class="messages">
                        {message_svg}
                    </g>
                </g>
            </svg>
            <div class="zoom-controls">
                <button class="zoom-btn" onclick="panZoom.zoomIn()" title="Zoom in">+</button>
                <button class="zoom-btn" onclick="panZoom.zoomOut()" title="Zoom out">−</button>
                <button class="zoom-btn" onclick="panZoom.fit()" title="Fit to view">⊡</button>
                <button class="zoom-btn" onclick="panZoom.reset()" title="Reset">↺</button>
            </div>
            <div class="keyboard-hint">
                <kbd>/</kbd> search &nbsp; <kbd>Esc</kbd> clear &nbsp; <kbd>↑↓</kbd> navigate
            </div>
        </div>
        
        <aside class="details-panel collapsed" id="details-panel">
            <div class="details-header">
                <span class="details-title">Span Details</span>
                <button class="details-close" onclick="closeDetails()">×</button>
            </div>
            <div class="details-content" id="details-content">
                <!-- Populated by JS -->
            </div>
        </aside>
    </main>
    
    <footer class="stats-bar">
        <div class="stat">
            <span class="stat-label">Spans:</span>
            <span class="stat-value">{len(trace.spans)}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Participants:</span>
            <span class="stat-value">{len(participants)}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Errors:</span>
            <span class="stat-value" style="color: var(--error-color)">{sum(1 for m in messages if m.has_error)}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Retries:</span>
            <span class="stat-value" style="color: #f59e0b">{sum(1 for m in messages if m.attempt > 1)}</span>
        </div>
    </footer>
    
    <script>
    // Vendored svg-pan-zoom
    {svg_pan_zoom_js}
    </script>
    
    <script>
    // Vendored Fuse.js
    {fuse_js}
    </script>
    
    <script>
    // Initialize
    const spansData = {spans_json};
    let panZoom;
    let selectedSpanId = null;
    let fuse;
    let activeFilters = new Set();
    
    // Initialize pan-zoom
    document.addEventListener('DOMContentLoaded', function() {{
        panZoom = svgPanZoom('#diagram', {{
            zoomEnabled: true,
            controlIconsEnabled: false,
            fit: true,
            center: true,
            contain: false,
            minZoom: 0.1,
            maxZoom: 10,
            zoomScaleSensitivity: 0.3
        }});
        
        // Resize handler to re-center on window resize
        window.addEventListener('resize', function() {{
            panZoom.resize();
            panZoom.fit();
            panZoom.center();
        }});
        
        // Initialize Fuse for search
        fuse = new Fuse(spansData, {{
            keys: ['operation', 'component', 'span_id'],
            threshold: 0.2,
            includeScore: true,
            ignoreLocation: true
        }});
        
        // Setup event listeners
        setupEventListeners();
    }});
    
    function setupEventListeners() {{
        // Click on messages
        document.querySelectorAll('.message').forEach(el => {{
            el.addEventListener('click', function(e) {{
                e.stopPropagation();
                const spanId = this.dataset.spanId;
                selectSpan(spanId);
            }});
        }});
        
        // Click outside to deselect
        document.querySelector('.svg-container').addEventListener('click', function(e) {{
            if (e.target === this || e.target.tagName === 'svg') {{
                clearSelection();
            }}
        }});
        
        // Search input
        const searchInput = document.getElementById('search');
        searchInput.addEventListener('input', function() {{
            filterSpans();
        }});
        
        // Filter buttons
        document.querySelectorAll('.filter-btn').forEach(btn => {{
            btn.addEventListener('click', function() {{
                const filter = this.dataset.filter;
                if (activeFilters.has(filter)) {{
                    activeFilters.delete(filter);
                    this.classList.remove('active');
                }} else {{
                    activeFilters.add(filter);
                    this.classList.add('active');
                }}
                filterSpans();
            }});
        }});
        
        // Keyboard shortcuts
        document.addEventListener('keydown', function(e) {{
            if (e.key === '/') {{
                e.preventDefault();
                searchInput.focus();
            }} else if (e.key === 'Escape') {{
                searchInput.blur();
                searchInput.value = '';
                clearSelection();
                filterSpans();
            }} else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {{
                navigateSpans(e.key === 'ArrowDown' ? 1 : -1);
            }}
        }});
    }}
    
    function selectSpan(spanId) {{
        // Clear previous selection
        document.querySelectorAll('.message').forEach(el => {{
            el.classList.remove('selected', 'highlighted', 'dimmed');
        }});
        
        selectedSpanId = spanId;
        
        // Highlight selected
        const selected = document.querySelector(`[data-span-id="${{spanId}}"]`);
        if (selected) {{
            selected.classList.add('selected');
            
            // Dim others
            document.querySelectorAll('.message').forEach(el => {{
                if (el.dataset.spanId !== spanId) {{
                    el.classList.add('dimmed');
                }}
            }});
            
            // Show details panel
            showDetails(selected.dataset.span);
        }}
    }}
    
    function clearSelection() {{
        selectedSpanId = null;
        document.querySelectorAll('.message').forEach(el => {{
            el.classList.remove('selected', 'highlighted', 'dimmed');
        }});
        closeDetails();
    }}
    
    function showDetails(spanJson) {{
        const span = JSON.parse(spanJson);
        const panel = document.getElementById('details-panel');
        const content = document.getElementById('details-content');
        
        // In timeline mode, request and response are separate messages.
        // Merge all data for this span_id to show complete details.
        const allSpanData = spansData.filter(s => s.span_id === span.span_id);
        const mergedSpan = {{ ...span }};
        
        for (const s of allSpanData) {{
            if (s.request && !mergedSpan.request) mergedSpan.request = s.request;
            if (s.response && !mergedSpan.response) mergedSpan.response = s.response;
            if (s.error && !mergedSpan.error) mergedSpan.error = s.error;
            if (s.latency_ms && !mergedSpan.latency_ms) mergedSpan.latency_ms = s.latency_ms;
            if (s.has_error) mergedSpan.has_error = true;
        }}
        
        // Use clean operation name (remove " response" suffix for display)
        const displayOperation = mergedSpan.operation.replace(/ response$/, '');
        
        let html = `
            <div class="detail-section">
                <div class="detail-label">Operation</div>
                <div class="detail-value">${{escapeHtml(displayOperation)}}</div>
            </div>
            <div class="detail-section">
                <div class="detail-label">Component</div>
                <div class="detail-value">${{escapeHtml(mergedSpan.component)}}</div>
            </div>
            <div class="detail-section">
                <div class="detail-label">Target</div>
                <div class="detail-value">${{escapeHtml(mergedSpan.target || mergedSpan.component)}}</div>
            </div>
            <div class="detail-section">
                <div class="detail-label">Span ID</div>
                <div class="detail-value" style="font-family: monospace; font-size: 0.75rem;">${{escapeHtml(mergedSpan.span_id)}}</div>
            </div>
            <div class="detail-section">
                <div class="detail-label">Latency</div>
                <div class="detail-value">${{mergedSpan.latency_ms ? mergedSpan.latency_ms.toFixed(2) + ' ms' : 'N/A'}}</div>
            </div>
            <div class="detail-section">
                <div class="detail-label">Attempt</div>
                <div class="detail-value ${{mergedSpan.attempt > 1 ? 'error' : ''}}">${{mergedSpan.attempt}}</div>
            </div>
            <div class="detail-section">
                <div class="detail-label">Status</div>
                <div class="detail-value ${{mergedSpan.has_error ? 'error' : 'success'}}">${{mergedSpan.has_error ? '❌ Error' : '✅ Success'}}</div>
            </div>
        `;
        
        if (mergedSpan.request) {{
            html += renderPayloadSection('Request', mergedSpan.request, 'request');
        }}
        
        if (mergedSpan.response) {{
            html += renderPayloadSection('Response', mergedSpan.response, 'response');
        }}
        
        if (mergedSpan.error) {{
            html += renderPayloadSection('Error', mergedSpan.error, 'error', true);
        }}
        
        content.innerHTML = html;
        panel.classList.remove('collapsed');
    }}
    
    function closeDetails() {{
        document.getElementById('details-panel').classList.add('collapsed');
    }}
    
    function filterSpans() {{
        const searchTerm = document.getElementById('search').value.trim();
        let visibleSpanIds = new Set(spansData.map(s => s.span_id));
        let searchMatchIds = new Set();
        
        // Apply search filter - highlight matches, don't hide non-matches
        if (searchTerm) {{
            const results = fuse.search(searchTerm);
            searchMatchIds = new Set(results.map(r => r.item.span_id));
        }}
        
        // Apply active filters (these DO hide non-matching)
        if (activeFilters.has('errors')) {{
            const errorIds = new Set(spansData.filter(s => s.has_error).map(s => s.span_id));
            visibleSpanIds = new Set([...visibleSpanIds].filter(id => errorIds.has(id)));
        }}
        
        if (activeFilters.has('retries')) {{
            const retryIds = new Set(spansData.filter(s => s.attempt > 1).map(s => s.span_id));
            visibleSpanIds = new Set([...visibleSpanIds].filter(id => retryIds.has(id)));
        }}
        
        // Show/hide/highlight messages
        let visibleCount = 0;
        document.querySelectorAll('.message').forEach(el => {{
            const spanId = el.dataset.spanId;
            const isVisible = visibleSpanIds.has(spanId);
            const isSearchMatch = searchMatchIds.has(spanId);
            
            if (isVisible) {{
                el.classList.remove('hidden');
                visibleCount++;
                
                // Highlight search matches, dim non-matches when searching
                if (searchTerm) {{
                    if (isSearchMatch) {{
                        el.classList.add('search-match');
                        el.classList.remove('dimmed');
                    }} else {{
                        el.classList.remove('search-match');
                        el.classList.add('dimmed');
                    }}
                }} else {{
                    el.classList.remove('search-match', 'dimmed');
                }}
            }} else {{
                el.classList.add('hidden');
                el.classList.remove('search-match', 'dimmed');
            }}
        }});
        
        // Show/hide "no results" message
        const noResultsEl = document.getElementById('no-results');
        if (noResultsEl) {{
            if (visibleCount === 0 && (activeFilters.size > 0 || searchTerm)) {{
                noResultsEl.style.display = 'flex';
                const filterText = [];
                if (activeFilters.has('errors')) filterText.push('errors');
                if (activeFilters.has('retries')) filterText.push('retries');
                if (searchTerm) filterText.push(`"${{searchTerm}}"`);
                noResultsEl.querySelector('.no-results-text').textContent = 
                    `No spans match: ${{filterText.join(' + ')}}`;
            }} else {{
                noResultsEl.style.display = 'none';
            }}
        }}
    }}
    
    function navigateSpans(direction) {{
        const visible = Array.from(document.querySelectorAll('.message:not(.hidden)'));
        if (visible.length === 0) return;
        
        if (!selectedSpanId) {{
            selectSpan(visible[0].dataset.spanId);
            return;
        }}
        
        const currentIdx = visible.findIndex(el => el.dataset.spanId === selectedSpanId);
        const newIdx = Math.max(0, Math.min(visible.length - 1, currentIdx + direction));
        selectSpan(visible[newIdx].dataset.spanId);
    }}
    
    function toggleTheme() {{
        const body = document.body;
        const btn = document.querySelector('.theme-btn');
        if (body.getAttribute('data-theme') === 'dark') {{
            body.removeAttribute('data-theme');
            btn.textContent = '🌙';
        }} else {{
            body.setAttribute('data-theme', 'dark');
            btn.textContent = '☀️';
        }}
    }}
    
    // Payload rendering helpers
    const MAX_PAYLOAD_DISPLAY = 10000; // 10KB display limit
    
    function formatBytes(bytes) {{
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }}
    
    function renderPayloadSection(label, payload, id, isError = false) {{
        const jsonStr = JSON.stringify(payload, null, 2);
        const byteSize = new Blob([jsonStr]).size;
        const isTruncated = jsonStr.length > MAX_PAYLOAD_DISPLAY;
        const displayJson = isTruncated ? jsonStr.substring(0, MAX_PAYLOAD_DISPLAY) + '\\n... (truncated)' : jsonStr;
        
        const errorStyle = isError ? 'border-color: var(--error-color);' : '';
        const truncatedBadge = isTruncated ? '<span class="payload-truncated">TRUNCATED</span>' : '';
        
        // Store full JSON for copy
        window['__payload_' + id] = jsonStr;
        
        return `
            <div class="detail-section">
                <div class="payload-container">
                    <div class="payload-header">
                        <div class="detail-label">${{label}}</div>
                        <div class="payload-meta">
                            <span class="payload-size">${{formatBytes(byteSize)}}</span>
                            ${{truncatedBadge}}
                            <button class="copy-btn" onclick="copyPayload('${{id}}', this)">📋 Copy</button>
                        </div>
                    </div>
                    <pre class="json-viewer" style="${{errorStyle}}">${{escapeHtml(displayJson)}}</pre>
                </div>
            </div>
        `;
    }}
    
    function copyPayload(id, btn) {{
        const json = window['__payload_' + id];
        if (!json) return;
        
        navigator.clipboard.writeText(json).then(() => {{
            btn.classList.add('copied');
            btn.textContent = '✅ Copied!';
            setTimeout(() => {{
                btn.classList.remove('copied');
                btn.textContent = '📋 Copy';
            }}, 2000);
        }}).catch(err => {{
            // Fallback for older browsers
            const textarea = document.createElement('textarea');
            textarea.value = json;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            btn.classList.add('copied');
            btn.textContent = '✅ Copied!';
            setTimeout(() => {{
                btn.classList.remove('copied');
                btn.textContent = '📋 Copy';
            }}, 2000);
        }});
    }}
    
    function escapeHtml(str) {{
        if (typeof str !== 'string') return str;
        return str.replace(/&/g, '&amp;')
                  .replace(/</g, '&lt;')
                  .replace(/>/g, '&gt;')
                  .replace(/"/g, '&quot;');
    }}
    </script>
</body>
</html>'''


def render_mini_svg(
    trace: Trace,
    width: int = 200,
    height: int = 80,
) -> str:
    """Render a minimal SVG thumbnail of the trace.

    Args:
        trace: The trace to render.
        width: SVG width in pixels.
        height: SVG height in pixels.

    Returns:
        SVG string (not full HTML document).
    """
    participants = _extract_participants(trace)
    messages = _extract_messages(trace, participants)

    if not participants:
        return f'<svg width="{width}" height="{height}"></svg>'

    # Calculate scaling
    num_participants = len(participants)
    num_messages = len(messages)

    participant_spacing = width / (num_participants + 1)
    message_spacing = (height - 20) / max(num_messages, 1)

    # Render simplified elements
    participant_lines = []
    for i, p in enumerate(participants):
        x = participant_spacing * (i + 1)
        participant_lines.append(
            f'<line x1="{x}" y1="10" x2="{x}" y2="{height - 10}" '
            f'stroke="{p.color["bg"]}" stroke-width="2" opacity="0.6"/>'
        )
        participant_lines.append(
            f'<circle cx="{x}" cy="10" r="4" fill="{p.color["bg"]}"/>'
        )

    message_lines = []
    for i, m in enumerate(messages):
        from_x = participant_spacing * (m.from_participant.index + 1)
        to_x = participant_spacing * (m.to_participant.index + 1)
        y = 20 + i * message_spacing

        color = "#ef4444" if m.has_error else "#6b7280"

        if from_x == to_x:
            # Self-call: small arc
            message_lines.append(
                f'<path d="M {from_x} {y} Q {from_x + 15} {y + 5} {from_x} {y + 10}" '
                f'fill="none" stroke="{color}" stroke-width="1"/>'
            )
        else:
            message_lines.append(
                f'<line x1="{from_x}" y1="{y}" x2="{to_x}" y2="{y}" '
                f'stroke="{color}" stroke-width="1" marker-end="url(#mini-arrow)"/>'
            )

    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
    <defs>
        <marker id="mini-arrow" markerWidth="6" markerHeight="4" refX="5" refY="2" orient="auto">
            <polygon points="0 0, 6 2, 0 4" fill="#6b7280"/>
        </marker>
    </defs>
    {''.join(participant_lines)}
    {''.join(message_lines)}
</svg>'''
