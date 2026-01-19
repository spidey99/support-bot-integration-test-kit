"""Integration tests that simulate real user flows.

These tests run CLI commands as subprocesses to catch bugs that unit tests miss:
- Import errors (missing imports)
- CLI argument parsing issues
- Environment variable handling
- File system interactions
- The "export" prefix handling in .env files

These are slow but catch real bugs that happen at the seams.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


# Skip these in CI unless explicitly enabled
pytestmark = pytest.mark.skipif(
    os.environ.get("ITK_RUN_INTEGRATION_TESTS") != "1",
    reason="Integration tests require ITK_RUN_INTEGRATION_TESTS=1"
)


class TestBootstrapFlow:
    """Test the bootstrap flow as a real user would experience it."""

    @pytest.fixture
    def isolated_project(self, tmp_path: Path) -> Path:
        """Create an isolated project directory with ITK installed."""
        project = tmp_path / "project"
        project.mkdir()
        
        # Copy ITK source (simulating dropin copy)
        src_itk = Path(__file__).parent.parent
        itk_dest = project / "itk"
        
        # Copy relevant directories
        for item in ["src", "pyproject.toml", "cases", "fixtures", "schemas"]:
            src = src_itk / item
            if src.exists():
                if src.is_dir():
                    shutil.copytree(src, itk_dest / item)
                else:
                    (itk_dest).mkdir(exist_ok=True)
                    shutil.copy(src, itk_dest / item)
        
        return project

    def run_itk(self, project: Path, *args: str) -> subprocess.CompletedProcess:
        """Run ITK command in project directory."""
        env = {
            **os.environ,
            "PYTHONPATH": str(project / "itk" / "src"),
            # Force UTF-8 encoding on Windows to handle emoji in CLI output
            "PYTHONUTF8": "1",
        }
        return subprocess.run(
            [sys.executable, "-m", "itk", *args],
            cwd=project / "itk",
            capture_output=True,
            text=True,
            env=env,
        )

    def test_bootstrap_creates_env_without_crash(self, isolated_project: Path) -> None:
        """Bootstrap should complete without crashing."""
        result = self.run_itk(isolated_project, "bootstrap", "--offline")
        
        assert result.returncode == 0, f"Bootstrap failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        assert (isolated_project / "itk" / ".env").exists()
        assert "Bootstrap complete" in result.stdout

    def test_bootstrap_does_not_create_env_with_fixme(self, isolated_project: Path) -> None:
        """Bootstrap should not create .env with FIXME placeholders."""
        # Create .env.example to verify it's not auto-copied
        (isolated_project / "itk" / ".env.example").write_text(
            "AWS_ACCESS_KEY_ID=FIXME\nAWS_SECRET_ACCESS_KEY=FIXME\n"
        )
        
        result = self.run_itk(isolated_project, "bootstrap", "--offline")
        
        assert result.returncode == 0, f"Bootstrap failed: {result.stderr}"
        env_content = (isolated_project / "itk" / ".env").read_text()
        assert "FIXME" not in env_content

    def test_bootstrap_preserves_export_prefix_credentials(self, isolated_project: Path) -> None:
        """Credentials with 'export' prefix should be preserved on --force.
        
        This tests the flow where users paste output from:
        aws configure export-credentials --format env
        """
        # Simulate user pasting credentials with export prefix
        (isolated_project / "itk" / ".env").write_text(
            "export AWS_ACCESS_KEY_ID=AKIATEST123\n"
            "export AWS_SECRET_ACCESS_KEY=secrettest\n"
            "export AWS_SESSION_TOKEN=tokentest\n"
        )
        
        result = self.run_itk(isolated_project, "bootstrap", "--force", "--offline")
        
        assert result.returncode == 0, f"Bootstrap failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        
        env_content = (isolated_project / "itk" / ".env").read_text()
        
        # Credentials should be preserved (without export prefix in output)
        assert "AKIATEST123" in env_content
        assert "secrettest" in env_content
        assert "tokentest" in env_content
        
        # The key should be parsed correctly (not "export AWS_ACCESS_KEY_ID")
        lines = env_content.strip().split("\n")
        cred_lines = [l for l in lines if "AKIATEST123" in l]
        assert any(l.startswith("AWS_ACCESS_KEY_ID=") for l in cred_lines), \
            f"Credential key not parsed correctly. Lines: {cred_lines}"

    def test_bootstrap_preserves_quoted_credentials(self, isolated_project: Path) -> None:
        """Credentials with quotes should be preserved."""
        (isolated_project / "itk" / ".env").write_text(
            'export AWS_ACCESS_KEY_ID="AKIATEST456"\n'
            "export AWS_SECRET_ACCESS_KEY='secretwithspecial!@#'\n"
        )
        
        result = self.run_itk(isolated_project, "bootstrap", "--force", "--offline")
        
        assert result.returncode == 0, f"Bootstrap failed: {result.stderr}"
        
        env_content = (isolated_project / "itk" / ".env").read_text()
        assert "AKIATEST456" in env_content

    def test_bootstrap_result_has_discovered_attribute(self, isolated_project: Path) -> None:
        """BootstrapResult should have discovered attribute (regression test)."""
        # This tests the bug we fixed where BootstrapResult.discovered was missing
        from itk.bootstrap import bootstrap
        
        result = bootstrap(
            root=isolated_project / "itk",
            skip_discovery=True,
            force=True,
        )
        
        # Should have discovered attribute (even if None when skipping discovery)
        assert hasattr(result, "discovered")


class TestEnvParsing:
    """Test .env file parsing edge cases."""

    def test_parse_env_file_handles_export_prefix(self, tmp_path: Path) -> None:
        """parse_env_file should handle 'export' prefix correctly."""
        from itk.config import parse_env_file
        
        env_file = tmp_path / ".env"
        env_file.write_text(
            "export AWS_ACCESS_KEY_ID=AKIATEST\n"
            "export AWS_SECRET_ACCESS_KEY=secret\n"
            "export AWS_SESSION_TOKEN=token\n"
            "AWS_REGION=us-east-1\n"  # Without export
        )
        
        parsed = parse_env_file(env_file)
        
        # Keys should NOT have 'export ' prefix
        assert "AWS_ACCESS_KEY_ID" in parsed
        assert "export AWS_ACCESS_KEY_ID" not in parsed
        assert parsed["AWS_ACCESS_KEY_ID"] == "AKIATEST"
        assert parsed["AWS_SECRET_ACCESS_KEY"] == "secret"
        assert parsed["AWS_SESSION_TOKEN"] == "token"
        assert parsed["AWS_REGION"] == "us-east-1"

    def test_parse_env_file_handles_quoted_values(self, tmp_path: Path) -> None:
        """parse_env_file should strip quotes from values."""
        from itk.config import parse_env_file
        
        env_file = tmp_path / ".env"
        env_file.write_text(
            'AWS_ACCESS_KEY_ID="AKIAQUOTED"\n'
            "AWS_SECRET_ACCESS_KEY='secretsingle'\n"
            'export AWS_SESSION_TOKEN="quotedexport"\n'
        )
        
        parsed = parse_env_file(env_file)
        
        # Values should have quotes stripped
        assert parsed["AWS_ACCESS_KEY_ID"] == "AKIAQUOTED"
        assert parsed["AWS_SECRET_ACCESS_KEY"] == "secretsingle"
        assert parsed["AWS_SESSION_TOKEN"] == "quotedexport"

    def test_parse_env_file_handles_empty_lines_and_comments(self, tmp_path: Path) -> None:
        """parse_env_file should skip empty lines and comments."""
        from itk.config import parse_env_file
        
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# Comment\n"
            "  \n"
            "AWS_REGION=us-east-1\n"
            "  # Indented comment\n"
            "\n"
            "ITK_MODE=live\n"
        )
        
        parsed = parse_env_file(env_file)
        
        assert parsed.get("AWS_REGION") == "us-east-1"
        assert parsed.get("ITK_MODE") == "live"
        assert len(parsed) == 2


class TestCLIImports:
    """Test that CLI module imports work correctly."""

    def test_cli_imports_without_error(self) -> None:
        """CLI module should import without missing imports."""
        # This is a regression test for missing 'import os'
        src_dir = Path(__file__).parent.parent / "src"
        env = {**os.environ, "PYTHONPATH": str(src_dir)}
        result = subprocess.run(
            [sys.executable, "-c", "from itk import cli; print('OK')"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert "OK" in result.stdout

    def test_bootstrap_module_imports_without_error(self) -> None:
        """Bootstrap module should import without errors."""
        src_dir = Path(__file__).parent.parent / "src"
        env = {**os.environ, "PYTHONPATH": str(src_dir)}
        result = subprocess.run(
            [sys.executable, "-c", "from itk import bootstrap; print('OK')"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert "OK" in result.stdout


class TestDevFixturesMode:
    """Test that dev-fixtures mode works completely offline."""

    def test_render_fixture_no_aws_needed(self, tmp_path: Path) -> None:
        """render-fixture should work without any AWS credentials."""
        # Clear all AWS env vars
        env = {k: v for k, v in os.environ.items() 
               if not k.startswith("AWS_")}
        env["PYTHONPATH"] = str(Path(__file__).parent.parent / "src")
        
        # Get fixture path
        fixture = Path(__file__).parent.parent / "fixtures" / "logs" / "sample_run_001.jsonl"
        
        if not fixture.exists():
            pytest.skip("Fixture file not found")
        
        result = subprocess.run(
            [sys.executable, "-m", "itk", "render-fixture", 
             "--fixture", str(fixture), 
             "--out", str(tmp_path / "out")],
            capture_output=True,
            text=True,
            env=env,
        )
        
        assert result.returncode == 0, f"render-fixture failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        assert (tmp_path / "out" / "index.html").exists() or (tmp_path / "out" / "trace-viewer.html").exists()
