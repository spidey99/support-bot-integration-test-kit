"""ITK configuration management.

Handles:
- Environment mode (dev-fixtures vs live)
- .env file loading with precedence: CLI > .env > env vars
- Resolver hook for dynamic target resolution
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Mode(str, Enum):
    """ITK execution mode."""

    DEV_FIXTURES = "dev-fixtures"
    LIVE = "live"


@dataclass
class Targets:
    """Resolved target resources for live mode."""

    sqs_queue_url: str | None = None
    log_groups: list[str] = field(default_factory=list)
    aws_region: str = "us-east-1"
    lambda_function_name: str | None = None
    bedrock_agent_id: str | None = None
    bedrock_agent_alias_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Targets:
        """Create Targets from a dictionary."""
        return cls(
            sqs_queue_url=data.get("sqs_queue_url"),
            log_groups=data.get("log_groups", []),
            aws_region=data.get("aws_region", "us-east-1"),
            lambda_function_name=data.get("lambda_function_name"),
            bedrock_agent_id=data.get("bedrock_agent_id"),
            bedrock_agent_alias_id=data.get("bedrock_agent_alias_id"),
            extra={
                k: v
                for k, v in data.items()
                if k
                not in {
                    "sqs_queue_url",
                    "log_groups",
                    "aws_region",
                    "lambda_function_name",
                    "bedrock_agent_id",
                    "bedrock_agent_alias_id",
                }
            },
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result: dict[str, Any] = {
            "aws_region": self.aws_region,
        }
        if self.sqs_queue_url:
            result["sqs_queue_url"] = self.sqs_queue_url
        if self.log_groups:
            result["log_groups"] = self.log_groups
        if self.lambda_function_name:
            result["lambda_function_name"] = self.lambda_function_name
        if self.bedrock_agent_id:
            result["bedrock_agent_id"] = self.bedrock_agent_id
        if self.bedrock_agent_alias_id:
            result["bedrock_agent_alias_id"] = self.bedrock_agent_alias_id
        if self.extra:
            result.update(self.extra)
        return result


@dataclass
class Config:
    """ITK runtime configuration."""

    mode: Mode = Mode.LIVE
    targets: Targets = field(default_factory=Targets)
    redact_keys: list[str] = field(default_factory=list)
    redact_patterns: list[str] = field(default_factory=list)
    log_delay_seconds: int = 0
    log_query_window_seconds: int = 3600
    soak_max_inflight: int = 5
    env_file_path: Path | None = None

    def is_live(self) -> bool:
        """Check if running in live mode."""
        return self.mode == Mode.LIVE

    def is_dev_fixtures(self) -> bool:
        """Check if running in dev-fixtures mode."""
        return self.mode == Mode.DEV_FIXTURES


def parse_env_file(env_file: Path) -> dict[str, str]:
    """Parse a .env file into a dictionary.

    Supports:
    - KEY=value
    - KEY="quoted value"
    - KEY='single quoted'
    - export KEY=value (AWS SSO format)
    - export KEY="quoted value"
    - # comments
    - Empty lines
    
    This allows pasting AWS SSO credentials directly:
        export AWS_ACCESS_KEY_ID="ASIA..."
        export AWS_SECRET_ACCESS_KEY="..."
        export AWS_SESSION_TOKEN="..."
    """
    result: dict[str, str] = {}

    if not env_file.exists():
        return result

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith("#"):
            continue

        # Handle 'export KEY=value' format (AWS SSO copy-paste)
        if line.startswith("export "):
            line = line[7:]  # Remove 'export ' prefix

        # Skip lines without =
        if "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        # Remove quotes
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        result[key] = value

    return result


def _find_env_file(start: Path | None = None) -> Path | None:
    """Find .env file by walking up directory tree.

    Stops at git root, home directory, or filesystem root.
    Returns None if not found.
    """
    current = (start or Path.cwd()).resolve()
    
    # Safely get home directory
    try:
        home = Path.home()
    except RuntimeError:
        home = None  # Can't determine home, just walk to root

    for _ in range(20):  # Max depth
        # Check for .env
        env_file = current / ".env"
        if env_file.exists():
            return env_file

        # Stop conditions
        if home and current == home:
            break
        if current == current.parent:
            break

        # Stop at git root (but check .env first)
        if (current / ".git").exists():
            break

        current = current.parent

    return None


def resolve_targets_from_command(resolver_cmd: str) -> Targets:
    """Execute resolver command and parse JSON output.

    The resolver command should output JSON matching itk.targets.schema.json.

    Args:
        resolver_cmd: Shell command to execute

    Returns:
        Targets parsed from command output

    Raises:
        RuntimeError: If command fails or output is invalid
    """
    try:
        result = subprocess.run(
            resolver_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Resolver command failed (exit {result.returncode}): {result.stderr}"
            )

        output = result.stdout.strip()
        if not output:
            raise RuntimeError("Resolver command produced no output")

        data = json.loads(output)
        return Targets.from_dict(data)

    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Resolver command timed out after 30s: {resolver_cmd}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Resolver command output is not valid JSON: {e}") from e


def load_config(
    mode: str | None = None,
    env_file: str | Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> Config:
    """Load configuration with precedence: CLI > .env > env vars.

    Args:
        mode: Explicit mode override (dev-fixtures or live)
        env_file: Path to .env file to load
        cli_overrides: Additional CLI-provided overrides

    Returns:
        Loaded Config instance
    """
    cli_overrides = cli_overrides or {}

    # Step 1: Load environment variables as base
    env_vars = dict(os.environ)

    # Step 2: Load .env file and merge (overrides env vars)
    env_file_path: Path | None = None
    if env_file:
        env_file_path = Path(env_file)
        if env_file_path.exists():
            file_vars = parse_env_file(env_file_path)
            env_vars.update(file_vars)
            # Also update os.environ so ${VAR} substitutions work
            # Only update non-empty values to avoid clobbering existing env vars
            for k, v in file_vars.items():
                if v:  # Only set non-empty values
                    os.environ[k] = v
    else:
        # Auto-discover .env by walking up directory tree
        env_file_path = _find_env_file()
        if env_file_path and env_file_path.exists():
            file_vars = parse_env_file(env_file_path)
            env_vars.update(file_vars)
            # Also update os.environ so ${VAR} substitutions work
            # Only update non-empty values to avoid clobbering existing env vars
            for k, v in file_vars.items():
                if v:  # Only set non-empty values
                    os.environ[k] = v

    # Step 3: Determine mode
    resolved_mode: Mode
    if mode:
        # CLI explicit mode takes precedence
        resolved_mode = Mode(mode)
    elif "ITK_MODE" in env_vars:
        resolved_mode = Mode(env_vars["ITK_MODE"])
    else:
        # Default to live (Tier-3 expectation)
        resolved_mode = Mode.LIVE

    # Step 4: Resolve targets
    targets: Targets
    resolver_cmd = env_vars.get("ITK_RESOLVER_CMD")

    if resolver_cmd and resolved_mode == Mode.LIVE:
        # Execute resolver to get dynamic targets
        targets = resolve_targets_from_command(resolver_cmd)
    else:
        # Build targets from individual env vars
        log_groups_str = env_vars.get("ITK_LOG_GROUPS", "")
        log_groups = [g.strip() for g in log_groups_str.split(",") if g.strip()]

        targets = Targets(
            sqs_queue_url=env_vars.get("ITK_SQS_QUEUE_URL"),
            log_groups=log_groups,
            aws_region=env_vars.get("ITK_AWS_REGION", "us-east-1"),
            lambda_function_name=env_vars.get("ITK_LAMBDA_FUNCTION_NAME"),
            bedrock_agent_id=env_vars.get("ITK_BEDROCK_AGENT_ID"),
            bedrock_agent_alias_id=env_vars.get("ITK_BEDROCK_AGENT_ALIAS_ID"),
        )

    # Step 5: Parse other config values
    redact_keys_str = env_vars.get("ITK_REDACT_KEYS", "")
    redact_keys = [k.strip() for k in redact_keys_str.split(",") if k.strip()]

    redact_patterns_str = env_vars.get("ITK_REDACT_PATTERNS", "")
    redact_patterns = [p.strip() for p in redact_patterns_str.split(",") if p.strip()]

    log_delay = int(env_vars.get("ITK_LOG_DELAY_SECONDS", "0"))
    query_window = int(env_vars.get("ITK_LOG_QUERY_WINDOW_SECONDS", "3600"))
    max_inflight = int(env_vars.get("ITK_SOAK_MAX_INFLIGHT", "5"))

    return Config(
        mode=resolved_mode,
        targets=targets,
        redact_keys=redact_keys,
        redact_patterns=redact_patterns,
        log_delay_seconds=log_delay,
        log_query_window_seconds=query_window,
        soak_max_inflight=max_inflight,
        env_file_path=env_file_path,
    )


# Global config instance (set by CLI)
_config: Config | None = None


def get_config() -> Config:
    """Get the current configuration.

    Raises:
        RuntimeError: If config not initialized (call load_config first)
    """
    if _config is None:
        raise RuntimeError("Config not initialized. Call load_config() first.")
    return _config


def set_config(config: Config) -> None:
    """Set the global configuration."""
    global _config
    _config = config
