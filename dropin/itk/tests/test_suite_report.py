"""Tests for suite reporting module."""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from itk.report import (
    CaseResult,
    CaseStatus,
    SuiteResult,
    generate_suite_id,
)
from itk.report.html_report import (
    render_suite_report,
    write_suite_report,
    _format_duration,
    _format_timestamp,
)
from itk.report.suite_runner import (
    discover_cases,
    run_suite,
)


# ============================================================================
# Test CaseResult
# ============================================================================


class TestCaseResult:
    """Tests for CaseResult dataclass."""

    def test_create_passed_result(self) -> None:
        result = CaseResult(
            case_id="test-001",
            case_name="Test Case",
            status=CaseStatus.PASSED,
            duration_ms=100.5,
            span_count=10,
        )
        assert result.passed is True
        assert result.case_id == "test-001"
        assert result.duration_ms == 100.5

    def test_create_failed_result(self) -> None:
        result = CaseResult(
            case_id="test-002",
            case_name="Failed Case",
            status=CaseStatus.FAILED,
            duration_ms=200.0,
            invariant_failures=["no_errors", "valid_timestamps"],
        )
        assert result.passed is False
        assert len(result.invariant_failures) == 2

    def test_create_error_result(self) -> None:
        result = CaseResult(
            case_id="test-003",
            case_name="Error Case",
            status=CaseStatus.ERROR,
            duration_ms=50.0,
            error_message="Connection failed",
        )
        assert result.passed is False
        assert result.error_message == "Connection failed"

    def test_to_dict(self) -> None:
        result = CaseResult(
            case_id="test-001",
            case_name="Test Case",
            status=CaseStatus.PASSED,
            duration_ms=100.0,
            span_count=5,
            error_count=1,
        )
        d = result.to_dict()
        assert d["case_id"] == "test-001"
        assert d["status"] == "passed"
        assert d["span_count"] == 5
        assert d["error_count"] == 1


# ============================================================================
# Test SuiteResult
# ============================================================================


class TestSuiteResult:
    """Tests for SuiteResult dataclass."""

    def test_empty_suite(self) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Empty Suite",
            started_at="2024-01-01T00:00:00Z",
        )
        assert suite.total_cases == 0
        assert suite.passed_count == 0
        assert suite.all_passed is False
        assert suite.pass_rate == 0.0

    def test_suite_with_all_passed(self) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Passing Suite",
            started_at="2024-01-01T00:00:00Z",
            cases=[
                CaseResult(case_id="t1", case_name="Test 1", status=CaseStatus.PASSED, duration_ms=100),
                CaseResult(case_id="t2", case_name="Test 2", status=CaseStatus.PASSED, duration_ms=100),
            ],
        )
        assert suite.total_cases == 2
        assert suite.passed_count == 2
        assert suite.failed_count == 0
        assert suite.all_passed is True
        assert suite.pass_rate == 100.0

    def test_suite_with_mixed_results(self) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Mixed Suite",
            started_at="2024-01-01T00:00:00Z",
            cases=[
                CaseResult(case_id="t1", case_name="Test 1", status=CaseStatus.PASSED, duration_ms=100),
                CaseResult(case_id="t2", case_name="Test 2", status=CaseStatus.FAILED, duration_ms=100),
                CaseResult(case_id="t3", case_name="Test 3", status=CaseStatus.ERROR, duration_ms=100),
                CaseResult(case_id="t4", case_name="Test 4", status=CaseStatus.SKIPPED, duration_ms=0),
            ],
        )
        assert suite.total_cases == 4
        assert suite.passed_count == 1
        assert suite.failed_count == 1
        assert suite.error_count == 1
        assert suite.skipped_count == 1
        assert suite.all_passed is False
        assert suite.pass_rate == 25.0

    def test_total_spans(self) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Suite",
            started_at="2024-01-01T00:00:00Z",
            cases=[
                CaseResult(case_id="t1", case_name="T1", status=CaseStatus.PASSED, duration_ms=100, span_count=10),
                CaseResult(case_id="t2", case_name="T2", status=CaseStatus.PASSED, duration_ms=100, span_count=20),
            ],
        )
        assert suite.total_spans == 30

    def test_total_errors(self) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Suite",
            started_at="2024-01-01T00:00:00Z",
            cases=[
                CaseResult(case_id="t1", case_name="T1", status=CaseStatus.PASSED, duration_ms=100, error_count=2),
                CaseResult(case_id="t2", case_name="T2", status=CaseStatus.FAILED, duration_ms=100, error_count=3),
            ],
        )
        assert suite.total_errors == 5

    def test_to_dict(self) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Test Suite",
            started_at="2024-01-01T00:00:00Z",
            finished_at="2024-01-01T00:01:00Z",
            duration_ms=60000,
            mode="dev-fixtures",
            cases=[
                CaseResult(case_id="t1", case_name="Test 1", status=CaseStatus.PASSED, duration_ms=100),
            ],
        )
        d = suite.to_dict()
        assert d["suite_id"] == "suite-001"
        assert d["suite_name"] == "Test Suite"
        assert d["summary"]["total"] == 1
        assert d["summary"]["passed"] == 1
        assert d["summary"]["pass_rate"] == 100.0
        assert len(d["cases"]) == 1


# ============================================================================
# Test helper functions
# ============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_generate_suite_id(self) -> None:
        suite_id = generate_suite_id()
        assert suite_id.startswith("suite-")
        assert len(suite_id) == 21  # suite-YYYYMMDD-HHMMSS

    def test_format_duration_ms(self) -> None:
        assert _format_duration(100) == "100ms"
        assert _format_duration(999) == "999ms"

    def test_format_duration_seconds(self) -> None:
        assert _format_duration(1000) == "1.0s"
        assert _format_duration(2500) == "2.5s"
        assert _format_duration(59999) == "60.0s"

    def test_format_duration_minutes(self) -> None:
        assert _format_duration(60000) == "1m 0s"
        assert _format_duration(90000) == "1m 30s"
        assert _format_duration(125000) == "2m 5s"

    def test_format_timestamp(self) -> None:
        result = _format_timestamp("2024-01-15T10:30:00Z")
        assert "2024-01-15" in result
        assert "10:30:00" in result

    def test_format_timestamp_none(self) -> None:
        assert _format_timestamp(None) == "—"


# ============================================================================
# Test case discovery
# ============================================================================


class TestCaseDiscovery:
    """Tests for case discovery."""

    def test_discover_cases_empty_dir(self, tmp_path: Path) -> None:
        cases = discover_cases(tmp_path)
        assert cases == []

    def test_discover_cases_nonexistent_dir(self, tmp_path: Path) -> None:
        cases = discover_cases(tmp_path / "nonexistent")
        assert cases == []

    def test_discover_cases_yaml_files(self, tmp_path: Path) -> None:
        (tmp_path / "case1.yaml").write_text("id: case1")
        (tmp_path / "case2.yaml").write_text("id: case2")
        (tmp_path / "README.md").write_text("# README")  # Should be ignored

        cases = discover_cases(tmp_path)

        assert len(cases) == 2
        assert any("case1.yaml" in str(c) for c in cases)
        assert any("case2.yaml" in str(c) for c in cases)

    def test_discover_cases_yml_extension(self, tmp_path: Path) -> None:
        (tmp_path / "case1.yml").write_text("id: case1")

        cases = discover_cases(tmp_path)

        assert len(cases) == 1

    def test_discover_cases_sorted(self, tmp_path: Path) -> None:
        (tmp_path / "z-case.yaml").write_text("id: z")
        (tmp_path / "a-case.yaml").write_text("id: a")
        (tmp_path / "m-case.yaml").write_text("id: m")

        cases = discover_cases(tmp_path)

        assert cases[0].name == "a-case.yaml"
        assert cases[1].name == "m-case.yaml"
        assert cases[2].name == "z-case.yaml"


# ============================================================================
# Test HTML report rendering
# ============================================================================


class TestHTMLReport:
    """Tests for HTML report rendering."""

    def test_render_suite_report_basic(self) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Test Suite",
            started_at="2024-01-01T00:00:00Z",
            finished_at="2024-01-01T00:01:00Z",
            duration_ms=60000,
            cases=[
                CaseResult(case_id="t1", case_name="Test 1", status=CaseStatus.PASSED, duration_ms=100),
            ],
        )

        html = render_suite_report(suite)

        assert "<!DOCTYPE html>" in html
        assert "Test Suite" in html
        assert "suite-001" in html

    def test_render_suite_report_includes_stats(self) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Suite",
            started_at="2024-01-01T00:00:00Z",
            cases=[
                CaseResult(case_id="t1", case_name="T1", status=CaseStatus.PASSED, duration_ms=100, span_count=10),
                CaseResult(case_id="t2", case_name="T2", status=CaseStatus.FAILED, duration_ms=100, span_count=20),
            ],
        )

        html = render_suite_report(suite)

        assert "Total Cases" in html
        assert "Passed" in html
        assert "Failed" in html
        assert "Pass Rate" in html

    def test_render_suite_report_includes_case_rows(self) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Suite",
            started_at="2024-01-01T00:00:00Z",
            cases=[
                CaseResult(
                    case_id="test-case-001",
                    case_name="My Test Case",
                    status=CaseStatus.PASSED,
                    duration_ms=150,
                    span_count=5,
                ),
            ],
        )

        html = render_suite_report(suite)

        assert "test-case-001" in html
        assert "My Test Case" in html
        assert "150ms" in html

    def test_render_suite_report_error_details(self) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Suite",
            started_at="2024-01-01T00:00:00Z",
            cases=[
                CaseResult(
                    case_id="t1",
                    case_name="T1",
                    status=CaseStatus.ERROR,
                    duration_ms=100,
                    error_message="Connection refused",
                ),
            ],
        )

        html = render_suite_report(suite)

        assert "Connection refused" in html
        assert "ERROR" in html

    def test_render_suite_report_invariant_failures(self) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Suite",
            started_at="2024-01-01T00:00:00Z",
            cases=[
                CaseResult(
                    case_id="t1",
                    case_name="T1",
                    status=CaseStatus.FAILED,
                    duration_ms=100,
                    invariant_failures=["no_errors", "valid_timestamps"],
                ),
            ],
        )

        html = render_suite_report(suite)

        assert "no_errors" in html
        assert "valid_timestamps" in html

    def test_render_suite_report_has_filters(self) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Suite",
            started_at="2024-01-01T00:00:00Z",
            cases=[],
        )

        html = render_suite_report(suite)

        assert 'data-filter="all"' in html
        assert 'data-filter="passed"' in html
        assert 'data-filter="failed"' in html

    def test_render_suite_report_has_dark_mode(self) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Suite",
            started_at="2024-01-01T00:00:00Z",
            cases=[],
        )

        html = render_suite_report(suite)

        assert '[data-theme="dark"]' in html
        assert "toggleTheme" in html

    def test_render_suite_report_with_thumbnail(self) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Suite",
            started_at="2024-01-01T00:00:00Z",
            cases=[
                CaseResult(
                    case_id="t1",
                    case_name="T1",
                    status=CaseStatus.PASSED,
                    duration_ms=100,
                    thumbnail_svg='<svg><circle/></svg>',
                ),
            ],
        )

        html = render_suite_report(suite)

        assert "<svg><circle/></svg>" in html

    def test_render_suite_report_with_viewer_link(self) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Suite",
            started_at="2024-01-01T00:00:00Z",
            cases=[
                CaseResult(
                    case_id="t1",
                    case_name="T1",
                    status=CaseStatus.PASSED,
                    duration_ms=100,
                    trace_viewer_path="t1/trace-viewer.html",
                    timeline_path="t1/timeline.html",
                ),
            ],
        )

        html = render_suite_report(suite)

        assert 't1/trace-viewer.html' in html
        assert ">Trace<" in html  # Button text
        assert 't1/timeline.html' in html
        assert ">Timeline<" in html  # Timeline button


# ============================================================================
# Test write_suite_report
# ============================================================================


class TestWriteSuiteReport:
    """Tests for writing suite report files."""

    def test_write_creates_index_html(self, tmp_path: Path) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Suite",
            started_at="2024-01-01T00:00:00Z",
            cases=[],
        )

        write_suite_report(suite, tmp_path)

        assert (tmp_path / "index.html").exists()

    def test_write_creates_index_json(self, tmp_path: Path) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Suite",
            started_at="2024-01-01T00:00:00Z",
            cases=[
                CaseResult(case_id="t1", case_name="T1", status=CaseStatus.PASSED, duration_ms=100),
            ],
        )

        write_suite_report(suite, tmp_path)

        json_path = tmp_path / "index.json"
        assert json_path.exists()

        data = json.loads(json_path.read_text())
        assert data["suite_id"] == "suite-001"
        assert data["summary"]["total"] == 1
        assert len(data["cases"]) == 1

    def test_write_creates_directory(self, tmp_path: Path) -> None:
        suite = SuiteResult(
            suite_id="suite-001",
            suite_name="Suite",
            started_at="2024-01-01T00:00:00Z",
            cases=[],
        )

        out_dir = tmp_path / "nested" / "output"
        write_suite_report(suite, out_dir)

        assert out_dir.exists()
        assert (out_dir / "index.html").exists()
