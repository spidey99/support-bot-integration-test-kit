from __future__ import annotations

import html
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Sequence

from itk.trace.span_model import Span
from itk.trace.trace_model import Trace
from itk.redaction import Redactor, RedactionConfig

if TYPE_CHECKING:
    from itk.assertions.invariants import InvariantResult
    from itk.audit.gap_detector import LoggingGap
    from itk.cases.loader import CaseConfig
    from itk.compare.compare import CompareResult


# Module-level redactor, can be configured
_redactor: Optional[Redactor] = None


def get_redactor() -> Redactor:
    """Get the current redactor instance."""
    global _redactor
    if _redactor is None:
        _redactor = Redactor()
    return _redactor


def set_redactor(redactor: Redactor) -> None:
    """Set the module redactor instance."""
    global _redactor
    _redactor = redactor


def disable_redaction() -> None:
    """Disable redaction for artifact output."""
    config = RedactionConfig(enabled=False)
    set_redactor(Redactor(config))


def _generate_run_id() -> str:
    """Generate a run ID based on current timestamp."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def write_run_artifacts(
    *,
    out_dir: Path,
    trace: Trace,
    mermaid: str,
    case: Optional["CaseConfig"] = None,
    invariant_results: Optional[Sequence["InvariantResult"]] = None,
    agent_response: Optional[dict] = None,
    mode: str = "dev-fixtures",
) -> None:
    """Write all artifacts for a run.

    Creates:
    - index.html: Top-level HTML report with links to viewers
    - spans.jsonl: JSONL of all spans
    - payloads/<span_id>.request.json: Request payloads
    - payloads/<span_id>.response.json: Response payloads
    - sequence.mmd: Mermaid sequence diagram
    - report.md: Human-readable report

    Redaction is applied to all payload data by default.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    payload_dir = out_dir / "payloads"
    payload_dir.mkdir(exist_ok=True)

    redactor = get_redactor()

    # Write spans.jsonl with redaction
    spans_path = out_dir / "spans.jsonl"
    with spans_path.open("w", encoding="utf-8") as f:
        for s in trace.spans:
            span_dict = asdict(s)
            # Redact request/response payloads
            if span_dict.get("request"):
                span_dict["request"] = redactor.redact_dict(span_dict["request"])
            if span_dict.get("response"):
                span_dict["response"] = redactor.redact_dict(span_dict["response"])
            if span_dict.get("error"):
                span_dict["error"] = redactor.redact_dict(span_dict["error"])
            f.write(json.dumps(span_dict, ensure_ascii=False) + "\n")

    # Write payload files with redaction
    for s in trace.spans:
        if s.request is not None:
            redacted_req = redactor.redact_dict(s.request)
            (payload_dir / f"{s.span_id}.request.json").write_text(
                json.dumps(redacted_req, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        if s.response is not None:
            redacted_res = redactor.redact_dict(s.response)
            (payload_dir / f"{s.span_id}.response.json").write_text(
                json.dumps(redacted_res, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        if s.error is not None:
            redacted_err = redactor.redact_dict(s.error)
            (payload_dir / f"{s.span_id}.error.json").write_text(
                json.dumps(redacted_err, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    # Write mermaid
    (out_dir / "sequence.mmd").write_text(mermaid, encoding="utf-8")

    # Write HTML sequence diagram (legacy)
    from itk.diagrams.html_renderer import render_html_sequence
    
    title = f"Sequence Diagram — {case.id}" if case else "Sequence Diagram"
    html_diagram = render_html_sequence(trace, title=title, include_payloads=True)
    (out_dir / "sequence.html").write_text(html_diagram, encoding="utf-8")

    # Write enhanced interactive trace viewer
    from itk.diagrams.trace_viewer import render_trace_viewer, render_mini_svg
    
    viewer_title = f"Trace Viewer — {case.id}" if case else "Trace Viewer"
    trace_viewer_html = render_trace_viewer(trace, title=viewer_title)
    (out_dir / "trace-viewer.html").write_text(trace_viewer_html, encoding="utf-8")

    # Write mini SVG thumbnail
    mini_svg = render_mini_svg(trace)
    (out_dir / "thumbnail.svg").write_text(mini_svg, encoding="utf-8")

    # Write timeline view
    from itk.diagrams.timeline_view import render_timeline_viewer, render_mini_timeline
    
    timeline_title = f"Timeline — {case.id}" if case else "Timeline"
    timeline_html = render_timeline_viewer(trace, title=timeline_title)
    (out_dir / "timeline.html").write_text(timeline_html, encoding="utf-8")

    # Write mini timeline thumbnail
    mini_timeline = render_mini_timeline(trace)
    (out_dir / "timeline-thumbnail.svg").write_text(mini_timeline, encoding="utf-8")

    # Write markdown report
    report = _build_report(trace=trace, case=case, invariant_results=invariant_results)
    (out_dir / "report.md").write_text(report, encoding="utf-8")

    # Write top-level HTML report (index.html)
    html_report = render_run_report_html(
        trace=trace,
        case=case,
        invariant_results=invariant_results,
        agent_response=agent_response,
        mode=mode,
        artifacts_dir=out_dir,
    )
    (out_dir / "index.html").write_text(html_report, encoding="utf-8")


def _build_report(
    *,
    trace: Trace,
    case: Optional["CaseConfig"] = None,
    invariant_results: Optional[Sequence["InvariantResult"]] = None,
) -> str:
    """Build a markdown report."""
    lines: list[str] = ["# ITK Run Report", ""]

    # Case info
    if case:
        lines.extend(
            [
                "## Case",
                f"- **ID**: {case.id}",
                f"- **Name**: {case.name}",
                f"- **Entrypoint**: {case.entrypoint.type}",
                "",
            ]
        )

    # Summary
    lines.extend(
        [
            "## Summary",
            f"- **Spans**: {len(trace.spans)}",
            f"- **Components**: {len(set(s.component for s in trace.spans))}",
            "",
        ]
    )

    # Invariant results
    if invariant_results:
        lines.append("## Invariants")
        for result in invariant_results:
            status = "✅ PASS" if result.passed else "❌ FAIL"
            lines.append(f"- {status} `{result.name}`")
            if result.details:
                for k, v in result.details.items():
                    lines.append(f"  - {k}: {v}")
        lines.append("")

    # Span summary table
    lines.extend(
        [
            "## Spans",
            "",
            "| Span ID | Component | Operation | Has Request | Has Response |",
            "|---------|-----------|-----------|-------------|--------------|",
        ]
    )
    for s in trace.spans:
        has_req = "✅" if s.request else "❌"
        has_res = "✅" if s.response else ("⚠️ error" if s.error else "❌")
        lines.append(f"| {s.span_id} | {s.component} | {s.operation} | {has_req} | {has_res} |")
    lines.append("")

    # Artifacts
    lines.extend(
        [
            "## Artifacts",
            "- `spans.jsonl`: Raw span data",
            "- `payloads/`: Request/response JSON files",
            "- `sequence.mmd`: Mermaid sequence diagram",
            "",
        ]
    )

    return "\n".join(lines)


def write_audit_artifacts(
    *,
    out_dir: Path,
    trace: Trace,
    gaps: Sequence["LoggingGap"],
    case: "CaseConfig",
) -> None:
    """Write audit artifacts.

    Creates:
    - logging-gaps.md: Human-readable gap report
    - gaps.json: Machine-readable gaps
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write logging-gaps.md
    md = _build_gaps_markdown(trace=trace, gaps=gaps, case=case)
    (out_dir / "logging-gaps.md").write_text(md, encoding="utf-8")

    # Write gaps.json
    gaps_data = [
        {
            "severity": g.severity,
            "component": g.component,
            "span_id": g.span_id,
            "issue": g.issue,
            "recommendation": g.recommendation,
        }
        for g in gaps
    ]
    (out_dir / "gaps.json").write_text(
        json.dumps(gaps_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _build_gaps_markdown(
    *,
    trace: Trace,
    gaps: Sequence["LoggingGap"],
    case: "CaseConfig",
) -> str:
    """Build a markdown report for logging gaps."""
    lines: list[str] = ["# Logging Gap Audit Report", ""]

    # Summary
    critical_count = sum(1 for g in gaps if g.severity == "critical")
    warning_count = sum(1 for g in gaps if g.severity == "warning")
    info_count = sum(1 for g in gaps if g.severity == "info")

    lines.extend(
        [
            "## Summary",
            f"- **Case**: {case.id}",
            f"- **Spans analyzed**: {len(trace.spans)}",
            f"- **Critical gaps**: {critical_count}",
            f"- **Warnings**: {warning_count}",
            f"- **Info**: {info_count}",
            "",
        ]
    )

    if not gaps:
        lines.extend(
            [
                "## Result",
                "✅ No logging gaps detected!",
                "",
            ]
        )
        return "\n".join(lines)

    # Group gaps by severity
    for severity in ["critical", "warning", "info"]:
        severity_gaps = [g for g in gaps if g.severity == severity]
        if not severity_gaps:
            continue

        emoji = {"critical": "🔴", "warning": "🟡", "info": "🔵"}[severity]
        lines.extend(
            [
                f"## {emoji} {severity.title()} ({len(severity_gaps)})",
                "",
            ]
        )

        for g in severity_gaps:
            span_ref = f" (span: `{g.span_id}`)" if g.span_id else ""
            lines.extend(
                [
                    f"### {g.component}{span_ref}",
                    f"**Issue**: {g.issue}",
                    "",
                    f"**Recommendation**: {g.recommendation}",
                    "",
                ]
            )

    # Actionable checklist
    lines.extend(
        [
            "## Action Checklist",
            "",
        ]
    )
    components_needing_logs = sorted(
        set(g.component for g in gaps if g.severity in ("critical", "warning"))
    )
    for comp in components_needing_logs:
        lines.append(f"- [ ] Add logging to `{comp}`")
    lines.append("")

    # Example log format
    lines.extend(
        [
            "## Recommended Log Format",
            "",
            "Add a WARN-level JSON log line at each boundary:",
            "",
            "```json",
            "{",
            '  "span_id": "unique-id",',
            '  "component": "lambda:my-function",',
            '  "operation": "InvokeLambda",',
            '  "ts_start": "2026-01-15T12:00:00.000Z",',
            '  "lambda_request_id": "aws-request-id",',
            '  "request": { ... }',
            "}",
            "```",
            "",
        ]
    )

    return "\n".join(lines)


def write_compare_artifacts(
    *,
    out_dir: Path,
    result: "CompareResult",
) -> None:
    """Write compare artifacts.

    Creates:
    - comparison.md: Human-readable comparison report
    - comparison.json: Machine-readable delta data
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write comparison.md
    md = _build_comparison_markdown(result)
    (out_dir / "comparison.md").write_text(md, encoding="utf-8")

    # Write comparison.json
    data = {
        "baseline": result.baseline_label,
        "current": result.current_label,
        "summary": {
            "new_paths": len(result.new_paths),
            "missing_paths": len(result.missing_paths),
            "latency_regressions": len(result.significant_latency_changes),
            "error_regressions": len(result.error_regressions),
            "has_regressions": result.has_regressions,
        },
        "deltas": [
            {
                "signature": d.signature.signature_string,
                "baseline_count": d.baseline_count,
                "current_count": d.current_count,
                "baseline_avg_latency_ms": d.baseline_avg_latency_ms,
                "current_avg_latency_ms": d.current_avg_latency_ms,
                "latency_delta_pct": d.latency_delta_pct,
                "baseline_error_count": d.baseline_error_count,
                "current_error_count": d.current_error_count,
                "error_rate_delta": d.error_rate_delta,
            }
            for d in result.deltas
        ],
    }
    (out_dir / "comparison.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def render_run_report_html(
    *,
    trace: Trace,
    case: Optional["CaseConfig"] = None,
    invariant_results: Optional[Sequence["InvariantResult"]] = None,
    agent_response: Optional[dict] = None,
    mode: str = "dev-fixtures",
    artifacts_dir: Optional[Path] = None,
) -> str:
    """Render a top-level HTML report for a single test run.
    
    Similar to soak-report.html but for individual test runs.
    Shows summary stats, links to trace viewer and timeline, and span details.
    """
    from datetime import datetime, timezone
    
    # Calculate stats
    span_count = len(trace.spans)
    components = sorted(set(s.component for s in trace.spans))
    operations = sorted(set(s.operation for s in trace.spans))
    error_spans = [s for s in trace.spans if s.error]
    
    # Invariant summary
    inv_passed = sum(1 for r in (invariant_results or []) if r.passed)
    inv_total = len(invariant_results or [])
    all_pass = inv_passed == inv_total and inv_total > 0
    
    # Case info
    case_id = case.id if case else "Unknown"
    case_name = case.name if case else "Unnamed Test"
    entrypoint = case.entrypoint.type if case else "unknown"
    
    # Agent response preview
    response_preview = ""
    if agent_response:
        if isinstance(agent_response, dict):
            resp_text = agent_response.get("response", agent_response.get("completion", ""))
            if resp_text:
                response_preview = str(resp_text)[:200] + ("..." if len(str(resp_text)) > 200 else "")
    
    # Calculate duration if we have timestamps
    duration_ms = 0
    if trace.spans:
        timestamps = [s.ts_start for s in trace.spans if s.ts_start]
        # Duration is calculated from span timing if available
        # (ts_start to ts_end per span could be summed, but for now just note span count)
    
    # Relative path for artifacts
    artifacts_rel = "."
    
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ITK Run Report — {case_id}</title>
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
            --border-color: #334155;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: system-ui, -apple-system, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            padding: 20px;
            min-height: 100vh;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 12px;
        }}
        h1 {{
            font-size: 1.5rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        h1 .status {{
            font-size: 0.75rem;
            padding: 4px 12px;
            border-radius: 4px;
            text-transform: uppercase;
            font-weight: bold;
        }}
        h1 .status.pass {{ background: var(--accent-green); color: #000; }}
        h1 .status.fail {{ background: var(--accent-red); color: #fff; }}
        .meta {{
            color: var(--text-secondary);
            font-size: 0.85rem;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 12px;
            margin-bottom: 24px;
        }}
        .stat-card {{
            background: var(--bg-card);
            padding: 16px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }}
        .stat-card .value {{
            font-size: 2rem;
            font-weight: bold;
        }}
        .stat-card .label {{
            color: var(--text-secondary);
            font-size: 0.8rem;
            margin-top: 4px;
        }}
        .stat-card.pass .value {{ color: var(--accent-green); }}
        .stat-card.fail .value {{ color: var(--accent-red); }}
        .stat-card.info .value {{ color: var(--accent-blue); }}
        
        .section {{
            background: var(--bg-secondary);
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            border: 1px solid var(--border-color);
        }}
        .section h2 {{
            font-size: 1.1rem;
            margin-bottom: 16px;
            color: var(--accent-blue);
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .viewer-links {{
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .viewer-link {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 12px 20px;
            background: var(--bg-card);
            border-radius: 8px;
            text-decoration: none;
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            transition: all 0.2s;
        }}
        .viewer-link:hover {{
            border-color: var(--accent-blue);
            background: #1a4670;
        }}
        .viewer-link .icon {{
            font-size: 1.5rem;
        }}
        .viewer-link .label {{
            font-weight: 500;
        }}
        .viewer-link .desc {{
            font-size: 0.75rem;
            color: var(--text-secondary);
        }}
        
        .response-preview {{
            background: var(--bg-card);
            padding: 16px;
            border-radius: 8px;
            font-family: ui-monospace, monospace;
            font-size: 0.9rem;
            white-space: pre-wrap;
            word-break: break-word;
            border-left: 3px solid var(--accent-purple);
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
        }}
        th, td {{
            padding: 10px 12px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}
        th {{
            background: var(--bg-card);
            font-weight: 500;
            color: var(--text-secondary);
        }}
        tr:hover td {{
            background: rgba(96, 165, 250, 0.1);
        }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 500;
        }}
        .badge.pass {{ background: var(--accent-green); color: #000; }}
        .badge.fail {{ background: var(--accent-red); color: #fff; }}
        .badge.lambda {{ background: #ff9900; color: #000; }}
        .badge.bedrock {{ background: #8b5cf6; color: #fff; }}
        .badge.agent {{ background: #00a4ef; color: #fff; }}
        .badge.default {{ background: #6b7280; color: #fff; }}
        
        .invariants-list {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}
        .invariant {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            background: var(--bg-card);
            border-radius: 6px;
        }}
        .invariant.pass {{ border-left: 3px solid var(--accent-green); }}
        .invariant.fail {{ border-left: 3px solid var(--accent-red); }}
        .invariant .icon {{ font-size: 1.1rem; }}
        .invariant .name {{ font-family: ui-monospace, monospace; }}
        
        .tag-list {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }}
        .tag {{
            background: var(--bg-card);
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 0.8rem;
            font-family: ui-monospace, monospace;
        }}
        
        footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid var(--border-color);
            color: var(--text-secondary);
            font-size: 0.8rem;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>
                📊 {case_id}
                <span class="status {'pass' if all_pass else 'fail'}">{'PASS' if all_pass else 'FAIL'}</span>
            </h1>
            <div class="meta">{case_name} • {entrypoint} • {mode}</div>
        </div>
        <div class="meta">{timestamp}</div>
    </div>
    
    <div class="stats-grid">
        <div class="stat-card info">
            <div class="value">{span_count}</div>
            <div class="label">Spans</div>
        </div>
        <div class="stat-card info">
            <div class="value">{len(components)}</div>
            <div class="label">Components</div>
        </div>
        <div class="stat-card {'pass' if inv_passed == inv_total else 'fail'}">
            <div class="value">{inv_passed}/{inv_total}</div>
            <div class="label">Invariants</div>
        </div>
        <div class="stat-card {'fail' if error_spans else 'pass'}">
            <div class="value">{len(error_spans)}</div>
            <div class="label">Errors</div>
        </div>
    </div>
    
    <div class="section">
        <h2>🔗 Visualizations</h2>
        <div class="viewer-links">
            <a href="{artifacts_rel}/trace-viewer.html" class="viewer-link">
                <span class="icon">🔍</span>
                <div>
                    <div class="label">Trace Viewer</div>
                    <div class="desc">Interactive sequence diagram</div>
                </div>
            </a>
            <a href="{artifacts_rel}/timeline.html" class="viewer-link">
                <span class="icon">⏱️</span>
                <div>
                    <div class="label">Timeline</div>
                    <div class="desc">Temporal span visualization</div>
                </div>
            </a>
            <a href="{artifacts_rel}/sequence.html" class="viewer-link">
                <span class="icon">📐</span>
                <div>
                    <div class="label">Sequence Diagram</div>
                    <div class="desc">Legacy HTML diagram</div>
                </div>
            </a>
        </div>
    </div>
    
    {f'''<div class="section">
        <h2>💬 Agent Response</h2>
        <div class="response-preview">{html.escape(response_preview) if response_preview else "(No response captured)"}</div>
    </div>''' if agent_response else ''}
    
    <div class="section">
        <h2>✅ Invariants</h2>
        <div class="invariants-list">
            {''.join(f'''<div class="invariant {'pass' if r.passed else 'fail'}">
                <span class="icon">{'✅' if r.passed else '❌'}</span>
                <span class="name">{r.name}</span>
            </div>''' for r in (invariant_results or []))}
        </div>
    </div>
    
    <div class="section">
        <h2>🏷️ Components</h2>
        <div class="tag-list">
            {''.join(f'<span class="tag">{c}</span>' for c in components)}
        </div>
    </div>
    
    <div class="section">
        <h2>📋 Spans</h2>
        <table>
            <thead>
                <tr>
                    <th>Span ID</th>
                    <th>Component</th>
                    <th>Operation</th>
                    <th>Latency</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                {''.join(_render_span_row(s) for s in trace.spans)}
            </tbody>
        </table>
    </div>
    
    <div class="section">
        <h2>📁 Artifacts</h2>
        <table>
            <tbody>
                <tr><td><a href="{artifacts_rel}/spans.jsonl" style="color: var(--accent-blue);">spans.jsonl</a></td><td>Raw span data (JSONL)</td></tr>
                <tr><td><a href="{artifacts_rel}/sequence.mmd" style="color: var(--accent-blue);">sequence.mmd</a></td><td>Mermaid sequence diagram</td></tr>
                <tr><td><a href="{artifacts_rel}/report.md" style="color: var(--accent-blue);">report.md</a></td><td>Markdown report</td></tr>
                <tr><td><a href="{artifacts_rel}/payloads/" style="color: var(--accent-blue);">payloads/</a></td><td>Request/response JSON files</td></tr>
            </tbody>
        </table>
    </div>
    
    <footer>
        Generated by ITK (Integration Test Kit) • <a href="https://github.com/spidey99/support-bot-integration-test-kit" style="color: var(--accent-blue);">GitHub</a>
    </footer>
</body>
</html>"""


def _render_span_row(s: Span) -> str:
    """Render a single span table row."""
    component_type = s.component.split(":")[0] if ":" in s.component else s.component
    badge_class = component_type.lower() if component_type.lower() in ("lambda", "bedrock", "agent") else "default"
    
    # Calculate latency from ts_start/ts_end if available
    latency = "—"
    if s.ts_start and s.ts_end:
        try:
            from datetime import datetime
            start = datetime.fromisoformat(s.ts_start.replace("Z", "+00:00"))
            end = datetime.fromisoformat(s.ts_end.replace("Z", "+00:00"))
            ms = (end - start).total_seconds() * 1000
            latency = f"{ms:.1f}ms"
        except (ValueError, TypeError):
            pass
    
    status = "❌ Error" if s.error else "✅ OK"
    return f"""<tr>
        <td><code>{s.span_id[:16]}...</code></td>
        <td><span class="badge {badge_class}">{component_type}</span> {s.component}</td>
        <td>{s.operation}</td>
        <td>{latency}</td>
        <td>{status}</td>
    </tr>"""


def _build_comparison_markdown(result: "CompareResult") -> str:
    """Build a markdown comparison report."""
    lines: list[str] = ["# ITK Comparison Report", ""]

    # Summary
    lines.extend(
        [
            "## Summary",
            f"- **Baseline**: {result.baseline_label}",
            f"- **Current**: {result.current_label}",
            f"- **Total paths compared**: {len(result.deltas)}",
            "",
        ]
    )

    # Verdict
    if result.has_regressions:
        lines.extend(
            [
                "### ❌ REGRESSIONS DETECTED",
                "",
            ]
        )
        if result.missing_paths:
            lines.append(f"- **{len(result.missing_paths)}** path(s) missing in current")
        if result.error_regressions:
            lines.append(f"- **{len(result.error_regressions)}** path(s) with increased errors")
        lines.append("")
    else:
        lines.extend(
            [
                "### ✅ No regressions detected",
                "",
            ]
        )

    # New paths
    if result.new_paths:
        lines.extend(
            [
                "## 🆕 New Paths",
                f"Paths present in current but not in baseline ({len(result.new_paths)}):",
                "",
            ]
        )
        for d in result.new_paths:
            lines.append(f"- `{d.signature.signature_string}` (count: {d.current_count})")
        lines.append("")

    # Missing paths
    if result.missing_paths:
        lines.extend(
            [
                "## ⚠️ Missing Paths",
                f"Paths present in baseline but not in current ({len(result.missing_paths)}):",
                "",
            ]
        )
        for d in result.missing_paths:
            lines.append(f"- `{d.signature.signature_string}` (was: {d.baseline_count})")
        lines.append("")

    # Latency changes
    significant = result.significant_latency_changes
    if significant:
        lines.extend(
            [
                "## ⏱️ Significant Latency Changes (>10%)",
                "",
                "| Path | Baseline (ms) | Current (ms) | Delta |",
                "|------|---------------|--------------|-------|",
            ]
        )
        for d in significant:
            delta_str = f"{d.latency_delta_pct:+.1f}%"
            lines.append(
                f"| `{d.signature.signature_string[:40]}...` | "
                f"{d.baseline_avg_latency_ms:.1f} | "
                f"{d.current_avg_latency_ms:.1f} | "
                f"{delta_str} |"
            )
        lines.append("")

    # Error changes
    if result.error_regressions:
        lines.extend(
            [
                "## 🔴 Error Rate Increases",
                "",
                "| Path | Baseline Rate | Current Rate | Delta |",
                "|------|---------------|--------------|-------|",
            ]
        )
        for d in result.error_regressions:
            lines.append(
                f"| `{d.signature.signature_string[:40]}...` | "
                f"{d.error_rate_baseline:.1%} | "
                f"{d.error_rate_current:.1%} | "
                f"{d.error_rate_delta:+.1%} |"
            )
        lines.append("")

    # Stable paths
    stable = [
        d for d in result.changed_paths
        if abs(d.latency_delta_pct) <= 10.0 and d.error_rate_delta <= 0.0
    ]
    if stable:
        lines.extend(
            [
                "## ✅ Stable Paths",
                f"{len(stable)} path(s) with no significant changes.",
                "",
            ]
        )

    return "\n".join(lines)
