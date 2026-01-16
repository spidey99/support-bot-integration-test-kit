"""HTML report generator for suite results.

Generates a consolidated index.html with:
- Summary statistics
- Per-case rows with status, duration, span count, errors
- Mini SVG thumbnails
- Links to full trace viewers
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from itk.report import CaseResult, CaseStatus, SuiteResult


# Status colors and icons
STATUS_STYLES = {
    CaseStatus.PASSED: {"color": "#10b981", "bg": "#d1fae5", "icon": "✅", "label": "PASSED"},
    CaseStatus.FAILED: {"color": "#ef4444", "bg": "#fee2e2", "icon": "❌", "label": "FAILED"},
    CaseStatus.ERROR: {"color": "#f59e0b", "bg": "#fef3c7", "icon": "⚠️", "label": "ERROR"},
    CaseStatus.SKIPPED: {"color": "#6b7280", "bg": "#f3f4f6", "icon": "⏭️", "label": "SKIPPED"},
}


def _format_duration(ms: float) -> str:
    """Format duration in human-readable form."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    elif ms < 60000:
        return f"{ms/1000:.1f}s"
    else:
        mins = int(ms / 60000)
        secs = (ms % 60000) / 1000
        return f"{mins}m {secs:.0f}s"


def _format_timestamp(iso_str: Optional[str]) -> str:
    """Format ISO timestamp for display."""
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return iso_str


def _render_case_row(case: CaseResult, index: int) -> str:
    """Render a single case row in the results table."""
    style = STATUS_STYLES[case.status]

    # Thumbnail SVG or placeholder
    thumbnail = ""
    if case.thumbnail_svg:
        thumbnail = f'<div class="thumbnail">{case.thumbnail_svg}</div>'
    else:
        thumbnail = '<div class="thumbnail placeholder">—</div>'

    # Link to trace viewer
    viewer_link = ""
    if case.trace_viewer_path:
        viewer_link = f'<a href="{html.escape(case.trace_viewer_path)}" class="view-btn">Trace</a>'
    
    # Link to timeline
    timeline_link = ""
    if case.timeline_path:
        timeline_link = f'<a href="{html.escape(case.timeline_path)}" class="view-btn timeline-btn">Timeline</a>'

    # Error/failure details
    details = ""
    if case.error_message:
        details = f'<div class="error-msg">{html.escape(case.error_message)}</div>'
    elif case.invariant_failures:
        failures = ", ".join(case.invariant_failures)
        details = f'<div class="invariant-failures">Failed: {html.escape(failures)}</div>'

    return f'''
    <tr class="case-row" data-status="{case.status.value}">
        <td class="col-index">{index + 1}</td>
        <td class="col-status">
            <span class="status-badge" style="background: {style['bg']}; color: {style['color']}">
                {style['icon']} {style['label']}
            </span>
        </td>
        <td class="col-case">
            <div class="case-id">{html.escape(case.case_id)}</div>
            <div class="case-name">{html.escape(case.case_name)}</div>
            {details}
        </td>
        <td class="col-duration">{_format_duration(case.duration_ms)}</td>
        <td class="col-spans">{case.span_count}</td>
        <td class="col-errors">{case.error_count if case.error_count else '—'}</td>
        <td class="col-retries">{case.retry_count if case.retry_count else '—'}</td>
        <td class="col-thumbnail">{thumbnail}</td>
        <td class="col-actions">{viewer_link} {timeline_link}</td>
    </tr>'''


def render_suite_report(suite: SuiteResult, title: Optional[str] = None) -> str:
    """Render HTML report for suite results.

    Args:
        suite: Suite execution results.
        title: Optional page title.

    Returns:
        Complete HTML document as string.
    """
    title = title or f"Suite Report — {suite.suite_name}"

    # Summary stats
    pass_rate = suite.pass_rate
    pass_rate_color = "#10b981" if pass_rate >= 80 else "#f59e0b" if pass_rate >= 50 else "#ef4444"

    # Case rows
    case_rows = "\n".join(_render_case_row(c, i) for i, c in enumerate(suite.cases))

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
            --success-color: #10b981;
            --error-color: #ef4444;
            --warning-color: #f59e0b;
            --muted-color: #6b7280;
        }}

        [data-theme="dark"] {{
            --bg-color: #1f2937;
            --text-color: #f9fafb;
            --border-color: #374151;
            --panel-bg: #111827;
            --accent-color: #60a5fa;
            --success-color: #34d399;
            --error-color: #f87171;
            --warning-color: #fbbf24;
            --muted-color: #9ca3af;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-color);
            color: var(--text-color);
            line-height: 1.5;
            padding: 2rem;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        /* Header */
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border-color);
        }}

        .header h1 {{
            font-size: 1.75rem;
            font-weight: 600;
        }}

        .header-meta {{
            color: var(--muted-color);
            font-size: 0.875rem;
            margin-top: 0.5rem;
        }}

        .theme-btn {{
            padding: 0.5rem 0.75rem;
            border: 1px solid var(--border-color);
            border-radius: 0.375rem;
            background: var(--bg-color);
            color: var(--text-color);
            cursor: pointer;
            font-size: 1rem;
        }}

        /* Summary cards */
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}

        .summary-card {{
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            padding: 1rem;
            text-align: center;
        }}

        .summary-value {{
            font-size: 2rem;
            font-weight: 700;
        }}

        .summary-label {{
            font-size: 0.75rem;
            color: var(--muted-color);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .pass-rate {{
            color: {pass_rate_color};
        }}

        /* Filters */
        .filters {{
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
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

        /* Results table */
        .results-table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--bg-color);
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            overflow: hidden;
        }}

        .results-table th {{
            background: var(--panel-bg);
            padding: 0.75rem 1rem;
            text-align: left;
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--muted-color);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-bottom: 1px solid var(--border-color);
        }}

        .results-table td {{
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border-color);
            vertical-align: middle;
        }}

        .results-table tr:last-child td {{
            border-bottom: none;
        }}

        .case-row.hidden {{
            display: none;
        }}

        /* Status badge */
        .status-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
            padding: 0.25rem 0.5rem;
            border-radius: 0.25rem;
            font-size: 0.75rem;
            font-weight: 500;
        }}

        /* Case info */
        .case-id {{
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.875rem;
            font-weight: 500;
        }}

        .case-name {{
            font-size: 0.75rem;
            color: var(--muted-color);
        }}

        .error-msg, .invariant-failures {{
            font-size: 0.75rem;
            color: var(--error-color);
            margin-top: 0.25rem;
        }}

        /* Columns */
        .col-index {{ width: 50px; text-align: center; color: var(--muted-color); }}
        .col-status {{ width: 100px; }}
        .col-case {{ min-width: 200px; }}
        .col-duration {{ width: 80px; text-align: right; font-family: monospace; }}
        .col-spans {{ width: 70px; text-align: center; }}
        .col-errors {{ width: 70px; text-align: center; }}
        .col-retries {{ width: 70px; text-align: center; }}
        .col-thumbnail {{ width: 220px; }}
        .col-actions {{ width: 100px; text-align: center; }}

        /* Thumbnail */
        .thumbnail {{
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 0.25rem;
            padding: 0.25rem;
            height: 60px;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }}

        .thumbnail svg {{
            max-width: 100%;
            max-height: 100%;
        }}

        .thumbnail.placeholder {{
            color: var(--muted-color);
        }}

        /* View button */
        .view-btn {{
            display: inline-block;
            padding: 0.375rem 0.75rem;
            background: var(--accent-color);
            color: white;
            text-decoration: none;
            border-radius: 0.25rem;
            font-size: 0.75rem;
            font-weight: 500;
            transition: opacity 0.15s;
            margin-right: 0.25rem;
        }}

        .view-btn:hover {{
            opacity: 0.9;
        }}
        
        .timeline-btn {{
            background: #f59e0b;
        }}

        /* Footer */
        .footer {{
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border-color);
            color: var(--muted-color);
            font-size: 0.75rem;
            display: flex;
            justify-content: space-between;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <div>
                <h1>{html.escape(suite.suite_name)}</h1>
                <div class="header-meta">
                    Suite ID: {html.escape(suite.suite_id)} · 
                    Mode: {html.escape(suite.mode)} ·
                    Duration: {_format_duration(suite.duration_ms)}
                </div>
            </div>
            <button class="theme-btn" onclick="toggleTheme()">🌙</button>
        </header>

        <section class="summary">
            <div class="summary-card">
                <div class="summary-value">{suite.total_cases}</div>
                <div class="summary-label">Total Cases</div>
            </div>
            <div class="summary-card">
                <div class="summary-value" style="color: var(--success-color)">{suite.passed_count}</div>
                <div class="summary-label">Passed</div>
            </div>
            <div class="summary-card">
                <div class="summary-value" style="color: var(--error-color)">{suite.failed_count}</div>
                <div class="summary-label">Failed</div>
            </div>
            <div class="summary-card">
                <div class="summary-value" style="color: var(--warning-color)">{suite.error_count}</div>
                <div class="summary-label">Errors</div>
            </div>
            <div class="summary-card">
                <div class="summary-value pass-rate">{suite.pass_rate:.0f}%</div>
                <div class="summary-label">Pass Rate</div>
            </div>
            <div class="summary-card">
                <div class="summary-value">{suite.total_spans}</div>
                <div class="summary-label">Total Spans</div>
            </div>
        </section>

        <div class="filters">
            <button class="filter-btn active" data-filter="all">All</button>
            <button class="filter-btn" data-filter="passed">✅ Passed</button>
            <button class="filter-btn" data-filter="failed">❌ Failed</button>
            <button class="filter-btn" data-filter="error">⚠️ Error</button>
            <button class="filter-btn" data-filter="skipped">⏭️ Skipped</button>
        </div>

        <table class="results-table">
            <thead>
                <tr>
                    <th class="col-index">#</th>
                    <th class="col-status">Status</th>
                    <th class="col-case">Case</th>
                    <th class="col-duration">Duration</th>
                    <th class="col-spans">Spans</th>
                    <th class="col-errors">Errors</th>
                    <th class="col-retries">Retries</th>
                    <th class="col-thumbnail">Diagram</th>
                    <th class="col-actions">Actions</th>
                </tr>
            </thead>
            <tbody>
                {case_rows}
            </tbody>
        </table>

        <footer class="footer">
            <span>Generated: {_format_timestamp(suite.finished_at)}</span>
            <span>ITK Suite Report</span>
        </footer>
    </div>

    <script>
    // Theme toggle
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

    // Filter functionality
    document.querySelectorAll('.filter-btn').forEach(btn => {{
        btn.addEventListener('click', function() {{
            const filter = this.dataset.filter;

            // Update active state
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            // Filter rows
            document.querySelectorAll('.case-row').forEach(row => {{
                if (filter === 'all' || row.dataset.status === filter) {{
                    row.classList.remove('hidden');
                }} else {{
                    row.classList.add('hidden');
                }}
            }});
        }});
    }});
    </script>
</body>
</html>'''


def write_suite_report(suite: SuiteResult, out_dir: Path) -> None:
    """Write suite report files.

    Generates:
    - index.html: Interactive HTML report
    - index.json: Machine-readable summary

    Args:
        suite: Suite execution results.
        out_dir: Output directory.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write HTML report
    html_content = render_suite_report(suite)
    (out_dir / "index.html").write_text(html_content, encoding="utf-8")

    # Write JSON summary
    json_content = json.dumps(suite.to_dict(), indent=2, ensure_ascii=False)
    (out_dir / "index.json").write_text(json_content, encoding="utf-8")
