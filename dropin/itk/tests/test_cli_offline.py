"""Tests for the offline CLI pipeline."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


class TestRenderFixture:
    """Tests for the render-fixture command."""

    def test_render_fixture_produces_artifacts(
        self, sample_fixture_path: Path, tmp_path: Path
    ) -> None:
        """Verify render-fixture produces all expected artifact files."""
        out_dir = tmp_path / "output"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "itk",
                "render-fixture",
                "--fixture",
                str(sample_fixture_path),
                "--out",
                str(out_dir),
            ],
            cwd=str(Path(__file__).parent.parent / "src"),
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        # Check all expected files exist
        assert (out_dir / "sequence.mmd").exists(), "sequence.mmd missing"
        assert (out_dir / "spans.jsonl").exists(), "spans.jsonl missing"
        assert (out_dir / "report.md").exists(), "report.md missing"
        assert (out_dir / "payloads").is_dir(), "payloads/ directory missing"

    def test_render_fixture_mermaid_has_participants(
        self, sample_fixture_path: Path, tmp_path: Path
    ) -> None:
        """Verify the Mermaid diagram contains expected participants."""
        out_dir = tmp_path / "output"

        subprocess.run(
            [
                sys.executable,
                "-m",
                "itk",
                "render-fixture",
                "--fixture",
                str(sample_fixture_path),
                "--out",
                str(out_dir),
            ],
            cwd=str(Path(__file__).parent.parent / "src"),
            capture_output=True,
        )

        mermaid = (out_dir / "sequence.mmd").read_text()

        assert "sequenceDiagram" in mermaid
        assert "participant" in mermaid
        # Check for expected components from sample fixture
        assert "entrypoint_sqs_event" in mermaid
        assert "agent_gatekeeper" in mermaid
        assert "lambda_actionGroupFoo" in mermaid


class TestRunDevFixtures:
    """Tests for the run --mode dev-fixtures command."""

    def test_run_dev_fixtures_with_case(
        self, example_case_path: Path, tmp_path: Path
    ) -> None:
        """Verify run --mode dev-fixtures produces artifacts for a case."""
        out_dir = tmp_path / "run-output"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "itk",
                "run",
                "--case",
                str(example_case_path),
                "--mode",
                "dev-fixtures",
                "--out",
                str(out_dir),
            ],
            cwd=str(Path(__file__).parent.parent / "src"),
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}\n{result.stdout}"

        # Check artifacts
        assert (out_dir / "sequence.mmd").exists()
        assert (out_dir / "spans.jsonl").exists()
        assert (out_dir / "report.md").exists()

        # Verify spans.jsonl is valid JSONL
        spans_content = (out_dir / "spans.jsonl").read_text()
        for line in spans_content.strip().split("\n"):
            obj = json.loads(line)
            assert "span_id" in obj
            assert "component" in obj
            assert "operation" in obj

    def test_run_dev_fixtures_creates_payload_files(
        self, example_case_path: Path, tmp_path: Path
    ) -> None:
        """Verify payload JSON files are created for spans with request/response."""
        out_dir = tmp_path / "run-output"

        subprocess.run(
            [
                sys.executable,
                "-m",
                "itk",
                "run",
                "--case",
                str(example_case_path),
                "--mode",
                "dev-fixtures",
                "--out",
                str(out_dir),
            ],
            cwd=str(Path(__file__).parent.parent / "src"),
            capture_output=True,
        )

        payloads_dir = out_dir / "payloads"
        assert payloads_dir.is_dir()

        # Should have at least some payload files
        payload_files = list(payloads_dir.glob("*.json"))
        assert len(payload_files) > 0, "No payload files created"

        # Verify they're valid JSON
        for pf in payload_files:
            json.loads(pf.read_text())

    def test_run_dev_fixtures_report_contains_case_info(
        self, example_case_path: Path, tmp_path: Path
    ) -> None:
        """Verify the report.md contains case information."""
        out_dir = tmp_path / "run-output"

        subprocess.run(
            [
                sys.executable,
                "-m",
                "itk",
                "run",
                "--case",
                str(example_case_path),
                "--mode",
                "dev-fixtures",
                "--out",
                str(out_dir),
            ],
            cwd=str(Path(__file__).parent.parent / "src"),
            capture_output=True,
        )

        report = (out_dir / "report.md").read_text()

        assert "example-001" in report
        assert "Example SQS-shaped entrypoint" in report
        assert "sqs_event" in report


class TestAuditDevFixtures:
    """Tests for the audit --mode dev-fixtures command."""

    def test_audit_dev_fixtures_produces_gaps_report(
        self, example_case_path: Path, tmp_path: Path
    ) -> None:
        """Verify audit --mode dev-fixtures produces logging-gaps.md."""
        out_dir = tmp_path / "audit-output"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "itk",
                "audit",
                "--case",
                str(example_case_path),
                "--mode",
                "dev-fixtures",
                "--out",
                str(out_dir),
            ],
            cwd=str(Path(__file__).parent.parent / "src"),
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        # Check audit artifacts
        assert (out_dir / "logging-gaps.md").exists()
        assert (out_dir / "gaps.json").exists()

        # Verify gaps.json is valid
        gaps = json.loads((out_dir / "gaps.json").read_text())
        assert isinstance(gaps, list)


class TestRenderFixtureFormat:
    """Tests for render-fixture --format option."""

    def test_render_fixture_format_html(
        self, sample_fixture_path: Path, tmp_path: Path
    ) -> None:
        """Verify --format html produces only HTML output."""
        out_dir = tmp_path / "output"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "itk",
                "render-fixture",
                "--fixture",
                str(sample_fixture_path),
                "--out",
                str(out_dir),
                "--format",
                "html",
            ],
            cwd=str(Path(__file__).parent.parent / "src"),
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert (out_dir / "trace-viewer.html").exists()
        # Should not have other outputs
        assert not (out_dir / "sequence.mmd").exists()

    def test_render_fixture_format_mermaid(
        self, sample_fixture_path: Path, tmp_path: Path
    ) -> None:
        """Verify --format mermaid produces only Mermaid output."""
        out_dir = tmp_path / "output"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "itk",
                "render-fixture",
                "--fixture",
                str(sample_fixture_path),
                "--out",
                str(out_dir),
                "--format",
                "mermaid",
            ],
            cwd=str(Path(__file__).parent.parent / "src"),
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert (out_dir / "sequence.mmd").exists()
        mermaid = (out_dir / "sequence.mmd").read_text()
        assert "sequenceDiagram" in mermaid

    def test_render_fixture_format_json(
        self, sample_fixture_path: Path, tmp_path: Path
    ) -> None:
        """Verify --format json produces JSON spans output."""
        out_dir = tmp_path / "output"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "itk",
                "render-fixture",
                "--fixture",
                str(sample_fixture_path),
                "--out",
                str(out_dir),
                "--format",
                "json",
            ],
            cwd=str(Path(__file__).parent.parent / "src"),
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert (out_dir / "spans.json").exists()
        
        # Verify it's valid JSON array
        spans = json.loads((out_dir / "spans.json").read_text())
        assert isinstance(spans, list)
        assert len(spans) > 0
        assert "span_id" in spans[0]
        assert "component" in spans[0]

    def test_render_fixture_format_svg(
        self, sample_fixture_path: Path, tmp_path: Path
    ) -> None:
        """Verify --format svg produces SVG files."""
        out_dir = tmp_path / "output"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "itk",
                "render-fixture",
                "--fixture",
                str(sample_fixture_path),
                "--out",
                str(out_dir),
                "--format",
                "svg",
            ],
            cwd=str(Path(__file__).parent.parent / "src"),
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert (out_dir / "sequence.svg").exists()
        assert (out_dir / "timeline.svg").exists()
        
        # Verify they're valid SVG
        svg_content = (out_dir / "sequence.svg").read_text()
        assert "<svg" in svg_content
        assert "</svg>" in svg_content


class TestServeCommand:
    """Tests for the serve command."""

    def test_serve_help_shows_options(self) -> None:
        """Verify serve --help shows expected options."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "itk",
                "serve",
                "--help",
            ],
            cwd=str(Path(__file__).parent.parent / "src"),
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "--port" in result.stdout
        assert "--no-browser" in result.stdout
        assert "--watch" in result.stdout

