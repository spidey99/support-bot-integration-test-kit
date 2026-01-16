from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from itk.assertions.invariants import run_invariants
from itk.cases.loader import load_case
from itk.config import Config, Mode, load_config, set_config
from itk.diagrams.mermaid_seq import render_mermaid_sequence
from itk.logs.parse import load_fixture_jsonl_as_spans
from itk.trace.build_trace import build_trace_from_spans
from itk.trace.span_model import Span
from itk.trace.trace_model import Trace
from itk.utils.artifacts import (
    write_run_artifacts,
    write_audit_artifacts,
    write_compare_artifacts,
    disable_redaction,
)


def _resolve_fixture_for_case(case_path: Path, offline: bool) -> Path:
    """Resolve the fixture path for a given case.

    In offline mode, we look for:
    1. Explicit fixture_path in the case YAML
    2. A sibling .jsonl file with the same name as the case
    3. A fixture in fixtures/logs/ matching the case ID
    """
    case = load_case(case_path)

    # Option 1: explicit in case
    if case.fixture_path and case.fixture_path.exists():
        return case.fixture_path

    # Option 2: sibling file
    sibling = case_path.with_suffix(".jsonl")
    if sibling.exists():
        return sibling

    # Option 3: look in fixtures/logs/
    # Walk up to find the itk root (contains schemas/)
    current = case_path.resolve().parent
    for _ in range(10):
        fixtures_dir = current / "fixtures" / "logs"
        if fixtures_dir.exists():
            # Try case ID or sample
            candidate = fixtures_dir / f"{case.id}.jsonl"
            if candidate.exists():
                return candidate
            # Fall back to sample_run_001.jsonl for now
            sample = fixtures_dir / "sample_run_001.jsonl"
            if sample.exists():
                return sample
            break
        current = current.parent

    raise FileNotFoundError(
        f"No fixture found for case '{case.id}'. "
        f"Provide a fixture path in the case YAML or create {case_path.with_suffix('.jsonl')}"
    )


# Output format options
OUTPUT_FORMATS = ["all", "html", "mermaid", "json", "svg"]


def _cmd_render_fixture(args: argparse.Namespace) -> int:
    fixture_path = Path(args.fixture)
    out_dir = Path(args.out)
    output_format = getattr(args, "format", "all")

    spans = load_fixture_jsonl_as_spans(fixture_path)
    trace = build_trace_from_spans(spans)

    mermaid = render_mermaid_sequence(trace)
    
    # Write artifacts based on format
    if output_format == "all":
        write_run_artifacts(out_dir=out_dir, trace=trace, mermaid=mermaid)
        print(f"Artifacts written to {out_dir}")
    elif output_format == "html":
        from itk.diagrams.trace_viewer import render_trace_viewer
        out_dir.mkdir(parents=True, exist_ok=True)
        html = render_trace_viewer(trace, title="Trace Viewer")
        (out_dir / "trace-viewer.html").write_text(html, encoding="utf-8")
        print(f"HTML written to {out_dir / 'trace-viewer.html'}")
    elif output_format == "mermaid":
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "sequence.mmd").write_text(mermaid, encoding="utf-8")
        print(f"Mermaid written to {out_dir / 'sequence.mmd'}")
    elif output_format == "json":
        out_dir.mkdir(parents=True, exist_ok=True)
        spans_data = [_span_to_dict(s) for s in trace.spans]
        (out_dir / "spans.json").write_text(
            json.dumps(spans_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"JSON written to {out_dir / 'spans.json'}")
    elif output_format == "svg":
        from itk.diagrams.trace_viewer import render_trace_viewer
        from itk.diagrams.timeline_view import render_mini_timeline
        out_dir.mkdir(parents=True, exist_ok=True)
        # Export full SVG sequence diagram
        svg = _render_full_svg(trace)
        (out_dir / "sequence.svg").write_text(svg, encoding="utf-8")
        # Also export timeline
        timeline_svg = render_mini_timeline(trace, width=800, height=400)
        (out_dir / "timeline.svg").write_text(timeline_svg, encoding="utf-8")
        print(f"SVG files written to {out_dir}")
    
    return 0


def _span_to_dict(span: Span) -> dict:
    """Convert a Span to a JSON-serializable dict."""
    return {
        "span_id": span.span_id,
        "parent_span_id": span.parent_span_id,
        "component": span.component,
        "operation": span.operation,
        "ts_start": span.ts_start,
        "ts_end": span.ts_end,
        "attempt": span.attempt,
        "request": span.request,
        "response": span.response,
        "error": span.error,
    }


def _render_full_svg(trace: Trace) -> str:
    """Render a full SVG sequence diagram (standalone, no HTML wrapper)."""
    from itk.diagrams.trace_viewer import (
        _extract_participants,
        _extract_messages,
        _build_span_tree,
        _render_svg_participant,
        _render_svg_message,
        PARTICIPANT_WIDTH,
        PARTICIPANT_GAP,
        PARTICIPANT_HEADER_HEIGHT,
        MESSAGE_HEIGHT,
        PADDING,
    )
    
    participants = _extract_participants(trace)
    messages = _extract_messages(trace, participants)
    span_tree = _build_span_tree(trace)
    
    # Calculate dimensions
    num_participants = len(participants) if participants else 1
    num_messages = len(messages) if messages else 1
    
    svg_width = PADDING * 2 + num_participants * (PARTICIPANT_WIDTH + PARTICIPANT_GAP)
    svg_height = PADDING * 2 + PARTICIPANT_HEADER_HEIGHT + num_messages * MESSAGE_HEIGHT + 50
    lifeline_height = num_messages * MESSAGE_HEIGHT + 50
    
    # Render participants
    participant_svg = "\n".join(
        _render_svg_participant(p, lifeline_height) for p in participants
    )
    
    # Render messages
    message_svg = "\n".join(
        _render_svg_message(m, span_tree) for m in messages
    )
    
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_width} {svg_height}" width="{svg_width}" height="{svg_height}">
    <style>
        .participant-box {{ fill: #f3f4f6; stroke: #374151; stroke-width: 2; }}
        .participant-label {{ font-family: sans-serif; font-size: 12px; font-weight: 600; }}
        .lifeline {{ stroke: #9ca3af; stroke-dasharray: 4 2; }}
        .message-line {{ stroke: #374151; stroke-width: 1.5; }}
        .message-line.error {{ stroke: #ef4444; }}
        .message-label {{ font-family: sans-serif; font-size: 11px; }}
        .latency-label {{ font-family: monospace; font-size: 9px; fill: #6b7280; }}
        .retry-badge {{ font-family: sans-serif; font-size: 9px; fill: #f59e0b; }}
        .activation-box {{ fill: #dbeafe; stroke: #3b82f6; }}
        .status-indicator {{ font-size: 12px; }}
    </style>
    <defs>
        <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#374151" />
        </marker>
        <marker id="arrowhead-return" markerWidth="10" markerHeight="7" refX="1" refY="3.5" orient="auto">
            <polygon points="10 0, 0 3.5, 10 7" fill="#374151" />
        </marker>
    </defs>
    <g class="diagram">
        {participant_svg}
        {message_svg}
    </g>
</svg>'''


def _cmd_run(args: argparse.Namespace) -> int:
    """Run a case.

    In dev-fixtures mode: load fixture, build trace, emit artifacts.
    In live mode (Tier 3): replay entrypoint, pull logs, build trace, emit artifacts.
    """
    case_path = Path(args.case)
    out_dir = Path(args.out)
    no_redact = getattr(args, "no_redact", False)

    # Load config with mode from CLI or .env
    mode_arg = getattr(args, "mode", None)
    env_file = getattr(args, "env_file", None)
    config = load_config(mode=mode_arg, env_file=env_file)
    set_config(config)

    if no_redact:
        disable_redaction()

    if not case_path.exists():
        print(f"ERROR: Case file not found: {case_path}", file=sys.stderr)
        return 1

    case = load_case(case_path)

    if config.is_dev_fixtures():
        # Dev-fixtures mode: use fixture
        try:
            fixture_path = _resolve_fixture_for_case(case_path, offline=True)
        except FileNotFoundError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        spans = load_fixture_jsonl_as_spans(fixture_path)
        trace = build_trace_from_spans(spans)
    else:
        # Live mode: Tier 3 implementation needed
        raise NotImplementedError(
            "Live mode requires AWS access + work repo configuration. "
            "Use --mode dev-fixtures for fixture-based runs, or implement in Tier 3."
        )

    # Run invariant checks
    invariant_results = run_invariants(trace)

    # Render mermaid
    mermaid = render_mermaid_sequence(trace)

    # Write artifacts
    write_run_artifacts(
        out_dir=out_dir,
        trace=trace,
        mermaid=mermaid,
        case=case,
        invariant_results=invariant_results,
    )

    # Report summary
    passed = all(r.passed for r in invariant_results)
    print(f"Case: {case.id} ({case.name})")
    print(f"Spans: {len(trace.spans)}")
    print(f"Invariants: {'PASS' if passed else 'FAIL'}")
    print(f"Artifacts: {out_dir}")

    return 0 if passed else 1


def _cmd_derive(args: argparse.Namespace) -> int:
    raise NotImplementedError(
        "Tier 3 command: derives cases from CloudWatch logs. Implement in work environment."
    )


def _cmd_audit(args: argparse.Namespace) -> int:
    """Audit logging gaps for a case.

    In dev-fixtures mode: analyze fixture spans for missing fields.
    In live mode (Tier 3): pull logs and analyze.
    """
    case_path = Path(args.case)
    out_dir = Path(args.out)

    # Load config with mode from CLI or .env
    mode_arg = getattr(args, "mode", None)
    env_file = getattr(args, "env_file", None)
    config = load_config(mode=mode_arg, env_file=env_file)
    set_config(config)

    if not case_path.exists():
        print(f"ERROR: Case file not found: {case_path}", file=sys.stderr)
        return 1

    case = load_case(case_path)

    if config.is_dev_fixtures():
        try:
            fixture_path = _resolve_fixture_for_case(case_path, offline=True)
        except FileNotFoundError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        spans = load_fixture_jsonl_as_spans(fixture_path)
        trace = build_trace_from_spans(spans)
    else:
        raise NotImplementedError(
            "Live audit requires AWS access. Use --mode dev-fixtures for fixture-based audit."
        )

    # Perform audit
    from itk.audit.gap_detector import detect_gaps

    gaps = detect_gaps(trace, case)

    # Write audit artifacts
    write_audit_artifacts(out_dir=out_dir, trace=trace, gaps=gaps, case=case)

    # Report summary
    print(f"Case: {case.id}")
    print(f"Spans analyzed: {len(trace.spans)}")
    print(f"Gaps detected: {len(gaps)}")
    print(f"Audit artifacts: {out_dir}")

    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    """Compare two run outputs and produce a delta report.

    Loads spans.jsonl from both directories and compares path signatures,
    latencies, and error rates.
    """
    dir_a = Path(args.a)
    dir_b = Path(args.b)
    out_dir = Path(args.out)

    # Load spans from both directories
    spans_a_path = dir_a / "spans.jsonl"
    spans_b_path = dir_b / "spans.jsonl"

    if not spans_a_path.exists():
        print(f"ERROR: spans.jsonl not found in {dir_a}", file=sys.stderr)
        return 1

    if not spans_b_path.exists():
        print(f"ERROR: spans.jsonl not found in {dir_b}", file=sys.stderr)
        return 1

    # Load and build traces
    def load_spans_jsonl(path: Path) -> list[Span]:
        spans: list[Span] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            spans.append(Span(**data))
        return spans

    spans_a = load_spans_jsonl(spans_a_path)
    spans_b = load_spans_jsonl(spans_b_path)

    trace_a = Trace(spans=spans_a)
    trace_b = Trace(spans=spans_b)

    # Compare
    from itk.compare.compare import compare_traces

    result = compare_traces(
        baseline=trace_a,
        current=trace_b,
        baseline_label=str(dir_a),
        current_label=str(dir_b),
    )

    # Write artifacts
    write_compare_artifacts(out_dir=out_dir, result=result)

    # Report summary
    print(f"Baseline: {dir_a}")
    print(f"Current: {dir_b}")
    print(f"New paths: {len(result.new_paths)}")
    print(f"Missing paths: {len(result.missing_paths)}")
    print(f"Regressions: {'YES' if result.has_regressions else 'NO'}")
    print(f"Comparison artifacts: {out_dir}")

    return 1 if result.has_regressions else 0


def _cmd_generate_fixture(args: argparse.Namespace) -> int:
    """Generate a JSONL fixture from a YAML definition."""
    yaml_path = Path(args.definition)
    output_path = Path(args.out)

    if not yaml_path.exists():
        print(f"ERROR: Definition file not found: {yaml_path}", file=sys.stderr)
        return 1

    from itk.fixtures import generate_fixture_file

    try:
        count = generate_fixture_file(yaml_path, output_path)
        print(f"Generated {count} spans to {output_path}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def _cmd_validate(args: argparse.Namespace) -> int:
    """Validate case YAML or fixture JSONL against schemas."""
    from itk.validation import validate_case, validate_fixture

    results = []

    # Validate case files
    case_paths = getattr(args, "case", None) or []
    for case_path in case_paths:
        result = validate_case(case_path)
        results.append(result)
        print(result.summary())

    # Validate fixture files
    fixture_paths = getattr(args, "fixture", None) or []
    for fixture_path in fixture_paths:
        result = validate_fixture(fixture_path)
        results.append(result)
        print(result.summary())

    if not results:
        print("No files specified. Use --case and/or --fixture.", file=sys.stderr)
        return 1

    # Return 0 if all valid, 1 if any invalid
    return 0 if all(r.valid for r in results) else 1


def _cmd_scan(args: argparse.Namespace) -> int:
    """Scan a codebase for components and compare against test coverage."""
    from itk.scanner import (
        scan_codebase,
        compare_with_cases,
        generate_coverage_report,
        generate_skeleton_cases,
    )

    repo_path = Path(args.repo)
    out_dir = Path(args.out)

    if not repo_path.exists():
        print(f"ERROR: Repository path not found: {repo_path}", file=sys.stderr)
        return 1

    # Resolve cases and fixtures directories
    # First check if user provided explicit paths
    cases_dir = Path(args.cases) if args.cases else None
    fixtures_dir = Path(args.fixtures) if args.fixtures else None

    # If not provided, try to find them relative to current working directory
    # (assuming we're in an itk workspace)
    if cases_dir is None:
        candidate = Path.cwd() / "cases"
        if candidate.exists():
            cases_dir = candidate

    if fixtures_dir is None:
        candidate = Path.cwd() / "fixtures" / "logs"
        if candidate.exists():
            fixtures_dir = candidate

    print(f"Scanning: {repo_path}")
    print(f"Cases dir: {cases_dir or '(not found)'}")
    print(f"Fixtures dir: {fixtures_dir or '(not found)'}")
    print()

    # Scan the codebase
    result = scan_codebase(repo_path)

    print(f"Found {len(result.components)} components:")
    for comp in result.components:
        print(f"  - {comp.component_type}: {comp.name} ({comp.file_path}:{comp.line_number})")

    print()
    print(f"Found {len(result.branches)} branches:")
    for branch in result.branches[:5]:  # Show first 5
        print(f"  - {branch.branch_type} at {branch.file_path}:{branch.line_number}")
    if len(result.branches) > 5:
        print(f"  ... and {len(result.branches) - 5} more")

    print()
    print(f"Found {len(result.logging_gaps)} potential logging gaps:")
    for gap in result.logging_gaps[:10]:  # Show first 10
        print(f"  - {gap.gap_type} at {gap.file_path}:{gap.line_number}")
    if len(result.logging_gaps) > 10:
        print(f"  ... and {len(result.logging_gaps) - 10} more")

    # Compare with cases if we have a cases directory
    if cases_dir and cases_dir.exists():
        print()
        coverage = compare_with_cases(result, cases_dir, fixtures_dir)
        total = len(result.components)
        covered = len(coverage["covered"])
        print(f"Coverage: {covered}/{total} components")
        print(f"  Covered: {covered}")
        print(f"  Uncovered: {len(coverage['uncovered'])}")
    else:
        coverage = {"covered": [], "uncovered": [], "extra": []}

    # Write artifacts
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write scan result JSON
    scan_json = out_dir / "scan_result.json"
    scan_json.write_text(
        json.dumps(
            {
                "repo_path": str(repo_path),
                "scanned_files": result.scanned_files,
                "components": [
                    {
                        "component_type": c.component_type,
                        "component_id": c.component_id,
                        "name": c.name,
                        "file_path": str(c.file_path),
                        "line_number": c.line_number,
                        "handler": c.handler,
                        "details": c.details,
                    }
                    for c in result.components
                ],
                "branches": [
                    {
                        "branch_type": b.branch_type,
                        "condition": b.condition,
                        "file_path": str(b.file_path),
                        "line_number": b.line_number,
                        "parent_function": b.parent_function,
                        "has_logging": b.has_logging,
                    }
                    for b in result.branches
                ],
                "logging_gaps": [
                    {
                        "gap_type": g.gap_type,
                        "file_path": str(g.file_path),
                        "line_number": g.line_number,
                        "function_name": g.function_name,
                        "suggestion": g.suggestion,
                    }
                    for g in result.logging_gaps
                ],
                "coverage": coverage,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Write coverage report markdown
    report = generate_coverage_report(result, coverage)
    report_path = out_dir / "coverage_report.md"
    report_path.write_text(report, encoding="utf-8")

    # Generate skeleton cases if requested
    if args.generate_skeletons and coverage["uncovered"]:
        skeletons = generate_skeleton_cases(result, coverage["uncovered"])
        skeletons_dir = out_dir / "skeleton_cases"
        skeletons_dir.mkdir(parents=True, exist_ok=True)
        
        import yaml
        for skeleton in skeletons:
            skeleton_file = skeletons_dir / f"{skeleton['id']}.yaml"
            skeleton_file.write_text(
                yaml.dump(skeleton, default_flow_style=False, sort_keys=False),
                encoding="utf-8",
            )
        print()
        print(f"Generated {len(skeletons)} skeleton case files in {skeletons_dir}")

    print()
    print(f"Artifacts written to {out_dir}")
    print(f"  - scan_result.json")
    print(f"  - coverage_report.md")

    return 0


def _cmd_suite(args: argparse.Namespace) -> int:
    """Run a test suite and generate consolidated report."""
    from itk.report.suite_runner import run_suite
    from itk.report.hierarchical_report import write_hierarchical_report

    cases_dir = Path(args.cases_dir)
    out_dir = Path(args.out)
    suite_name = getattr(args, "name", None)
    use_flat_report = getattr(args, "flat", False)

    # Load config with mode from CLI or .env
    mode_arg = getattr(args, "mode", None)
    env_file = getattr(args, "env_file", None)
    config = load_config(mode=mode_arg, env_file=env_file)
    set_config(config)

    if not cases_dir.exists():
        print(f"ERROR: Cases directory not found: {cases_dir}", file=sys.stderr)
        return 1

    print(f"Running suite: {suite_name or cases_dir.name}")
    print(f"Cases dir: {cases_dir}")
    print(f"Mode: {config.mode.value}")
    print()

    # Progress callback
    def on_case_complete(result):
        status_icon = {
            "passed": "✅",
            "failed": "❌",
            "error": "⚠️",
            "skipped": "⏭️",
        }.get(result.status.value, "?")
        print(f"  {status_icon} {result.case_id} ({result.duration_ms:.0f}ms)")

    # Run suite
    suite = run_suite(
        cases_dir=cases_dir,
        out_dir=out_dir,
        suite_name=suite_name,
        on_case_complete=on_case_complete,
    )

    # Write report (use hierarchical by default, flat with --flat flag)
    if use_flat_report:
        from itk.report.html_report import write_suite_report
        write_suite_report(suite, out_dir)
    else:
        write_hierarchical_report(suite, out_dir)

    # Summary
    print()
    print(f"Suite: {suite.suite_name}")
    print(f"Results: {suite.passed_count}/{suite.total_cases} passed ({suite.pass_rate:.0f}%)")
    print(f"Duration: {suite.duration_ms:.0f}ms")
    print(f"Report: {out_dir / 'index.html'}")

    return 0 if suite.all_passed else 1


def _cmd_soak(args: argparse.Namespace) -> int:
    """Run a soak/endurance test with adaptive rate control."""
    from itk.soak import SoakConfig, SoakMode
    from itk.soak.soak_runner import run_soak_with_case
    from itk.soak.soak_report import write_soak_report

    case_path = Path(args.case)
    out_dir = Path(args.out)
    duration = getattr(args, "duration", None)
    iterations = getattr(args, "iterations", None)
    initial_rate = getattr(args, "initial_rate", 1.0)
    summary_only = getattr(args, "summary_only", False)
    detailed = not summary_only  # --summary-only disables detailed mode

    # Load config with mode from CLI or .env
    mode_arg = getattr(args, "mode", None)
    env_file = getattr(args, "env_file", None)
    config = load_config(mode=mode_arg, env_file=env_file)
    set_config(config)

    if not case_path.exists():
        print(f"ERROR: Case file not found: {case_path}", file=sys.stderr)
        return 1

    # Validate duration vs iterations
    if duration and iterations:
        print("ERROR: Specify --duration or --iterations, not both", file=sys.stderr)
        return 1

    if not duration and not iterations:
        # Default to 10 iterations for quick test
        iterations = 10

    # Build soak config
    if duration:
        soak_mode = SoakMode.DURATION
        soak_config = SoakConfig(
            mode=soak_mode,
            duration_seconds=duration,
            initial_rate=initial_rate,
        )
    else:
        soak_mode = SoakMode.ITERATIONS
        soak_config = SoakConfig(
            mode=soak_mode,
            iterations=iterations,
            initial_rate=initial_rate,
        )

    print(f"Soak test: {case_path.stem}")
    print(f"Mode: {soak_mode.value} ({duration}s)" if duration else f"Mode: {soak_mode.value} ({iterations} iterations)")
    print(f"Initial rate: {initial_rate} req/s")
    print(f"Detailed: {'yes (per-iteration artifacts)' if detailed else 'no (summary only)'}")
    print()

    # Progress callback with status icons (ASCII-safe for Windows)
    def on_iteration(iteration):
        status_icons = {
            "passed": "[PASS]",
            "warning": "[WARN]",
            "failed": "[FAIL]",
            "error": "[ERR!]",
        }
        icon = status_icons.get(iteration.status, "[????]")
        throttle = " [THROTTLE]" if iteration.throttle_events else ""
        retry_info = f" (retries: {iteration.retry_count})" if iteration.retry_count > 0 else ""
        print(f"  {icon} Iteration {iteration.iteration}: {iteration.duration_ms:.0f}ms{retry_info}{throttle}")

    # Run soak
    result = run_soak_with_case(
        case_path=case_path,
        config=soak_config,
        out_dir=out_dir,
        mode=config.mode.value,
        detailed=detailed,
        on_iteration=on_iteration,
    )

    # Write report
    report_path = write_soak_report(result, out_dir)

    # Summary with consistency metrics
    print()
    print(f"Soak complete: {result.soak_id}")
    print(f"Iterations: {result.total_iterations}")
    print(f"Pass rate: {result.pass_rate * 100:.1f}%")
    print(f"Consistency: {result.consistency_score * 100:.1f}% (clean passes / total passes)")
    print(f"  Clean: {result.total_clean_passes} | Warnings: {result.total_warnings} | Failed: {result.total_failures}")
    print(f"Retries: {result.total_retries} total (avg {result.avg_retries_per_iteration:.1f}/iter, max {result.max_retries})")
    print(f"Throttle events: {len(result.all_throttle_events)}")
    print(f"Final rate: {result.final_rate:.2f} req/s")
    print(f"Report: {report_path}")

    # Return 0 if pass rate is acceptable (>90%)
    return 0 if result.pass_rate >= 0.9 else 1


def _cmd_serve(args: argparse.Namespace) -> int:
    """Serve artifacts directory with live reload."""
    import http.server
    import socketserver
    import threading
    import time
    import webbrowser
    from functools import partial
    
    directory = Path(args.directory).resolve()
    port = args.port
    no_browser = getattr(args, "no_browser", False)
    watch = getattr(args, "watch", False)
    
    if not directory.exists():
        print(f"ERROR: Directory not found: {directory}", file=sys.stderr)
        return 1
    
    # Custom handler that serves from the specified directory
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)
        
        def log_message(self, format, *args):
            # Quieter logging
            print(f"  {args[0]}")
        
        def end_headers(self):
            # Add headers to prevent caching for live reload
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            super().end_headers()
    
    # Try to find an available port
    for attempt in range(10):
        try:
            with socketserver.TCPServer(("", port), Handler) as httpd:
                url = f"http://localhost:{port}"
                
                print(f"Serving artifacts from: {directory}")
                print(f"URL: {url}")
                print()
                
                # Determine best file to open
                index_file = None
                for candidate in ["index.html", "trace-viewer.html", "timeline.html", "sequence.html"]:
                    if (directory / candidate).exists():
                        index_file = candidate
                        break
                
                if index_file:
                    open_url = f"{url}/{index_file}"
                else:
                    open_url = url
                
                if not no_browser:
                    print(f"Opening: {open_url}")
                    webbrowser.open(open_url)
                
                print("Press Ctrl+C to stop")
                print()
                
                if watch:
                    print("Watching for file changes...")
                    # Simple file watcher - track mtimes
                    last_check = time.time()
                    mtimes: dict[str, float] = {}
                    
                    def check_changes():
                        nonlocal last_check, mtimes
                        changed = False
                        for f in directory.rglob("*"):
                            if f.is_file():
                                mtime = f.stat().st_mtime
                                key = str(f)
                                if key in mtimes and mtimes[key] != mtime:
                                    print(f"  Changed: {f.name}")
                                    changed = True
                                mtimes[key] = mtime
                        return changed
                    
                    # Initial scan
                    check_changes()
                
                try:
                    httpd.serve_forever()
                except KeyboardInterrupt:
                    print("\nStopping server...")
                    return 0
                    
        except OSError as e:
            if "Address already in use" in str(e) or e.errno == 10048:  # Windows error
                port += 1
                continue
            raise
    
    print(f"ERROR: Could not find available port after 10 attempts", file=sys.stderr)
    return 1


def main() -> None:
    p = argparse.ArgumentParser(
        prog="itk",
        description="Integration Test Kit: sequence diagram generation and log analysis",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # render-fixture (Tier 2 offline)
    p_fx = sub.add_parser(
        "render-fixture",
        help="Offline: render sequence diagram from fixture logs",
    )
    p_fx.add_argument("--fixture", required=True, help="Path to a JSONL fixture file")
    p_fx.add_argument("--out", required=True, help="Output directory for artifacts")
    p_fx.add_argument(
        "--format",
        choices=OUTPUT_FORMATS,
        default="all",
        help="Output format: all (default), html, mermaid, json, or svg",
    )
    p_fx.set_defaults(func=_cmd_render_fixture)

    # run (both dev-fixtures and live)
    p_run = sub.add_parser(
        "run",
        help="Run a case (dev-fixtures mode or live against QA)",
    )
    p_run.add_argument("--case", required=True, help="Path to case YAML file")
    p_run.add_argument("--out", required=True, help="Output directory for artifacts")
    p_run.add_argument(
        "--mode",
        choices=["dev-fixtures", "live"],
        help="Execution mode (default: live, or from ITK_MODE env var)",
    )
    p_run.add_argument(
        "--env-file",
        dest="env_file",
        help="Path to .env file (default: ./.env)",
    )
    p_run.add_argument(
        "--no-redact",
        action="store_true",
        dest="no_redact",
        help="Disable PII redaction in artifacts (use with caution)",
    )
    p_run.set_defaults(func=_cmd_run)

    # derive (Tier 3 only)
    p_der = sub.add_parser(
        "derive",
        help="Tier 3: derive cases from CloudWatch logs",
    )
    p_der.add_argument(
        "--entrypoint",
        required=True,
        choices=["sqs_event", "lambda_direct", "bedrock_agent"],
        help="Entrypoint type to look for",
    )
    p_der.add_argument("--since", required=True, help="Time window (e.g., 24h, 1d)")
    p_der.add_argument("--out", required=True, help="Output directory for derived cases")
    p_der.set_defaults(func=_cmd_derive)

    # audit
    p_aud = sub.add_parser(
        "audit",
        help="Audit logging gaps for a case",
    )
    p_aud.add_argument("--case", required=True, help="Path to case YAML file")
    p_aud.add_argument("--out", required=True, help="Output directory for audit report")
    p_aud.add_argument(
        "--mode",
        choices=["dev-fixtures", "live"],
        help="Execution mode (default: live, or from ITK_MODE env var)",
    )
    p_aud.add_argument(
        "--env-file",
        dest="env_file",
        help="Path to .env file (default: ./.env)",
    )
    p_aud.set_defaults(func=_cmd_audit)

    # compare
    p_cmp = sub.add_parser(
        "compare",
        help="Compare two run outputs",
    )
    p_cmp.add_argument("--a", required=True, help="First run artifacts directory")
    p_cmp.add_argument("--b", required=True, help="Second run artifacts directory")
    p_cmp.add_argument("--out", required=True, help="Output directory for comparison")
    p_cmp.set_defaults(func=_cmd_compare)

    # generate-fixture
    p_gen = sub.add_parser(
        "generate-fixture",
        help="Generate JSONL fixture from YAML definition",
    )
    p_gen.add_argument(
        "--definition", required=True, help="Path to YAML fixture definition file"
    )
    p_gen.add_argument("--out", required=True, help="Output path for JSONL fixture")
    p_gen.set_defaults(func=_cmd_generate_fixture)

    # validate
    p_val = sub.add_parser(
        "validate",
        help="Validate case YAML or fixture JSONL against schemas",
    )
    p_val.add_argument(
        "--case",
        action="append",
        help="Path to case YAML file to validate (can be repeated)",
    )
    p_val.add_argument(
        "--fixture",
        action="append",
        help="Path to fixture JSONL file to validate (can be repeated)",
    )
    p_val.set_defaults(func=_cmd_validate)

    # scan
    p_scan = sub.add_parser(
        "scan",
        help="Scan a codebase for components and compare against test coverage",
    )
    p_scan.add_argument(
        "--repo",
        required=True,
        help="Path to the repository to scan",
    )
    p_scan.add_argument(
        "--out",
        required=True,
        help="Output directory for scan artifacts",
    )
    p_scan.add_argument(
        "--cases",
        help="Path to cases directory (defaults to ./cases)",
    )
    p_scan.add_argument(
        "--fixtures",
        help="Path to fixtures directory (defaults to ./fixtures/logs)",
    )
    p_scan.add_argument(
        "--generate-skeletons",
        action="store_true",
        dest="generate_skeletons",
        help="Generate skeleton case YAMLs for uncovered components",
    )
    p_scan.set_defaults(func=_cmd_scan)

    # suite
    p_suite = sub.add_parser(
        "suite",
        help="Run a test suite (multiple cases) and generate report",
    )
    p_suite.add_argument(
        "--cases-dir",
        required=True,
        dest="cases_dir",
        help="Directory containing case YAML files",
    )
    p_suite.add_argument(
        "--out",
        required=True,
        help="Output directory for suite artifacts",
    )
    p_suite.add_argument(
        "--name",
        help="Suite name (defaults to directory name)",
    )
    p_suite.add_argument(
        "--flat",
        action="store_true",
        help="Use flat table report instead of hierarchical view",
    )
    p_suite.add_argument(
        "--mode",
        choices=["dev-fixtures", "live"],
        help="Execution mode (default: live, or from ITK_MODE env var)",
    )
    p_suite.add_argument(
        "--env-file",
        dest="env_file",
        help="Path to .env file (default: ./.env)",
    )
    p_suite.set_defaults(func=_cmd_suite)

    # soak
    p_soak = sub.add_parser(
        "soak",
        help="Run a soak/endurance test with adaptive rate control",
    )
    p_soak.add_argument(
        "--case",
        required=True,
        help="Path to case YAML file to soak",
    )
    p_soak.add_argument(
        "--out",
        required=True,
        help="Output directory for soak artifacts",
    )
    p_soak.add_argument(
        "--duration",
        type=int,
        help="Run for this many seconds (exclusive with --iterations)",
    )
    p_soak.add_argument(
        "--iterations",
        type=int,
        help="Run this many iterations (exclusive with --duration)",
    )
    p_soak.add_argument(
        "--initial-rate",
        type=float,
        default=1.0,
        dest="initial_rate",
        help="Initial rate in requests/second (default: 1.0)",
    )
    p_soak.add_argument(
        "--detailed",
        action="store_true",
        default=True,
        help="Save per-iteration artifacts for drill-down (default: true)",
    )
    p_soak.add_argument(
        "--summary-only",
        action="store_true",
        dest="summary_only",
        help="Skip per-iteration artifacts (summary report only)",
    )
    p_soak.add_argument(
        "--mode",
        choices=["dev-fixtures", "live"],
        help="Execution mode (default: live, or from ITK_MODE env var)",
    )
    p_soak.add_argument(
        "--env-file",
        dest="env_file",
        help="Path to .env file (default: ./.env)",
    )
    p_soak.set_defaults(func=_cmd_soak)

    # serve
    p_serve = sub.add_parser(
        "serve",
        help="Serve artifacts directory with HTTP server for preview",
    )
    p_serve.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to serve (default: current directory)",
    )
    p_serve.add_argument(
        "--port",
        "-p",
        type=int,
        default=8080,
        help="Port to serve on (default: 8080)",
    )
    p_serve.add_argument(
        "--no-browser",
        action="store_true",
        dest="no_browser",
        help="Don't open browser automatically",
    )
    p_serve.add_argument(
        "--watch",
        "-w",
        action="store_true",
        help="Watch for file changes and log them",
    )
    p_serve.set_defaults(func=_cmd_serve)

    args = p.parse_args()
    rc = args.func(args)
    raise SystemExit(rc)
