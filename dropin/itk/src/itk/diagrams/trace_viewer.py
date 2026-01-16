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
    """Extract messages from trace spans."""
    messages: list[MessageInfo] = []
    span_map = {s.span_id: s for s in trace.spans}
    participant_map = {p.label: p for p in participants}

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
    """Render SVG for a message with call and return arrows.
    
    Visual structure:
    - Call arrow: caller → callee (solid)
    - Activation box: on callee lifeline during span duration
    - Status indicator: ✅ or ❌ on activation box
    - Return arrow: callee → caller (dashed, unless async/fire-and-forget)
    """
    from_x = msg.from_participant.x_center
    to_x = msg.to_participant.x_center
    y = msg.y_position
    
    is_self = from_x == to_x
    is_error = msg.has_error
    is_retry = msg.attempt > 1
    is_async = getattr(msg.span, 'is_async', False) or getattr(msg.span, 'is_one_way', False)
    
    error_class = "error" if is_error else ""
    retry_badge = f'<text x="{max(from_x, to_x) + 10}" y="{y - 20}" class="retry-badge">retry {msg.attempt}</text>' if is_retry else ""
    
    latency_text = f"{msg.latency_ms:.0f}ms" if msg.latency_ms else ""
    
    # Status indicator
    status_icon = "❌" if is_error else "✅"
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
        "request": msg.request,
        "response": msg.response,
        "error": msg.error,
    }))
    
    if is_self:
        # Self-call: curved arrow with activation box
        activation_height = 30
        return f'''
        <g class="message self-message {error_class}" data-span-id="{msg.span_id}" data-span='{span_data}'>
            <!-- Call arrow (curved out) -->
            <path d="M {from_x} {y} C {from_x + 50} {y}, {from_x + 50} {y}, {from_x + 50} {y + activation_height // 2}"
                  fill="none" stroke="currentColor" stroke-width="2" marker-end="url(#arrowhead)"/>
            <!-- Activation box -->
            <rect x="{from_x - 8}" y="{y}" width="16" height="{activation_height}" 
                  fill="var(--panel-bg)" stroke="currentColor" stroke-width="1" class="activation-box"/>
            <!-- Status indicator -->
            <text x="{from_x}" y="{y + activation_height // 2 + 4}" text-anchor="middle" class="status-indicator {status_class}">{status_icon}</text>
            <!-- Return arrow (curved back) -->
            <path d="M {from_x + 50} {y + activation_height // 2} C {from_x + 50} {y + activation_height}, {from_x + 50} {y + activation_height}, {from_x + 8} {y + activation_height}"
                  fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="4,2" marker-end="url(#arrowhead-return)"/>
            <!-- Labels -->
            <text x="{from_x + 60}" y="{y + 10}" class="message-label">{html.escape(msg.operation)}</text>
            <text x="{from_x + 60}" y="{y + 25}" class="message-latency">{latency_text}</text>
            {retry_badge}
        </g>'''
    else:
        # Normal arrow with call/return pair
        direction = 1 if to_x > from_x else -1
        mid_x = (from_x + to_x) // 2
        arrow_offset = 10 * direction
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
        
        /* SVG styles */
        .lifeline {{
            opacity: 0.5;
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
            opacity: 0.2;
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
            <svg id="diagram" viewBox="0 0 {svg_width} {svg_height}" preserveAspectRatio="xMidYMid meet">
                <defs>
                    <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                        <polygon points="0 0, 10 3.5, 0 7" fill="currentColor"/>
                    </marker>
                    <marker id="arrowhead-return" markerWidth="10" markerHeight="7" refX="1" refY="3.5" orient="auto">
                        <polygon points="10 0, 0 3.5, 10 7" fill="currentColor"/>
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
            minZoom: 0.1,
            maxZoom: 10,
            zoomScaleSensitivity: 0.3
        }});
        
        // Initialize Fuse for search
        fuse = new Fuse(spansData, {{
            keys: ['operation', 'component', 'span_id'],
            threshold: 0.4,
            includeScore: true
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
        
        let html = `
            <div class="detail-section">
                <div class="detail-label">Operation</div>
                <div class="detail-value">${{escapeHtml(span.operation)}}</div>
            </div>
            <div class="detail-section">
                <div class="detail-label">Component</div>
                <div class="detail-value">${{escapeHtml(span.component)}}</div>
            </div>
            <div class="detail-section">
                <div class="detail-label">Target</div>
                <div class="detail-value">${{escapeHtml(span.target || span.component)}}</div>
            </div>
            <div class="detail-section">
                <div class="detail-label">Span ID</div>
                <div class="detail-value" style="font-family: monospace; font-size: 0.75rem;">${{escapeHtml(span.span_id)}}</div>
            </div>
            <div class="detail-section">
                <div class="detail-label">Latency</div>
                <div class="detail-value">${{span.latency_ms ? span.latency_ms.toFixed(2) + ' ms' : 'N/A'}}</div>
            </div>
            <div class="detail-section">
                <div class="detail-label">Attempt</div>
                <div class="detail-value ${{span.attempt > 1 ? 'error' : ''}}">${{span.attempt}}</div>
            </div>
            <div class="detail-section">
                <div class="detail-label">Status</div>
                <div class="detail-value ${{span.has_error ? 'error' : 'success'}}">${{span.has_error ? '❌ Error' : '✅ Success'}}</div>
            </div>
        `;
        
        if (span.request) {{
            html += renderPayloadSection('Request', span.request, 'request');
        }}
        
        if (span.response) {{
            html += renderPayloadSection('Response', span.response, 'response');
        }}
        
        if (span.error) {{
            html += renderPayloadSection('Error', span.error, 'error', true);
        }}
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
        
        // Apply search filter
        if (searchTerm) {{
            const results = fuse.search(searchTerm);
            visibleSpanIds = new Set(results.map(r => r.item.span_id));
        }}
        
        // Apply active filters
        if (activeFilters.has('errors')) {{
            const errorIds = new Set(spansData.filter(s => s.has_error).map(s => s.span_id));
            visibleSpanIds = new Set([...visibleSpanIds].filter(id => errorIds.has(id)));
        }}
        
        if (activeFilters.has('retries')) {{
            const retryIds = new Set(spansData.filter(s => s.attempt > 1).map(s => s.span_id));
            visibleSpanIds = new Set([...visibleSpanIds].filter(id => retryIds.has(id)));
        }}
        
        // Show/hide messages
        document.querySelectorAll('.message').forEach(el => {{
            if (visibleSpanIds.has(el.dataset.spanId)) {{
                el.classList.remove('hidden');
            }} else {{
                el.classList.add('hidden');
            }}
        }});
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
