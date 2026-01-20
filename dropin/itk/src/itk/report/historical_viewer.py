"""Historical execution viewer for retrospective log analysis.

This module provides functionality to fetch CloudWatch logs for a time window,
group them by execution (trace_id/session_id), and generate browsable artifacts
including a gallery page linking all discovered executions.
"""
from __future__ import annotations

import html
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional, Sequence

from itk.trace.span_model import Span
from itk.trace.trace_model import Trace
from itk.trace.build_trace import build_trace_from_spans
from itk.logs.parse import parse_cloudwatch_logs


@dataclass
class ExecutionSummary:
    """Summary of a single execution (trace)."""
    
    execution_id: str
    timestamp: datetime
    span_count: int
    duration_ms: float
    status: str  # "passed", "error", "warning"
    error_count: int
    retry_count: int
    components: list[str]
    artifact_dir: str  # relative path to artifacts
    
    @property
    def status_icon(self) -> str:
        """Get status icon for display."""
        icons = {
            "passed": "✅",
            "error": "❌",
            "warning": "⚠️",
            "unknown": "❓",
        }
        return icons.get(self.status, "❓")


@dataclass
class ViewResult:
    """Result of viewing historical executions."""
    
    start_time: datetime
    end_time: datetime
    total_logs: int
    executions: list[ExecutionSummary] = field(default_factory=list)
    orphan_span_count: int = 0
    
    @property
    def execution_count(self) -> int:
        """Total number of executions found."""
        return len(self.executions)
    
    @property
    def passed_count(self) -> int:
        """Number of passed executions."""
        return sum(1 for e in self.executions if e.status == "passed")
    
    @property
    def error_count(self) -> int:
        """Number of failed executions."""
        return sum(1 for e in self.executions if e.status == "error")
    
    @property
    def warning_count(self) -> int:
        """Number of warning executions."""
        return sum(1 for e in self.executions if e.status == "warning")


def group_spans_by_execution(spans: list[Span]) -> tuple[dict[str, list[Span]], list[Span]]:
    """Group spans by execution (trace_id, session_id, or request_id).
    
    Args:
        spans: List of parsed spans.
        
    Returns:
        Tuple of (grouped spans dict, orphan spans list).
        The dict keys are execution IDs, values are lists of spans.
    """
    groups: dict[str, list[Span]] = defaultdict(list)
    orphans: list[Span] = []
    
    for span in spans:
        # Try various correlation IDs in priority order
        exec_id = (
            span.itk_trace_id or
            span.bedrock_session_id or
            span.lambda_request_id or
            span.xray_trace_id
        )
        
        if exec_id:
            groups[exec_id].append(span)
        else:
            orphans.append(span)
    
    return dict(groups), orphans


def analyze_execution(spans: list[Span]) -> tuple[str, int, int]:
    """Analyze an execution to determine its status.
    
    Args:
        spans: List of spans for the execution.
        
    Returns:
        Tuple of (status, error_count, retry_count).
    """
    error_count = sum(1 for s in spans if s.error is not None)
    # attempt > 1 means it's a retry (attempt 1 is the first try, attempt 2+ are retries)
    retry_count = sum(1 for s in spans if (s.attempt or 1) > 1)
    
    if error_count > 0:
        status = "error"
    elif retry_count > 0:
        status = "warning"
    else:
        status = "passed"
    
    return status, error_count, retry_count


def compute_execution_duration(spans: list[Span]) -> float:
    """Compute total duration of an execution in milliseconds.
    
    Args:
        spans: List of spans for the execution.
        
    Returns:
        Duration in milliseconds, or 0 if unable to compute.
    """
    if not spans:
        return 0.0
    
    # Get earliest start and latest end
    starts = [s.ts_start for s in spans if s.ts_start]
    ends = [s.ts_end for s in spans if s.ts_end]
    
    if not starts or not ends:
        return 0.0
    
    try:
        earliest = min(datetime.fromisoformat(ts.replace("Z", "+00:00")) for ts in starts)
        latest = max(datetime.fromisoformat(ts.replace("Z", "+00:00")) for ts in ends)
        return (latest - earliest).total_seconds() * 1000
    except (ValueError, TypeError):
        return 0.0


def get_execution_timestamp(spans: list[Span]) -> datetime:
    """Get the timestamp of an execution (earliest span start).
    
    Args:
        spans: List of spans for the execution.
        
    Returns:
        Earliest timestamp, or datetime.min if none found.
    """
    if not spans:
        return datetime.min.replace(tzinfo=timezone.utc)
    
    starts = [s.ts_start for s in spans if s.ts_start]
    if not starts:
        return datetime.min.replace(tzinfo=timezone.utc)
    
    try:
        return min(datetime.fromisoformat(ts.replace("Z", "+00:00")) for ts in starts)
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def get_unique_components(spans: list[Span]) -> list[str]:
    """Get list of unique component types in execution.
    
    Args:
        spans: List of spans.
        
    Returns:
        Sorted list of unique component names.
    """
    components = set()
    for span in spans:
        if span.component:
            components.add(span.component)
    return sorted(components)


def build_execution_summary(
    exec_id: str,
    spans: list[Span],
    artifact_dir: str,
) -> ExecutionSummary:
    """Build a summary for an execution.
    
    Args:
        exec_id: Execution/trace ID.
        spans: List of spans for the execution.
        artifact_dir: Relative path to artifact directory.
        
    Returns:
        ExecutionSummary dataclass.
    """
    status, error_count, retry_count = analyze_execution(spans)
    
    return ExecutionSummary(
        execution_id=exec_id,
        timestamp=get_execution_timestamp(spans),
        span_count=len(spans),
        duration_ms=compute_execution_duration(spans),
        status=status,
        error_count=error_count,
        retry_count=retry_count,
        components=get_unique_components(spans),
        artifact_dir=artifact_dir,
    )


def filter_executions(
    executions: list[ExecutionSummary],
    filter_type: str,
) -> list[ExecutionSummary]:
    """Filter executions by status.
    
    Args:
        executions: List of execution summaries.
        filter_type: One of "all", "errors", "warnings", "passed".
        
    Returns:
        Filtered list of executions.
    """
    if filter_type == "all":
        return executions
    elif filter_type == "errors":
        return [e for e in executions if e.status == "error"]
    elif filter_type == "warnings":
        return [e for e in executions if e.status in ("warning", "error")]
    elif filter_type == "passed":
        return [e for e in executions if e.status == "passed"]
    else:
        return executions


def render_gallery_html(result: ViewResult, title: str = "Historical Executions") -> str:
    """Render the gallery HTML page.
    
    Args:
        result: ViewResult with all execution summaries.
        title: Page title.
        
    Returns:
        Complete HTML document as string.
    """
    # Summary stats
    total = result.execution_count
    passed = result.passed_count
    errors = result.error_count
    warnings = result.warning_count
    
    pass_rate = (passed / total * 100) if total > 0 else 0
    pass_rate_color = "#10b981" if pass_rate >= 80 else "#f59e0b" if pass_rate >= 50 else "#ef4444"
    
    # Build execution rows
    execution_rows = []
    for i, exec_summary in enumerate(result.executions):
        row_class = "even" if i % 2 == 0 else "odd"
        status_class = f"status-{exec_summary.status}"
        
        # Format timestamp
        ts_str = exec_summary.timestamp.strftime("%Y-%m-%d %H:%M:%S") if exec_summary.timestamp != datetime.min.replace(tzinfo=timezone.utc) else "Unknown"
        
        # Format duration
        if exec_summary.duration_ms > 0:
            if exec_summary.duration_ms >= 1000:
                duration_str = f"{exec_summary.duration_ms / 1000:.2f}s"
            else:
                duration_str = f"{exec_summary.duration_ms:.0f}ms"
        else:
            duration_str = "-"
        
        # Components badges
        component_badges = " ".join(
            f'<span class="badge">{html.escape(c)}</span>'
            for c in exec_summary.components[:3]  # Limit to first 3
        )
        if len(exec_summary.components) > 3:
            component_badges += f' <span class="badge-more">+{len(exec_summary.components) - 3}</span>'
        
        # Short ID for display
        short_id = exec_summary.execution_id[:12] if len(exec_summary.execution_id) > 12 else exec_summary.execution_id
        
        row = f'''
        <tr class="{row_class} {status_class}" data-status="{exec_summary.status}">
            <td class="col-status">{exec_summary.status_icon}</td>
            <td class="col-id" title="{html.escape(exec_summary.execution_id)}">{html.escape(short_id)}</td>
            <td class="col-timestamp">{ts_str}</td>
            <td class="col-duration">{duration_str}</td>
            <td class="col-spans">{exec_summary.span_count}</td>
            <td class="col-errors">{exec_summary.error_count if exec_summary.error_count > 0 else "-"}</td>
            <td class="col-retries">{exec_summary.retry_count if exec_summary.retry_count > 0 else "-"}</td>
            <td class="col-components">{component_badges}</td>
            <td class="col-actions">
                <a href="{exec_summary.artifact_dir}/trace-viewer.html" class="btn btn-primary">🔍 View</a>
                <a href="{exec_summary.artifact_dir}/timeline.html" class="btn btn-secondary">📊 Timeline</a>
            </td>
        </tr>'''
        execution_rows.append(row)
    
    rows_html = "\n".join(execution_rows)
    
    # Time window formatting
    time_start = result.start_time.strftime("%Y-%m-%d %H:%M:%S")
    time_end = result.end_time.strftime("%Y-%m-%d %H:%M:%S")
    
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
            max-width: 1600px;
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
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}

        .stat-card {{
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            padding: 1rem;
            text-align: center;
        }}

        .stat-value {{
            font-size: 2rem;
            font-weight: 700;
        }}

        .stat-label {{
            color: var(--muted-color);
            font-size: 0.875rem;
            margin-top: 0.25rem;
        }}

        .stat-passed .stat-value {{ color: var(--success-color); }}
        .stat-errors .stat-value {{ color: var(--error-color); }}
        .stat-warnings .stat-value {{ color: var(--warning-color); }}

        /* Filters */
        .filters {{
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
            flex-wrap: wrap;
        }}

        .filter-btn {{
            padding: 0.5rem 1rem;
            border: 1px solid var(--border-color);
            border-radius: 0.375rem;
            background: var(--bg-color);
            color: var(--text-color);
            cursor: pointer;
            font-size: 0.875rem;
            transition: all 0.15s;
        }}

        .filter-btn:hover {{
            background: var(--panel-bg);
        }}

        .filter-btn.active {{
            background: var(--accent-color);
            color: white;
            border-color: var(--accent-color);
        }}

        /* Table */
        .table-container {{
            overflow-x: auto;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.875rem;
        }}

        th, td {{
            padding: 0.75rem;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}

        th {{
            background: var(--panel-bg);
            font-weight: 600;
            position: sticky;
            top: 0;
            z-index: 10;
        }}

        tr.odd {{
            background: var(--panel-bg);
        }}

        tr:hover {{
            background: color-mix(in srgb, var(--accent-color) 10%, var(--bg-color));
        }}

        tr.status-error {{
            background: color-mix(in srgb, var(--error-color) 10%, var(--bg-color));
        }}

        tr.status-warning {{
            background: color-mix(in srgb, var(--warning-color) 10%, var(--bg-color));
        }}

        .col-status {{ width: 40px; text-align: center; }}
        .col-id {{ font-family: monospace; font-size: 0.8rem; }}
        .col-duration {{ text-align: right; }}
        .col-spans {{ text-align: right; }}
        .col-errors {{ text-align: right; }}
        .col-retries {{ text-align: right; }}
        .col-actions {{ white-space: nowrap; }}

        /* Badges */
        .badge {{
            display: inline-block;
            padding: 0.125rem 0.375rem;
            font-size: 0.7rem;
            border-radius: 0.25rem;
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            margin-right: 0.25rem;
        }}

        .badge-more {{
            display: inline-block;
            padding: 0.125rem 0.375rem;
            font-size: 0.7rem;
            color: var(--muted-color);
        }}

        /* Buttons */
        .btn {{
            display: inline-block;
            padding: 0.375rem 0.75rem;
            font-size: 0.75rem;
            border-radius: 0.25rem;
            text-decoration: none;
            transition: all 0.15s;
            margin-right: 0.25rem;
        }}

        .btn-primary {{
            background: var(--accent-color);
            color: white;
        }}

        .btn-primary:hover {{
            opacity: 0.9;
        }}

        .btn-secondary {{
            background: var(--panel-bg);
            color: var(--text-color);
            border: 1px solid var(--border-color);
        }}

        .btn-secondary:hover {{
            background: var(--border-color);
        }}

        /* Empty state */
        .empty-state {{
            text-align: center;
            padding: 4rem 2rem;
            color: var(--muted-color);
        }}

        .empty-state .icon {{
            font-size: 3rem;
            margin-bottom: 1rem;
        }}

        /* Hidden rows for filtering */
        tr.hidden {{
            display: none;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>{html.escape(title)}</h1>
                <div class="header-meta">
                    {time_start} → {time_end}
                    · {result.total_logs:,} log events
                    · {result.execution_count} executions
                    {f"· {result.orphan_span_count} orphan spans" if result.orphan_span_count > 0 else ""}
                </div>
            </div>
            <button class="theme-btn" onclick="toggleTheme()">🌙</button>
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{total}</div>
                <div class="stat-label">Total Executions</div>
            </div>
            <div class="stat-card stat-passed">
                <div class="stat-value">{passed}</div>
                <div class="stat-label">Passed</div>
            </div>
            <div class="stat-card stat-warnings">
                <div class="stat-value">{warnings}</div>
                <div class="stat-label">Warnings</div>
            </div>
            <div class="stat-card stat-errors">
                <div class="stat-value">{errors}</div>
                <div class="stat-label">Errors</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color: {pass_rate_color}">{pass_rate:.0f}%</div>
                <div class="stat-label">Pass Rate</div>
            </div>
        </div>

        <div class="filters">
            <button class="filter-btn active" data-filter="all" onclick="filterTable('all')">All ({total})</button>
            <button class="filter-btn" data-filter="passed" onclick="filterTable('passed')">✅ Passed ({passed})</button>
            <button class="filter-btn" data-filter="warning" onclick="filterTable('warning')">⚠️ Warnings ({warnings})</button>
            <button class="filter-btn" data-filter="error" onclick="filterTable('error')">❌ Errors ({errors})</button>
        </div>

        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th class="col-status">Status</th>
                        <th class="col-id">Execution ID</th>
                        <th class="col-timestamp">Timestamp</th>
                        <th class="col-duration">Duration</th>
                        <th class="col-spans">Spans</th>
                        <th class="col-errors">Errors</th>
                        <th class="col-retries">Retries</th>
                        <th class="col-components">Components</th>
                        <th class="col-actions">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html if execution_rows else '<tr><td colspan="9" class="empty-state"><div class="icon">📭</div><div>No executions found in this time window</div></td></tr>'}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        // Theme toggle
        function toggleTheme() {{
            const html = document.documentElement;
            const current = html.getAttribute('data-theme');
            html.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
            localStorage.setItem('theme', html.getAttribute('data-theme'));
        }}

        // Load saved theme
        const savedTheme = localStorage.getItem('theme');
        if (savedTheme) {{
            document.documentElement.setAttribute('data-theme', savedTheme);
        }} else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {{
            document.documentElement.setAttribute('data-theme', 'dark');
        }}

        // Filter table
        function filterTable(status) {{
            // Update active button
            document.querySelectorAll('.filter-btn').forEach(btn => {{
                btn.classList.toggle('active', btn.dataset.filter === status);
            }});

            // Filter rows
            document.querySelectorAll('tbody tr').forEach(row => {{
                if (status === 'all') {{
                    row.classList.remove('hidden');
                }} else {{
                    const rowStatus = row.dataset.status;
                    row.classList.toggle('hidden', rowStatus !== status);
                }}
            }});
        }}
    </script>
</body>
</html>'''


def load_logs_from_file(logs_file: Path) -> list[dict[str, Any]]:
    """Load log events from a local JSONL file.
    
    Args:
        logs_file: Path to JSONL file with log events.
        
    Returns:
        List of log event dicts with 'timestamp' and 'message' keys.
    """
    events = []
    with logs_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                # Ensure required fields
                if "message" not in event:
                    # Treat the whole line as the message
                    event = {"message": line, "timestamp": event.get("timestamp", "")}
                events.append(event)
            except json.JSONDecodeError:
                # Plain text line - wrap it
                events.append({"message": line, "timestamp": ""})
    return events


def fetch_logs_for_time_window(
    log_groups: list[str],
    start_time: datetime,
    end_time: datetime,
    region: str = "us-east-1",
    limit: int = 10000,
) -> list[dict[str, Any]]:
    """Fetch CloudWatch logs for a time window.
    
    Uses Logs Insights for efficiency, but falls back to filter_log_events
    if Logs Insights returns 0 results (common on newly-created log groups
    due to indexing delay).
    
    Args:
        log_groups: List of log group names to query.
        start_time: Start of time window.
        end_time: End of time window.
        region: AWS region.
        limit: Maximum number of log events to fetch.
        
    Returns:
        List of log event dicts with 'timestamp' and 'message' keys.
    """
    from itk.logs.cloudwatch_fetch import CloudWatchLogsClient, CloudWatchQuery
    
    cw_client = CloudWatchLogsClient(region=region, offline=False)
    
    query = CloudWatchQuery(
        log_groups=log_groups,
        query_string=f"fields @timestamp, @message, @logStream | sort @timestamp asc | limit {limit}",
        start_time_ms=int(start_time.timestamp() * 1000),
        end_time_ms=int(end_time.timestamp() * 1000),
    )
    
    result = cw_client.run_query(query)
    
    events = [
        {"timestamp": r.get("@timestamp", ""), "message": r.get("@message", "")}
        for r in result.results
    ]
    
    # Fallback: If Logs Insights returns 0 results, try filter_log_events
    # This handles the indexing delay on newly-created log groups
    if not events and log_groups:
        events = _fetch_logs_with_filter(log_groups, start_time, end_time, region, limit)
    
    return events


def _fetch_logs_with_filter(
    log_groups: list[str],
    start_time: datetime,
    end_time: datetime,
    region: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Fallback log fetcher using filter_log_events API.
    
    This is slower than Logs Insights but works immediately on new log groups
    without waiting for indexing.
    """
    import boto3
    
    client = boto3.client("logs", region_name=region)
    events: list[dict[str, Any]] = []
    
    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)
    
    for log_group in log_groups:
        try:
            paginator = client.get_paginator("filter_log_events")
            page_iterator = paginator.paginate(
                logGroupName=log_group,
                startTime=start_ms,
                endTime=end_ms,
                limit=min(limit, 10000),  # API max is 10000 per page
            )
            
            for page in page_iterator:
                for event in page.get("events", []):
                    # Convert timestamp from epoch ms to ISO format
                    ts_ms = event.get("timestamp", 0)
                    ts_dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                    events.append({
                        "timestamp": ts_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                        "message": event.get("message", ""),
                    })
                    
                    if len(events) >= limit:
                        break
                
                if len(events) >= limit:
                    break
                    
        except Exception:
            # Log group might not exist or be inaccessible
            continue
    
    # Sort by timestamp
    events.sort(key=lambda e: e.get("timestamp", ""))
    return events[:limit]
