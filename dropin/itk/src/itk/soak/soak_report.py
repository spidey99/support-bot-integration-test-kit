"""Live soak test HTML report that updates during execution.

Generates an HTML report that can be refreshed to show:
- Current iteration progress
- Consistency metrics (clean pass % vs warning pass %)
- Retry distribution
- Pass/fail rate over time
- Throttle events timeline
- Rate adjustments chart
- Per-iteration drill-down (detailed mode)
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
    passed = result.total_passed
    clean = result.total_clean_passes
    warnings = result.total_warnings
    failed = result.total_failures
    pass_rate = result.pass_rate * 100 if total > 0 else 0
    consistency = result.consistency_score * 100 if result.total_passed > 0 else 0
    warning_rate = result.warning_rate * 100 if result.total_passed > 0 else 0

    # Retry stats
    total_retries = result.total_retries
    avg_retries = result.avg_retries_per_iteration
    max_retries = result.max_retries

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

    # Iteration data for charts and table
    iteration_data = []
    for it in result.iterations:
        iteration_data.append({
            "iteration": it.iteration,
            "passed": it.passed,
            "status": it.status,
            "duration_ms": it.duration_ms,
            "retry_count": it.retry_count,
            "error_count": it.error_count,
            "throttles": len(it.throttle_events),
            "is_clean_pass": it.is_clean_pass,
            "artifacts_dir": it.artifacts_dir,
        })

    # Determine if detailed mode (per-iteration artifacts)
    has_artifacts = any(it.artifacts_dir for it in result.iterations)

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
            --accent-purple: #a78bfa;
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
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: var(--bg-card);
            padding: 12px;
            border-radius: 8px;
        }}
        .stat-card .value {{
            font-size: 1.75rem;
            font-weight: bold;
        }}
        .stat-card .label {{
            color: var(--text-secondary);
            font-size: 0.8rem;
        }}
        .stat-card.pass .value {{ color: var(--accent-green); }}
        .stat-card.fail .value {{ color: var(--accent-red); }}
        .stat-card.warning .value {{ color: var(--accent-yellow); }}
        .stat-card.throttle .value {{ color: var(--accent-yellow); }}
        .stat-card.consistency .value {{ color: var(--accent-purple); }}
        
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
        
        /* Consistency gauge */
        .consistency-bar {{
            height: 24px;
            background: var(--bg-card);
            border-radius: 4px;
            overflow: hidden;
            display: flex;
            margin-top: 10px;
        }}
        .consistency-bar .clean {{ background: var(--accent-green); }}
        .consistency-bar .warning {{ background: var(--accent-yellow); }}
        .consistency-bar .fail {{ background: var(--accent-red); }}
        .consistency-legend {{
            display: flex;
            gap: 20px;
            margin-top: 8px;
            font-size: 0.85rem;
        }}
        .consistency-legend span {{
            display: flex;
            align-items: center;
            gap: 5px;
        }}
        .consistency-legend .dot {{
            width: 12px;
            height: 12px;
            border-radius: 2px;
        }}
        .consistency-legend .dot.clean {{ background: var(--accent-green); }}
        .consistency-legend .dot.warning {{ background: var(--accent-yellow); }}
        .consistency-legend .dot.fail {{ background: var(--accent-red); }}
        
        .progress-bar {{
            height: 20px;
            background: var(--bg-card);
            border-radius: 4px;
            overflow: hidden;
            display: flex;
        }}
        .progress-bar .pass {{ background: var(--accent-green); }}
        .progress-bar .fail {{ background: var(--accent-red); }}
        
        /* Iteration table */
        .iteration-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.875rem;
        }}
        .iteration-table th,
        .iteration-table td {{
            padding: 8px 12px;
            text-align: left;
            border-bottom: 1px solid var(--bg-card);
        }}
        .iteration-table th {{
            background: var(--bg-card);
            color: var(--text-secondary);
            cursor: pointer;
            user-select: none;
        }}
        .iteration-table th:hover {{
            background: var(--bg-primary);
        }}
        .iteration-table tbody tr:hover {{
            background: var(--bg-card);
        }}
        .iteration-table .status-cell {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .iteration-table .link {{
            color: var(--accent-blue);
            text-decoration: none;
        }}
        .iteration-table .link:hover {{
            text-decoration: underline;
        }}
        
        /* Filters */
        .filters {{
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }}
        .filter-btn {{
            padding: 6px 12px;
            border: none;
            border-radius: 4px;
            background: var(--bg-card);
            color: var(--text-primary);
            cursor: pointer;
            font-size: 0.85rem;
        }}
        .filter-btn:hover {{
            background: var(--bg-primary);
        }}
        .filter-btn.active {{
            background: var(--accent-blue);
            color: #000;
        }}
        
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
            grid-template-columns: repeat(auto-fill, minmax(24px, 1fr));
            gap: 3px;
        }}
        .iteration-cell {{
            aspect-ratio: 1;
            min-width: 24px;
            min-height: 24px;
            border-radius: 3px;
            cursor: pointer;
            transition: transform 0.1s, box-shadow 0.1s;
        }}
        .iteration-cell:hover {{
            transform: scale(1.2);
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            z-index: 1;
        }}
        .iteration-cell.pass {{ background: var(--accent-green); }}
        .iteration-cell.warning {{ background: var(--accent-yellow); }}
        .iteration-cell.fail {{ background: var(--accent-red); }}
        .iteration-cell.throttle {{ 
            background: var(--accent-yellow);
            box-shadow: inset 0 0 0 2px var(--accent-red);
        }}
        
        footer {{
            margin-top: 40px;
            text-align: center;
            color: var(--text-secondary);
            font-size: 0.75rem;
        }}
        
        .scroll-container {{
            max-height: 500px;
            overflow-y: auto;
        }}
        
        /* Dark/Light mode toggle */
        .theme-toggle {{
            position: fixed;
            top: 20px;
            right: 20px;
            background: var(--bg-card);
            border: none;
            border-radius: 8px;
            padding: 8px 12px;
            cursor: pointer;
            font-size: 1.2rem;
            z-index: 100;
        }}
        .theme-toggle:hover {{
            background: var(--bg-primary);
        }}
        
        /* Light mode */
        body.light-mode {{
            --bg-primary: #f5f5f7;
            --bg-secondary: #ffffff;
            --bg-card: #e8e8ed;
            --text-primary: #1d1d1f;
            --text-secondary: #6e6e73;
        }}
        
        /* Filter count indicator */
        .filter-count {{
            margin-left: 10px;
            color: var(--text-secondary);
            font-size: 0.85rem;
        }}
        
        /* Actions column styling */
        .action-btn {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 4px 8px;
            background: var(--bg-card);
            border-radius: 4px;
            color: var(--accent-blue);
            text-decoration: none;
            font-size: 0.8rem;
            margin-right: 6px;
            transition: background 0.15s;
        }}
        .action-btn:hover {{
            background: var(--bg-primary);
            text-decoration: none;
        }}
    </style>
</head>
<body>
    <button class="theme-toggle" onclick="document.body.classList.toggle('light-mode'); this.textContent = document.body.classList.contains('light-mode') ? '🌙' : '☀️'" title="Toggle light/dark mode">☀️</button>
    
    <h1>
        🔄 Soak Test: {result.case_name}
        <span class="status {'complete' if result.duration_seconds > 0 else 'running'}">
            {result.mode.value}
        </span>
    </h1>
    
    <!-- Key Metrics Grid -->
    <div class="stats-grid">
        <div class="stat-card">
            <div class="value">{total}</div>
            <div class="label">Iterations</div>
        </div>
        <div class="stat-card pass">
            <div class="value">{pass_rate:.1f}%</div>
            <div class="label">Pass Rate</div>
        </div>
        <div class="stat-card consistency">
            <div class="value">{consistency:.0f}%</div>
            <div class="label">Consistency</div>
        </div>
        <div class="stat-card warning">
            <div class="value">{warnings}</div>
            <div class="label">⚠️ Warnings</div>
        </div>
        <div class="stat-card fail">
            <div class="value">{failed}</div>
            <div class="label">❌ Failures</div>
        </div>
        <div class="stat-card">
            <div class="value">{total_retries}</div>
            <div class="label">Total Retries</div>
        </div>
        <div class="stat-card throttle">
            <div class="value">{len(all_throttles)}</div>
            <div class="label">🚦 Throttles</div>
        </div>
        <div class="stat-card">
            <div class="value">{result.avg_iteration_ms:.0f}ms</div>
            <div class="label">Avg Duration</div>
        </div>
    </div>
    
    <!-- Consistency Breakdown -->
    <div class="section">
        <h2>Consistency Breakdown</h2>
        <p style="color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 10px;">
            Consistency = Clean Passes ÷ Total Passes • Reveals LLM non-determinism masked by retries
        </p>
        <div class="consistency-bar">
            <div class="clean" style="width: {(clean/total*100) if total else 0}%"></div>
            <div class="warning" style="width: {(warnings/total*100) if total else 0}%"></div>
            <div class="fail" style="width: {(failed/total*100) if total else 0}%"></div>
        </div>
        <div class="consistency-legend">
            {'<span><span class="dot clean"></span>✅ Clean: ' + str(clean) + '</span>' if clean > 0 else ''}
            {'<span><span class="dot warning"></span>⚠️ Warnings: ' + str(warnings) + '</span>' if warnings > 0 else ''}
            {'<span><span class="dot fail"></span>❌ Failed: ' + str(failed) + '</span>' if failed > 0 else ''}
            {'' if (clean + warnings + failed) > 0 else '<span style="color: var(--text-secondary)">No iterations yet</span>'}
        </div>
        <p style="color: var(--text-secondary); font-size: 0.85rem; margin-top: 12px;">
            Retries: {total_retries} total • Avg: {avg_retries:.1f}/iter • Max: {max_retries}
        </p>
    </div>
    
    <!-- Iteration Grid (Visual Overview) -->
    <div class="section">
        <h2>Iteration Grid</h2>
        <div class="iteration-grid">
            {"".join(_render_iteration_cell(it) for it in result.iterations)}
        </div>
    </div>
    
    <!-- Iteration Table (Drill-down) -->
    <div class="section">
        <h2>Iteration Details {'(click to drill-down)' if has_artifacts else ''}</h2>
        <div class="filters">
            <button class="filter-btn active" data-filter="all">All</button>
            <button class="filter-btn" data-filter="warning">⚠️ Warnings Only</button>
            <button class="filter-btn" data-filter="failed">❌ Failed Only</button>
            <button class="filter-btn" data-filter="retries">🔄 Has Retries</button>
            <span class="filter-count" id="filter-count">Showing {total} of {total}</span>
        </div>
        <div class="scroll-container">
            <table class="iteration-table">
                <thead>
                    <tr>
                        <th data-sort="iteration"># ⇅</th>
                        <th data-sort="status">Status ⇅</th>
                        <th data-sort="duration_ms">Duration ⇅</th>
                        <th data-sort="retry_count">Retries ⇅</th>
                        <th data-sort="error_count">Errors ⇅</th>
                        <th data-sort="throttles">Throttles ⇅</th>
                        {'<th>Actions</th>' if has_artifacts else ''}
                    </tr>
                </thead>
                <tbody id="iteration-body">
                    {"".join(_render_iteration_row(it, has_artifacts) for it in result.iterations)}
                </tbody>
            </table>
        </div>
    </div>
    
    <!-- Rate Adjustments -->
    <div class="section">
        <h2>Rate Adjustments ({len(result.rate_history)})</h2>
        <div class="rate-history">
            {"".join(_render_rate_change(r) for r in result.rate_history) or '<span style="color: var(--text-secondary)">No rate changes</span>'}
        </div>
    </div>
    
    <!-- Throttle Events -->
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
        const totalIterations = {total};
        
        // Update filter count
        function updateFilterCount() {{
            const visible = document.querySelectorAll('#iteration-body tr:not([style*="display: none"])').length;
            document.getElementById('filter-count').textContent = `Showing ${{visible}} of ${{totalIterations}}`;
        }}
        
        // Filter functionality
        document.querySelectorAll('.filter-btn').forEach(btn => {{
            btn.addEventListener('click', () => {{
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const filter = btn.dataset.filter;
                
                document.querySelectorAll('#iteration-body tr').forEach(row => {{
                    const status = row.dataset.status;
                    const retries = parseInt(row.dataset.retries || '0');
                    
                    let show = true;
                    if (filter === 'warning') show = status === 'warning';
                    else if (filter === 'failed') show = status === 'failed' || status === 'error';
                    else if (filter === 'retries') show = retries > 0;
                    
                    row.style.display = show ? '' : 'none';
                }});
                
                updateFilterCount();
            }});
        }});
        
        // Sort functionality
        let sortDir = {{}};
        document.querySelectorAll('th[data-sort]').forEach(th => {{
            th.addEventListener('click', () => {{
                const col = th.dataset.sort;
                sortDir[col] = !sortDir[col];
                
                const tbody = document.getElementById('iteration-body');
                const rows = Array.from(tbody.querySelectorAll('tr'));
                
                rows.sort((a, b) => {{
                    let aVal = a.dataset[col] || a.cells[getColIndex(col)].textContent;
                    let bVal = b.dataset[col] || b.cells[getColIndex(col)].textContent;
                    
                    // Numeric sort for numbers
                    if (!isNaN(aVal)) {{
                        aVal = parseFloat(aVal);
                        bVal = parseFloat(bVal);
                    }}
                    
                    if (aVal < bVal) return sortDir[col] ? 1 : -1;
                    if (aVal > bVal) return sortDir[col] ? -1 : 1;
                    return 0;
                }});
                
                rows.forEach(row => tbody.appendChild(row));
            }});
        }});
        
        function getColIndex(col) {{
            const cols = ['iteration', 'status', 'duration_ms', 'retry_count', 'error_count', 'throttles'];
            return cols.indexOf(col);
        }}
    </script>
</body>
</html>"""


def _render_iteration_cell(iteration: SoakIteration) -> str:
    """Render a single iteration cell in the grid."""
    from pathlib import Path
    
    # Determine visual class
    if iteration.throttle_events:
        cls = "throttle"
        title = f"Iteration {iteration.iteration}: throttled"
    elif iteration.status == "warning":
        cls = "warning"
        title = f"Iteration {iteration.iteration}: warning (retries: {iteration.retry_count})"
    elif iteration.passed:
        cls = "pass"
        title = f"Iteration {iteration.iteration}: passed ({iteration.duration_ms:.0f}ms)"
    else:
        cls = "fail"
        title = f"Iteration {iteration.iteration}: {iteration.status}"
    
    # If detailed mode, make cell clickable
    onclick = ""
    if iteration.artifacts_dir:
        art_path = Path(iteration.artifacts_dir)
        iter_num = f"{iteration.iteration:04d}"
        case_name = art_path.name
        onclick = f' onclick="window.location.href=\'iterations/{iter_num}/{case_name}/trace-viewer.html\'"'
    
    return f'<div class="iteration-cell {cls}" title="{title}"{onclick}></div>'


def _render_iteration_row(iteration: SoakIteration, has_artifacts: bool) -> str:
    """Render a single iteration row in the table."""
    from pathlib import Path
    
    # Status icon
    status_icons = {
        "passed": "✅",
        "warning": "⚠️",
        "failed": "❌",
        "error": "💥",
        "skipped": "⏭️",
    }
    icon = status_icons.get(iteration.status, "❓")
    
    # Duration display: show "<1ms" for very fast iterations
    duration_display = "<1ms" if iteration.duration_ms < 1 else f"{iteration.duration_ms:.0f}ms"
    
    # Build action links if detailed mode
    actions = ""
    if has_artifacts and iteration.artifacts_dir:
        # Extract relative path from artifacts_dir
        # Path like: c:\...\iterations\0000\demo-warning-001
        # We need: iterations/0000/demo-warning-001
        art_path = Path(iteration.artifacts_dir)
        iter_num = f"{iteration.iteration:04d}"
        case_name = art_path.name  # e.g., "demo-warning-001"
        
        actions = f'''<td>
            <a href="iterations/{iter_num}/{case_name}/trace-viewer.html" class="action-btn" title="View trace">🔍 Trace</a>
            <a href="iterations/{iter_num}/{case_name}/timeline.html" class="action-btn" title="View timeline">📊 Timeline</a>
        </td>'''
    elif has_artifacts:
        actions = '<td>—</td>'
    
    return f'''<tr data-status="{iteration.status}" data-retries="{iteration.retry_count}" 
               data-iteration="{iteration.iteration}" data-duration_ms="{iteration.duration_ms:.0f}"
               data-retry_count="{iteration.retry_count}" data-error_count="{iteration.error_count}"
               data-throttles="{len(iteration.throttle_events)}">
        <td>{iteration.iteration}</td>
        <td><span class="status-cell">{icon} {iteration.status}</span></td>
        <td>{duration_display}</td>
        <td>{iteration.retry_count}</td>
        <td>{iteration.error_count}</td>
        <td>{len(iteration.throttle_events)}</td>
        {actions}
    </tr>'''


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
