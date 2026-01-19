"""Tests for itk.config module."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from itk.config import (
    Config,
    Mode,
    Targets,
    load_config,
    parse_env_file,
    resolve_targets_from_command,
)


class TestMode:
    """Tests for Mode enum."""

    def test_mode_values(self) -> None:
        assert Mode.DEV_FIXTURES.value == "dev-fixtures"
        assert Mode.LIVE.value == "live"

    def test_mode_from_string(self) -> None:
        assert Mode("dev-fixtures") == Mode.DEV_FIXTURES
        assert Mode("live") == Mode.LIVE


class TestTargets:
    """Tests for Targets dataclass."""

    def test_default_targets(self) -> None:
        targets = Targets()
        assert targets.sqs_queue_url is None
        assert targets.log_groups == []
        assert targets.aws_region == "us-east-1"

    def test_targets_from_dict(self) -> None:
        data = {
            "sqs_queue_url": "https://sqs.us-east-1.amazonaws.com/123/queue",
            "log_groups": ["/aws/lambda/func1", "/aws/lambda/func2"],
            "aws_region": "us-west-2",
            "lambda_function_name": "my-func",
            "custom_key": "custom_value",
        }
        targets = Targets.from_dict(data)

        assert targets.sqs_queue_url == "https://sqs.us-east-1.amazonaws.com/123/queue"
        assert targets.log_groups == ["/aws/lambda/func1", "/aws/lambda/func2"]
        assert targets.aws_region == "us-west-2"
        assert targets.lambda_function_name == "my-func"
        assert targets.extra == {"custom_key": "custom_value"}

    def test_targets_to_dict(self) -> None:
        targets = Targets(
            sqs_queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            log_groups=["/aws/lambda/func1"],
            aws_region="us-east-1",
        )
        result = targets.to_dict()

        assert result["sqs_queue_url"] == "https://sqs.us-east-1.amazonaws.com/123/queue"
        assert result["log_groups"] == ["/aws/lambda/func1"]
        assert result["aws_region"] == "us-east-1"

    def test_targets_to_dict_omits_empty(self) -> None:
        targets = Targets()
        result = targets.to_dict()

        assert "sqs_queue_url" not in result
        assert "log_groups" not in result
        assert "aws_region" in result  # Has default value

    def test_validate_good_config(self) -> None:
        """Valid config should have no errors."""
        targets = Targets(
            log_groups=["/aws/lambda/my-real-function"],
            bedrock_agent_id="ABCD1234XY",
        )
        errors = targets.validate()
        assert errors == []

    def test_validate_catches_malformed_log_groups(self) -> None:
        """Detect duplicated key name in value (agent copy-paste error)."""
        targets = Targets(
            log_groups=["ITK_LOG_GROUPS=/aws/lambda/my-function"],
        )
        errors = targets.validate()
        assert len(errors) == 1
        assert "Malformed log group" in errors[0]
        assert "copy-paste error" in errors[0]

    def test_validate_catches_fixme_placeholders(self) -> None:
        """Detect FIXME placeholder values."""
        targets = Targets(
            log_groups=["/aws/lambda/FIXME-your-function"],
        )
        errors = targets.validate()
        assert len(errors) == 1
        assert "Placeholder" in errors[0]

    def test_validate_catches_example_placeholders(self) -> None:
        """Detect example placeholder values from .env.example."""
        targets = Targets(
            log_groups=["/aws/lambda/my-handler", "/aws/lambda/my-other-handler"],
        )
        errors = targets.validate()
        assert len(errors) == 2
        assert all("placeholder from .env.example" in e for e in errors)

    def test_validate_catches_placeholder_agent_id(self) -> None:
        """Detect placeholder agent ID."""
        targets = Targets(
            bedrock_agent_id="<your-agent-id>",
        )
        errors = targets.validate()
        assert len(errors) == 1
        assert "Placeholder agent ID" in errors[0]


class TestConfig:
    """Tests for Config dataclass."""

    def test_default_config(self) -> None:
        config = Config()
        assert config.mode == Mode.LIVE
        assert config.is_live() is True
        assert config.is_dev_fixtures() is False

    def test_dev_fixtures_config(self) -> None:
        config = Config(mode=Mode.DEV_FIXTURES)
        assert config.is_live() is False
        assert config.is_dev_fixtures() is True


class TestParseEnvFile:
    """Tests for parse_env_file function."""

    def test_parse_simple_env(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=value1\nKEY2=value2\n")

        result = parse_env_file(env_file)

        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_parse_quoted_values(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text('DOUBLE="double quoted"\nSINGLE=\'single quoted\'\n')

        result = parse_env_file(env_file)

        assert result == {"DOUBLE": "double quoted", "SINGLE": "single quoted"}

    def test_parse_comments_and_empty_lines(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("# Comment\nKEY=value\n\n# Another comment\n")

        result = parse_env_file(env_file)

        assert result == {"KEY": "value"}

    def test_parse_nonexistent_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / "nonexistent.env"

        result = parse_env_file(env_file)

        assert result == {}

    def test_parse_strips_whitespace(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("  KEY  =  value  \n")

        result = parse_env_file(env_file)

        assert result == {"KEY": "value"}

    def test_parse_skips_lines_without_equals(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("VALID=value\nINVALID LINE\nANOTHER=okay\n")

        result = parse_env_file(env_file)

        assert result == {"VALID": "value", "ANOTHER": "okay"}

    def test_parse_export_prefix(self, tmp_path: Path) -> None:
        """Should handle 'export KEY=value' format (AWS SSO paste)."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            'export AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"\n'
            'export AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"\n'
            'export AWS_SESSION_TOKEN="token123"\n'
        )

        result = parse_env_file(env_file)

        assert result["AWS_ACCESS_KEY_ID"] == "AKIAIOSFODNN7EXAMPLE"
        assert result["AWS_SECRET_ACCESS_KEY"] == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        assert result["AWS_SESSION_TOKEN"] == "token123"

    def test_parse_mixed_export_and_regular(self, tmp_path: Path) -> None:
        """Should handle mix of export and regular KEY=value."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ITK_MODE=live\n"
            "export AWS_ACCESS_KEY_ID=AKIAEXAMPLE\n"
            "ITK_AWS_REGION=us-east-1\n"
        )

        result = parse_env_file(env_file)

        assert result["ITK_MODE"] == "live"
        assert result["AWS_ACCESS_KEY_ID"] == "AKIAEXAMPLE"
        assert result["ITK_AWS_REGION"] == "us-east-1"

    def test_parse_export_unquoted(self, tmp_path: Path) -> None:
        """Should handle 'export KEY=value' without quotes."""
        env_file = tmp_path / ".env"
        env_file.write_text("export MY_VAR=some_value\n")

        result = parse_env_file(env_file)

        assert result["MY_VAR"] == "some_value"


class TestResolveTargetsFromCommand:
    """Tests for resolve_targets_from_command function."""

    def test_resolve_valid_json_output(self) -> None:
        expected_output = json.dumps(
            {
                "sqs_queue_url": "https://sqs.us-east-1.amazonaws.com/123/queue",
                "log_groups": ["/aws/lambda/func1"],
                "aws_region": "us-east-1",
            }
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = expected_output
            mock_run.return_value.stderr = ""

            targets = resolve_targets_from_command("echo test")

            assert targets.sqs_queue_url == "https://sqs.us-east-1.amazonaws.com/123/queue"
            assert targets.log_groups == ["/aws/lambda/func1"]
            assert targets.aws_region == "us-east-1"

    def test_resolve_command_failure(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = "Command failed"

            with pytest.raises(RuntimeError, match="Resolver command failed"):
                resolve_targets_from_command("failing-command")

    def test_resolve_empty_output(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""

            with pytest.raises(RuntimeError, match="no output"):
                resolve_targets_from_command("empty-command")

    def test_resolve_invalid_json(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "not valid json"
            mock_run.return_value.stderr = ""

            with pytest.raises(RuntimeError, match="not valid JSON"):
                resolve_targets_from_command("bad-json-command")


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_default_live_mode(self) -> None:
        # Clear any ITK env vars
        with patch.dict(os.environ, {}, clear=True):
            config = load_config()
            assert config.mode == Mode.LIVE

    def test_load_config_explicit_mode(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = load_config(mode="dev-fixtures")
            assert config.mode == Mode.DEV_FIXTURES

    def test_load_config_from_env_var(self, tmp_path: Path) -> None:
        # Change to a temp dir without .env file to prevent auto-discovery
        import os as os_module
        old_cwd = os_module.getcwd()
        try:
            os_module.chdir(tmp_path)
            with patch.dict(os.environ, {"ITK_MODE": "dev-fixtures"}, clear=True):
                config = load_config()
                assert config.mode == Mode.DEV_FIXTURES
        finally:
            os_module.chdir(old_cwd)

    def test_load_config_cli_overrides_env(self) -> None:
        with patch.dict(os.environ, {"ITK_MODE": "dev-fixtures"}, clear=True):
            config = load_config(mode="live")
            assert config.mode == Mode.LIVE

    def test_load_config_from_env_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("ITK_MODE=dev-fixtures\nITK_AWS_REGION=us-west-2\n")

        with patch.dict(os.environ, {}, clear=True):
            config = load_config(env_file=env_file)
            assert config.mode == Mode.DEV_FIXTURES
            assert config.targets.aws_region == "us-west-2"

    def test_load_config_env_file_overrides_env_var(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("ITK_MODE=dev-fixtures\n")

        with patch.dict(os.environ, {"ITK_MODE": "live"}, clear=True):
            config = load_config(env_file=env_file)
            assert config.mode == Mode.DEV_FIXTURES

    def test_load_config_parses_log_groups(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ITK_MODE=dev-fixtures\n"
            "ITK_LOG_GROUPS=/aws/lambda/func1,/aws/lambda/func2\n"
        )

        with patch.dict(os.environ, {}, clear=True):
            config = load_config(env_file=env_file)
            assert config.targets.log_groups == [
                "/aws/lambda/func1",
                "/aws/lambda/func2",
            ]

    def test_load_config_parses_redact_keys(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ITK_MODE=dev-fixtures\n"
            "ITK_REDACT_KEYS=password,secret,api_key\n"
        )

        with patch.dict(os.environ, {}, clear=True):
            config = load_config(env_file=env_file)
            assert config.redact_keys == ["password", "secret", "api_key"]

    def test_load_config_parses_numeric_values(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ITK_MODE=dev-fixtures\n"
            "ITK_LOG_DELAY_SECONDS=30\n"
            "ITK_LOG_QUERY_WINDOW_SECONDS=7200\n"
            "ITK_SOAK_MAX_INFLIGHT=10\n"
        )

        with patch.dict(os.environ, {}, clear=True):
            config = load_config(env_file=env_file)
            assert config.log_delay_seconds == 30
            assert config.log_query_window_seconds == 7200
            assert config.soak_max_inflight == 10

    def test_load_config_resolver_in_live_mode(self) -> None:
        resolver_output = json.dumps(
            {
                "sqs_queue_url": "https://sqs.us-east-1.amazonaws.com/123/resolved-queue",
                "log_groups": ["/aws/lambda/resolved-func"],
            }
        )

        with patch.dict(
            os.environ,
            {"ITK_RESOLVER_CMD": "echo test"},
            clear=True,
        ):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = resolver_output
                mock_run.return_value.stderr = ""

                config = load_config(mode="live")

                assert config.targets.sqs_queue_url == (
                    "https://sqs.us-east-1.amazonaws.com/123/resolved-queue"
                )
                assert config.targets.log_groups == ["/aws/lambda/resolved-func"]

    def test_load_config_resolver_not_called_in_dev_fixtures(self) -> None:
        with patch.dict(
            os.environ,
            {"ITK_RESOLVER_CMD": "should-not-run"},
            clear=True,
        ):
            with patch("subprocess.run") as mock_run:
                config = load_config(mode="dev-fixtures")

                # Resolver should not be called in dev-fixtures mode
                mock_run.assert_not_called()
                assert config.mode == Mode.DEV_FIXTURES
