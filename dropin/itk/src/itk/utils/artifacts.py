from __future__ import annotations

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
) -> None:
    """Write all artifacts for a run.

    Creates:
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

    # Write report
    report = _build_report(trace=trace, case=case, invariant_results=invariant_results)
    (out_dir / "report.md").write_text(report, encoding="utf-8")


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
