"""Live soak test HTML report that updates during execution.

Generates an HTML report that can be refreshed to show:
- Current iteration progress
- Pass/fail rate over time
- Throttle events timeline
- Rate adjustments chart
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import SoakIteration, SoakResult, ThrottleType


def render_soak_report(result: SoakResult) -> str:
    """Render a soak test result as HTML.

    Args:
        result: SoakResult to render.

    Returns:
        HTML string.
    """
    # Calculate stats
    total = len(result.iterations)
    passed = sum(1 for i in result.iterations if i.passed)
    failed = total - passed
    pass_rate = result.pass_rate * 100 if total > 0 else 0

    # Throttle stats
    all_throttles = result.all_throttle_events
    throttle_by_type: dict[str, int] = {}
    for t in all_throttles:
        key = t.throttle_type.value
        throttle_by_type[key] = throttle_by_type.get(key, 0) + 1

    # Rate history for chart
    rate_data = [{"x": 0, "y": result.rate_history[0].old_rate}] if result.rate_history else []
    for i, change in enumerate(result.rate_history):
        rate_data.append({"x": i + 1, "y": change.new_rate})

    # Iteration data for charts
    iteration_data = []
    for it in result.iterations:
        iteration_data.append({
            "iteration": it.iteration,
            "passed": it.passed,
            "duration_ms": it.duration_ms,
            "throttles": len(it.throttle_events),
        })

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="5">
    <title>Soak Test: {result.case_name}</title>
    <style>
        :root {{
            --bg-primary: #1a1a2e;
            --bg-secondary: #16213e;
            --bg-card: #0f3460;
            --text-primary: #eee;
            --text-secondary: #aaa;
            --accent-green: #4ade80;
            --accent-red: #f87171;
            --accent-yellow: #fbbf24;
            --accent-blue: #60a5fa;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: system-ui, -apple-system, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            padding: 20px;
            min-height: 100vh;
        }}
        h1 {{
            font-size: 1.5rem;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        h1 .status {{
            font-size: 0.75rem;
            padding: 4px 8px;
            border-radius: 4px;
            text-transform: uppercase;
        }}
        h1 .status.running {{ background: var(--accent-blue); }}
        h1 .status.complete {{ background: var(--accent-green); color: #000; }}
        h1 .status.failed {{ background: var(--accent-red); }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: var(--bg-card);
            padding: 15px;
            border-radius: 8px;
        }}
        .stat-card .value {{
            font-size: 2rem;
            font-weight: bold;
        }}
        .stat-card .label {{
            color: var(--text-secondary);
            font-size: 0.875rem;
        }}
        .stat-card.pass .value {{ color: var(--accent-green); }}
        .stat-card.fail .value {{ color: var(--accent-red); }}
        .stat-card.throttle .value {{ color: var(--accent-yellow); }}
        
        .section {{
            background: var(--bg-secondary);
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .section h2 {{
            font-size: 1rem;
            margin-bottom: 15px;
            color: var(--text-secondary);
        }}
        
        .progress-bar {{
            height: 20px;
            background: var(--bg-card);
            border-radius: 4px;
            overflow: hidden;
            display: flex;
        }}
        .progress-bar .pass {{ background: var(--accent-green); }}
        .progress-bar .fail {{ background: var(--accent-red); }}
        
        .timeline {{
            max-height: 300px;
            overflow-y: auto;
        }}
        .timeline-item {{
            display: flex;
            gap: 10px;
            padding: 8px 0;
            border-bottom: 1px solid var(--bg-card);
            font-size: 0.875rem;
        }}
        .timeline-item .time {{
            color: var(--text-secondary);
            min-width: 100px;
        }}
        .timeline-item .type {{
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.75rem;
        }}
        .timeline-item .type.http-429 {{ background: var(--accent-red); color: #000; }}
        .timeline-item .type.aws-throttle {{ background: var(--accent-yellow); color: #000; }}
        .timeline-item .type.retry-storm {{ background: #f472b6; color: #000; }}
        .timeline-item .type.timeout {{ background: #a78bfa; color: #000; }}
        .timeline-item .type.rate-limit {{ background: #fb923c; color: #000; }}
        
        .rate-history {{
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
        }}
        .rate-change {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
        }}
        .rate-change.throttle {{ background: var(--accent-red); color: #000; }}
        .rate-change.stability {{ background: var(--accent-green); color: #000; }}
        
        .iteration-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(20px, 1fr));
            gap: 2px;
        }}
        .iteration-cell {{
            aspect-ratio: 1;
            border-radius: 2px;
        }}
        .iteration-cell.pass {{ background: var(--accent-green); }}
        .iteration-cell.fail {{ background: var(--accent-red); }}
        .iteration-cell.throttle {{ background: var(--accent-yellow); }}
        
        footer {{
            margin-top: 40px;
            text-align: center;
            color: var(--text-secondary);
            font-size: 0.75rem;
        }}
    </style>
</head>
<body>
    <h1>
        🔄 Soak Test: {result.case_name}
        <span class="status {'complete' if result.duration_seconds > 0 else 'running'}">
            {result.mode.value}
        </span>
    </h1>
    
    <div class="stats-grid">
        <div class="stat-card">
            <div class="value">{total}</div>
            <div class="label">Iterations</div>
        </div>
        <div class="stat-card pass">
            <div class="value">{pass_rate:.1f}%</div>
            <div class="label">Pass Rate</div>
        </div>
        <div class="stat-card fail">
            <div class="value">{failed}</div>
            <div class="label">Failures</div>
        </div>
        <div class="stat-card throttle">
            <div class="value">{len(all_throttles)}</div>
            <div class="label">Throttles</div>
        </div>
        <div class="stat-card">
            <div class="value">{result.final_rate:.2f}</div>
            <div class="label">Final Rate (req/s)</div>
        </div>
        <div class="stat-card">
            <div class="value">{result.avg_iteration_ms:.0f}ms</div>
            <div class="label">Avg Duration</div>
        </div>
    </div>
    
    <div class="section">
        <h2>Progress</h2>
        <div class="progress-bar">
            <div class="pass" style="width: {(passed/total*100) if total else 0}%"></div>
            <div class="fail" style="width: {(failed/total*100) if total else 0}%"></div>
        </div>
    </div>
    
    <div class="section">
        <h2>Iteration Grid</h2>
        <div class="iteration-grid">
            {"".join(_render_iteration_cell(it) for it in result.iterations)}
        </div>
    </div>
    
    <div class="section">
        <h2>Rate Adjustments ({len(result.rate_history)})</h2>
        <div class="rate-history">
            {"".join(_render_rate_change(r) for r in result.rate_history) or '<span style="color: var(--text-secondary)">No rate changes</span>'}
        </div>
    </div>
    
    <div class="section">
        <h2>Throttle Events ({len(all_throttles)})</h2>
        <div class="timeline">
            {"".join(_render_throttle_event(t) for t in all_throttles[-50:]) or '<span style="color: var(--text-secondary)">No throttle events</span>'}
        </div>
    </div>
    
    <footer>
        <p>Soak ID: {result.soak_id}</p>
        <p>Started: {result.start_time} | Duration: {result.duration_seconds:.1f}s</p>
        <p>Generated by ITK • Auto-refreshes every 5s</p>
    </footer>
    
    <script>
        // Data for potential charting
        const iterationData = {json.dumps(iteration_data)};
        const rateData = {json.dumps(rate_data)};
    </script>
</body>
</html>"""


def _render_iteration_cell(iteration: SoakIteration) -> str:
    """Render a single iteration cell."""
    if iteration.throttle_events:
        cls = "throttle"
        title = f"Iteration {iteration.iteration}: throttled"
    elif iteration.passed:
        cls = "pass"
        title = f"Iteration {iteration.iteration}: passed ({iteration.duration_ms:.0f}ms)"
    else:
        cls = "fail"
        title = f"Iteration {iteration.iteration}: failed"
    return f'<div class="iteration-cell {cls}" title="{title}"></div>'


def _render_rate_change(change) -> str:
    """Render a rate change badge."""
    direction = "↓" if change.new_rate < change.old_rate else "↑"
    return f'<span class="rate-change {change.reason}">{direction} {change.old_rate:.2f}→{change.new_rate:.2f}</span>'


def _render_throttle_event(event: ThrottleEvent) -> str:
    """Render a throttle event in the timeline."""
    type_class = event.throttle_type.value.lower().replace("_", "-")
    time_str = event.timestamp.split("T")[1][:8] if "T" in event.timestamp else event.timestamp
    return f'''<div class="timeline-item">
        <span class="time">{time_str}</span>
        <span class="type {type_class}">{event.throttle_type.value}</span>
        <span class="details">{event.details or event.source}</span>
    </div>'''


def write_soak_report(result: SoakResult, out_dir: Path) -> Path:
    """Write soak report to disk.

    Args:
        result: SoakResult to write.
        out_dir: Output directory.

    Returns:
        Path to the HTML report.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write HTML
    html_path = out_dir / "soak-report.html"
    html_path.write_text(render_soak_report(result), encoding="utf-8")

    # Write JSON for programmatic access
    json_path = out_dir / "soak-result.json"
    json_path.write_text(
        json.dumps(result.to_dict(), indent=2),
        encoding="utf-8",
    )

    return html_path
