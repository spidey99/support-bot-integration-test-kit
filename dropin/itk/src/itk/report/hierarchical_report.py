"""Hierarchical HTML report generator for test suites.

Generates a modern xUnit-style test report with:
- Collapsible test suite groups
- Expandable test rows with details and mini sequence diagrams
- Modal overlay for full interactive trace viewer
- Keyboard navigation and accessibility

Layout:
┌─────────────────────────────────────────────────────────────────────────────┐
│  ITK Test Report                                        2026-01-15 14:32    │
│  ══════════════════════════════════════════════════════════════════════════ │
│  Summary: 45 passed, 3 failed, 2 skipped | Duration: 2m 34s                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ▼ SQS Entrypoint Tests                             15/15 passed     32s    │
│    ├─ ✅ test_basic_sqs_event                          1.2s                 │
│    │    [expanded: mini diagram + details]        [View Full Trace]         │
│    ├─ ✅ test_sqs_with_retry                           2.1s                 │
│    └─ ❌ test_sqs_timeout                              5.0s                 │
│                                                                              │
│  ▶ Bedrock Agent Tests                              12/12 passed     45s    │
│  ▶ Lambda Direct Tests                              15/18 passed     35s    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Clicking "View Full Trace" opens modal with full trace-viewer.html content.
"""
from __future__ import annotations

import html
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from itk.report import CaseResult, CaseStatus, SuiteResult


# Status configuration
STATUS_CONFIG = {
    CaseStatus.PASSED: {
        "color": "#10b981",
        "bg": "#d1fae5",
        "dark_bg": "#064e3b",
        "icon": "✅",
        "label": "PASSED",
    },
    CaseStatus.PASSED_WITH_WARNINGS: {
        "color": "#f59e0b",
        "bg": "#fef3c7",
        "dark_bg": "#78350f",
        "icon": "⚠️",
        "label": "PASSED*",
    },
    CaseStatus.FAILED: {
        "color": "#ef4444",
        "bg": "#fee2e2",
        "dark_bg": "#7f1d1d",
        "icon": "❌",
        "label": "FAILED",
    },
    CaseStatus.ERROR: {
        "color": "#f59e0b",
        "bg": "#fef3c7",
        "dark_bg": "#78350f",
        "icon": "💥",
        "label": "ERROR",
    },
    CaseStatus.SKIPPED: {
        "color": "#6b7280",
        "bg": "#f3f4f6",
        "dark_bg": "#374151",
        "icon": "⏭️",
        "label": "SKIPPED",
    },
}


@dataclass
class TestGroup:
    """A group of related test cases (test suite)."""

    name: str
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.cases if c.status == CaseStatus.PASSED)

    @property
    def total_count(self) -> int:
        return len(self.cases)

    @property
    def duration_ms(self) -> float:
        return sum(c.duration_ms for c in self.cases)

    @property
    def all_passed(self) -> bool:
        return all(c.status == CaseStatus.PASSED for c in self.cases)

    @property
    def has_failures(self) -> bool:
        return any(c.status in (CaseStatus.FAILED, CaseStatus.ERROR) for c in self.cases)


def _format_duration(ms: float) -> str:
    """Format duration in human-readable form."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    elif ms < 60000:
        return f"{ms / 1000:.1f}s"
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
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso_str


def _group_cases(cases: list[CaseResult]) -> list[TestGroup]:
    """Group test cases by prefix/suite.

    Groups by common prefix before first underscore or hyphen,
    or by directory-like patterns in case IDs.
    """
    groups: dict[str, list[CaseResult]] = defaultdict(list)

    for case in cases:
        # Try to extract group from case_id
        # Patterns: "sqs_test_basic", "sqs-test-basic", "sqs/test_basic"
        case_id = case.case_id

        # Pattern 1: prefix_rest (e.g., sqs_entrypoint_test)
        if "_" in case_id:
            parts = case_id.split("_")
            if len(parts) >= 2:
                group_name = f"{parts[0]}_{parts[1]}" if len(parts) > 2 else parts[0]
            else:
                group_name = parts[0]
        # Pattern 2: prefix-rest (e.g., sqs-entrypoint-test)
        elif "-" in case_id:
            parts = case_id.split("-")
            group_name = parts[0]
        # Pattern 3: directory-like (e.g., sqs/test)
        elif "/" in case_id:
            group_name = case_id.split("/")[0]
        else:
            group_name = "default"

        # Prettify group name
        group_name = group_name.replace("_", " ").replace("-", " ").title()
        groups[group_name].append(case)

    # Convert to TestGroup objects, sorted by name
    return [TestGroup(name=name, cases=cases) for name, cases in sorted(groups.items())]


def _render_test_details(case: CaseResult) -> str:
    """Render the expandable details section for a test."""
    style = STATUS_CONFIG[case.status]

    # Mini sequence diagram
    diagram_html = ""
    if case.thumbnail_svg:
        diagram_html = f'''
        <div class="test-diagram">
            <div class="diagram-label">Sequence Diagram</div>
            <div class="diagram-container">{case.thumbnail_svg}</div>
        </div>'''

    # Timeline thumbnail
    timeline_html = ""
    if case.timeline_svg:
        timeline_html = f'''
        <div class="test-timeline">
            <div class="diagram-label">Timeline</div>
            <div class="diagram-container">{case.timeline_svg}</div>
        </div>'''

    # Error/failure info
    error_html = ""
    if case.error_message:
        error_html = f'''
        <div class="test-error">
            <div class="error-label">Error</div>
            <pre class="error-content">{html.escape(case.error_message)}</pre>
        </div>'''
    elif case.invariant_failures:
        failures = ", ".join(case.invariant_failures)
        error_html = f'''
        <div class="test-error invariant-failure">
            <div class="error-label">Failed Invariants</div>
            <pre class="error-content">{html.escape(failures)}</pre>
        </div>'''

    # Metrics
    metrics_html = f'''
    <div class="test-metrics">
        <div class="metric">
            <span class="metric-value">{case.span_count}</span>
            <span class="metric-label">Spans</span>
        </div>
        <div class="metric">
            <span class="metric-value">{case.error_count or 0}</span>
            <span class="metric-label">Errors</span>
        </div>
        <div class="metric">
            <span class="metric-value">{case.retry_count or 0}</span>
            <span class="metric-label">Retries</span>
        </div>
        <div class="metric">
            <span class="metric-value">{_format_duration(case.duration_ms)}</span>
            <span class="metric-label">Duration</span>
        </div>
    </div>'''

    # Action buttons
    actions_html = ""
    if case.trace_viewer_path:
        timeline_modal_btn = ""
        if case.timeline_path:
            timeline_modal_btn = f'''
            <button class="btn btn-primary open-timeline-modal-btn" 
                    data-timeline-path="{html.escape(case.timeline_path)}"
                    title="Open timeline view in modal">
                📊 View Timeline
            </button>'''
        
        actions_html = f'''
        <div class="test-actions">
            <div class="btn-row">
                <button class="btn btn-primary btn-half open-modal-btn" 
                        data-trace-path="{html.escape(case.trace_viewer_path)}"
                        title="Open full interactive trace viewer">
                    🔍 Sequence
                </button>
                <button class="btn btn-primary btn-half open-timeline-modal-btn" 
                        data-timeline-path="{html.escape(case.timeline_path or case.trace_viewer_path)}"
                        title="Open timeline view in modal">
                    📊 Timeline
                </button>
            </div>
            <div class="btn-row">
                <a href="{html.escape(case.trace_viewer_path)}" 
                   class="btn btn-secondary btn-half" 
                   target="_blank"
                   title="Open sequence diagram in new tab">
                    ↗️ Sequence Tab
                </a>
                <a href="{html.escape(case.timeline_path or case.trace_viewer_path)}" 
                   class="btn btn-secondary btn-half"
                   target="_blank"
                   title="Open timeline view in new tab">
                    ↗️ Timeline Tab
                </a>
            </div>
        </div>'''

    return f'''
    <div class="test-details" style="display: none;">
        <div class="details-content">
            <div class="details-left">
                {diagram_html}
                {timeline_html}
            </div>
            <div class="details-right">
                {metrics_html}
                {error_html}
                {actions_html}
            </div>
        </div>
    </div>'''


def _render_test_row(case: CaseResult, index: int) -> str:
    """Render a single test row with expandable details."""
    style = STATUS_CONFIG[case.status]
    case_id_safe = html.escape(case.case_id)

    details_html = _render_test_details(case)

    return f'''
    <div class="test-row" data-status="{case.status.value}" data-case-id="{case_id_safe}">
        <div class="test-header" onclick="toggleTest(this)" role="button" tabindex="0">
            <span class="test-expand">▶</span>
            <span class="test-status" style="color: {style['color']}">{style['icon']}</span>
            <span class="test-name">{html.escape(case.case_name)}</span>
            <span class="test-id">{case_id_safe}</span>
            <span class="test-duration">{_format_duration(case.duration_ms)}</span>
        </div>
        {details_html}
    </div>'''


def _render_test_group(group: TestGroup, group_index: int) -> str:
    """Render a collapsible test group (suite)."""
    status_class = "passed" if group.all_passed else "failed" if group.has_failures else "mixed"

    # Render all test rows in this group
    test_rows = "\n".join(_render_test_row(c, i) for i, c in enumerate(group.cases))

    # Group status summary
    status_text = f"{group.passed_count}/{group.total_count} passed"
    status_color = "#10b981" if group.all_passed else "#ef4444" if group.has_failures else "#f59e0b"

    return f'''
    <div class="test-group {status_class}" data-group="{group_index}">
        <div class="group-header" onclick="toggleGroup(this)" role="button" tabindex="0">
            <span class="group-expand">▼</span>
            <span class="group-name">{html.escape(group.name)}</span>
            <span class="group-stats" style="color: {status_color}">{status_text}</span>
            <span class="group-duration">{_format_duration(group.duration_ms)}</span>
        </div>
        <div class="group-tests">
            {test_rows}
        </div>
    </div>'''


def render_hierarchical_report(
    suite: SuiteResult,
    title: Optional[str] = None,
    embed_trace_viewer: bool = True,
) -> str:
    """Render hierarchical HTML test report.

    Args:
        suite: Suite execution results.
        title: Optional page title.
        embed_trace_viewer: If True, embed trace viewer JS/CSS for modal.

    Returns:
        Complete HTML document as string.
    """
    title = title or f"Test Report — {suite.suite_name}"

    # Group cases into test suites
    groups = _group_cases(suite.cases)

    # Render groups
    groups_html = "\n".join(_render_test_group(g, i) for i, g in enumerate(groups))

    # Pass rate color
    pass_rate = suite.pass_rate
    pass_rate_color = "#10b981" if pass_rate >= 80 else "#f59e0b" if pass_rate >= 50 else "#ef4444"

    # Load trace viewer assets for modal
    modal_assets = ""
    if embed_trace_viewer:
        modal_assets = _get_modal_assets()

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <style>
{_get_css()}
    </style>
</head>
<body>
    <div class="app">
        <!-- Header -->
        <header class="header">
            <div class="header-left">
                <h1 class="title">{html.escape(suite.suite_name)}</h1>
                <div class="subtitle">
                    Suite ID: <code>{html.escape(suite.suite_id)}</code> · 
                    Mode: <code>{html.escape(suite.mode)}</code> · 
                    Duration: <strong>{_format_duration(suite.duration_ms)}</strong>
                </div>
            </div>
            <div class="header-right">
                <button class="theme-btn" onclick="toggleTheme()" title="Toggle dark mode">🌙</button>
            </div>
        </header>

        <!-- Summary Cards -->
        <section class="summary">
            <div class="summary-card">
                <div class="card-value">{suite.total_cases}</div>
                <div class="card-label">Total Tests</div>
            </div>
            <div class="summary-card success">
                <div class="card-value">{suite.passed_count}</div>
                <div class="card-label">Passed</div>
            </div>
            <div class="summary-card error">
                <div class="card-value">{suite.failed_count}</div>
                <div class="card-label">Failed</div>
            </div>
            <div class="summary-card warning">
                <div class="card-value">{suite.error_count}</div>
                <div class="card-label">Errors</div>
            </div>
            <div class="summary-card" style="--card-color: {pass_rate_color}">
                <div class="card-value" style="color: {pass_rate_color}">{pass_rate:.0f}%</div>
                <div class="card-label">Pass Rate</div>
            </div>
            <div class="summary-card">
                <div class="card-value">{suite.total_spans}</div>
                <div class="card-label">Total Spans</div>
            </div>
        </section>

        <!-- Toolbar -->
        <div class="toolbar">
            <div class="toolbar-left">
                <button class="tool-btn" onclick="expandAll()">Expand All</button>
                <button class="tool-btn" onclick="collapseAll()">Collapse All</button>
            </div>
            <div class="toolbar-center">
                <input type="text" id="search" class="search-input" placeholder="🔍 Search tests..." oninput="filterTests(this.value)">
            </div>
            <div class="toolbar-right">
                <button class="filter-btn active" data-filter="all">All</button>
                <button class="filter-btn" data-filter="passed">✅</button>
                <button class="filter-btn" data-filter="failed">❌</button>
                <button class="filter-btn" data-filter="error">⚠️</button>
            </div>
        </div>

        <!-- Test Groups -->
        <main class="test-groups">
            {groups_html}
        </main>

        <!-- Footer -->
        <footer class="footer">
            <span>Generated: {_format_timestamp(suite.finished_at)}</span>
            <span>ITK Test Report</span>
        </footer>
    </div>

    <!-- Modal for full trace viewer -->
    <div id="trace-modal" class="modal" onclick="closeModalOnBackdrop(event)">
        <div class="modal-content">
            <div class="modal-header">
                <h2 class="modal-title">Trace Viewer</h2>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body">
                <iframe id="trace-iframe" src="about:blank"></iframe>
            </div>
        </div>
    </div>

    <script>
{_get_js()}
    </script>
    {modal_assets}
</body>
</html>'''


def _get_css() -> str:
    """Get the CSS styles for the report."""
    return '''
        :root {
            --bg: #ffffff;
            --bg-secondary: #f9fafb;
            --text: #1f2937;
            --text-muted: #6b7280;
            --border: #e5e7eb;
            --accent: #3b82f6;
            --success: #10b981;
            --error: #ef4444;
            --warning: #f59e0b;
            --card-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        [data-theme="dark"] {
            --bg: #111827;
            --bg-secondary: #1f2937;
            --text: #f9fafb;
            --text-muted: #9ca3af;
            --border: #374151;
            --card-shadow: 0 1px 3px rgba(0,0,0,0.3);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }

        .app {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }

        /* Header */
        .header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 2rem;
            padding-bottom: 1.5rem;
            border-bottom: 2px solid var(--border);
        }

        .title {
            font-size: 1.75rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }

        .subtitle {
            color: var(--text-muted);
            font-size: 0.875rem;
        }

        .subtitle code {
            background: var(--bg-secondary);
            padding: 0.125rem 0.375rem;
            border-radius: 0.25rem;
            font-size: 0.8125rem;
        }

        .theme-btn {
            padding: 0.5rem 0.75rem;
            border: 1px solid var(--border);
            border-radius: 0.5rem;
            background: var(--bg);
            color: var(--text);
            cursor: pointer;
            font-size: 1.25rem;
            transition: all 0.15s;
        }

        .theme-btn:hover {
            border-color: var(--accent);
        }

        /* Summary Cards */
        .summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }

        .summary-card {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 0.75rem;
            padding: 1.25rem;
            text-align: center;
            box-shadow: var(--card-shadow);
        }

        .summary-card.success { border-left: 4px solid var(--success); }
        .summary-card.error { border-left: 4px solid var(--error); }
        .summary-card.warning { border-left: 4px solid var(--warning); }

        .card-value {
            font-size: 2rem;
            font-weight: 700;
            line-height: 1.2;
        }

        .summary-card.success .card-value { color: var(--success); }
        .summary-card.error .card-value { color: var(--error); }
        .summary-card.warning .card-value { color: var(--warning); }

        .card-label {
            font-size: 0.75rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-top: 0.25rem;
        }

        /* Toolbar */
        .toolbar {
            display: flex;
            gap: 1rem;
            align-items: center;
            margin-bottom: 1.5rem;
            padding: 1rem;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 0.5rem;
        }

        .toolbar-left, .toolbar-right {
            display: flex;
            gap: 0.5rem;
        }

        .toolbar-center {
            flex: 1;
        }

        .tool-btn, .filter-btn {
            padding: 0.5rem 0.875rem;
            border: 1px solid var(--border);
            border-radius: 0.375rem;
            background: var(--bg);
            color: var(--text);
            font-size: 0.8125rem;
            cursor: pointer;
            transition: all 0.15s;
        }

        .tool-btn:hover, .filter-btn:hover {
            border-color: var(--accent);
        }

        .filter-btn.active {
            background: var(--accent);
            color: white;
            border-color: var(--accent);
        }

        .search-input {
            width: 100%;
            padding: 0.5rem 1rem;
            border: 1px solid var(--border);
            border-radius: 0.375rem;
            background: var(--bg);
            color: var(--text);
            font-size: 0.875rem;
        }

        .search-input:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        }

        /* Test Groups */
        .test-groups {
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }

        .test-group {
            border: 1px solid var(--border);
            border-radius: 0.75rem;
            overflow: hidden;
            background: var(--bg);
        }

        .test-group.passed { border-left: 4px solid var(--success); }
        .test-group.failed { border-left: 4px solid var(--error); }
        .test-group.mixed { border-left: 4px solid var(--warning); }

        .group-header {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 1rem 1.25rem;
            background: var(--bg-secondary);
            cursor: pointer;
            user-select: none;
            transition: background 0.15s;
        }

        .group-header:hover {
            background: var(--border);
        }

        .group-header:focus {
            outline: 2px solid var(--accent);
            outline-offset: -2px;
        }

        .group-expand {
            font-size: 0.75rem;
            color: var(--text-muted);
            transition: transform 0.2s;
        }

        .test-group.collapsed .group-expand {
            transform: rotate(-90deg);
        }

        .group-name {
            font-weight: 600;
            font-size: 1rem;
            flex: 1;
        }

        .group-stats {
            font-size: 0.875rem;
            font-weight: 500;
        }

        .group-duration {
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.8125rem;
            color: var(--text-muted);
        }

        .group-tests {
            border-top: 1px solid var(--border);
        }

        .test-group.collapsed .group-tests {
            display: none;
        }

        /* Test Rows */
        .test-row {
            border-bottom: 1px solid var(--border);
        }

        .test-row:last-child {
            border-bottom: none;
        }

        .test-row.hidden {
            display: none;
        }

        .test-header {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.75rem 1.25rem;
            padding-left: 2.5rem;
            cursor: pointer;
            user-select: none;
            transition: background 0.15s;
        }

        .test-header:hover {
            background: var(--bg-secondary);
        }

        .test-header:focus {
            outline: 2px solid var(--accent);
            outline-offset: -2px;
        }

        .test-expand {
            font-size: 0.625rem;
            color: var(--text-muted);
            transition: transform 0.2s;
        }

        .test-row.expanded .test-expand {
            transform: rotate(90deg);
        }

        .test-status {
            font-size: 1rem;
        }

        .test-name {
            font-weight: 500;
            flex: 1;
        }

        .test-id {
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.75rem;
            color: var(--text-muted);
            background: var(--bg-secondary);
            padding: 0.125rem 0.5rem;
            border-radius: 0.25rem;
        }

        .test-duration {
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.8125rem;
            color: var(--text-muted);
            min-width: 60px;
            text-align: right;
        }

        /* Test Details (expanded) */
        .test-details {
            padding: 1.5rem;
            padding-left: 3.5rem;
            background: var(--bg-secondary);
            border-top: 1px solid var(--border);
        }

        .details-content {
            display: grid;
            grid-template-columns: 1fr 300px;
            gap: 2rem;
        }

        @media (max-width: 900px) {
            .details-content {
                grid-template-columns: 1fr;
            }
        }

        .details-left {
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }

        .test-diagram, .test-timeline {
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 0.5rem;
            overflow: hidden;
        }

        .diagram-label {
            padding: 0.5rem 0.75rem;
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border);
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .diagram-container {
            padding: 1rem;
            min-height: 120px;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .diagram-container svg {
            max-width: 100%;
            max-height: 200px;
        }

        /* Metrics */
        .test-metrics {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 0.75rem;
            margin-bottom: 1rem;
        }

        .metric {
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 0.5rem;
            padding: 0.75rem;
            text-align: center;
        }

        .metric-value {
            font-size: 1.25rem;
            font-weight: 700;
            display: block;
        }

        .metric-label {
            font-size: 0.6875rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        /* Error display */
        .test-error {
            background: var(--bg);
            border: 1px solid var(--error);
            border-radius: 0.5rem;
            margin-bottom: 1rem;
        }

        .test-error.invariant-failure {
            border-color: var(--warning);
        }

        .error-label {
            padding: 0.5rem 0.75rem;
            background: rgba(239, 68, 68, 0.1);
            border-bottom: 1px solid var(--border);
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--error);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .invariant-failure .error-label {
            background: rgba(245, 158, 11, 0.1);
            color: var(--warning);
        }

        .error-content {
            padding: 0.75rem;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.8125rem;
            white-space: pre-wrap;
            word-break: break-word;
            margin: 0;
            background: transparent;
        }

        /* Action buttons */
        .test-actions {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }

        .btn-row {
            display: flex;
            gap: 0.5rem;
        }

        .btn-half {
            flex: 1;
            font-size: 0.75rem;
            padding: 0.5rem 0.75rem;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            padding: 0.625rem 1rem;
            border: none;
            border-radius: 0.5rem;
            font-size: 0.875rem;
            font-weight: 500;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.15s;
        }

        .btn-primary {
            background: var(--accent);
            color: white;
        }

        .btn-primary:hover {
            opacity: 0.9;
        }

        .btn-secondary {
            background: var(--bg);
            color: var(--text);
            border: 1px solid var(--border);
        }

        .btn-secondary:hover {
            border-color: var(--accent);
        }

        /* Footer */
        .footer {
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            color: var(--text-muted);
            font-size: 0.75rem;
        }

        /* Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.75);
            z-index: 1000;
            align-items: center;
            justify-content: center;
            padding: 2rem;
        }

        .modal.open {
            display: flex;
        }

        .modal-content {
            background: var(--bg);
            border-radius: 0.75rem;
            width: 100%;
            max-width: 1400px;
            height: 90vh;
            display: flex;
            flex-direction: column;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
            overflow: hidden;
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border);
            background: var(--bg-secondary);
        }

        .modal-title {
            font-size: 1.125rem;
            font-weight: 600;
        }

        .modal-close {
            width: 2rem;
            height: 2rem;
            border: none;
            background: transparent;
            font-size: 1.5rem;
            color: var(--text-muted);
            cursor: pointer;
            border-radius: 0.25rem;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.15s;
        }

        .modal-close:hover {
            background: var(--border);
            color: var(--text);
        }

        .modal-body {
            flex: 1;
            overflow: hidden;
        }

        .modal-body iframe {
            width: 100%;
            height: 100%;
            border: none;
        }

        /* Keyboard focus indicators */
        :focus-visible {
            outline: 2px solid var(--accent);
            outline-offset: 2px;
        }
    '''


def _get_js() -> str:
    """Get the JavaScript for the report."""
    return '''
    // Theme toggle
    function toggleTheme() {
        const body = document.body;
        const btn = document.querySelector('.theme-btn');
        if (body.getAttribute('data-theme') === 'dark') {
            body.removeAttribute('data-theme');
            btn.textContent = '🌙';
            localStorage.setItem('theme', 'light');
        } else {
            body.setAttribute('data-theme', 'dark');
            btn.textContent = '☀️';
            localStorage.setItem('theme', 'dark');
        }
    }

    // Restore theme from localStorage
    (function() {
        const saved = localStorage.getItem('theme');
        if (saved === 'dark') {
            document.body.setAttribute('data-theme', 'dark');
            document.querySelector('.theme-btn').textContent = '☀️';
        }
    })();

    // Toggle test group expand/collapse
    function toggleGroup(header) {
        const group = header.closest('.test-group');
        group.classList.toggle('collapsed');
    }

    // Toggle test row expand/collapse
    function toggleTest(header) {
        const row = header.closest('.test-row');
        const details = row.querySelector('.test-details');
        
        if (row.classList.contains('expanded')) {
            row.classList.remove('expanded');
            details.style.display = 'none';
        } else {
            row.classList.add('expanded');
            details.style.display = 'block';
        }
    }

    // Expand all groups and tests
    function expandAll() {
        document.querySelectorAll('.test-group').forEach(g => g.classList.remove('collapsed'));
        document.querySelectorAll('.test-row').forEach(r => {
            r.classList.add('expanded');
            r.querySelector('.test-details').style.display = 'block';
        });
    }

    // Collapse all groups and tests
    function collapseAll() {
        document.querySelectorAll('.test-group').forEach(g => g.classList.add('collapsed'));
        document.querySelectorAll('.test-row').forEach(r => {
            r.classList.remove('expanded');
            r.querySelector('.test-details').style.display = 'none';
        });
    }

    // Filter tests by status
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const filter = this.dataset.filter;

            // Update active state
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            // Filter test rows
            document.querySelectorAll('.test-row').forEach(row => {
                if (filter === 'all' || row.dataset.status === filter) {
                    row.classList.remove('hidden');
                } else {
                    row.classList.add('hidden');
                }
            });

            // Hide empty groups
            document.querySelectorAll('.test-group').forEach(group => {
                const visibleTests = group.querySelectorAll('.test-row:not(.hidden)');
                if (visibleTests.length === 0) {
                    group.style.display = 'none';
                } else {
                    group.style.display = 'block';
                }
            });
        });
    });

    // Search filter
    function filterTests(query) {
        query = query.toLowerCase().trim();

        document.querySelectorAll('.test-row').forEach(row => {
            const name = row.querySelector('.test-name').textContent.toLowerCase();
            const id = row.querySelector('.test-id').textContent.toLowerCase();

            if (!query || name.includes(query) || id.includes(query)) {
                row.classList.remove('hidden');
            } else {
                row.classList.add('hidden');
            }
        });

        // Update group visibility
        document.querySelectorAll('.test-group').forEach(group => {
            const visibleTests = group.querySelectorAll('.test-row:not(.hidden)');
            group.style.display = visibleTests.length === 0 ? 'none' : 'block';
        });
    }

    // Modal functionality
    function openModal(tracePath, title) {
        const modal = document.getElementById('trace-modal');
        const iframe = document.getElementById('trace-iframe');
        const modalTitle = modal.querySelector('.modal-title');
        
        // Set title and iframe src
        modalTitle.textContent = title || 'Trace Viewer';
        iframe.src = tracePath;
        
        // Show modal
        modal.classList.add('open');
        document.body.style.overflow = 'hidden';
        
        // Focus modal for keyboard nav
        modal.focus();
    }

    function closeModal() {
        const modal = document.getElementById('trace-modal');
        const iframe = document.getElementById('trace-iframe');
        
        modal.classList.remove('open');
        document.body.style.overflow = '';
        iframe.src = 'about:blank';
    }

    function closeModalOnBackdrop(event) {
        if (event.target.id === 'trace-modal') {
            closeModal();
        }
    }

    // Handle "View Full Trace" button clicks
    document.querySelectorAll('.open-modal-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const tracePath = this.dataset.tracePath;
            if (tracePath) {
                openModal(tracePath, 'Sequence Diagram');
            }
        });
    });

    // Handle "View Timeline" button clicks
    document.querySelectorAll('.open-timeline-modal-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const timelinePath = this.dataset.timelinePath;
            if (timelinePath) {
                openModal(timelinePath, 'Timeline View');
            }
        });
    });

    // Keyboard navigation
    document.addEventListener('keydown', function(e) {
        // Escape to close modal
        if (e.key === 'Escape') {
            const modal = document.getElementById('trace-modal');
            if (modal.classList.contains('open')) {
                closeModal();
            }
        }

        // Enter to toggle focused element
        if (e.key === 'Enter') {
            const focused = document.activeElement;
            if (focused.classList.contains('group-header') ||
                focused.classList.contains('test-header')) {
                focused.click();
            }
        }
    });
    '''


def _get_modal_assets() -> str:
    """Get additional assets for the modal trace viewer."""
    # For now, the modal loads the trace viewer via iframe
    # This could be enhanced to inline the viewer JS/CSS for better UX
    return ""


def write_hierarchical_report(suite: SuiteResult, out_dir: Path) -> None:
    """Write hierarchical suite report files.

    Generates:
    - index.html: Interactive hierarchical HTML report
    - index.json: Machine-readable summary

    Args:
        suite: Suite execution results.
        out_dir: Output directory.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write HTML report
    html_content = render_hierarchical_report(suite)
    (out_dir / "index.html").write_text(html_content, encoding="utf-8")

    # Write JSON summary
    json_content = json.dumps(suite.to_dict(), indent=2, ensure_ascii=False)
    (out_dir / "index.json").write_text(json_content, encoding="utf-8")
