"""Suite runner for executing multiple test cases.

This module handles discovery and execution of test cases in a suite,
collecting results and generating consolidated reports.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Sequence

from itk.assertions.invariants import run_all_invariants
from itk.cases.loader import load_case, CaseConfig
from itk.config import Config, get_config
from itk.diagrams.mermaid_seq import render_mermaid_sequence
from itk.diagrams.trace_viewer import render_mini_svg
from itk.logs.parse import load_fixture_jsonl_as_spans
from itk.report import CaseResult, CaseStatus, SuiteResult, generate_suite_id
from itk.trace.build_trace import build_trace_from_spans
from itk.trace.trace_model import Trace
from itk.utils.artifacts import write_run_artifacts


def discover_cases(cases_dir: Path, pattern: str = "*.yaml") -> list[Path]:
    """Discover test case files in a directory.

    Args:
        cases_dir: Directory containing case YAML files.
        pattern: Glob pattern for case files.

    Returns:
        List of paths to case files, sorted alphabetically.
    """
    if not cases_dir.exists():
        return []

    cases = list(cases_dir.glob(pattern))
    # Also check for .yml extension
    cases.extend(cases_dir.glob(pattern.replace(".yaml", ".yml")))

    # Filter out README and other non-case files
    cases = [c for c in cases if c.stem.lower() != "readme"]

    return sorted(cases)


def resolve_fixture_for_case(case_path: Path) -> Optional[Path]:
    """Resolve the fixture path for a given case.

    Looks for:
    1. Explicit fixture_path in the case YAML
    2. A sibling .jsonl file with the same name as the case
    3. A fixture in fixtures/logs/ matching the case ID

    Returns:
        Path to fixture file, or None if not found.
    """
    try:
        case = load_case(case_path)
    except Exception:
        return None

    # Option 1: explicit in case
    if case.fixture_path and case.fixture_path.exists():
        return case.fixture_path

    # Option 2: sibling file
    sibling = case_path.with_suffix(".jsonl")
    if sibling.exists():
        return sibling

    # Option 3: look in fixtures/logs/
    current = case_path.resolve().parent
    for _ in range(10):
        fixtures_dir = current / "fixtures" / "logs"
        if fixtures_dir.exists():
            candidate = fixtures_dir / f"{case.id}.jsonl"
            if candidate.exists():
                return candidate
            # Fall back to sample
            sample = fixtures_dir / "sample_run_001.jsonl"
            if sample.exists():
                return sample
            break
        current = current.parent

    return None


def run_case_dev_fixtures(
    case_path: Path,
    out_dir: Optional[Path] = None,
) -> CaseResult:
    """Run a single case in dev-fixtures mode.

    Args:
        case_path: Path to case YAML file.
        out_dir: Output directory for artifacts. If None, skip artifact writing.
            Used for soak testing where we don't want artifacts per iteration.

    Returns:
        CaseResult with execution details.
    """
    started_at = datetime.now(timezone.utc).isoformat()
    start_time = time.perf_counter()

    try:
        case = load_case(case_path)
    except Exception as e:
        return CaseResult(
            case_id=case_path.stem,
            case_name=case_path.stem,
            status=CaseStatus.ERROR,
            duration_ms=0,
            error_message=f"Failed to load case: {e}",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )

    # Resolve fixture
    fixture_path = resolve_fixture_for_case(case_path)
    if not fixture_path:
        return CaseResult(
            case_id=case.id,
            case_name=case.name,
            status=CaseStatus.ERROR,
            duration_ms=0,
            error_message=f"No fixture found for case",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )

    try:
        # Load and build trace
        spans = load_fixture_jsonl_as_spans(fixture_path)
        trace = build_trace_from_spans(spans)

        # Run invariants
        invariant_results = run_all_invariants(trace)

        # Render artifacts and write if out_dir provided
        mermaid = render_mermaid_sequence(trace)
        case_out_dir: Optional[Path] = None

        if out_dir is not None:
            # Create case-specific output dir
            case_out_dir = out_dir / case.id
            write_run_artifacts(
                out_dir=case_out_dir,
                trace=trace,
                mermaid=mermaid,
                case=case,
                invariant_results=invariant_results,
            )

        # Generate mini SVG for report thumbnail
        mini_svg = render_mini_svg(trace)

        # Calculate metrics
        duration_ms = (time.perf_counter() - start_time) * 1000
        error_count = sum(1 for s in trace.spans if s.error)
        retry_count = sum(1 for s in trace.spans if (s.attempt or 1) > 1)

        # Determine status
        failed_invariants = [r.name for r in invariant_results if not r.passed]
        if failed_invariants:
            status = CaseStatus.FAILED
        elif retry_count > 0 or error_count > 0:
            status = CaseStatus.PASSED_WITH_WARNINGS
        else:
            status = CaseStatus.PASSED

        # Generate mini timeline
        from itk.diagrams.timeline_view import render_mini_timeline
        mini_timeline = render_mini_timeline(trace)

        return CaseResult(
            case_id=case.id,
            case_name=case.name,
            status=status,
            duration_ms=duration_ms,
            span_count=len(trace.spans),
            error_count=error_count,
            retry_count=retry_count,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            invariant_failures=failed_invariants,
            artifacts_dir=str(case_out_dir) if case_out_dir else None,
            trace_viewer_path=f"{case.id}/trace-viewer.html" if case_out_dir else None,
            timeline_path=f"{case.id}/timeline.html" if case_out_dir else None,
            thumbnail_svg=mini_svg,
            timeline_svg=mini_timeline,
            spans=trace.spans,  # Include spans for soak testing
        )

    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        return CaseResult(
            case_id=case.id,
            case_name=case.name,
            status=CaseStatus.ERROR,
            duration_ms=duration_ms,
            error_message=str(e),
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )


def run_suite(
    cases_dir: Path,
    out_dir: Path,
    suite_name: Optional[str] = None,
    case_filter: Optional[Callable[[Path], bool]] = None,
    on_case_complete: Optional[Callable[[CaseResult], None]] = None,
) -> SuiteResult:
    """Run a test suite.

    Args:
        cases_dir: Directory containing case YAML files.
        out_dir: Output directory for all artifacts.
        suite_name: Optional suite name (defaults to directory name).
        case_filter: Optional function to filter which cases to run.
        on_case_complete: Optional callback after each case completes.

    Returns:
        SuiteResult with all case results.
    """
    config = get_config()
    suite_id = generate_suite_id()
    started_at = datetime.now(timezone.utc).isoformat()
    start_time = time.perf_counter()

    # Discover cases
    case_paths = discover_cases(cases_dir)
    if case_filter:
        case_paths = [p for p in case_paths if case_filter(p)]

    # Create output directory
    out_dir.mkdir(parents=True, exist_ok=True)

    # Initialize suite result
    suite = SuiteResult(
        suite_id=suite_id,
        suite_name=suite_name or cases_dir.name,
        started_at=started_at,
        mode=config.mode.value if config else "dev-fixtures",
    )

    # Run each case
    for case_path in case_paths:
        if config and config.is_dev_fixtures():
            result = run_case_dev_fixtures(case_path, out_dir)
        else:
            # Live mode placeholder
            result = CaseResult(
                case_id=case_path.stem,
                case_name=case_path.stem,
                status=CaseStatus.SKIPPED,
                duration_ms=0,
                error_message="Live mode not implemented in Tier 2",
            )

        suite.cases.append(result)

        if on_case_complete:
            on_case_complete(result)

    # Finalize suite
    suite.finished_at = datetime.now(timezone.utc).isoformat()
    suite.duration_ms = (time.perf_counter() - start_time) * 1000

    return suite
