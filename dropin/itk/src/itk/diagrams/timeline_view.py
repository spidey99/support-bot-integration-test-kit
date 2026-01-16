"""Timeline visualization showing spans on a time axis.

This module generates a timeline view with:
- Horizontal bars proportional to span duration
- Color-coding by component type
- Critical path highlighting
- Pan/zoom support
- Dark mode toggle
"""
from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from itk.trace.trace_model import Trace
from itk.trace.span_model import Span
from itk.diagrams.trace_viewer import COMPONENT_COLORS, _load_vendor_js


# Timeline layout constants
ROW_HEIGHT = 40
ROW_GAP = 8
LABEL_WIDTH = 200
PADDING = 40
MIN_BAR_WIDTH = 4  # Minimum visible width for very short spans


@dataclass
class TimelineSpan:
    """A span with computed timeline positioning."""

    span: Span
    row: int
    start_ms: float
    end_ms: float
    duration_ms: float
    component_type: str
    is_critical: bool = False


def _parse_timestamp(ts: str | None) -> datetime | None:
    """Parse ISO timestamp string to datetime."""
    if not ts:
        return None
    try:
        # Handle various ISO formats
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _compute_duration_ms(ts_start: str | None, ts_end: str | None) -> float | None:
    """Compute duration in milliseconds between two timestamps."""
    start = _parse_timestamp(ts_start)
    end = _parse_timestamp(ts_end)
    if start and end:
        return (end - start).total_seconds() * 1000
    return None


def _get_component_type(component: str) -> str:
    """Extract component type from component string like 'lambda:handler'."""
    if ":" in component:
        return component.split(":")[0].lower()
    return component.lower()


def _build_span_tree(spans: list[Span]) -> dict[str, list[str]]:
    """Build parent → children mapping."""
    tree: dict[str, list[str]] = {}
    for span in spans:
        if span.parent_span_id:
            if span.parent_span_id not in tree:
                tree[span.parent_span_id] = []
            tree[span.parent_span_id].append(span.span_id)
    return tree


def _find_critical_path(
    spans: list[Span],
    span_map: dict[str, Span],
    tree: dict[str, list[str]],
) -> set[str]:
    """Find the critical path (longest chain of sequential spans).
    
    The critical path is the sequence of spans that determines the
    total execution time - the longest path through the span tree.
    """
    if not spans:
        return set()

    # Find root spans
    root_ids = [s.span_id for s in spans if not s.parent_span_id]
    if not root_ids:
        # No roots, use all spans
        root_ids = [spans[0].span_id]

    def get_path_duration(span_id: str, path: list[str]) -> tuple[float, list[str]]:
        """Recursively compute longest path duration from this span."""
        span = span_map.get(span_id)
        if not span:
            return 0.0, path

        current_path = path + [span_id]
        duration = _compute_duration_ms(span.ts_start, span.ts_end) or 0.0

        children = tree.get(span_id, [])
        if not children:
            return duration, current_path

        # Find child with longest path
        max_child_duration = 0.0
        max_child_path: list[str] = []
        for child_id in children:
            child_duration, child_path = get_path_duration(child_id, current_path)
            if child_duration > max_child_duration:
                max_child_duration = child_duration
                max_child_path = child_path

        return duration + max_child_duration, max_child_path

    # Find longest path starting from any root
    longest_path: list[str] = []
    longest_duration = 0.0
    for root_id in root_ids:
        duration, path = get_path_duration(root_id, [])
        if duration > longest_duration:
            longest_duration = duration
            longest_path = path

    return set(longest_path)


def _extract_timeline_spans(trace: Trace) -> tuple[list[TimelineSpan], float, float]:
    """Extract timeline positioning data from trace.
    
    Returns:
        Tuple of (timeline_spans, min_time_ms, max_time_ms)
    """
    if not trace.spans:
        return [], 0.0, 0.0

    # Build span map and tree
    span_map = {s.span_id: s for s in trace.spans}
    tree = _build_span_tree(trace.spans)

    # Find critical path
    critical_ids = _find_critical_path(trace.spans, span_map, tree)

    # Parse all timestamps and find time bounds
    timestamps: list[datetime] = []
    for span in trace.spans:
        ts_start = _parse_timestamp(span.ts_start)
        ts_end = _parse_timestamp(span.ts_end)
        if ts_start:
            timestamps.append(ts_start)
        if ts_end:
            timestamps.append(ts_end)

    if not timestamps:
        # No valid timestamps, use sequential positioning
        timeline_spans = []
        for i, span in enumerate(trace.spans):
            timeline_spans.append(TimelineSpan(
                span=span,
                row=i,
                start_ms=i * 100,
                end_ms=(i + 1) * 100,
                duration_ms=100,
                component_type=_get_component_type(span.component),
                is_critical=span.span_id in critical_ids,
            ))
        return timeline_spans, 0.0, len(trace.spans) * 100

    min_time = min(timestamps)
    max_time = max(timestamps)
    time_range_ms = (max_time - min_time).total_seconds() * 1000

    # Ensure minimum time range for visualization
    if time_range_ms < 100:
        time_range_ms = 100

    # Assign rows (simple: one row per span, ordered by start time)
    spans_with_times: list[tuple[Span, float, float]] = []
    for span in trace.spans:
        ts_start = _parse_timestamp(span.ts_start)
        ts_end = _parse_timestamp(span.ts_end)
        
        if ts_start:
            start_ms = (ts_start - min_time).total_seconds() * 1000
        else:
            start_ms = 0.0
            
        if ts_end:
            end_ms = (ts_end - min_time).total_seconds() * 1000
        else:
            # If no end time, use start + small duration
            end_ms = start_ms + 10

        spans_with_times.append((span, start_ms, end_ms))

    # Sort by start time
    spans_with_times.sort(key=lambda x: x[1])

    # Create timeline spans
    timeline_spans = []
    for row, (span, start_ms, end_ms) in enumerate(spans_with_times):
        duration_ms = max(end_ms - start_ms, 1)  # At least 1ms
        timeline_spans.append(TimelineSpan(
            span=span,
            row=row,
            start_ms=start_ms,
            end_ms=end_ms,
            duration_ms=duration_ms,
            component_type=_get_component_type(span.component),
            is_critical=span.span_id in critical_ids,
        ))

    return timeline_spans, 0.0, time_range_ms


def _render_timeline_bar(
    ts: TimelineSpan,
    time_range_ms: float,
    chart_width: int,
) -> str:
    """Render a single timeline bar as SVG."""
    colors = COMPONENT_COLORS.get(ts.component_type, COMPONENT_COLORS["default"])
    
    y = PADDING + ts.row * (ROW_HEIGHT + ROW_GAP)
    
    # Calculate bar position and width
    if time_range_ms > 0:
        x_start = LABEL_WIDTH + (ts.start_ms / time_range_ms) * chart_width
        bar_width = max((ts.duration_ms / time_range_ms) * chart_width, MIN_BAR_WIDTH)
    else:
        x_start = LABEL_WIDTH
        bar_width = chart_width

    # Critical path styling
    stroke_width = 3 if ts.is_critical else 1
    critical_class = "critical" if ts.is_critical else ""

    # Error styling
    is_error = ts.span.error is not None
    error_class = "error" if is_error else ""

    # Operation label
    operation = html.escape(ts.span.operation or "unknown")
    component = html.escape(ts.span.component)
    
    # Duration label
    if ts.duration_ms >= 1000:
        duration_label = f"{ts.duration_ms / 1000:.2f}s"
    else:
        duration_label = f"{ts.duration_ms:.0f}ms"

    # Span data for click handling
    span_data = html.escape(json.dumps({
        "span_id": ts.span.span_id,
        "operation": ts.span.operation,
        "component": ts.span.component,
        "duration_ms": ts.duration_ms,
        "is_critical": ts.is_critical,
        "has_error": is_error,
        "request": ts.span.request,
        "response": ts.span.response,
        "error": ts.span.error,
    }))

    return f'''
    <g class="timeline-row {critical_class} {error_class}" data-span-id="{ts.span.span_id}" data-span='{span_data}'>
        <!-- Label -->
        <text x="{PADDING}" y="{y + ROW_HEIGHT // 2 + 5}" class="row-label" text-anchor="start">
            {operation}
        </text>
        
        <!-- Bar -->
        <rect x="{x_start}" y="{y}" width="{bar_width}" height="{ROW_HEIGHT}"
              rx="4" ry="4"
              fill="{colors['bg']}" stroke="{colors['stroke']}" stroke-width="{stroke_width}"
              class="timeline-bar" />
        
        <!-- Duration label on bar -->
        <text x="{x_start + bar_width / 2}" y="{y + ROW_HEIGHT // 2 + 5}" 
              class="duration-label" text-anchor="middle" fill="{colors['text']}">
            {duration_label}
        </text>
        
        <!-- Critical path indicator -->
        {f'<circle cx="{LABEL_WIDTH - 10}" cy="{y + ROW_HEIGHT // 2}" r="4" fill="#ef4444" class="critical-dot" />' if ts.is_critical else ''}
    </g>'''


def _render_time_axis(time_range_ms: float, chart_width: int, num_rows: int) -> str:
    """Render the time axis with tick marks."""
    axis_y = PADDING + num_rows * (ROW_HEIGHT + ROW_GAP) + 20
    
    # Determine tick interval
    if time_range_ms <= 100:
        tick_interval = 10
    elif time_range_ms <= 1000:
        tick_interval = 100
    elif time_range_ms <= 10000:
        tick_interval = 1000
    else:
        tick_interval = 5000

    ticks = []
    t = 0.0
    while t <= time_range_ms:
        x = LABEL_WIDTH + (t / time_range_ms) * chart_width if time_range_ms > 0 else LABEL_WIDTH
        
        if t >= 1000:
            label = f"{t / 1000:.1f}s"
        else:
            label = f"{t:.0f}ms"
            
        ticks.append(f'''
        <line x1="{x}" y1="{axis_y - 5}" x2="{x}" y2="{axis_y + 5}" stroke="var(--border-color)" />
        <text x="{x}" y="{axis_y + 20}" class="axis-label" text-anchor="middle">{label}</text>
        ''')
        t += tick_interval

    # Axis line
    axis_line = f'<line x1="{LABEL_WIDTH}" y1="{axis_y}" x2="{LABEL_WIDTH + chart_width}" y2="{axis_y}" stroke="var(--border-color)" stroke-width="2" />'

    return f'''
    <g class="time-axis">
        {axis_line}
        {"".join(ticks)}
    </g>'''


def render_timeline_viewer(
    trace: Trace,
    title: str = "Timeline View",
) -> str:
    """Render a timeline visualization as interactive HTML.
    
    Args:
        trace: The trace to visualize.
        title: Page title.
        
    Returns:
        Complete HTML document string.
    """
    timeline_spans, min_time, max_time = _extract_timeline_spans(trace)
    time_range_ms = max_time - min_time
    
    # Calculate SVG dimensions
    num_rows = len(timeline_spans) if timeline_spans else 1
    chart_width = 800
    svg_width = LABEL_WIDTH + chart_width + PADDING * 2
    svg_height = PADDING * 2 + num_rows * (ROW_HEIGHT + ROW_GAP) + 60  # Extra for axis

    # Render bars
    bars_svg = "\n".join(
        _render_timeline_bar(ts, time_range_ms, chart_width)
        for ts in timeline_spans
    )

    # Render time axis
    axis_svg = _render_time_axis(time_range_ms, chart_width, num_rows)

    # Load vendored JS
    svg_pan_zoom_js = _load_vendor_js("svg-pan-zoom.min.js")

    # Build spans JSON for details panel
    spans_json = json.dumps([
        {
            "span_id": ts.span.span_id,
            "operation": ts.span.operation,
            "component": ts.span.component,
            "duration_ms": ts.duration_ms,
            "is_critical": ts.is_critical,
            "has_error": ts.span.error is not None,
            "request": ts.span.request,
            "response": ts.span.response,
            "error": ts.span.error,
        }
        for ts in timeline_spans
    ])

    # Stats
    total_duration = sum(ts.duration_ms for ts in timeline_spans)
    critical_count = sum(1 for ts in timeline_spans if ts.is_critical)
    error_count = sum(1 for ts in timeline_spans if ts.span.error)

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
            --critical-color: #f59e0b;
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
            --critical-color: #fbbf24;
            --muted-color: #9ca3af;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-color);
            color: var(--text-color);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }}
        
        header {{
            background: var(--panel-bg);
            border-bottom: 1px solid var(--border-color);
            padding: 1rem 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .title {{
            font-size: 1.25rem;
            font-weight: 600;
        }}
        
        .controls {{
            display: flex;
            gap: 0.75rem;
            align-items: center;
        }}
        
        .btn {{
            background: var(--accent-color);
            color: white;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 0.375rem;
            cursor: pointer;
            font-size: 0.875rem;
            transition: opacity 0.15s;
        }}
        
        .btn:hover {{
            opacity: 0.9;
        }}
        
        .theme-btn {{
            background: transparent;
            border: 1px solid var(--border-color);
            color: var(--text-color);
            padding: 0.5rem;
            border-radius: 0.375rem;
            cursor: pointer;
            font-size: 1rem;
        }}
        
        main {{
            flex: 1;
            display: flex;
            overflow: hidden;
        }}
        
        .svg-container {{
            flex: 1;
            overflow: hidden;
            position: relative;
            background: var(--bg-color);
        }}
        
        #timeline {{
            width: 100%;
            height: 100%;
        }}
        
        .row-label {{
            font-size: 0.75rem;
            fill: var(--text-color);
            font-weight: 500;
        }}
        
        .duration-label {{
            font-size: 0.625rem;
            font-weight: 600;
            pointer-events: none;
        }}
        
        .axis-label {{
            font-size: 0.625rem;
            fill: var(--muted-color);
        }}
        
        .timeline-row {{
            cursor: pointer;
            transition: opacity 0.15s;
        }}
        
        .timeline-row:hover .timeline-bar {{
            filter: brightness(1.1);
        }}
        
        .timeline-row.selected .timeline-bar {{
            stroke-width: 3;
            stroke: var(--accent-color);
        }}
        
        .timeline-row.critical .timeline-bar {{
            stroke: var(--critical-color);
        }}
        
        .timeline-row.error .timeline-bar {{
            stroke: var(--error-color);
        }}
        
        .critical-dot {{
            animation: pulse 2s infinite;
        }}
        
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}
        
        .zoom-controls {{
            position: absolute;
            bottom: 1rem;
            right: 1rem;
            display: flex;
            gap: 0.25rem;
            background: var(--panel-bg);
            padding: 0.25rem;
            border-radius: 0.375rem;
            border: 1px solid var(--border-color);
        }}
        
        .zoom-btn {{
            background: transparent;
            border: none;
            color: var(--text-color);
            width: 2rem;
            height: 2rem;
            cursor: pointer;
            font-size: 1rem;
            border-radius: 0.25rem;
        }}
        
        .zoom-btn:hover {{
            background: var(--border-color);
        }}
        
        /* Details panel */
        .details-panel {{
            width: 350px;
            background: var(--panel-bg);
            border-left: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            transition: transform 0.2s;
        }}
        
        .details-panel.collapsed {{
            transform: translateX(100%);
            position: absolute;
            right: 0;
            height: 100%;
        }}
        
        .details-header {{
            padding: 1rem;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .details-title {{
            font-weight: 600;
        }}
        
        .details-close {{
            background: transparent;
            border: none;
            font-size: 1.25rem;
            cursor: pointer;
            color: var(--muted-color);
        }}
        
        .details-content {{
            flex: 1;
            overflow-y: auto;
            padding: 1rem;
        }}
        
        .detail-section {{
            margin-bottom: 1rem;
        }}
        
        .detail-label {{
            font-size: 0.75rem;
            color: var(--muted-color);
            text-transform: uppercase;
            margin-bottom: 0.25rem;
        }}
        
        .detail-value {{
            font-size: 0.875rem;
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
            max-height: 200px;
            overflow-y: auto;
        }}
        
        .badge {{
            display: inline-block;
            padding: 0.125rem 0.5rem;
            border-radius: 9999px;
            font-size: 0.625rem;
            font-weight: 600;
        }}
        
        .badge-critical {{
            background: var(--critical-color);
            color: #000;
        }}
        
        .badge-error {{
            background: var(--error-color);
            color: #fff;
        }}
        
        /* Stats bar */
        .stats-bar {{
            background: var(--panel-bg);
            border-top: 1px solid var(--border-color);
            padding: 0.75rem 1.5rem;
            display: flex;
            gap: 2rem;
        }}
        
        .stat {{
            display: flex;
            gap: 0.5rem;
            align-items: center;
        }}
        
        .stat-label {{
            font-size: 0.75rem;
            color: var(--muted-color);
        }}
        
        .stat-value {{
            font-size: 0.875rem;
            font-weight: 600;
        }}
        
        /* Legend */
        .legend {{
            display: flex;
            gap: 1rem;
            align-items: center;
            font-size: 0.75rem;
        }}
        
        .legend-item {{
            display: flex;
            gap: 0.25rem;
            align-items: center;
        }}
        
        .legend-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }}
        
        .legend-dot.critical {{
            background: var(--critical-color);
        }}
        
        .legend-dot.error {{
            background: var(--error-color);
        }}
    </style>
</head>
<body>
    <header>
        <span class="title">{html.escape(title)}</span>
        <div class="controls">
            <div class="legend">
                <div class="legend-item">
                    <span class="legend-dot critical"></span>
                    <span>Critical Path</span>
                </div>
                <div class="legend-item">
                    <span class="legend-dot error"></span>
                    <span>Error</span>
                </div>
            </div>
            <button class="theme-btn" onclick="toggleTheme()" title="Toggle dark mode">🌙</button>
        </div>
    </header>
    
    <main>
        <div class="svg-container">
            <svg id="timeline" viewBox="0 0 {svg_width} {svg_height}" preserveAspectRatio="xMidYMid meet">
                <g class="timeline-content">
                    {bars_svg}
                    {axis_svg}
                </g>
            </svg>
            <div class="zoom-controls">
                <button class="zoom-btn" onclick="panZoom.zoomIn()" title="Zoom in">+</button>
                <button class="zoom-btn" onclick="panZoom.zoomOut()" title="Zoom out">−</button>
                <button class="zoom-btn" onclick="panZoom.fit()" title="Fit to view">⊡</button>
                <button class="zoom-btn" onclick="panZoom.reset()" title="Reset">↺</button>
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
            <span class="stat-value">{len(timeline_spans)}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Total Duration:</span>
            <span class="stat-value">{time_range_ms:.0f}ms</span>
        </div>
        <div class="stat">
            <span class="stat-label">Critical Path:</span>
            <span class="stat-value" style="color: var(--critical-color)">{critical_count} spans</span>
        </div>
        <div class="stat">
            <span class="stat-label">Errors:</span>
            <span class="stat-value" style="color: var(--error-color)">{error_count}</span>
        </div>
    </footer>
    
    <script>
    // Vendored svg-pan-zoom
    {svg_pan_zoom_js}
    </script>
    
    <script>
    const spansData = {spans_json};
    let panZoom;
    let selectedSpanId = null;
    
    document.addEventListener('DOMContentLoaded', function() {{
        panZoom = svgPanZoom('#timeline', {{
            zoomEnabled: true,
            controlIconsEnabled: false,
            fit: true,
            center: true,
            minZoom: 0.1,
            maxZoom: 10,
            zoomScaleSensitivity: 0.3
        }});
        
        // Click handlers for timeline rows
        document.querySelectorAll('.timeline-row').forEach(el => {{
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
    }});
    
    function selectSpan(spanId) {{
        // Clear previous selection
        document.querySelectorAll('.timeline-row.selected').forEach(el => {{
            el.classList.remove('selected');
        }});
        
        // Select new span
        const row = document.querySelector(`.timeline-row[data-span-id="${{spanId}}"]`);
        if (row) {{
            row.classList.add('selected');
            selectedSpanId = spanId;
            showDetails(row.dataset.span);
        }}
    }}
    
    function clearSelection() {{
        document.querySelectorAll('.timeline-row.selected').forEach(el => {{
            el.classList.remove('selected');
        }});
        selectedSpanId = null;
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
                <div class="detail-label">Duration</div>
                <div class="detail-value">${{span.duration_ms.toFixed(2)}}ms</div>
            </div>
            <div class="detail-section">
                <div class="detail-label">Status</div>
                <div class="detail-value">
                    ${{span.is_critical ? '<span class="badge badge-critical">Critical Path</span>' : ''}}
                    ${{span.has_error ? '<span class="badge badge-error">Error</span>' : ''}}
                    ${{!span.is_critical && !span.has_error ? '<span style="color: var(--success-color)">✓ OK</span>' : ''}}
                </div>
            </div>
        `;
        
        if (span.request) {{
            html += `
                <div class="detail-section">
                    <div class="detail-label">Request</div>
                    <pre class="json-viewer">${{escapeHtml(JSON.stringify(span.request, null, 2))}}</pre>
                </div>
            `;
        }}
        
        if (span.response) {{
            html += `
                <div class="detail-section">
                    <div class="detail-label">Response</div>
                    <pre class="json-viewer">${{escapeHtml(JSON.stringify(span.response, null, 2))}}</pre>
                </div>
            `;
        }}
        
        if (span.error) {{
            html += `
                <div class="detail-section">
                    <div class="detail-label">Error</div>
                    <pre class="json-viewer" style="border-color: var(--error-color)">${{escapeHtml(JSON.stringify(span.error, null, 2))}}</pre>
                </div>
            `;
        }}
        
        content.innerHTML = html;
        panel.classList.remove('collapsed');
    }}
    
    function closeDetails() {{
        document.getElementById('details-panel').classList.add('collapsed');
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


def render_mini_timeline(
    trace: Trace,
    width: int = 200,
    height: int = 60,
) -> str:
    """Render a minimal timeline thumbnail.
    
    Args:
        trace: The trace to render.
        width: SVG width in pixels.
        height: SVG height in pixels.
        
    Returns:
        SVG string (not full HTML).
    """
    timeline_spans, min_time, max_time = _extract_timeline_spans(trace)
    time_range_ms = max_time - min_time
    
    if not timeline_spans:
        return f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"></svg>'
    
    # Calculate row height to fit all spans
    num_rows = len(timeline_spans)
    row_height = max(height / num_rows, 4)
    
    bars = []
    for ts in timeline_spans:
        colors = COMPONENT_COLORS.get(ts.component_type, COMPONENT_COLORS["default"])
        
        y = ts.row * row_height
        if time_range_ms > 0:
            x = (ts.start_ms / time_range_ms) * width
            bar_width = max((ts.duration_ms / time_range_ms) * width, 2)
        else:
            x = 0
            bar_width = width
            
        stroke = colors["stroke"]
        if ts.is_critical:
            stroke = "#f59e0b"
        if ts.span.error:
            stroke = "#ef4444"
            
        bars.append(
            f'<rect x="{x}" y="{y}" width="{bar_width}" height="{row_height - 1}" '
            f'rx="1" fill="{colors["bg"]}" stroke="{stroke}" stroke-width="1" />'
        )
    
    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
        {"".join(bars)}
    </svg>'''
