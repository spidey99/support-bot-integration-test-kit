"""Tests for the bootstrap module."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from itk.bootstrap import (
    find_project_root,
    find_env_file,
    check_credentials,
    get_default_region,
    get_default_profile,
    discover_resources_minimal,
    generate_env_content,
    generate_example_case,
    ensure_directories,
    bootstrap,
    CredentialStatus,
    BootstrapResult,
)


class TestFindProjectRoot:
    """Tests for find_project_root."""

    def test_finds_git_directory(self, tmp_path: Path) -> None:
        """Should find root when .git exists."""
        (tmp_path / ".git").mkdir()
        subdir = tmp_path / "src" / "lib"
        subdir.mkdir(parents=True)

        result = find_project_root(subdir)
        assert result == tmp_path

    def test_finds_pyproject_toml(self, tmp_path: Path) -> None:
        """Should find root when pyproject.toml exists."""
        (tmp_path / "pyproject.toml").touch()
        subdir = tmp_path / "src"
        subdir.mkdir()

        result = find_project_root(subdir)
        assert result == tmp_path

    def test_finds_env_file(self, tmp_path: Path) -> None:
        """Should find root when .env exists."""
        (tmp_path / ".env").touch()
        subdir = tmp_path / "nested"
        subdir.mkdir()

        result = find_project_root(subdir)
        assert result == tmp_path

    def test_returns_start_when_no_markers(self, tmp_path: Path) -> None:
        """Should return start directory when no markers found."""
        result = find_project_root(tmp_path)
        assert result == tmp_path


class TestFindEnvFile:
    """Tests for find_env_file."""

    def test_finds_env_in_current_dir(self, tmp_path: Path) -> None:
        """Should find .env in current directory."""
        env_file = tmp_path / ".env"
        env_file.touch()

        result = find_env_file(tmp_path)
        assert result == env_file

    def test_finds_env_in_parent_dir(self, tmp_path: Path) -> None:
        """Should find .env in parent directory."""
        env_file = tmp_path / ".env"
        env_file.touch()
        subdir = tmp_path / "src"
        subdir.mkdir()

        result = find_env_file(subdir)
        assert result == env_file

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        """Should return None when no .env found."""
        result = find_env_file(tmp_path)
        assert result is None


class TestCheckCredentials:
    """Tests for check_credentials."""

    def test_returns_invalid_when_boto3_not_installed(self) -> None:
        """Should return invalid when boto3 is not available."""
        with patch.dict("sys.modules", {"boto3": None}):
            # Force re-import failure
            import importlib
            with patch("builtins.__import__", side_effect=ImportError):
                result = check_credentials()
                assert not result.valid
                assert "boto3" in result.error or result.fix_command

    def test_returns_valid_with_mock_sts(self) -> None:
        """Should return valid when STS call succeeds."""
        mock_session = MagicMock()
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Account": "123456789012",
            "Arn": "arn:aws:iam::123456789012:user/test",
        }
        mock_session.client.return_value = mock_sts
        mock_session.region_name = "us-east-1"

        with patch("boto3.Session", return_value=mock_session):
            result = check_credentials(region="us-east-1")
            assert result.valid
            assert result.account_id == "123456789012"
            assert result.region == "us-east-1"

    def test_returns_invalid_on_credential_error(self) -> None:
        """Should return invalid with fix command on credential error."""
        with patch("boto3.Session") as mock:
            mock.return_value.client.return_value.get_caller_identity.side_effect = (
                Exception("No credentials configured")
            )
            result = check_credentials()
            assert not result.valid
            assert result.fix_command is not None


class TestGetDefaultRegion:
    """Tests for get_default_region."""

    def test_returns_from_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return region from AWS_REGION env var."""
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        assert get_default_region() == "eu-west-1"

    def test_returns_from_itk_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return region from ITK_AWS_REGION env var."""
        monkeypatch.delenv("AWS_REGION", raising=False)
        monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
        monkeypatch.setenv("ITK_AWS_REGION", "ap-southeast-1")
        assert get_default_region() == "ap-southeast-1"

    def test_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return us-east-1 as default."""
        monkeypatch.delenv("AWS_REGION", raising=False)
        monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
        monkeypatch.delenv("ITK_AWS_REGION", raising=False)
        
        with patch("boto3.Session") as mock:
            mock.return_value.region_name = None
            assert get_default_region() == "us-east-1"


class TestGetDefaultProfile:
    """Tests for get_default_profile."""

    def test_returns_from_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return profile from AWS_PROFILE env var."""
        monkeypatch.setenv("AWS_PROFILE", "my-profile")
        assert get_default_profile() == "my-profile"

    def test_returns_none_when_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return None when AWS_PROFILE not set."""
        monkeypatch.delenv("AWS_PROFILE", raising=False)
        assert get_default_profile() is None


class TestGenerateEnvContent:
    """Tests for generate_env_content."""

    def test_generates_basic_content(self) -> None:
        """Should generate basic .env content."""
        content = generate_env_content(
            region="us-east-1",
            log_groups=["/aws/lambda/test"],
        )
        assert "ITK_MODE=live" in content
        assert "AWS_REGION=us-east-1" in content
        assert "ITK_LOG_GROUPS=/aws/lambda/test" in content

    def test_includes_agent_config(self) -> None:
        """Should include agent config when provided."""
        content = generate_env_content(
            region="us-east-1",
            log_groups=[],
            agent_id="AGENTID123",
            alias_id="ALIASID456",
        )
        assert "ITK_WORKER_AGENT_ID=AGENTID123" in content
        assert "ITK_WORKER_ALIAS_ID=ALIASID456" in content

    def test_includes_queue_url(self) -> None:
        """Should include SQS queue URL when provided."""
        content = generate_env_content(
            region="us-east-1",
            log_groups=[],
            queue_url="https://sqs.us-east-1.amazonaws.com/123/test",
        )
        assert "ITK_SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123/test" in content

    def test_preserves_existing_credentials(self) -> None:
        """Should preserve AWS credentials from existing .env."""
        existing = {
            "AWS_ACCESS_KEY_ID": "AKIATEST123",
            "AWS_SECRET_ACCESS_KEY": "secretkey123",
            "AWS_SESSION_TOKEN": "token123",
            "AWS_REGION": "us-west-2",
        }
        content = generate_env_content(
            region="us-east-1",  # Discovered region, but existing should take precedence
            log_groups=["/aws/lambda/new"],
            existing_env=existing,
        )
        assert "AWS_ACCESS_KEY_ID=AKIATEST123" in content
        assert "AWS_SECRET_ACCESS_KEY=secretkey123" in content
        assert "AWS_SESSION_TOKEN=token123" in content
        assert "AWS_REGION=us-west-2" in content  # Should preserve existing region

    def test_preserves_existing_profile(self) -> None:
        """Should preserve AWS_PROFILE from existing .env."""
        existing = {"AWS_PROFILE": "my-sso-profile"}
        content = generate_env_content(
            region="us-east-1",
            log_groups=[],
            existing_env=existing,
        )
        assert "AWS_PROFILE=my-sso-profile" in content
        assert "AWS_ACCESS_KEY_ID" not in content  # Should not add key placeholders


class TestGenerateExampleCase:
    """Tests for generate_example_case."""

    def test_generates_bedrock_case_with_placeholders_when_no_agent(self) -> None:
        """Should generate bedrock_invoke_agent case with placeholders when no agent provided."""
        content = generate_example_case()
        assert "id: example-001" in content
        assert "bedrock_invoke_agent" in content
        assert "YOUR_AGENT_ID_HERE" in content
        assert "TSTALIASID" in content

    def test_generates_bedrock_case_with_agent(self) -> None:
        """Should generate bedrock case when agent provided."""
        content = generate_example_case(
            agent_id="AGENTID123",
            alias_id="ALIASID456",
        )
        assert "bedrock_invoke_agent" in content
        assert "AGENTID123" in content
        assert "ALIASID456" in content

    def test_uses_latest_version_without_alias(self) -> None:
        """Should use agent_version: latest when no alias."""
        content = generate_example_case(agent_id="AGENTID123")
        assert "agent_version: latest" in content


class TestEnsureDirectories:
    """Tests for ensure_directories."""

    def test_creates_directories(self, tmp_path: Path) -> None:
        """Should create cases, fixtures, artifacts directories."""
        created = ensure_directories(tmp_path)

        assert (tmp_path / "cases").exists()
        assert (tmp_path / "fixtures" / "logs").exists()
        assert (tmp_path / "artifacts").exists()
        assert len(created) == 3

    def test_idempotent(self, tmp_path: Path) -> None:
        """Should not recreate existing directories."""
        (tmp_path / "cases").mkdir()

        created = ensure_directories(tmp_path)

        # Only 2 new directories (fixtures/logs and artifacts)
        assert len(created) == 2
        assert tmp_path / "cases" not in created


class TestBootstrap:
    """Tests for bootstrap function."""

    def test_creates_env_file(self, tmp_path: Path) -> None:
        """Should create .env file."""
        result = bootstrap(root=tmp_path, skip_discovery=True)

        assert result.success
        assert result.env_file is not None
        assert result.env_file.exists()

    def test_creates_example_case(self, tmp_path: Path) -> None:
        """Should create example case file."""
        result = bootstrap(root=tmp_path, skip_discovery=True)

        assert result.success
        assert result.first_case is not None
        assert result.first_case.exists()

    def test_does_not_overwrite_existing(self, tmp_path: Path) -> None:
        """Should not overwrite existing files without force."""
        (tmp_path / "cases").mkdir()
        existing_env = tmp_path / ".env"
        existing_env.write_text("EXISTING=true", encoding="utf-8")

        result = bootstrap(root=tmp_path, skip_discovery=True, force=False)

        assert result.success
        assert existing_env.read_text() == "EXISTING=true"
        assert ".env already exists" in " ".join(result.warnings)

    def test_overwrites_with_force(self, tmp_path: Path) -> None:
        """Should overwrite existing files with force=True."""
        existing_env = tmp_path / ".env"
        existing_env.write_text("EXISTING=true", encoding="utf-8")

        result = bootstrap(root=tmp_path, skip_discovery=True, force=True)

        assert result.success
        assert "ITK_MODE" in existing_env.read_text()

    def test_returns_artifacts_dir(self, tmp_path: Path) -> None:
        """Should return artifacts directory path."""
        result = bootstrap(root=tmp_path, skip_discovery=True)

        assert result.artifacts_dir == tmp_path / "artifacts"
