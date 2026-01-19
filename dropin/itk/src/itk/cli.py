from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from itk.assertions.invariants import run_invariants
from itk.cases.loader import load_case
from itk.config import Config, Mode, load_config, set_config
from itk.diagrams.mermaid_seq import render_mermaid_sequence
from itk.logs.parse import load_fixture_jsonl_as_spans, load_realistic_logs_as_spans, parse_cloudwatch_logs
from itk.trace.build_trace import build_trace_from_spans
from itk.trace.span_model import Span
from itk.trace.trace_model import Trace
from itk.utils.artifacts import (
    write_run_artifacts,
    write_audit_artifacts,
    write_compare_artifacts,
    disable_redaction,
)


def _check_startup() -> None:
    """Perform startup checks: Python version, venv, auto-copy .env."""
    import os
    import shutil
    
    # Check Python version
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 10):
        print(f"ERROR: ITK requires Python 3.10 or later.", file=sys.stderr)
        print(f"       You are running Python {major}.{minor}.", file=sys.stderr)
        print(f"       Please upgrade: https://www.python.org/downloads/", file=sys.stderr)
        sys.exit(1)
    
    # Warn if not in venv (but don't block)
    in_venv = sys.prefix != sys.base_prefix
    if not in_venv:
        # Only warn if ITK_SUPPRESS_VENV_WARNING is not set
        if not os.environ.get("ITK_SUPPRESS_VENV_WARNING"):
            print("⚠️  Not running in a virtual environment (recommended).", file=sys.stderr)
            print("   Create one with: python -m venv .venv && .venv\\Scripts\\activate", file=sys.stderr)
            print("   To suppress: set ITK_SUPPRESS_VENV_WARNING=1", file=sys.stderr)
            print("", file=sys.stderr)
    
    # Auto-copy .env.example to .env if missing
    env_file = Path.cwd() / ".env"
    env_example = Path.cwd() / ".env.example"
    if not env_file.exists() and env_example.exists():
        shutil.copy(env_example, env_file)
        print(f"ℹ️  Created .env from .env.example. Edit it with your configuration.", file=sys.stderr)


def _resolve_fixture_for_case(case_path: Path, offline: bool) -> Path:
    """Resolve the fixture path for a given case.

    In offline mode, we look for:
    1. Explicit fixture_path in the case YAML
    2. A sibling .jsonl file with the same name as the case
    3. A fixture in fixtures/logs/ matching the case ID

    Raises:
        FileNotFoundError: With a helpful message explaining how to create a fixture.
    """
    case = load_case(case_path)

    # Option 1: explicit in case
    if case.fixture_path:
        if case.fixture_path.exists():
            return case.fixture_path
        else:
            raise FileNotFoundError(
                f"Fixture path specified in case YAML does not exist: {case.fixture_path}\n\n"
                f"To create a fixture:\n"
                f"  1. Run the case in live mode first: itk run --case {case_path} --mode live --out ./out\n"
                f"  2. Or create a fixture from YAML definition: itk generate-fixture --definition def.yaml --out {case.fixture_path}"
            )

    # Option 2: sibling file
    sibling = case_path.with_suffix(".jsonl")
    if sibling.exists():
        return sibling

    # Option 3: look in fixtures/logs/
    # Walk up to find the itk root (contains schemas/)
    current = case_path.resolve().parent
    fixtures_dir: Path | None = None
    for _ in range(10):
        candidate_dir = current / "fixtures" / "logs"
        if candidate_dir.exists():
            fixtures_dir = candidate_dir
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

    # Build helpful error message
    sibling_path = case_path.with_suffix(".jsonl")
    if fixtures_dir:
        fixture_candidate = fixtures_dir / f"{case.id}.jsonl"
        raise FileNotFoundError(
            f"No fixture found for case '{case.id}'.\n\n"
            f"Expected locations (checked in order):\n"
            f"  1. fixture_path in case YAML (not set)\n"
            f"  2. {sibling_path}\n"
            f"  3. {fixture_candidate}\n\n"
            f"To create a fixture:\n"
            f"  - Run in live mode first: itk run --case {case_path} --mode live --out ./out\n"
            f"  - Create from logs: itk derive --entrypoint bedrock_invoke_agent --since 24h --out ./derived\n"
            f"  - Generate from definition: itk generate-fixture --definition def.yaml --out {sibling_path}\n\n"
            f"See docs/02-test-case-format.md for fixture format details."
        )
    else:
        raise FileNotFoundError(
            f"No fixture found for case '{case.id}'.\n\n"
            f"Create a fixture file at: {sibling_path}\n\n"
            f"To create a fixture:\n"
            f"  - Run in live mode first: itk run --case {case_path} --mode live --out ./out\n"
            f"  - Create from logs: itk derive --entrypoint bedrock_invoke_agent --since 24h --out ./derived\n"
            f"  - Generate from definition: itk generate-fixture --definition def.yaml --out {sibling_path}\n\n"
            f"See docs/02-test-case-format.md for fixture format details."
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


def _resolve_env_var(value: str) -> str:
    """Resolve ${ENV_VAR} placeholders in a string."""
    import os
    import re
    
    pattern = r'\$\{([^}]+)\}'
    
    def replace_var(match: re.Match) -> str:
        var_name = match.group(1)
        env_value = os.environ.get(var_name, "")
        if not env_value:
            raise ValueError(f"Environment variable {var_name} not set")
        return env_value
    
    return re.sub(pattern, replace_var, value)


def _auto_discover_log_groups(region: str, agent_id: str | None = None) -> list[str]:
    """Auto-discover relevant CloudWatch log groups.

    Looks for log groups containing 'lambda', 'agent', 'bot', 'bedrock', etc.
    Returns up to 5 most relevant log groups.
    """
    try:
        import boto3

        logs = boto3.client("logs", region_name=region)
        paginator = logs.get_paginator("describe_log_groups")

        found: list[str] = []
        keywords = ["lambda", "agent", "bot", "bedrock", "api", "orchestr"]

        for page in paginator.paginate(PaginationConfig={"MaxItems": 200}):
            for group in page.get("logGroups", []):
                name = group["logGroupName"].lower()
                # Prioritize log groups matching the agent name
                if agent_id and agent_id.lower() in name:
                    found.insert(0, group["logGroupName"])
                elif any(kw in name for kw in keywords):
                    found.append(group["logGroupName"])

        # Dedupe and limit
        seen = set()
        result = []
        for lg in found:
            if lg not in seen:
                seen.add(lg)
                result.append(lg)
            if len(result) >= 5:
                break

        return result
    except Exception:
        return []


def _run_live_mode(case_path: Path, config: Config) -> tuple[Trace, dict]:
    """Run a case in live mode against AWS resources.
    
    Returns:
        Tuple of (trace, agent_response_dict)
        
    Raises:
        CredentialsExpiredError: If AWS credentials have expired
    """
    import os
    import time
    from datetime import datetime, timezone, timedelta
    
    from itk.logs.cloudwatch_fetch import CredentialsExpiredError
    
    case = load_case(case_path)
    entrypoint = case.entrypoint
    
    if entrypoint.type != "bedrock_invoke_agent":
        raise NotImplementedError(
            f"Live mode for entrypoint type '{entrypoint.type}' not implemented. "
            f"Currently only 'bedrock_invoke_agent' is supported."
        )
    
    # Resolve target from env vars
    target_config = entrypoint.target
    agent_id = _resolve_env_var(target_config.get("agent_id", ""))
    agent_alias_id = _resolve_env_var(target_config.get("agent_alias_id", ""))
    agent_version = _resolve_env_var(target_config.get("agent_version", ""))
    region = target_config.get("region", os.environ.get("AWS_REGION", "us-east-1"))
    
    # Resolve version/alias using version resolver
    from itk.entrypoints.version_resolver import resolve_agent_target
    
    resolved = resolve_agent_target(
        agent_id=agent_id,
        agent_alias_id=agent_alias_id if agent_alias_id else None,
        agent_version=agent_version if agent_version else None,
        region=region,
        offline=False,
    )
    
    print(f"[live] Agent ID: {resolved.agent_id}")
    print(f"[live] Alias ID: {resolved.agent_alias_id}")
    if resolved.resolved_version:
        print(f"[live] Version: {resolved.resolved_version} (via {resolved.resolution_method})")
    print(f"[live] Region: {region}")
    
    # Get payload
    payload = entrypoint.payload
    input_text = payload.get("inputText", "")
    enable_trace = payload.get("enableTrace", True)
    
    if not input_text:
        raise ValueError("entrypoint.payload.inputText is required")
    
    # Mark time before invocation
    start_time = datetime.now(timezone.utc)
    
    # Invoke the agent using resolved alias
    from itk.entrypoints.bedrock_agent import BedrockAgentAdapter, BedrockAgentTarget
    
    target = BedrockAgentTarget(
        agent_id=resolved.agent_id,
        agent_alias_id=resolved.agent_alias_id,
        agent_version=resolved.resolved_version,
        region=region,
    )
    
    adapter = BedrockAgentAdapter(target, offline=False)
    
    print(f"[live] Invoking agent with: {input_text[:50]}...")
    response = adapter.invoke(
        input_text=input_text,
        enable_trace=enable_trace,
    )
    
    end_time = datetime.now(timezone.utc)
    
    print(f"[live] Response: {response.completion[:100]}...")
    print(f"[live] Traces captured: {len(response.traces)}")
    
    # Wait a moment for logs to propagate to CloudWatch
    print("[live] Waiting 3s for CloudWatch log propagation...")
    time.sleep(3)
    
    # Fetch CloudWatch logs
    log_groups = config.targets.log_groups
    if not log_groups:
        # Auto-discover log groups if not configured
        print("[live] No log groups configured, attempting auto-discovery...")
        log_groups = _auto_discover_log_groups(region, agent_id)
        if log_groups:
            print(f"[live] Auto-discovered: {log_groups}")
        else:
            print("[live] ⚠️  No log groups found, trace may be incomplete")
            log_groups = []
    
    if log_groups:
        print(f"[live] Fetching logs from: {log_groups}")
    
    from itk.logs.cloudwatch_fetch import CloudWatchLogsClient, CloudWatchQuery
    
    cw_client = CloudWatchLogsClient(region=region, offline=False)
    
    # Query for logs in the time window
    query = CloudWatchQuery(
        log_groups=log_groups,
        query_string="fields @timestamp, @message | sort @timestamp asc | limit 200",
        start_time_ms=int((start_time - timedelta(seconds=5)).timestamp() * 1000),
        end_time_ms=int((end_time + timedelta(seconds=10)).timestamp() * 1000),
    )
    
    result = cw_client.run_query(query)
    print(f"[live] Fetched {len(result.results)} log events")
    
    # Parse logs into spans
    log_events = [
        {"timestamp": r.get("@timestamp"), "message": r.get("@message", "")}
        for r in result.results
    ]
    
    spans = parse_cloudwatch_logs(log_events)
    print(f"[live] Parsed {len(spans)} spans from logs")
    
    # Also convert Bedrock traces to spans
    from itk.trace.trace_model import bedrock_traces_to_spans, parse_bedrock_trace_event
    
    # Parse raw trace dicts into BedrockTraceEvent objects
    trace_events = []
    for i, raw_trace in enumerate(response.traces):
        # Add session_id if not present (eventTime should already be there)
        raw_trace.setdefault("sessionId", response.session_id)
        raw_trace.setdefault("traceId", f"trace-{i:03d}")
        trace_events.append(parse_bedrock_trace_event(raw_trace))
    
    bedrock_spans = bedrock_traces_to_spans(trace_events, response.session_id)
    print(f"[live] Converted {len(bedrock_spans)} spans from Bedrock traces")
    
    # Combine all spans
    all_spans = list(spans) + list(bedrock_spans)
    
    # Build trace
    trace = build_trace_from_spans(all_spans)
    
    return trace, {
        "session_id": response.session_id,
        "completion": response.completion,
        "trace_count": len(response.traces),
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
    }


def _cmd_run(args: argparse.Namespace) -> int:
    """Run a case.

    In dev-fixtures mode: load fixture, build trace, emit artifacts.
    In live mode (Tier 3): replay entrypoint, pull logs, build trace, emit artifacts.
    """
    case_path = Path(args.case)
    out_dir = Path(args.out)
    no_redact = getattr(args, "no_redact", False)
    skip_preflight = getattr(args, "skip_preflight", False)

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
    agent_response: dict | None = None
    effective_mode = config.mode

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
        # Live mode: run preflight checks first (unless skipped)
        if not skip_preflight:
            from itk.preflight import run_preflight_checks
            import os
            
            region = os.environ.get("AWS_REGION", "us-east-1")
            log_groups = config.targets.log_groups
            
            # Get agent ID from case if available
            agent_id = None
            if case.entrypoint and case.entrypoint.target:
                raw_agent_id = case.entrypoint.target.get("agent_id", "")
                agent_id = _resolve_env_var(raw_agent_id) if raw_agent_id.startswith("$") else raw_agent_id
            
            print("[preflight] Running pre-flight checks...")
            preflight = run_preflight_checks(
                region=region,
                log_groups=log_groups if log_groups else None,
                agent_id=agent_id if agent_id else None,
            )
            preflight.print_summary()
            
            if preflight.critical_failed:
                print("\n❌ Pre-flight checks failed. Fix the issues above and retry.", file=sys.stderr)
                print("   Use --skip-preflight to bypass (not recommended).", file=sys.stderr)
                return 1
            print("")  # Blank line before main output
        
        # Live mode: invoke agent, fetch logs, build trace
        try:
            trace, agent_response = _run_live_mode(case_path, config)
            
            # Write agent response to artifacts
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "agent-response.json").write_text(
                json.dumps(agent_response, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            # Detect credential errors
            from itk.logs.cloudwatch_fetch import CredentialsExpiredError
            if isinstance(e, CredentialsExpiredError):
                print(f"ERROR: {e.message}", file=sys.stderr)
                print(f"FIX:   {e.fix_command}", file=sys.stderr)
                return 1
                
            print(f"ERROR: Live mode failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return 1

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
        agent_response=agent_response,
        mode=effective_mode,
    )

    # Report summary
    passed = all(r.passed for r in invariant_results)
    print(f"Case: {case.id} ({case.name})")
    print(f"Spans: {len(trace.spans)}")
    print(f"Invariants: {'PASS' if passed else 'FAIL'}")
    print(f"Artifacts: {out_dir}")
    print(f"Report: {out_dir / 'index.html'}")

    return 0 if passed else 1


def _parse_since(since: str) -> int:
    """Parse a 'since' duration string into milliseconds.
    
    Supports: 1h, 24h, 1d, 7d, 30m, etc.
    """
    import re
    
    match = re.match(r'^(\d+)([hdms])$', since.lower())
    if not match:
        raise ValueError(f"Invalid 'since' format: {since}. Use format like: 1h, 24h, 1d, 30m")
    
    value = int(match.group(1))
    unit = match.group(2)
    
    multipliers = {
        's': 1000,
        'm': 60 * 1000,
        'h': 60 * 60 * 1000,
        'd': 24 * 60 * 60 * 1000,
    }
    
    return value * multipliers[unit]


def _cmd_derive(args: argparse.Namespace) -> int:
    """Derive test cases from CloudWatch logs.
    
    Fetches logs from configured log groups, parses them into spans,
    groups by correlation IDs, and generates case YAML files.
    """
    import os
    import yaml
    from datetime import datetime, timezone, timedelta
    
    entrypoint_type = args.entrypoint
    since = args.since
    out_dir = Path(args.out)
    
    # Load config
    env_file = getattr(args, "env_file", None)
    config = load_config(mode="live", env_file=env_file)
    set_config(config)
    
    # Parse time window
    try:
        since_ms = _parse_since(since)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(milliseconds=since_ms)
    
    # Get log groups from config
    log_groups = config.targets.log_groups
    if not log_groups:
        log_groups = ["/aws/lambda/itk-haiku-invoker"]  # Default
    
    print(f"[derive] Entrypoint type: {entrypoint_type}")
    print(f"[derive] Time window: {start_time.isoformat()} to {end_time.isoformat()}")
    print(f"[derive] Log groups: {log_groups}")
    
    # Fetch logs
    from itk.logs.cloudwatch_fetch import CloudWatchLogsClient, CloudWatchQuery
    
    region = os.environ.get("AWS_REGION", "us-east-1")
    cw_client = CloudWatchLogsClient(region=region, offline=False)
    
    query = CloudWatchQuery(
        log_groups=log_groups,
        query_string="fields @timestamp, @message, @logStream | sort @timestamp asc | limit 1000",
        start_time_ms=int(start_time.timestamp() * 1000),
        end_time_ms=int(end_time.timestamp() * 1000),
    )
    
    try:
        result = cw_client.run_query(query)
    except Exception as e:
        print(f"ERROR: Failed to query CloudWatch: {e}", file=sys.stderr)
        return 1
    
    print(f"[derive] Fetched {len(result.results)} log events")
    
    if not result.results:
        print("[derive] No logs found in the specified time window")
        return 0
    
    # Parse logs into spans
    log_events = [
        {"timestamp": r.get("@timestamp"), "message": r.get("@message", "")}
        for r in result.results
    ]
    
    spans = parse_cloudwatch_logs(log_events)
    print(f"[derive] Parsed {len(spans)} spans")
    
    if not spans:
        print("[derive] No spans extracted from logs")
        return 0
    
    # Group spans by trace/request ID
    from collections import defaultdict
    
    trace_groups: dict[str, list[Span]] = defaultdict(list)
    orphan_spans: list[Span] = []
    
    for span in spans:
        # Use trace ID or request ID as grouping key
        key = span.itk_trace_id or span.lambda_request_id or span.bedrock_session_id
        if key:
            trace_groups[key].append(span)
        else:
            orphan_spans.append(span)
    
    print(f"[derive] Found {len(trace_groups)} distinct traces")
    if orphan_spans:
        print(f"[derive] {len(orphan_spans)} orphan spans (no correlation ID)")
    
    # Create output directory
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate case files
    cases_generated = 0
    
    for trace_id, trace_spans in trace_groups.items():
        # Generate case ID from trace ID
        case_id = f"derived-{trace_id[:12]}"
        
        # Determine first span's component for naming
        first_span = trace_spans[0]
        
        # Build case YAML
        # Build payload appropriate for the entrypoint type
        raw_payload = first_span.request or {}
        if entrypoint_type == "bedrock_invoke_agent":
            # Extract inputText from various possible sources in log data
            input_text = (
                raw_payload.get("inputText") or
                raw_payload.get("prompt_preview") or
                raw_payload.get("prompt") or
                raw_payload.get("text") or
                "Derived test input"
            )
            payload = {"inputText": input_text}
        else:
            payload = raw_payload
        
        case_data = {
            "id": case_id,
            "name": f"Derived from {first_span.component}:{first_span.operation}",
            "entrypoint": {
                "type": entrypoint_type,
                "target": {
                    "agent_id": "${ITK_WORKER_AGENT_ID}",
                    "agent_alias_id": "${ITK_WORKER_ALIAS_ID}",
                    "region": region,
                } if entrypoint_type == "bedrock_invoke_agent" else {},
                "payload": payload,
            },
            "expected": {
                "invariants": [
                    {"name": "has_spans"},
                    {"name": "has_entrypoint"},
                ],
            },
            "notes": {
                "source": "derived from CloudWatch logs",
                "derived_from_trace_id": trace_id,
                "span_count": len(trace_spans),
                "time_window": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                },
            },
        }
        
        # Write case file
        case_path = out_dir / f"{case_id}.yaml"
        with open(case_path, "w", encoding="utf-8") as f:
            yaml.dump(case_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        
        # Write fixture file with spans
        fixture_path = out_dir / f"{case_id}.jsonl"
        with open(fixture_path, "w", encoding="utf-8") as f:
            for span in trace_spans:
                f.write(json.dumps(_span_to_dict(span), ensure_ascii=False) + "\n")
        
        cases_generated += 1
        print(f"[derive] Generated: {case_path.name} ({len(trace_spans)} spans)")
    
    print(f"\n[derive] Generated {cases_generated} case(s) in {out_dir}")
    
    return 0


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


def _cmd_explain_schema(args: argparse.Namespace) -> int:
    """Pretty-print the span schema with examples and descriptions."""
    schema_name = getattr(args, "schema", "span")
    
    # Map schema names to files
    schema_files = {
        "span": "itk.span.schema.json",
        "case": "itk.case.schema.json",
        "config": "itk.config.schema.json",
    }
    
    if schema_name not in schema_files:
        print(f"Unknown schema: {schema_name}", file=sys.stderr)
        print(f"Available: {', '.join(schema_files.keys())}", file=sys.stderr)
        return 1
    
    # Find schema file
    schema_filename = schema_files[schema_name]
    schema_path = None
    
    # Look in current directory first, then in package
    candidates = [
        Path.cwd() / "schemas" / schema_filename,
        Path(__file__).parent.parent.parent.parent / "schemas" / schema_filename,
    ]
    
    for candidate in candidates:
        if candidate.exists():
            schema_path = candidate
            break
    
    if not schema_path:
        print(f"Schema file not found: {schema_filename}", file=sys.stderr)
        return 1
    
    # Load and parse schema
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    
    print(f"ITK Schema: {schema_name}")
    print("=" * 60)
    print()
    
    if "title" in schema:
        print(f"Title: {schema['title']}")
    if "description" in schema:
        print(f"Description: {schema['description']}")
    print()
    
    # Show required fields
    required = schema.get("required", [])
    if required:
        print("Required Fields:")
        print("-" * 40)
        for field in required:
            prop = schema.get("properties", {}).get(field, {})
            field_type = _format_schema_type(prop)
            desc = prop.get("description", "")
            print(f"  ✅ {field}: {field_type}")
            if desc:
                print(f"      {desc}")
        print()
    
    # Show optional fields
    optional = [
        k for k in schema.get("properties", {}).keys()
        if k not in required
    ]
    if optional:
        print("Optional Fields:")
        print("-" * 40)
        for field in optional:
            prop = schema.get("properties", {}).get(field, {})
            field_type = _format_schema_type(prop)
            desc = prop.get("description", "")
            print(f"  ○ {field}: {field_type}")
            if desc:
                print(f"      {desc}")
        print()
    
    # Show example values
    print("Example Span:")
    print("-" * 40)
    example = {
        "span_id": "span-abc123",
        "component": "bedrock_agent",
        "operation": "InvokeAgent",
        "parent_span_id": "span-parent-789",
        "ts_start": "2026-01-17T10:00:00.000Z",
        "ts_end": "2026-01-17T10:00:01.234Z",
        "attempt": 1,
        "lambda_request_id": "12345678-1234-1234-1234-123456789abc",
        "request": {"agentId": "WYEP3TYH1A", "inputText": "Hello"},
        "response": {"completion": "Hi there!"},
        "error": None,
    }
    print(json.dumps(example, indent=2))
    print()
    
    print(f"Full schema: {schema_path}")
    print("Documentation: docs/10-log-field-glossary.md")
    
    return 0


def _format_schema_type(prop: dict) -> str:
    """Format a JSON Schema type for display."""
    t = prop.get("type", "any")
    if isinstance(t, list):
        # Union type like ["string", "null"]
        types = [x for x in t if x != "null"]
        nullable = "null" in t
        base = types[0] if types else "any"
        return f"{base}?" if nullable else base
    return t


def _cmd_validate_log(args: argparse.Namespace) -> int:
    """Validate each line of a JSONL file against the span schema."""
    import jsonschema
    
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"File not found: {file_path}", file=sys.stderr)
        return 1
    
    # Find schema file
    schema_path = None
    candidates = [
        Path.cwd() / "schemas" / "itk.span.schema.json",
        Path(__file__).parent.parent.parent.parent / "schemas" / "itk.span.schema.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            schema_path = candidate
            break
    
    if not schema_path:
        print("Span schema not found. Ensure schemas/itk.span.schema.json exists.", file=sys.stderr)
        return 1
    
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    
    print(f"Validating: {file_path}")
    print(f"Schema: {schema_path}")
    print("=" * 60)
    print()
    
    valid_count = 0
    invalid_count = 0
    errors = []
    
    with file_path.open(encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append((line_num, f"Invalid JSON: {e.msg}"))
                invalid_count += 1
                continue
            
            try:
                jsonschema.validate(data, schema)
                valid_count += 1
            except jsonschema.ValidationError as e:
                # Extract the most useful error message
                path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else "(root)"
                msg = e.message
                errors.append((line_num, f"{path}: {msg}"))
                invalid_count += 1
    
    # Print errors (up to 20)
    if errors:
        print("Validation Errors:")
        print("-" * 40)
        for line_num, msg in errors[:20]:
            print(f"  Line {line_num}: {msg}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more errors")
        print()
    
    # Summary
    total = valid_count + invalid_count
    print("Summary:")
    print("-" * 40)
    print(f"  Total lines: {total}")
    print(f"  Valid:       {valid_count} ✅")
    print(f"  Invalid:     {invalid_count} ❌")
    
    if invalid_count == 0:
        print()
        print("All spans are valid! ✅")
        return 0
    else:
        print()
        print("Fix the errors above and re-run validation.")
        return 1


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


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Check ITK environment and dependencies."""
    import os
    import platform
    
    issues = []
    warnings = []
    
    print("ITK Doctor - Environment Check")
    print("=" * 40)
    print()
    
    # 1. Python version
    py_version = platform.python_version()
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 10):
        issues.append(f"Python 3.10+ required, found {py_version}")
        print(f"❌ Python: {py_version} (requires 3.10+)")
    else:
        print(f"✅ Python: {py_version}")
    
    # 2. Virtual environment
    in_venv = sys.prefix != sys.base_prefix
    if in_venv:
        print(f"✅ Virtual environment: active")
    else:
        warnings.append("Not in a virtual environment (recommended)")
        print(f"⚠️  Virtual environment: not active (recommended)")
    
    # 3. Core dependencies (import_name, display_name)
    core_deps = [
        ("boto3", "boto3"),
        ("yaml", "PyYAML"),
        ("jsonschema", "jsonschema"),
        ("dotenv", "python-dotenv"),
    ]
    for import_name, display_name in core_deps:
        try:
            __import__(import_name)
            print(f"✅ {display_name}: installed")
        except ImportError:
            issues.append(f"Missing dependency: {display_name}")
            print(f"❌ {display_name}: NOT INSTALLED")
    
    # 4. .env file
    print()
    env_file = Path(getattr(args, "env_file", ".env") or ".env")
    if env_file.exists():
        print(f"✅ .env file: {env_file}")
        # Check for required variables in live mode
        mode = getattr(args, "mode", None) or os.environ.get("ITK_MODE", "live")
        if mode == "live":
            env_content = env_file.read_text()
            required_vars = ["AWS_REGION", "ITK_LOG_GROUPS"]
            optional_vars = ["ITK_WORKER_AGENT_ID", "ITK_WORKER_ALIAS_ID", "AWS_PROFILE"]
            for var in required_vars:
                if var in env_content and f"{var}=" in env_content:
                    # Check if it has a value (not empty after =)
                    import re
                    match = re.search(rf'^{var}=(.+)$', env_content, re.MULTILINE)
                    if match and match.group(1).strip():
                        print(f"   ✅ {var}: set")
                    else:
                        warnings.append(f"{var} is empty in .env")
                        print(f"   ⚠️  {var}: empty")
                else:
                    warnings.append(f"{var} not found in .env")
                    print(f"   ⚠️  {var}: not set")
    else:
        if Path(".env.example").exists():
            warnings.append(".env not found, but .env.example exists")
            print(f"⚠️  .env file: not found (run bootstrap or copy .env.example)")
        else:
            warnings.append(".env file not found")
            print(f"⚠️  .env file: not found")
    
    # 5. AWS credentials (if live mode requested)
    print()
    mode = getattr(args, "mode", None) or os.environ.get("ITK_MODE", "live")
    if mode == "live":
        try:
            import boto3
            sts = boto3.client("sts")
            identity = sts.get_caller_identity()
            print(f"✅ AWS credentials: valid")
            print(f"   Account: {identity['Account']}")
            print(f"   ARN: {identity['Arn']}")
        except Exception as e:
            err_msg = str(e)
            if "credentials" in err_msg.lower() or "token" in err_msg.lower():
                issues.append("AWS credentials not configured or expired")
                print(f"❌ AWS credentials: not configured")
                print(f"   Run: aws configure (or set up MFA session)")
            else:
                warnings.append(f"AWS check failed: {err_msg}")
                print(f"⚠️  AWS credentials: check failed ({err_msg[:50]}...)")
    else:
        print(f"ℹ️  AWS credentials: skipped (mode={mode})")
    
    # 6. Check cases directory
    print()
    cases_dirs = [Path("cases"), Path("dropin/itk/cases")]
    found_cases = False
    for cases_dir in cases_dirs:
        if cases_dir.exists():
            case_count = len(list(cases_dir.glob("*.yaml")))
            print(f"✅ Cases directory: {cases_dir} ({case_count} cases)")
            found_cases = True
            break
    if not found_cases:
        warnings.append("No cases directory found")
        print(f"⚠️  Cases directory: not found")
    
    # Summary
    print()
    print("=" * 40)
    if not issues and not warnings:
        print("✅ All checks passed! ITK is ready to use.")
        return 0
    elif not issues:
        print(f"⚠️  {len(warnings)} warning(s), but ITK should work.")
        for w in warnings:
            print(f"   • {w}")
        return 0
    else:
        print(f"❌ {len(issues)} issue(s) must be fixed:")
        for issue in issues:
            print(f"   • {issue}")
        if warnings:
            print(f"\n⚠️  Also {len(warnings)} warning(s):")
            for w in warnings:
                print(f"   • {w}")
        return 1


def _generate_discovered_env_lines(region: str, discovered: dict) -> list[str]:
    """Generate minimal .env lines from discovered resources."""
    lines = [
        "# ITK Configuration",
        "# Generated by: itk discover --apply",
        "",
        "ITK_MODE=live",
        f"ITK_AWS_REGION={region}",
        "",
    ]
    
    # Log groups
    if discovered.get("log_groups"):
        lines.append(f"ITK_LOG_GROUPS={','.join(discovered['log_groups'][:5])}")
    
    # First agent
    agents = discovered.get("bedrock_agents", [])
    if agents:
        first = agents[0]
        lines.append(f"ITK_WORKER_AGENT_ID={first['id']}")
        if first.get("aliases"):
            lines.append(f"ITK_WORKER_ALIAS_ID={first['aliases'][0]['id']}")
    
    # First queue
    queues = discovered.get("sqs_queues", [])
    if queues:
        lines.append(f"ITK_SQS_QUEUE_URL={queues[0]}")
    
    lines.append("")
    lines.append("# Timing")
    lines.append("ITK_LOG_DELAY_SECONDS=5")
    lines.append("")
    
    return lines


def _merge_env_content(existing: str, new_lines: list[str]) -> str:
    """Merge new env lines into existing .env content.
    
    Only adds/updates keys that don't exist or are empty.
    """
    # Parse existing keys
    existing_keys = set()
    for line in existing.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            value = line.split("=", 1)[1].strip()
            if value:  # Only count non-empty values
                existing_keys.add(key)
    
    # Filter new lines to only add missing keys
    merged = existing.rstrip() + "\n"
    added = []
    
    for line in new_lines:
        if not line.strip() or line.strip().startswith("#"):
            continue
        if "=" in line:
            key = line.split("=", 1)[0].strip()
            if key not in existing_keys:
                added.append(line)
    
    if added:
        merged += "\n# --- Added by itk discover --apply ---\n"
        merged += "\n".join(added)
        merged += "\n"
    
    return merged


def _cmd_discover(args: argparse.Namespace) -> int:
    """Discover AWS resources and generate .env.discovered file."""
    import os
    from datetime import datetime
    
    region = getattr(args, "region", None) or os.environ.get("AWS_REGION", "us-east-1")
    profile = getattr(args, "profile", None) or os.environ.get("AWS_PROFILE")
    out_file = Path(getattr(args, "out", ".env.discovered"))
    
    print("ITK Discover - AWS Resource Discovery")
    print("=" * 40)
    print(f"Region: {region}")
    if profile:
        print(f"Profile: {profile}")
    print()
    
    discovered = {
        "log_groups": [],
        "sqs_queues": [],
        "bedrock_agents": [],
        "lambda_functions": [],
    }
    errors = []

    
    # Set up boto3 session
    try:
        import boto3
        session_kwargs = {"region_name": region}
        if profile:
            session_kwargs["profile_name"] = profile
        session = boto3.Session(**session_kwargs)
    except Exception as e:
        print(f"❌ Failed to create AWS session: {e}")
        return 1
    
    # 1. Discover CloudWatch Log Groups
    print("Discovering CloudWatch Log Groups...")
    try:
        logs = session.client("logs")
        paginator = logs.get_paginator("describe_log_groups")
        for page in paginator.paginate():
            for group in page.get("logGroups", []):
                name = group["logGroupName"]
                # Filter to likely relevant groups
                if any(kw in name.lower() for kw in ["lambda", "agent", "bot", "api", "ecs", "fargate"]):
                    discovered["log_groups"].append(name)
        print(f"   Found {len(discovered['log_groups'])} relevant log groups")
    except Exception as e:
        err = str(e)
        if "AccessDenied" in err or "not authorized" in err.lower():
            errors.append("logs:DescribeLogGroups - Access denied")
            print(f"   ⚠️  Access denied for logs:DescribeLogGroups")
        else:
            errors.append(f"logs:DescribeLogGroups - {err[:50]}")
            print(f"   ⚠️  Error: {err[:60]}...")
    
    # 2. Discover SQS Queues
    print("Discovering SQS Queues...")
    try:
        sqs = session.client("sqs")
        response = sqs.list_queues()
        discovered["sqs_queues"] = response.get("QueueUrls", [])
        print(f"   Found {len(discovered['sqs_queues'])} queues")
    except Exception as e:
        err = str(e)
        if "AccessDenied" in err or "not authorized" in err.lower():
            errors.append("sqs:ListQueues - Access denied")
            print(f"   ⚠️  Access denied for sqs:ListQueues")
        else:
            errors.append(f"sqs:ListQueues - {err[:50]}")
            print(f"   ⚠️  Error: {err[:60]}...")
    
    # 3. Discover Lambda Functions
    print("Discovering Lambda Functions...")
    try:
        lam = session.client("lambda")
        paginator = lam.get_paginator("list_functions")
        for page in paginator.paginate():
            for func in page.get("Functions", []):
                discovered["lambda_functions"].append(func["FunctionName"])
        print(f"   Found {len(discovered['lambda_functions'])} functions")
    except Exception as e:
        err = str(e)
        if "AccessDenied" in err or "not authorized" in err.lower():
            errors.append("lambda:ListFunctions - Access denied")
            print(f"   ⚠️  Access denied for lambda:ListFunctions")
        else:
            errors.append(f"lambda:ListFunctions - {err[:50]}")
            print(f"   ⚠️  Error: {err[:60]}...")
    
    # 4. Discover Bedrock Agents with version/alias details
    print("Discovering Bedrock Agents...")
    try:
        bedrock = session.client("bedrock-agent")
        response = bedrock.list_agents()
        for agent in response.get("agentSummaries", []):
            agent_id = agent["agentId"]
            agent_info = {
                "id": agent_id,
                "name": agent.get("agentName", "unknown"),
                "status": agent.get("agentStatus", "unknown"),
                "versions": [],
                "aliases": [],
            }
            
            # Get versions for each agent
            try:
                versions_resp = bedrock.list_agent_versions(agentId=agent_id)
                for v in versions_resp.get("agentVersionSummaries", []):
                    version_info = {
                        "version": v.get("agentVersion", "?"),
                        "status": v.get("agentStatus", "unknown"),
                        "created": v.get("createdAt", "").isoformat() if hasattr(v.get("createdAt", ""), "isoformat") else str(v.get("createdAt", "")),
                    }
                    agent_info["versions"].append(version_info)
                # Sort versions by created date descending
                agent_info["versions"].sort(
                    key=lambda x: x.get("created", ""), reverse=True
                )
            except Exception:
                pass
            
            # Get aliases for each agent with version mapping
            try:
                aliases_resp = bedrock.list_agent_aliases(agentId=agent_id)
                for a in aliases_resp.get("agentAliasSummaries", []):
                    routing = a.get("routingConfiguration", [])
                    target_version = routing[0].get("agentVersion", "?") if routing else "?"
                    alias_info = {
                        "id": a["agentAliasId"],
                        "name": a.get("agentAliasName", "unknown"),
                        "version": target_version,
                        "status": a.get("agentAliasStatus", "unknown"),
                    }
                    agent_info["aliases"].append(alias_info)
            except Exception:
                pass
            
            discovered["bedrock_agents"].append(agent_info)
        print(f"   Found {len(discovered['bedrock_agents'])} agents")
    except Exception as e:
        err = str(e)
        if "AccessDenied" in err or "not authorized" in err.lower():
            errors.append("bedrock-agent:ListAgents - Access denied")
            print(f"   ⚠️  Access denied for bedrock-agent:ListAgents")
        elif "UnrecognizedClientException" in err:
            errors.append("bedrock-agent - Region may not support Bedrock")
            print(f"   ⚠️  Bedrock not available in this region")
        else:
            errors.append(f"bedrock-agent:ListAgents - {err[:50]}")
            print(f"   ⚠️  Error: {err[:60]}...")
    
    # Generate .env.discovered file
    print()
    print(f"Writing {out_file}...")
    
    lines = [
        f"# ITK Environment Discovery",
        f"# Generated: {datetime.now().isoformat()}",
        f"# Region: {region}",
        f"#",
        f"# Review these suggestions and copy the values you need to .env",
        f"#",
        "",
        "# === Required Settings ===",
        f"ITK_MODE=live",
        f"ITK_AWS_REGION={region}",
        "",
    ]
    
    # Log groups
    lines.append("# === CloudWatch Log Groups ===")
    lines.append("# Uncomment and edit the log groups you want to monitor:")
    if discovered["log_groups"]:
        # Suggest first 5, comment out the rest
        suggested = discovered["log_groups"][:5]
        lines.append(f"ITK_LOG_GROUPS={','.join(suggested)}")
        if len(discovered["log_groups"]) > 5:
            lines.append(f"# Other available log groups:")
            for lg in discovered["log_groups"][5:15]:  # Max 15 total
                lines.append(f"#   {lg}")
    else:
        lines.append("# ITK_LOG_GROUPS=  # No log groups found")
    lines.append("")
    
    # SQS queues
    lines.append("# === SQS Queues ===")
    if discovered["sqs_queues"]:
        lines.append(f"# ITK_SQS_QUEUE_URL={discovered['sqs_queues'][0]}")
        for q in discovered["sqs_queues"][1:5]:
            lines.append(f"#   Alternative: {q}")
    else:
        lines.append("# ITK_SQS_QUEUE_URL=  # No queues found")
    lines.append("")
    
    # Lambda functions
    lines.append("# === Lambda Functions ===")
    if discovered["lambda_functions"]:
        lines.append(f"# ITK_LAMBDA_FUNCTION_NAME={discovered['lambda_functions'][0]}")
        for fn in discovered["lambda_functions"][1:5]:
            lines.append(f"#   Alternative: {fn}")
    else:
        lines.append("# ITK_LAMBDA_FUNCTION_NAME=  # No functions found")
    lines.append("")
    
    # Bedrock agents with version/alias mapping
    lines.append("# === Bedrock Agents ===")
    if discovered["bedrock_agents"]:
        for agent in discovered["bedrock_agents"]:
            lines.append(f"#")
            lines.append(f"# Agent: {agent['name']}")
            lines.append(f"#   ID: {agent['id']}")
            lines.append(f"#   Status: {agent['status']}")
            
            # Show versions
            versions = agent.get("versions", [])
            if versions:
                lines.append(f"#   Versions ({len(versions)}):")
                # Show top 3 versions
                for v in versions[:3]:
                    status_icon = "✅" if v["status"] == "PREPARED" else "📝" if v["status"] == "DRAFT" else "❌"
                    lines.append(f"#     {status_icon} v{v['version']} ({v['status']})")
                if len(versions) > 3:
                    lines.append(f"#     ... and {len(versions) - 3} more")
            
            # Show aliases with version mapping
            aliases = agent.get("aliases", [])
            if aliases:
                lines.append(f"#   Aliases:")
                for alias in aliases:
                    lines.append(f"#     {alias['name']} ({alias['id']}) → v{alias['version']}")
            
            # Find latest prepared version
            latest_prepared = None
            for v in versions:
                if v["status"] == "PREPARED":
                    latest_prepared = v["version"]
                    break
            
            # Suggest config
            lines.append(f"#")
            lines.append(f"# ITK_WORKER_AGENT_ID={agent['id']}")
            if aliases:
                # Prefer alias pointing to latest prepared version
                best_alias = None
                for alias in aliases:
                    if alias["version"] == latest_prepared:
                        best_alias = alias
                        break
                if not best_alias and aliases:
                    best_alias = aliases[0]
                if best_alias:
                    lines.append(f"# ITK_WORKER_ALIAS_ID={best_alias['id']}  # {best_alias['name']} → v{best_alias['version']}")
            
            # Suggest using 'latest' mode
            if latest_prepared:
                lines.append(f"# Or use: agent_version: 'latest'  # Auto-resolves to v{latest_prepared}")
            
            lines.append(f"#")
    else:
        lines.append("# ITK_WORKER_AGENT_ID=  # No agents found")
        lines.append("# ITK_WORKER_ALIAS_ID=")
    lines.append("")
    
    # Errors encountered
    if errors:
        lines.append("# === Errors During Discovery ===")
        for err in errors:
            lines.append(f"# ⚠️  {err}")
        lines.append("")
    
    # Handle --apply flag: merge into .env instead of separate file
    apply_flag = getattr(args, "apply", False)
    if apply_flag:
        # Generate minimal .env content directly
        env_lines = _generate_discovered_env_lines(region, discovered)
        env_file = Path(".env")
        
        if env_file.exists():
            # Merge with existing .env
            existing = env_file.read_text(encoding="utf-8")
            merged = _merge_env_content(existing, env_lines)
            env_file.write_text(merged, encoding="utf-8")
            print(f"✅ Merged discovered values into {env_file}")
        else:
            # Create new .env
            env_file.write_text("\n".join(env_lines), encoding="utf-8")
            print(f"✅ Created {env_file} with discovered values")
    else:
        out_file.write_text("\n".join(lines), encoding="utf-8")
    
    # Summary
    print()
    print("=" * 40)
    total = sum(len(v) if isinstance(v, list) else 0 for v in discovered.values())
    print(f"Discovered {total} resources")
    
    # Print agent summary with versions
    if discovered["bedrock_agents"]:
        print()
        print("Bedrock Agents:")
        for agent in discovered["bedrock_agents"]:
            versions = agent.get("versions", [])
            prepared = [v for v in versions if v["status"] == "PREPARED"]
            latest = prepared[0]["version"] if prepared else "none"
            
            print(f"  📦 {agent['name']} ({agent['id']})")
            print(f"     Latest PREPARED: v{latest}")
            
            for alias in agent.get("aliases", []):
                arrow = "→"
                version_match = "✅" if alias["version"] == latest else ""
                print(f"     {alias['name']} ({alias['id']}) {arrow} v{alias['version']} {version_match}")
    
    print()
    if apply_flag:
        print("✅ Configuration applied to .env")
        print()
        print("Next steps:")
        print(f"  1. Review .env")
        print(f"  2. Run: itk doctor --mode live")
    else:
        print(f"Output: {out_file}")
        print()
        print("Next steps:")
        print(f"  1. Review {out_file}")
        print(f"  2. Copy desired values to .env")
        print(f"  3. Run: itk doctor --mode live")
        print()
        print("Or run: itk discover --apply  (to apply directly)")

    
    return 0


def _cmd_view(args: argparse.Namespace) -> int:
    """View historical executions from CloudWatch logs or local files.
    
    Fetches logs for a time window, groups by execution (trace_id/session_id),
    and generates browsable artifacts including a gallery page.
    """
    import os
    from datetime import datetime, timezone, timedelta
    
    from itk.report.historical_viewer import (
        ViewResult,
        group_spans_by_execution,
        build_execution_summary,
        filter_executions,
        render_gallery_html,
        load_logs_from_file,
        fetch_logs_for_time_window,
    )
    from itk.diagrams.trace_viewer import render_trace_viewer
    from itk.diagrams.timeline_view import render_timeline_viewer, render_mini_timeline
    
    # Parse args
    since = args.since
    until = getattr(args, "until", None)
    out_dir = Path(args.out)
    filter_type = getattr(args, "filter", "all") or "all"
    logs_file = getattr(args, "logs_file", None)
    log_groups_arg = getattr(args, "log_groups", None)
    region = getattr(args, "region", None) or os.environ.get("AWS_REGION", "us-east-1")
    profile = getattr(args, "profile", None)
    
    print("ITK View - Historical Execution Viewer")
    print("=" * 40)
    
    # Parse time window
    try:
        since_ms = _parse_since(since)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    
    end_time = datetime.now(timezone.utc)
    if until:
        try:
            until_ms = _parse_since(until)
            end_time = datetime.now(timezone.utc) - timedelta(milliseconds=until_ms)
        except ValueError as e:
            print(f"ERROR parsing --until: {e}", file=sys.stderr)
            return 1
    
    start_time = end_time - timedelta(milliseconds=since_ms)
    
    print(f"Time window: {start_time.strftime('%Y-%m-%d %H:%M:%S')} → {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Determine log source
    log_events: list[dict] = []
    
    if logs_file:
        # Offline mode: load from file
        logs_path = Path(logs_file)
        if not logs_path.exists():
            print(f"ERROR: Logs file not found: {logs_path}", file=sys.stderr)
            return 1
        
        print(f"Loading logs from: {logs_path}")
        log_events = load_logs_from_file(logs_path)
        print(f"  Loaded {len(log_events)} log events")
    else:
        # Live mode: fetch from CloudWatch
        if profile:
            os.environ["AWS_PROFILE"] = profile
        
        # Get log groups
        if log_groups_arg:
            log_groups = [g.strip() for g in log_groups_arg.split(",")]
        else:
            # Try from config
            env_file = getattr(args, "env_file", None)
            config = load_config(mode="live", env_file=env_file)
            log_groups = config.targets.log_groups
        
        if not log_groups:
            print("ERROR: No log groups specified.", file=sys.stderr)
            print("  Use --log-groups or set ITK_LOG_GROUPS in .env", file=sys.stderr)
            return 1
        
        print(f"Region: {region}")
        print(f"Log groups: {log_groups}")
        print()
        print("Fetching CloudWatch logs...")
        
        try:
            log_events = fetch_logs_for_time_window(
                log_groups=log_groups,
                start_time=start_time,
                end_time=end_time,
                region=region,
            )
            print(f"  Fetched {len(log_events)} log events")
        except Exception as e:
            print(f"ERROR: Failed to fetch logs: {e}", file=sys.stderr)
            return 1
    
    if not log_events:
        print()
        print("No log events found in the specified time window.")
        return 0
    
    # Parse logs into spans
    print()
    print("Parsing log events...")
    spans = parse_cloudwatch_logs(log_events)
    print(f"  Parsed {len(spans)} spans")
    
    if not spans:
        print()
        print("No spans extracted from logs.")
        return 0
    
    # Group by execution
    print()
    print("Grouping by execution...")
    groups, orphans = group_spans_by_execution(spans)
    print(f"  Found {len(groups)} distinct executions")
    if orphans:
        print(f"  {len(orphans)} orphan spans (no correlation ID)")
    
    # Create output directory
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Process each execution
    print()
    print("Generating artifacts...")
    
    execution_summaries = []
    
    for exec_id, exec_spans in groups.items():
        # Create execution subdirectory
        short_id = exec_id[:12] if len(exec_id) > 12 else exec_id
        exec_dir = out_dir / short_id
        exec_dir.mkdir(exist_ok=True)
        
        # Build trace
        trace = build_trace_from_spans(exec_spans)
        
        # Render trace viewer
        viewer_html = render_trace_viewer(trace)
        (exec_dir / "trace-viewer.html").write_text(viewer_html, encoding="utf-8")
        
        # Render timeline
        timeline_html = render_timeline_viewer(trace)
        (exec_dir / "timeline.html").write_text(timeline_html, encoding="utf-8")
        
        # Render thumbnail
        try:
            thumbnail_svg = render_mini_timeline(trace)
            (exec_dir / "thumbnail.svg").write_text(thumbnail_svg, encoding="utf-8")
        except Exception:
            pass  # Thumbnail is optional
        
        # Write spans.jsonl
        from dataclasses import asdict
        with (exec_dir / "spans.jsonl").open("w", encoding="utf-8") as f:
            for span in exec_spans:
                f.write(json.dumps(asdict(span), ensure_ascii=False) + "\n")
        
        # Build summary
        summary = build_execution_summary(
            exec_id=exec_id,
            spans=exec_spans,
            artifact_dir=short_id,
        )
        execution_summaries.append(summary)
    
    # Sort by timestamp (newest first)
    execution_summaries.sort(key=lambda x: x.timestamp, reverse=True)
    
    # Apply filter
    filtered = filter_executions(execution_summaries, filter_type)
    
    print(f"  Generated artifacts for {len(execution_summaries)} executions")
    if filter_type != "all":
        print(f"  Showing {len(filtered)} after filter: {filter_type}")
    
    # Build result
    result = ViewResult(
        start_time=start_time,
        end_time=end_time,
        total_logs=len(log_events),
        executions=filtered,
        orphan_span_count=len(orphans),
    )
    
    # Render gallery
    gallery_html = render_gallery_html(result)
    (out_dir / "index.html").write_text(gallery_html, encoding="utf-8")
    
    # Write result.json
    result_data = {
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "total_logs": len(log_events),
        "total_executions": len(execution_summaries),
        "filtered_executions": len(filtered),
        "filter": filter_type,
        "passed": result.passed_count,
        "warnings": result.warning_count,
        "errors": result.error_count,
        "orphan_spans": len(orphans),
    }
    (out_dir / "result.json").write_text(
        json.dumps(result_data, indent=2), encoding="utf-8"
    )
    
    # Summary
    print()
    print("=" * 40)
    print(f"Executions: {len(filtered)}")
    print(f"  ✅ Passed:   {result.passed_count}")
    print(f"  ⚠️  Warnings: {result.warning_count}")
    print(f"  ❌ Errors:   {result.error_count}")
    print()
    print(f"Gallery: {out_dir / 'index.html'}")
    
    return 0


def _cmd_show_config(args: argparse.Namespace) -> int:
    """Show effective configuration from all sources."""
    import os
    
    env_file = getattr(args, "env_file", None)
    mode = getattr(args, "mode", None)
    
    config = load_config(mode=mode, env_file=env_file)
    
    print("ITK Effective Configuration")
    print("=" * 50)
    print()
    
    # Show mode
    print(f"Mode: {config.mode.value}")
    print(f"  Source: {'CLI flag' if mode else 'env var or default'}")
    print()
    
    # Show env file
    if config.env_file_path:
        print(f"Env File: {config.env_file_path}")
    else:
        print("Env File: none loaded")
    print()
    
    # Show targets
    print("Targets:")
    print(f"  AWS Region: {config.targets.aws_region}")
    if config.targets.log_groups:
        print(f"  Log Groups: {', '.join(config.targets.log_groups)}")
    else:
        print(f"  Log Groups: (none)")
    if config.targets.sqs_queue_url:
        print(f"  SQS Queue: {config.targets.sqs_queue_url}")
    if config.targets.lambda_function_name:
        print(f"  Lambda: {config.targets.lambda_function_name}")
    if config.targets.bedrock_agent_id:
        print(f"  Bedrock Agent: {config.targets.bedrock_agent_id}")
        print(f"  Bedrock Alias: {config.targets.bedrock_agent_alias_id or '(none)'}")
    print()
    
    # Show redaction settings
    if config.redact_keys or config.redact_patterns:
        print("Redaction:")
        if config.redact_keys:
            print(f"  Keys: {', '.join(config.redact_keys)}")
        if config.redact_patterns:
            print(f"  Patterns: {', '.join(config.redact_patterns)}")
        print()
    
    # Show other settings
    print("Other Settings:")
    print(f"  Log Delay: {config.log_delay_seconds}s")
    print(f"  Query Window: {config.log_query_window_seconds}s")
    print(f"  Soak Max Inflight: {config.soak_max_inflight}")
    print()
    
    # Show relevant env vars
    print("Environment Variables:")
    env_vars = [
        "AWS_PROFILE", "AWS_REGION", "ITK_MODE", "ITK_LOG_GROUPS",
        "ITK_SQS_QUEUE_URL", "ITK_BEDROCK_AGENT_ID", "ITK_BEDROCK_AGENT_ALIAS_ID"
    ]
    for var in env_vars:
        val = os.environ.get(var)
        if val:
            # Truncate long values
            display = val if len(val) <= 40 else val[:37] + "..."
            print(f"  {var}={display}")
    
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    """Show current ITK status."""
    import os
    from datetime import datetime
    
    env_file = getattr(args, "env_file", None)
    
    print("ITK Status")
    print("=" * 40)
    print()
    
    # Load config
    try:
        config = load_config(env_file=env_file)
        print(f"Mode: {config.mode.value}")
        print(f"Region: {config.targets.aws_region}")
    except Exception as e:
        print(f"Mode: unknown (config error: {e})")
        config = None
    print()
    
    # Check for log groups
    if config and config.targets.log_groups:
        print(f"Log Groups ({len(config.targets.log_groups)}):")
        for lg in config.targets.log_groups[:5]:
            print(f"  • {lg}")
        if len(config.targets.log_groups) > 5:
            print(f"  ... and {len(config.targets.log_groups) - 5} more")
    else:
        print("Log Groups: (none configured)")
    print()
    
    # Check for recent artifacts
    artifacts_dirs = [Path("artifacts"), Path("dropin/itk/artifacts")]
    latest_run = None
    latest_time = None
    
    for artifacts_dir in artifacts_dirs:
        if artifacts_dir.exists():
            for subdir in artifacts_dir.iterdir():
                if subdir.is_dir():
                    report_file = subdir / "report.md"
                    if report_file.exists():
                        mtime = report_file.stat().st_mtime
                        if latest_time is None or mtime > latest_time:
                            latest_time = mtime
                            latest_run = subdir
    
    if latest_run:
        run_time = datetime.fromtimestamp(latest_time).strftime("%Y-%m-%d %H:%M:%S")
        print(f"Last Run: {latest_run.name}")
        print(f"  Time: {run_time}")
        # Check status from report
        report_content = (latest_run / "report.md").read_text(encoding="utf-8")
        if "PASS" in report_content:
            print(f"  Status: ✅ PASS")
        elif "FAIL" in report_content:
            print(f"  Status: ❌ FAIL")
        else:
            print(f"  Status: unknown")
    else:
        print("Last Run: (no runs found)")
    print()
    
    # Quick health check
    issues = []
    if not config:
        issues.append("Configuration could not be loaded")
    elif config.mode.value == "live":
        # Check AWS credentials
        try:
            import boto3
            boto3.client("sts").get_caller_identity()
        except Exception:
            issues.append("AWS credentials not configured or expired")
    
    if issues:
        print("Issues:")
        for issue in issues:
            print(f"  ⚠️  {issue}")
        print()
        print("Run 'itk doctor' for full diagnostics")
    else:
        print("Health: ✅ Ready")
    
    return 0


def _cmd_validate_env(args: argparse.Namespace) -> int:
    """Validate .env file for ITK configuration."""
    import os
    
    env_file = Path(getattr(args, "env_file", ".env") or ".env")
    mode = getattr(args, "mode", None) or os.environ.get("ITK_MODE", "live")
    
    print("ITK Environment Validation")
    print("=" * 40)
    print()
    
    issues = []
    warnings = []
    
    # 1. Check .env file exists
    if not env_file.exists():
        print(f"❌ .env file not found: {env_file}")
        issues.append("Missing .env file")
        print()
        print("Next step: Run 'itk discover' or copy .env.example")
        return 1
    
    print(f"✅ .env file: {env_file}")
    
    # 2. Parse .env file
    try:
        from itk.config import parse_env_file
        env_vars = parse_env_file(env_file)
        print(f"   Parsed {len(env_vars)} variables")
    except Exception as e:
        print(f"❌ Failed to parse .env: {e}")
        issues.append("Invalid .env format")
        return 1
    
    print()
    
    # 3. Check required fields based on mode
    print(f"Mode: {mode}")
    print()
    
    # Field aliases (ITK_* or standard AWS_*)
    field_aliases = {
        "ITK_AWS_REGION": ["ITK_AWS_REGION", "AWS_REGION"],
        "ITK_MODE": ["ITK_MODE"],
    }
    
    # Always required
    required = ["ITK_MODE"]
    if mode == "live":
        required.extend(["ITK_AWS_REGION"])
    
    # Check required fields
    print("Required fields:")
    for field in required:
        aliases = field_aliases.get(field, [field])
        found = False
        found_val = None
        found_source = None
        
        # Check .env first
        for alias in aliases:
            if alias in env_vars and env_vars[alias]:
                found = True
                found_val = env_vars[alias]
                found_source = alias
                break
        
        # Check environment
        if not found:
            for alias in aliases:
                if os.environ.get(alias):
                    found = True
                    found_val = os.environ[alias]
                    found_source = f"{alias} (from env)"
                    break
        
        if found:
            print(f"  ✅ {found_source}={found_val}")
        else:
            print(f"  ❌ {field} - missing or empty")
            issues.append(f"Missing required field: {field}")
    
    print()
    
    # 4. Check recommended fields
    recommended = ["ITK_LOG_GROUPS"]
    print("Recommended fields:")
    for field in recommended:
        val = env_vars.get(field) or os.environ.get(field)
        if val:
            display = val if len(val) <= 40 else val[:37] + "..."
            print(f"  ✅ {field}={display}")
        else:
            print(f"  ⚠️  {field} - not set")
            warnings.append(f"Recommended field not set: {field}")
    
    print()
    
    # 5. Check AWS credentials (live mode only)
    if mode == "live":
        print("AWS credentials:")
        try:
            import boto3
            sts = boto3.client("sts")
            identity = sts.get_caller_identity()
            print(f"  ✅ Valid - Account {identity['Account']}")
        except Exception as e:
            err = str(e)
            if "credentials" in err.lower() or "token" in err.lower():
                print(f"  ❌ Not configured or expired")
                issues.append("AWS credentials not configured")
            else:
                print(f"  ⚠️  Check failed: {err[:40]}...")
                warnings.append("AWS credential check failed")
    
    print()
    
    # Summary
    print("=" * 40)
    if not issues:
        if warnings:
            print(f"✅ Environment valid ({len(warnings)} warnings)")
        else:
            print("✅ Environment valid - ready to use!")
        return 0
    else:
        print(f"❌ {len(issues)} issue(s) found:")
        for issue in issues:
            print(f"   • {issue}")
        return 1


def _cmd_quickstart(args: argparse.Namespace) -> int:
    """Run quickstart workflow for new users."""
    import os
    import shutil
    import webbrowser
    
    print("ITK Quickstart")
    print("=" * 40)
    print()
    
    # Step 1: Check Python and dependencies
    print("Step 1: Checking environment...")
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 10):
        print(f"  ❌ Python 3.10+ required (found {major}.{minor})")
        return 1
    print(f"  ✅ Python {major}.{minor}")
    
    # Check key dependencies
    for dep, import_name in [("PyYAML", "yaml"), ("boto3", "boto3")]:
        try:
            __import__(import_name)
            print(f"  ✅ {dep} installed")
        except ImportError:
            print(f"  ❌ {dep} not installed")
            print()
            print("Run: pip install -e .[dev]")
            return 1
    print()
    
    # Step 2: Handle .env file
    print("Step 2: Configuration...")
    env_file = Path(".env")
    env_example = Path(".env.example")
    
    if not env_file.exists():
        if env_example.exists():
            shutil.copy(env_example, env_file)
            print(f"  ✅ Created .env from .env.example")
        else:
            print(f"  ⚠️  No .env file (will use defaults)")
    else:
        print(f"  ✅ .env file exists")
    print()
    
    # Step 3: Determine mode
    mode = os.environ.get("ITK_MODE", "dev-fixtures")
    print(f"Step 3: Mode = {mode}")
    
    # Step 4: Find and run first case
    print()
    print("Step 4: Running first test case...")
    cases_dir = Path("cases")
    if not cases_dir.exists():
        print(f"  ❌ No cases directory found")
        return 1
    
    case_files = list(cases_dir.glob("*.yaml"))
    if not case_files:
        print(f"  ❌ No case files in cases/")
        return 1
    
    # Prefer my-first-test.yaml or first file
    first_case = None
    for c in case_files:
        if "my-first-test" in c.name.lower() or "first" in c.name.lower():
            first_case = c
            break
    if not first_case:
        first_case = case_files[0]
    
    print(f"  Using: {first_case}")
    
    out_dir = Path("artifacts/quickstart")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Build args for run command using a simple namespace
    run_args = argparse.Namespace(
        case=str(first_case),
        out=str(out_dir),
        mode=mode,
        env_file=str(env_file) if env_file.exists() else None,
        no_redact=False,
    )
    
    print(f"  Running in {mode} mode...")
    try:
        result = _cmd_run(run_args)
        if result != 0:
            print(f"  ⚠️  Test completed with issues")
        else:
            print(f"  ✅ Test passed!")
    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        return 1
    
    print()
    
    # Step 5: Open trace viewer
    print("Step 5: Opening trace viewer...")
    trace_viewer = out_dir / "trace-viewer.html"
    if trace_viewer.exists():
        url = f"file://{trace_viewer.resolve()}"
        print(f"  Opening: {url}")
        try:
            webbrowser.open(url)
            print(f"  ✅ Opened in browser")
        except Exception:
            print(f"  ⚠️  Could not open browser automatically")
            print(f"  Open manually: {trace_viewer}")
    else:
        print(f"  ⚠️  trace-viewer.html not generated")
    
    print()
    print("=" * 40)
    print("✅ Quickstart complete!")
    print()
    print("Next steps:")
    print("  • Edit cases/ to add your own test cases")
    print("  • Run 'itk doctor' to check your setup")
    print("  • Run 'itk run --case <your-case.yaml> --out artifacts/run1'")
    
    return 0


def _cmd_bootstrap(args: argparse.Namespace) -> int:
    """Zero-config initialization: discover, configure, scaffold, run."""
    import webbrowser
    from itk.bootstrap import bootstrap, check_credentials, get_default_region, get_default_profile

    region = getattr(args, "region", None)
    profile = getattr(args, "profile", None)
    offline = getattr(args, "offline", False)
    force = getattr(args, "force", False)
    run_test = getattr(args, "run_test", True)

    print("ITK Bootstrap - Zero-Config Initialization")
    print("=" * 45)
    print()

    # Step 1: Credential check
    if not offline:
        region = region or get_default_region()
        profile = profile or get_default_profile()

        print("Step 1: Checking AWS credentials...")
        creds = check_credentials(region=region, profile=profile)
        if creds.valid:
            print(f"  ✅ AWS Account: {creds.account_id}")
            print(f"  ✅ Region: {creds.region}")
        else:
            print(f"  ⚠️  Credentials invalid: {creds.error}")
            if creds.fix_command:
                print(f"  Fix: {creds.fix_command}")
            print(f"  Continuing with offline scaffold...")
            offline = True
        print()
    else:
        print("Step 1: Skipping AWS (offline mode)")
        print()

    # Step 2: Run bootstrap
    print("Step 2: Discovering resources and scaffolding...")
    result = bootstrap(
        region=region,
        profile=profile,
        skip_discovery=offline,
        force=force,
    )

    for step in result.steps_completed:
        print(f"  ✅ {step}")
    for warn in result.warnings:
        print(f"  ⚠️  {warn}")
    for err in result.errors:
        print(f"  ❌ {err}")
    print()

    if not result.success:
        print("❌ Bootstrap failed")
        return 1

    # Step 3: Run example test (unless --no-run)
    if run_test and result.first_case and result.first_case.exists():
        print("Step 3: Running example test...")
        out_dir = Path("artifacts/bootstrap")
        out_dir.mkdir(parents=True, exist_ok=True)

        # Determine mode
        mode = "live" if not offline else "dev-fixtures"

        run_args = argparse.Namespace(
            case=str(result.first_case),
            out=str(out_dir),
            mode=mode,
            env_file=str(result.env_file) if result.env_file else None,
            no_redact=False,
        )

        try:
            run_result = _cmd_run(run_args)
            if run_result == 0:
                print(f"  ✅ Test passed!")
            else:
                print(f"  ⚠️  Test completed with issues")
        except FileNotFoundError as e:
            # Fixture not found in dev-fixtures mode - expected
            if offline:
                print(f"  ⚠️  No fixture available for dev-fixtures mode")
                print(f"  Create a fixture or run with --no-run and use live mode")
            else:
                print(f"  ❌ Error: {e}")
        except Exception as e:
            print(f"  ⚠️  Test error: {e}")
        print()

        # Step 4: Open results
        trace_viewer = out_dir / "trace-viewer.html"
        if trace_viewer.exists():
            print("Step 4: Opening results...")
            url = f"file://{trace_viewer.resolve()}"
            try:
                webbrowser.open(url)
                print(f"  ✅ Opened {trace_viewer}")
            except Exception:
                print(f"  Open manually: {trace_viewer}")
            print()
    else:
        print("Step 3: Skipping test run")
        print()

    # Summary
    print("=" * 45)
    print("✅ Bootstrap complete!")
    print()
    print("Created files:")
    if result.env_file:
        print(f"  • {result.env_file}")
    if result.first_case:
        print(f"  • {result.first_case}")
    print()
    print("Next steps:")
    print("  • Review .env and adjust settings")
    print("  • Edit cases/my-first-test.yaml for your use case")
    print("  • Run 'itk run --case cases/my-first-test.yaml --out artifacts/run1'")

    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    """Initialize ITK directory structure (no AWS required)."""
    from itk.bootstrap import bootstrap, find_project_root

    force = getattr(args, "force", False)

    print("ITK Init - Directory Scaffolding")
    print("=" * 35)
    print()

    root = find_project_root()
    print(f"Project root: {root}")
    print()

    result = bootstrap(
        root=root,
        skip_discovery=True,
        force=force,
    )

    for step in result.steps_completed:
        print(f"  ✅ {step}")
    for warn in result.warnings:
        print(f"  ⚠️  {warn}")

    print()
    print("Directories created:")
    print("  • cases/        - Test case definitions")
    print("  • fixtures/logs/ - JSONL log fixtures")
    print("  • artifacts/    - Test output directory")
    print()
    print("Next steps:")
    print("  • Run 'itk bootstrap' for full AWS setup")
    print("  • Or run 'itk discover' to find AWS resources")

    return 0


def main() -> None:
    # Perform startup checks
    _check_startup()
    
    p = argparse.ArgumentParser(
        prog="itk",
        description="Integration Test Kit: sequence diagram generation and log analysis",
    )
    
    # Global flags
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show full tracebacks on errors",
    )
    p.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
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
    p_run.add_argument(
        "--skip-preflight",
        action="store_true",
        dest="skip_preflight",
        help="Skip pre-flight checks in live mode (not recommended)",
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
        choices=["sqs_event", "lambda_invoke", "bedrock_invoke_agent", "http"],
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

    # explain-schema
    p_explain = sub.add_parser(
        "explain-schema",
        help="Pretty-print a schema with field descriptions and examples",
    )
    p_explain.add_argument(
        "schema",
        nargs="?",
        default="span",
        choices=["span", "case", "config"],
        help="Which schema to explain (default: span)",
    )
    p_explain.set_defaults(func=_cmd_explain_schema)

    # validate-log
    p_vallog = sub.add_parser(
        "validate-log",
        help="Validate each line of a JSONL file against the span schema",
    )
    p_vallog.add_argument(
        "--file", "-f",
        required=True,
        help="Path to JSONL file to validate",
    )
    p_vallog.set_defaults(func=_cmd_validate_log)

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

    # doctor
    p_doctor = sub.add_parser(
        "doctor",
        help="Check ITK environment, dependencies, and configuration",
    )
    p_doctor.add_argument(
        "--mode",
        choices=["dev-fixtures", "live"],
        default="live",
        help="Check for this mode (default: live)",
    )
    p_doctor.add_argument(
        "--env-file",
        dest="env_file",
        help="Path to .env file to check (default: ./.env)",
    )
    p_doctor.set_defaults(func=_cmd_doctor)

    # discover
    p_discover = sub.add_parser(
        "discover",
        help="Discover AWS resources and generate .env.discovered file",
    )
    p_discover.add_argument(
        "--region",
        help="AWS region to scan (default: from env or us-east-1)",
    )
    p_discover.add_argument(
        "--profile",
        help="AWS CLI profile to use",
    )
    p_discover.add_argument(
        "--out",
        default=".env.discovered",
        help="Output file path (default: .env.discovered)",
    )
    p_discover.add_argument(
        "--apply",
        action="store_true",
        help="Merge discovered values directly into .env (creates if missing)",
    )
    p_discover.set_defaults(func=_cmd_discover)

    # view - historical execution viewer
    p_view = sub.add_parser(
        "view",
        help="View historical executions from CloudWatch logs or local files",
    )
    p_view.add_argument(
        "--since",
        required=True,
        help="Time window start (e.g., 1h, 24h, 7d) - how far back to look",
    )
    p_view.add_argument(
        "--until",
        help="Time window end (e.g., 1h) - offset from now (optional)",
    )
    p_view.add_argument(
        "--out",
        required=True,
        help="Output directory for artifacts",
    )
    p_view.add_argument(
        "--log-groups",
        dest="log_groups",
        help="Comma-separated CloudWatch log groups to query",
    )
    p_view.add_argument(
        "--logs-file",
        dest="logs_file",
        help="Local JSONL file with log events (offline mode)",
    )
    p_view.add_argument(
        "--filter",
        choices=["all", "errors", "warnings", "passed"],
        default="all",
        help="Filter executions by status (default: all)",
    )
    p_view.add_argument(
        "--region",
        help="AWS region (default: from env or us-east-1)",
    )
    p_view.add_argument(
        "--profile",
        help="AWS CLI profile to use",
    )
    p_view.add_argument(
        "--env-file",
        dest="env_file",
        help="Path to .env file (default: ./.env)",
    )
    p_view.set_defaults(func=_cmd_view)

    # show-config
    p_show_config = sub.add_parser(
        "show-config",
        help="Show effective configuration from all sources",
    )
    p_show_config.add_argument(
        "--mode",
        choices=["dev-fixtures", "live"],
        help="Override mode for display",
    )
    p_show_config.add_argument(
        "--env-file",
        dest="env_file",
        help="Path to .env file (default: ./.env)",
    )
    p_show_config.set_defaults(func=_cmd_show_config)

    # status
    p_status = sub.add_parser(
        "status",
        help="Show current ITK status, mode, and last run info",
    )
    p_status.add_argument(
        "--env-file",
        dest="env_file",
        help="Path to .env file (default: ./.env)",
    )
    p_status.set_defaults(func=_cmd_status)

    # validate-env
    p_validate_env = sub.add_parser(
        "validate-env",
        help="Validate .env file configuration",
    )
    p_validate_env.add_argument(
        "--env-file",
        dest="env_file",
        help="Path to .env file to validate (default: ./.env)",
    )
    p_validate_env.add_argument(
        "--mode",
        choices=["dev-fixtures", "live"],
        help="Validate for this mode (default: from env or live)",
    )
    p_validate_env.set_defaults(func=_cmd_validate_env)

    # quickstart
    p_quickstart = sub.add_parser(
        "quickstart",
        help="Run quickstart workflow for new users",
    )
    p_quickstart.set_defaults(func=_cmd_quickstart)

    # bootstrap - zero-config initialization
    p_bootstrap = sub.add_parser(
        "bootstrap",
        help="Zero-config initialization: discover, configure, scaffold, run",
    )
    p_bootstrap.add_argument(
        "--region",
        help="AWS region (auto-detected if not specified)",
    )
    p_bootstrap.add_argument(
        "--profile",
        help="AWS CLI profile to use",
    )
    p_bootstrap.add_argument(
        "--offline",
        action="store_true",
        help="Skip AWS discovery (scaffold only)",
    )
    p_bootstrap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files",
    )
    p_bootstrap.add_argument(
        "--run",
        action="store_true",
        default=True,
        dest="run_test",
        help="Run example test after bootstrap (default: true)",
    )
    p_bootstrap.add_argument(
        "--no-run",
        action="store_false",
        dest="run_test",
        help="Skip running example test",
    )
    p_bootstrap.set_defaults(func=_cmd_bootstrap)

    # init - lightweight scaffolding only
    p_init = sub.add_parser(
        "init",
        help="Initialize ITK directory structure (no AWS required)",
    )
    p_init.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files",
    )
    p_init.set_defaults(func=_cmd_init)

    args = p.parse_args()
    
    # Set verbose mode for error handling
    from itk.errors import set_verbose, handle_exception, ErrorCode
    set_verbose(args.verbose)
    
    try:
        rc = args.func(args)
        raise SystemExit(rc)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user", file=sys.stderr)
        raise SystemExit(130)
    except FileNotFoundError as e:
        handle_exception(e, ErrorCode.E005, str(e))
        raise SystemExit(1)
    except Exception as e:
        # Generic exception handler
        from itk.errors import is_verbose
        if is_verbose():
            import traceback
            traceback.print_exc()
        else:
            print(f"Error: {e}", file=sys.stderr)
            print("Run with --verbose for full traceback", file=sys.stderr)
        raise SystemExit(1)
