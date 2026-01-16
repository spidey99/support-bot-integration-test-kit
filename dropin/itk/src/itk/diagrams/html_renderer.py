"""HTML sequence diagram renderer with modern styling."""
from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from typing import Any

from itk.trace.trace_model import Trace
from itk.trace.span_model import Span


# Component type → color scheme
COMPONENT_COLORS: dict[str, dict[str, str]] = {
    "lambda": {"bg": "#ff9900", "text": "#000", "icon": "λ"},
    "agent": {"bg": "#00a4ef", "text": "#fff", "icon": "🤖"},
    "model": {"bg": "#8b5cf6", "text": "#fff", "icon": "🧠"},
    "sqs": {"bg": "#ff4f8b", "text": "#fff", "icon": "📨"},
    "entrypoint": {"bg": "#10b981", "text": "#fff", "icon": "▶"},
    "bedrock": {"bg": "#8b5cf6", "text": "#fff", "icon": "🪨"},
    "default": {"bg": "#6b7280", "text": "#fff", "icon": "●"},
}


@dataclass
class ParticipantInfo:
    """Info about a participant in the sequence diagram."""
    
    id: str
    label: str
    component_type: str
    color: dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        if not self.color:
            self.color = COMPONENT_COLORS.get(
                self.component_type, COMPONENT_COLORS["default"]
            )


@dataclass
class MessageInfo:
    """Info about a message/arrow in the sequence diagram."""
    
    span_id: str
    from_participant: str
    to_participant: str
    operation: str
    attempt: int
    latency_ms: float | None
    has_error: bool
    request: dict[str, Any] | None
    response: dict[str, Any] | None
    error: dict[str, Any] | None


def _get_component_type(component: str) -> str:
    """Extract component type from component string like 'lambda:handler'."""
    if ":" in component:
        return component.split(":")[0].lower()
    return component.lower()


def _safe_id(s: str) -> str:
    """Convert string to safe HTML id."""
    return s.replace(":", "_").replace("-", "_").replace(".", "_")


def _compute_latency(span: Span) -> float | None:
    """Compute latency in ms from span timestamps."""
    if not span.ts_start or not span.ts_end:
        return None
    try:
        from datetime import datetime
        
        def parse_ts(ts: str) -> datetime:
            # Handle ISO format with or without Z
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
    """Extract unique participants from trace spans."""
    seen: dict[str, ParticipantInfo] = {}
    
    for span in trace.spans:
        comp = span.component
        if comp not in seen:
            comp_type = _get_component_type(comp)
            seen[comp] = ParticipantInfo(
                id=_safe_id(comp),
                label=comp,
                component_type=comp_type,
            )
    
    return list(seen.values())


def _extract_messages(trace: Trace, participants: list[ParticipantInfo]) -> list[MessageInfo]:
    """Extract messages from trace spans."""
    messages: list[MessageInfo] = []
    span_map = {s.span_id: s for s in trace.spans}
    participant_map = {p.label: p for p in participants}
    
    for span in trace.spans:
        from_comp = span.component
        
        # Determine target participant
        if span.parent_span_id and span.parent_span_id in span_map:
            parent = span_map[span.parent_span_id]
            to_comp = parent.component
        else:
            to_comp = from_comp  # Self-call for root spans
        
        messages.append(MessageInfo(
            span_id=span.span_id,
            from_participant=participant_map[from_comp].id if from_comp in participant_map else _safe_id(from_comp),
            to_participant=participant_map[to_comp].id if to_comp in participant_map else _safe_id(to_comp),
            operation=span.operation,
            attempt=span.attempt or 1,
            latency_ms=_compute_latency(span),
            has_error=span.error is not None,
            request=span.request,
            response=span.response,
            error=span.error,
        ))
    
    return messages


def _format_json_preview(data: dict[str, Any] | None, max_len: int = 100) -> str:
    """Format JSON for inline preview."""
    if not data:
        return ""
    try:
        text = json.dumps(data, indent=2)
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text
    except Exception:
        return str(data)[:max_len]


def render_html_sequence(
    trace: Trace,
    title: str = "Sequence Diagram",
    include_payloads: bool = True,
) -> str:
    """Render trace as an interactive HTML sequence diagram.
    
    Args:
        trace: The trace to render.
        title: Title for the diagram.
        include_payloads: Whether to include collapsible payload sections.
        
    Returns:
        Complete HTML document as string.
    """
    participants = _extract_participants(trace)
    messages = _extract_messages(trace, participants)
    
    # Build participant headers
    participant_html = []
    for p in participants:
        participant_html.append(f'''
        <div class="participant" style="--participant-bg: {p.color['bg']}; --participant-text: {p.color['text']};">
            <div class="participant-icon">{p.color['icon']}</div>
            <div class="participant-label">{html.escape(p.label)}</div>
            <div class="participant-line"></div>
        </div>''')
    
    # Build messages
    message_html = []
    participant_ids = [p.id for p in participants]
    
    for msg in messages:
        from_idx = participant_ids.index(msg.from_participant) if msg.from_participant in participant_ids else 0
        to_idx = participant_ids.index(msg.to_participant) if msg.to_participant in participant_ids else 0
        
        is_self = from_idx == to_idx
        direction = "right" if to_idx >= from_idx else "left"
        span_width = abs(to_idx - from_idx) + 1
        start_col = min(from_idx, to_idx) + 1
        
        latency_text = f"{msg.latency_ms:.0f}ms" if msg.latency_ms else ""
        error_class = "error" if msg.has_error else ""
        retry_badge = f'<span class="retry-badge">retry {msg.attempt - 1}</span>' if msg.attempt > 1 else ""
        
        payload_section = ""
        if include_payloads and (msg.request or msg.response or msg.error):
            payload_items = []
            if msg.request:
                payload_items.append(f'''
                <div class="payload-item">
                    <div class="payload-label">Request</div>
                    <pre class="payload-content">{html.escape(_format_json_preview(msg.request, 500))}</pre>
                </div>''')
            if msg.response:
                payload_items.append(f'''
                <div class="payload-item">
                    <div class="payload-label">Response</div>
                    <pre class="payload-content">{html.escape(_format_json_preview(msg.response, 500))}</pre>
                </div>''')
            if msg.error:
                payload_items.append(f'''
                <div class="payload-item error">
                    <div class="payload-label">Error</div>
                    <pre class="payload-content">{html.escape(_format_json_preview(msg.error, 500))}</pre>
                </div>''')
            
            payload_section = f'''
            <details class="payload-details">
                <summary>View Payloads</summary>
                <div class="payload-container">
                    {''.join(payload_items)}
                </div>
            </details>'''
        
        if is_self:
            message_html.append(f'''
            <div class="message self-message {error_class}" style="--start-col: {start_col};">
                <div class="message-content">
                    <div class="message-label">
                        <span class="operation">{html.escape(msg.operation)}</span>
                        {retry_badge}
                        <span class="latency">{latency_text}</span>
                    </div>
                    <div class="self-arrow"></div>
                </div>
                {payload_section}
            </div>''')
        else:
            message_html.append(f'''
            <div class="message {direction} {error_class}" style="--start-col: {start_col}; --span-width: {span_width};">
                <div class="message-content">
                    <div class="message-label">
                        <span class="operation">{html.escape(msg.operation)}</span>
                        {retry_badge}
                        <span class="latency">{latency_text}</span>
                    </div>
                    <div class="arrow {direction}"></div>
                </div>
                {payload_section}
            </div>''')
    
    num_participants = len(participants)
    
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
            --line-color: #d1d5db;
            --arrow-color: #3b82f6;
            --error-color: #ef4444;
            --success-color: #10b981;
            --code-bg: #f3f4f6;
            --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}
        
        [data-theme="dark"] {{
            --bg-color: #1f2937;
            --text-color: #f9fafb;
            --border-color: #374151;
            --line-color: #4b5563;
            --code-bg: #374151;
        }}
        
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: var(--bg-color);
            color: var(--text-color);
            line-height: 1.5;
            padding: 2rem;
            min-height: 100vh;
        }}
        
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border-color);
        }}
        
        h1 {{
            font-size: 1.5rem;
            font-weight: 600;
        }}
        
        .controls {{
            display: flex;
            gap: 1rem;
            align-items: center;
        }}
        
        .theme-toggle {{
            background: var(--code-bg);
            border: 1px solid var(--border-color);
            border-radius: 9999px;
            padding: 0.5rem 1rem;
            cursor: pointer;
            font-size: 0.875rem;
            color: var(--text-color);
            transition: all 0.2s;
        }}
        
        .theme-toggle:hover {{
            border-color: var(--arrow-color);
        }}
        
        .zoom-controls {{
            display: flex;
            gap: 0.25rem;
        }}
        
        .zoom-btn {{
            background: var(--code-bg);
            border: 1px solid var(--border-color);
            border-radius: 0.375rem;
            padding: 0.5rem 0.75rem;
            cursor: pointer;
            font-size: 1rem;
            color: var(--text-color);
            transition: all 0.2s;
        }}
        
        .zoom-btn:hover {{
            border-color: var(--arrow-color);
        }}
        
        .diagram-container {{
            overflow-x: auto;
            padding: 1rem 0;
        }}
        
        .diagram {{
            display: flex;
            flex-direction: column;
            min-width: max-content;
            transform-origin: top left;
            transition: transform 0.2s ease;
        }}
        
        .participants {{
            display: grid;
            grid-template-columns: repeat({num_participants}, minmax(150px, 1fr));
            gap: 0;  /* No gap - lifelines align with grid columns */
            margin-bottom: 1rem;
        }}
        
        .participant {{
            display: flex;
            flex-direction: column;
            align-items: center;
            position: relative;
            padding: 0 0.5rem;
        }}
        
        .participant-icon {{
            width: 3rem;
            height: 3rem;
            border-radius: 0.75rem;
            background: var(--participant-bg);
            color: var(--participant-text);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.25rem;
            box-shadow: var(--shadow);
            margin-bottom: 0.5rem;
        }}
        
        .participant-label {{
            font-size: 0.75rem;
            font-weight: 500;
            text-align: center;
            max-width: 140px;
            word-break: break-word;
        }}
        
        .participant-line {{
            position: absolute;
            top: 5rem;
            bottom: -1000px;
            width: 2px;
            background: var(--line-color);
            left: 50%;
            transform: translateX(-50%);
            z-index: 0;
        }}
        
        .messages {{
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
            position: relative;
            padding-top: 1rem;
        }}
        
        .message {{
            display: grid;
            grid-template-columns: repeat({num_participants}, minmax(150px, 1fr));
            gap: 0;  /* No gap to align arrows with lifelines */
            position: relative;
            z-index: 1;
        }}
        
        .message-content {{
            grid-column: var(--start-col) / span var(--span-width, 1);
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 0.25rem;
            position: relative;
            padding: 0 0.5rem;
        }}
        
        .self-message .message-content {{
            grid-column: var(--start-col);
        }}
        
        .arrow-container {{
            width: 100%;
            position: relative;
            display: flex;
            justify-content: center;
        }}
        
        .message-label {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            background: var(--bg-color);
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            border: 1px solid var(--border-color);
            font-size: 0.875rem;
            white-space: nowrap;
            z-index: 2;
        }}
        }}
        
        .operation {{
            font-weight: 500;
        }}
        
        .latency {{
            color: var(--success-color);
            font-size: 0.75rem;
        }}
        
        .retry-badge {{
            background: #fbbf24;
            color: #000;
            font-size: 0.625rem;
            padding: 0.125rem 0.375rem;
            border-radius: 9999px;
            font-weight: 600;
        }}
        
        .message.error .message-label {{
            border-color: var(--error-color);
        }}
        
        .message.error .operation {{
            color: var(--error-color);
        }}
        
        .arrow {{
            width: 100%;
            height: 2px;
            background: var(--arrow-color);
            position: relative;
        }}
        
        .arrow.right::after {{
            content: '';
            position: absolute;
            right: -1px;
            top: -4px;
            border: 5px solid transparent;
            border-left-color: var(--arrow-color);
        }}
        
        .arrow.left::after {{
            content: '';
            position: absolute;
            left: -1px;
            top: -4px;
            border: 5px solid transparent;
            border-right-color: var(--arrow-color);
        }}
        
        .message.error .arrow {{
            background: var(--error-color);
        }}
        
        .message.error .arrow.right::after {{
            border-left-color: var(--error-color);
        }}
        
        .message.error .arrow.left::after {{
            border-right-color: var(--error-color);
        }}
        
        .self-arrow {{
            width: 40px;
            height: 30px;
            border: 2px solid var(--arrow-color);
            border-left: none;
            border-radius: 0 10px 10px 0;
            position: relative;
        }}
        
        .self-arrow::after {{
            content: '';
            position: absolute;
            bottom: -1px;
            left: -5px;
            border: 5px solid transparent;
            border-top-color: var(--arrow-color);
        }}
        
        .payload-details {{
            grid-column: 1 / -1;
            margin-top: 0.5rem;
        }}
        
        .payload-details summary {{
            cursor: pointer;
            font-size: 0.75rem;
            color: var(--arrow-color);
            text-align: center;
            padding: 0.25rem;
        }}
        
        .payload-details summary:hover {{
            text-decoration: underline;
        }}
        
        .payload-container {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1rem;
            margin-top: 0.5rem;
            padding: 1rem;
            background: var(--code-bg);
            border-radius: 0.5rem;
        }}
        
        .payload-item {{
            background: var(--bg-color);
            border-radius: 0.375rem;
            overflow: hidden;
            border: 1px solid var(--border-color);
        }}
        
        .payload-item.error {{
            border-color: var(--error-color);
        }}
        
        .payload-label {{
            padding: 0.5rem 0.75rem;
            font-size: 0.75rem;
            font-weight: 600;
            background: var(--code-bg);
            border-bottom: 1px solid var(--border-color);
        }}
        
        .payload-item.error .payload-label {{
            background: var(--error-color);
            color: #fff;
        }}
        
        .payload-content {{
            padding: 0.75rem;
            font-size: 0.75rem;
            font-family: 'SF Mono', Monaco, Consolas, monospace;
            overflow-x: auto;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 200px;
            overflow-y: auto;
        }}
        
        .stats {{
            margin-top: 2rem;
            padding: 1rem;
            background: var(--code-bg);
            border-radius: 0.5rem;
            display: flex;
            gap: 2rem;
            font-size: 0.875rem;
        }}
        
        .stat-label {{
            color: var(--text-color);
            opacity: 0.7;
        }}
        
        .stat-value {{
            font-weight: 600;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{html.escape(title)}</h1>
        <div class="controls">
            <div class="zoom-controls">
                <button class="zoom-btn" onclick="zoom(0.9)">−</button>
                <button class="zoom-btn" onclick="zoom(1.1)">+</button>
                <button class="zoom-btn" onclick="resetZoom()">Reset</button>
            </div>
            <button class="theme-toggle" onclick="toggleTheme()">🌙 Dark Mode</button>
        </div>
    </div>
    
    <div class="diagram-container">
        <div class="diagram" id="diagram">
            <div class="participants">
                {''.join(participant_html)}
            </div>
            <div class="messages">
                {''.join(message_html)}
            </div>
        </div>
    </div>
    
    <div class="stats">
        <div><span class="stat-label">Spans:</span> <span class="stat-value">{len(trace.spans)}</span></div>
        <div><span class="stat-label">Participants:</span> <span class="stat-value">{len(participants)}</span></div>
        <div><span class="stat-label">Errors:</span> <span class="stat-value">{sum(1 for m in messages if m.has_error)}</span></div>
    </div>
    
    <script>
        let currentZoom = 1;
        
        function zoom(factor) {{
            currentZoom *= factor;
            currentZoom = Math.max(0.5, Math.min(2, currentZoom));
            document.getElementById('diagram').style.transform = `scale(${{currentZoom}})`;
        }}
        
        function resetZoom() {{
            currentZoom = 1;
            document.getElementById('diagram').style.transform = 'scale(1)';
        }}
        
        function toggleTheme() {{
            const body = document.body;
            const btn = document.querySelector('.theme-toggle');
            if (body.getAttribute('data-theme') === 'dark') {{
                body.removeAttribute('data-theme');
                btn.textContent = '🌙 Dark Mode';
            }} else {{
                body.setAttribute('data-theme', 'dark');
                btn.textContent = '☀️ Light Mode';
            }}
        }}
    </script>
</body>
</html>'''
