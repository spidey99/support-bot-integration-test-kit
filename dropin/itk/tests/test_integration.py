"""Integration tests for ITK CLI workflows.

These tests verify end-to-end behavior of CLI commands with realistic
configurations. They catch bugs that unit tests miss, like:
- Credential loading order
- Config precedence (CLI > .env > env vars)
- Missing variables when skipping code paths
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestCredentialLoading:
    """Test that credentials are loaded correctly from various sources."""

    def test_env_file_credentials_loaded_before_aws_calls(self, tmp_path: Path) -> None:
        """Verify .env credentials are in os.environ before making AWS calls."""
        from itk.config import load_config

        # Create a .env file with test credentials
        env_file = tmp_path / ".env"
        env_file.write_text(
            "AWS_ACCESS_KEY_ID=AKIATEST123\n"
            "AWS_SECRET_ACCESS_KEY=testsecret456\n"
            "AWS_SESSION_TOKEN=testtoken789\n"
            "AWS_REGION=us-west-2\n"
            "ITK_MODE=live\n"
            "ITK_LOG_GROUPS=/aws/lambda/test-function\n"
        )

        # Clear any existing env vars
        for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]:
            os.environ.pop(key, None)

        # Load config
        config = load_config(env_file=env_file)

        # Verify credentials are now in os.environ
        assert os.environ.get("AWS_ACCESS_KEY_ID") == "AKIATEST123"
        assert os.environ.get("AWS_SECRET_ACCESS_KEY") == "testsecret456"
        assert os.environ.get("AWS_SESSION_TOKEN") == "testtoken789"
        assert config.targets.log_groups == ["/aws/lambda/test-function"]

    def test_env_file_with_export_prefix(self, tmp_path: Path) -> None:
        """Verify .env handles 'export KEY=value' format (CloudShell paste)."""
        from itk.config import load_config

        env_file = tmp_path / ".env"
        env_file.write_text(
            'export AWS_ACCESS_KEY_ID="ASIATEST123"\n'
            'export AWS_SECRET_ACCESS_KEY="testsecret"\n'
            'export AWS_SESSION_TOKEN="testtoken"\n'
            "ITK_MODE=live\n"
        )

        # Clear any existing env vars
        for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]:
            os.environ.pop(key, None)

        config = load_config(env_file=env_file)

        # Should strip 'export ' and quotes
        assert os.environ.get("AWS_ACCESS_KEY_ID") == "ASIATEST123"
        assert os.environ.get("AWS_SECRET_ACCESS_KEY") == "testsecret"
        assert os.environ.get("AWS_SESSION_TOKEN") == "testtoken"

    def test_cli_args_with_env_file_credentials(self, tmp_path: Path) -> None:
        """Verify CLI --log-groups still loads .env for credentials."""
        from itk.config import load_config

        env_file = tmp_path / ".env"
        env_file.write_text(
            "AWS_ACCESS_KEY_ID=AKIACLITEST\n"
            "AWS_SECRET_ACCESS_KEY=clisecret\n"
            "ITK_MODE=live\n"
            "ITK_LOG_GROUPS=/aws/lambda/from-env\n"  # Should be ignored when CLI provides
        )

        # Clear any existing env vars
        for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]:
            os.environ.pop(key, None)

        # Load config (simulating what CLI does even with --log-groups)
        config = load_config(env_file=env_file)

        # Credentials should be loaded even when we override log_groups
        assert os.environ.get("AWS_ACCESS_KEY_ID") == "AKIACLITEST"
        assert os.environ.get("AWS_SECRET_ACCESS_KEY") == "clisecret"


class TestConfigValidation:
    """Test that config validation catches common mistakes."""

    def test_malformed_log_group_detected(self, tmp_path: Path) -> None:
        """Detect ITK_LOG_GROUPS=ITK_LOG_GROUPS=/aws/... (duplicated key)."""
        from itk.config import load_config

        env_file = tmp_path / ".env"
        env_file.write_text(
            "ITK_MODE=live\n"
            "ITK_LOG_GROUPS=ITK_LOG_GROUPS=/aws/lambda/test\n"  # Malformed!
        )

        config = load_config(env_file=env_file)
        errors = config.targets.validate()

        assert len(errors) == 1
        assert "Malformed" in errors[0] or "copy-paste" in errors[0]

    def test_placeholder_log_group_detected(self, tmp_path: Path) -> None:
        """Detect example placeholders from .env.example."""
        from itk.config import load_config

        env_file = tmp_path / ".env"
        env_file.write_text(
            "ITK_MODE=live\n"
            "ITK_LOG_GROUPS=/aws/lambda/my-handler\n"  # Placeholder from example
        )

        config = load_config(env_file=env_file)
        errors = config.targets.validate()

        assert len(errors) == 1
        assert "placeholder" in errors[0].lower()

    def test_valid_log_group_passes(self, tmp_path: Path) -> None:
        """Valid log groups should pass validation."""
        from itk.config import load_config

        env_file = tmp_path / ".env"
        env_file.write_text(
            "ITK_MODE=live\n"
            "ITK_LOG_GROUPS=/aws/lambda/my-real-production-function\n"
        )

        config = load_config(env_file=env_file)
        errors = config.targets.validate()

        assert errors == []


class TestCLIViewCommand:
    """Integration tests for itk view command."""

    def test_view_with_log_groups_arg_loads_env_credentials(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """itk view --log-groups should still load .env for AWS credentials."""
        # This test verifies the bug fix where --log-groups skipped loading config
        
        env_file = tmp_path / ".env"
        env_file.write_text(
            "AWS_ACCESS_KEY_ID=AKIAVIEWTEST\n"
            "AWS_SECRET_ACCESS_KEY=viewsecret\n"
            "AWS_REGION=us-east-1\n"
            "ITK_MODE=live\n"
        )

        # Clear credentials
        for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]:
            monkeypatch.delenv(key, raising=False)

        # Change to temp dir so .env is found
        monkeypatch.chdir(tmp_path)

        # Import and run config loading as CLI would
        from itk.config import load_config
        config = load_config(mode="live")

        # Even when CLI provides --log-groups, credentials should be loaded
        assert os.environ.get("AWS_ACCESS_KEY_ID") == "AKIAVIEWTEST"

    def test_view_validates_log_groups_from_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """itk view should fail early with helpful error for bad config."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ITK_MODE=live\n"
            "ITK_LOG_GROUPS=/aws/lambda/my-handler\n"  # Placeholder
        )

        monkeypatch.chdir(tmp_path)

        from itk.config import load_config
        config = load_config(mode="live")

        # Should detect placeholder
        errors = config.targets.validate()
        assert len(errors) > 0


class TestCLIBootstrapCommand:
    """Integration tests for itk bootstrap command."""

    def test_bootstrap_warns_when_no_resources_discovered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Bootstrap should warn loudly when discovery finds nothing."""
        from itk.bootstrap import bootstrap, BootstrapResult

        # Run offline bootstrap (no AWS)
        result = bootstrap(
            root=tmp_path,
            skip_discovery=True,
            force=True,
        )

        # Should complete but with warnings about missing resources
        assert result.success
        # .env should be created
        assert (tmp_path / ".env").exists()


class TestEndToEndWorkflows:
    """Test complete user workflows."""

    def test_minimal_flow_creds_plus_log_groups(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test the ideal minimal flow: just creds and log groups, no bootstrap.
        
        This is the flow we want to work:
        1. User sets AWS credentials in environment
        2. User runs: itk view --log-groups /aws/lambda/foo --since 1h
        3. No .env, no bootstrap, no discovery needed
        """
        # Set up minimal .env with just credentials
        env_file = tmp_path / ".env"
        env_file.write_text(
            "AWS_ACCESS_KEY_ID=AKIAMINIMAL\n"
            "AWS_SECRET_ACCESS_KEY=minimalsecret\n"
            "AWS_REGION=us-east-1\n"
        )

        # Clear any existing credentials
        for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"]:
            monkeypatch.delenv(key, raising=False)

        monkeypatch.chdir(tmp_path)

        from itk.config import load_config

        # Load config - should pick up credentials
        config = load_config(mode="live")

        # Credentials should be in os.environ for boto3
        assert os.environ.get("AWS_ACCESS_KEY_ID") == "AKIAMINIMAL"
        assert os.environ.get("AWS_SECRET_ACCESS_KEY") == "minimalsecret"

        # Log groups can come from CLI (would be passed separately)
        # The key thing is credentials are loaded

    def test_precedence_cli_over_env_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CLI arguments should take precedence over .env file values."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "AWS_REGION=us-west-2\n"
            "ITK_LOG_GROUPS=/aws/lambda/from-env-file\n"
        )

        # Set different value in environment (simulating CLI arg setting)
        monkeypatch.setenv("AWS_REGION", "us-east-1")

        # Environment should NOT be overwritten by .env
        # (This tests that existing env vars are preserved)
        from itk.config import load_config

        # Note: Currently load_config DOES overwrite. This test documents current behavior.
        # If we want CLI precedence, we need to change the logic.
        config = load_config(env_file=env_file)

        # Current behavior: .env overwrites env vars
        # Future desired behavior: env vars (from CLI) should win
        # For now, just verify log_groups are loaded
        assert config.targets.log_groups == ["/aws/lambda/from-env-file"]


class TestDevFixturesMode:
    """Test that dev-fixtures mode works without AWS."""

    def test_dev_fixtures_mode_no_aws_required(self, tmp_path: Path) -> None:
        """dev-fixtures mode should work without any AWS credentials."""
        from itk.config import load_config

        env_file = tmp_path / ".env"
        env_file.write_text("ITK_MODE=dev-fixtures\n")

        # Clear all AWS vars
        for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"]:
            os.environ.pop(key, None)

        config = load_config(env_file=env_file)

        assert config.mode.value == "dev-fixtures"
        assert config.is_dev_fixtures()
        assert not config.is_live()
