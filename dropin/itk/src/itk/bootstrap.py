"""ITK Bootstrap - Zero-config initialization.

This module provides the "drop in and go" experience:
1. Auto-detect environment and credentials
2. Discover AWS resources
3. Generate working .env
4. Create initial test case
5. Run and open results

Design principles:
- ZERO prompts - use sensible defaults
- Fail fast with clear messages
- Idempotent - safe to run multiple times
- Graceful degradation when things are missing
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BootstrapResult:
    """Result of bootstrap operation."""

    success: bool
    steps_completed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    env_file: Path | None = None
    first_case: Path | None = None
    artifacts_dir: Path | None = None


@dataclass
class CredentialStatus:
    """AWS credential check result."""

    valid: bool
    account_id: str | None = None
    arn: str | None = None
    region: str | None = None
    profile: str | None = None
    error: str | None = None
    fix_command: str | None = None


def find_project_root(start: Path | None = None) -> Path:
    """Walk up directory tree to find project root.

    Looks for:
    - .git directory
    - pyproject.toml
    - .env or .env.example
    - itk.config.yaml or itk.toml

    Returns start directory if no markers found.
    """
    current = (start or Path.cwd()).resolve()
    
    # Safely get home directory
    try:
        home = Path.home()
    except RuntimeError:
        home = None

    markers = [".git", "pyproject.toml", ".env", ".env.example", "itk.config.yaml", "itk.toml"]

    for _ in range(20):  # Max depth
        if home and current == home:
            break
        if current == current.parent:
            break

        for marker in markers:
            if (current / marker).exists():
                return current

        current = current.parent

    # Return original if no markers found
    return (start or Path.cwd()).resolve()


def find_env_file(start: Path | None = None) -> Path | None:
    """Find .env file by walking up directory tree.

    Returns None if not found.
    """
    current = (start or Path.cwd()).resolve()
    
    # Safely get home directory
    try:
        home = Path.home()
    except RuntimeError:
        home = None

    for _ in range(20):
        if home and current == home:
            break
        if current == current.parent:
            break

        env_file = current / ".env"
        if env_file.exists():
            return env_file

        current = current.parent

    return None


def check_credentials(region: str | None = None, profile: str | None = None) -> CredentialStatus:
    """Quick credential health check.

    Returns status with fix instructions if invalid.
    """
    try:
        import boto3
    except ImportError:
        return CredentialStatus(
            valid=False,
            error="boto3 not installed",
            fix_command="pip install boto3",
        )

    # Build session
    session_kwargs: dict[str, Any] = {}
    if region:
        session_kwargs["region_name"] = region
    if profile:
        session_kwargs["profile_name"] = profile

    try:
        session = boto3.Session(**session_kwargs)
        sts = session.client("sts")
        identity = sts.get_caller_identity()

        return CredentialStatus(
            valid=True,
            account_id=identity.get("Account"),
            arn=identity.get("Arn"),
            region=session.region_name,
            profile=profile or os.environ.get("AWS_PROFILE"),
        )
    except Exception as e:
        err = str(e)
        fix = None

        if "token" in err.lower() or "expired" in err.lower():
            if profile:
                fix = f"aws sso login --profile {profile}"
            else:
                fix = "aws sso login  # or refresh your MFA session"
        elif "credentials" in err.lower() or "NoCredentialsError" in str(type(e).__name__):
            fix = "aws configure  # or set AWS_PROFILE"
        elif "could not connect" in err.lower():
            fix = "Check your network connection"

        return CredentialStatus(
            valid=False,
            error=err[:100],
            fix_command=fix,
            profile=profile,
        )


def get_default_region() -> str:
    """Get region from environment or boto3 session."""
    # Explicit env vars
    for var in ["AWS_REGION", "AWS_DEFAULT_REGION", "ITK_AWS_REGION"]:
        if os.environ.get(var):
            return os.environ[var]

    # Try boto3 session
    try:
        import boto3

        session = boto3.Session()
        if session.region_name:
            return session.region_name
    except Exception:
        pass

    return "us-east-1"


def get_default_profile() -> str | None:
    """Get AWS profile from environment."""
    return os.environ.get("AWS_PROFILE")


def discover_resources_minimal(
    region: str, profile: str | None = None
) -> dict[str, Any]:
    """Lightweight discovery - just what we need to get started.

    Returns dict with log_groups, agents, region.
    Gracefully handles permission errors.
    """
    result: dict[str, Any] = {
        "region": region,
        "log_groups": [],
        "agents": [],
        "queues": [],
        "errors": [],
    }

    try:
        import boto3
    except ImportError:
        result["errors"].append("boto3 not installed")
        return result

    session_kwargs: dict[str, Any] = {"region_name": region}
    if profile:
        session_kwargs["profile_name"] = profile

    try:
        session = boto3.Session(**session_kwargs)
    except Exception as e:
        result["errors"].append(f"Session failed: {e}")
        return result

    # Log groups - most important for ITK
    try:
        logs = session.client("logs")
        paginator = logs.get_paginator("describe_log_groups")
        for page in paginator.paginate(PaginationConfig={"MaxItems": 100}):
            for group in page.get("logGroups", []):
                name = group["logGroupName"]
                # Filter to likely relevant
                keywords = ["lambda", "agent", "bot", "api", "ecs", "fargate", "bedrock"]
                if any(kw in name.lower() for kw in keywords):
                    result["log_groups"].append(name)
    except Exception as e:
        result["errors"].append(f"logs: {str(e)[:50]}")

    # Bedrock agents
    try:
        bedrock = session.client("bedrock-agent")
        resp = bedrock.list_agents()
        for agent in resp.get("agentSummaries", []):
            # Get aliases for auto-targeting
            aliases = []
            try:
                alias_resp = bedrock.list_agent_aliases(agentId=agent["agentId"])
                for a in alias_resp.get("agentAliasSummaries", []):
                    routing = a.get("routingConfiguration", [])
                    version = routing[0].get("agentVersion", "?") if routing else "?"
                    aliases.append({
                        "id": a["agentAliasId"],
                        "name": a.get("agentAliasName", "unknown"),
                        "version": version,
                    })
            except Exception:
                pass

            result["agents"].append({
                "id": agent["agentId"],
                "name": agent.get("agentName", "unknown"),
                "status": agent.get("agentStatus", "unknown"),
                "aliases": aliases,
            })
    except Exception as e:
        err = str(e)
        if "UnrecognizedClientException" not in err:  # Skip if Bedrock not in region
            result["errors"].append(f"bedrock: {err[:50]}")

    # SQS queues (optional, for queue-based invocation)
    try:
        sqs = session.client("sqs")
        resp = sqs.list_queues()
        result["queues"] = resp.get("QueueUrls", [])[:10]  # Limit to 10
    except Exception as e:
        result["errors"].append(f"sqs: {str(e)[:50]}")

    return result


def generate_env_content(
    region: str,
    log_groups: list[str],
    agent_id: str | None = None,
    alias_id: str | None = None,
    queue_url: str | None = None,
    existing_env: dict[str, str] | None = None,
) -> str:
    """Generate .env file content with discovered values.
    
    Args:
        existing_env: If provided, preserve these values (e.g., AWS credentials)
    """
    from datetime import datetime

    # Preserve existing credentials if provided
    existing = existing_env or {}

    lines = [
        "# ITK Environment Configuration",
        f"# Generated: {datetime.now().isoformat()}",
        "#",
        "# This file was auto-generated by 'itk bootstrap'",
        "# Edit as needed for your environment.",
        "",
        "# Mode: live (real AWS) or dev-fixtures (offline testing)",
        "ITK_MODE=live",
        "",
    ]

    # AWS credentials - preserve if they exist
    if existing.get("AWS_PROFILE"):
        lines.append(f"AWS_PROFILE={existing['AWS_PROFILE']}")
    elif existing.get("AWS_ACCESS_KEY_ID"):
        lines.append(f"AWS_ACCESS_KEY_ID={existing['AWS_ACCESS_KEY_ID']}")
        if existing.get("AWS_SECRET_ACCESS_KEY"):
            lines.append(f"AWS_SECRET_ACCESS_KEY={existing['AWS_SECRET_ACCESS_KEY']}")
        if existing.get("AWS_SESSION_TOKEN"):
            lines.append(f"AWS_SESSION_TOKEN={existing['AWS_SESSION_TOKEN']}")
    else:
        lines.append("# AWS_PROFILE=your-profile  # OR use access keys below")
        lines.append("# AWS_ACCESS_KEY_ID=")
        lines.append("# AWS_SECRET_ACCESS_KEY=")
        lines.append("# AWS_SESSION_TOKEN=  # If using temporary credentials")
    lines.append("")

    lines.append(f"AWS_REGION={existing.get('AWS_REGION', region)}")
    lines.append("")

    # Log groups
    if log_groups:
        lines.append("# CloudWatch log groups to monitor")
        lines.append(f"ITK_LOG_GROUPS={','.join(log_groups[:5])}")
    else:
        lines.append("# ITK_LOG_GROUPS=  # Run 'itk discover' to find log groups")

    lines.append("")

    # Agent
    if agent_id:
        lines.append("# Bedrock Agent")
        lines.append(f"ITK_WORKER_AGENT_ID={agent_id}")
        if alias_id:
            lines.append(f"ITK_WORKER_ALIAS_ID={alias_id}")
    else:
        lines.append("# ITK_WORKER_AGENT_ID=  # Set if using Bedrock agents")
        lines.append("# ITK_WORKER_ALIAS_ID=")

    lines.append("")

    # Queue
    if queue_url:
        lines.append("# SQS Queue (if using queue-based invocation)")
        lines.append(f"ITK_SQS_QUEUE_URL={queue_url}")
    else:
        lines.append("# ITK_SQS_QUEUE_URL=  # Set if using SQS entrypoint")

    lines.append("")

    # Timing defaults
    lines.extend([
        "# Timing",
        "ITK_LOG_DELAY_SECONDS=5",
        "ITK_LOG_QUERY_WINDOW_SECONDS=3600",
        "",
        "# Redaction (comma-separated)",
        "ITK_REDACT_KEYS=password,secret,api_key,token,authorization",
        "",
    ])

    return "\n".join(lines)


def generate_example_case(
    agent_id: str | None = None,
    agent_name: str | None = None,
    alias_id: str | None = None,
) -> str:
    """Generate a minimal example case YAML."""
    import yaml

    # Always default to bedrock_invoke_agent - it's the primary use case
    # and provides clear placeholders when no agent is discovered
    case: dict[str, Any] = {
        "id": "example-001",
        "name": "Example Test Case",
        "description": "Auto-generated example case. Edit to match your use case.",
        "entrypoint": {
            "type": "bedrock_invoke_agent",
        },
    }

    if agent_id:
        case["entrypoint"]["agent_id"] = agent_id
        if alias_id:
            case["entrypoint"]["alias_id"] = alias_id
        else:
            case["entrypoint"]["agent_version"] = "latest"
    else:
        # Provide placeholder with clear instructions
        case["entrypoint"]["agent_id"] = "YOUR_AGENT_ID_HERE"
        case["entrypoint"]["alias_id"] = "TSTALIASID"
        case["description"] = (
            "EDIT THIS: Replace YOUR_AGENT_ID_HERE with your Bedrock Agent ID. "
            "Find it in AWS Console → Bedrock → Agents."
        )

    case["entrypoint"]["prompt"] = "Hello, this is a test message."
    case["entrypoint"]["session_id"] = "itk-test-session"

    case["invariants"] = [
        {"type": "no_error_spans"},
        {"type": "max_duration_ms", "value": 30000},
    ]

    return yaml.dump(case, default_flow_style=False, sort_keys=False, allow_unicode=True)


def ensure_directories(root: Path) -> list[Path]:
    """Create standard ITK directory structure.

    Returns list of created directories.
    """
    dirs = [
        root / "cases",
        root / "fixtures" / "logs",
        root / "artifacts",
    ]

    created = []
    for d in dirs:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created.append(d)

    return created


def bootstrap(
    root: Path | None = None,
    region: str | None = None,
    profile: str | None = None,
    skip_discovery: bool = False,
    force: bool = False,
) -> BootstrapResult:
    """Full bootstrap: discover, configure, scaffold.

    Args:
        root: Project root (auto-detected if None)
        region: AWS region (auto-detected if None)
        profile: AWS profile (from env if None)
        skip_discovery: Skip AWS discovery (offline mode)
        force: Overwrite existing files

    Returns:
        BootstrapResult with status and created files
    """
    result = BootstrapResult(success=False)

    # Step 1: Find project root
    root = root or find_project_root()
    result.steps_completed.append(f"Project root: {root}")

    # Step 2: Check credentials (unless skipping discovery)
    if not skip_discovery:
        region = region or get_default_region()
        profile = profile or get_default_profile()

        creds = check_credentials(region=region, profile=profile)
        if not creds.valid:
            result.errors.append(f"AWS credentials invalid: {creds.error}")
            if creds.fix_command:
                result.errors.append(f"Fix: {creds.fix_command}")
            # Continue anyway - we can still scaffold
            result.warnings.append("Continuing without AWS discovery")
            skip_discovery = True
        else:
            result.steps_completed.append(f"AWS: {creds.account_id} ({creds.region})")

    # Step 3: Create directory structure
    created_dirs = ensure_directories(root)
    if created_dirs:
        result.steps_completed.append(f"Created directories: {[str(d.relative_to(root)) for d in created_dirs]}")

    # Step 4: Discover resources
    discovered: dict[str, Any] = {"log_groups": [], "agents": [], "queues": [], "region": region or "us-east-1"}
    if not skip_discovery:
        region = region or get_default_region()
        discovered = discover_resources_minimal(region, profile)
        if discovered["errors"]:
            for e in discovered["errors"]:
                result.warnings.append(f"Discovery: {e}")

        result.steps_completed.append(
            f"Discovered: {len(discovered['log_groups'])} log groups, "
            f"{len(discovered['agents'])} agents"
        )

    # Step 5: Generate .env
    env_file = root / ".env"
    
    # Parse existing .env to preserve credentials
    existing_env: dict[str, str] = {}
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    existing_env[key.strip()] = value.strip()
        except Exception:
            pass  # Best effort
    
    if not env_file.exists() or force:
        # Pick first agent if available
        agent_id = None
        alias_id = None
        if discovered["agents"]:
            first_agent = discovered["agents"][0]
            agent_id = first_agent["id"]
            # Prefer alias with version mapping
            if first_agent.get("aliases"):
                alias_id = first_agent["aliases"][0]["id"]

        content = generate_env_content(
            region=discovered["region"],
            log_groups=discovered["log_groups"],
            agent_id=agent_id,
            alias_id=alias_id,
            queue_url=discovered["queues"][0] if discovered["queues"] else None,
            existing_env=existing_env,  # Preserve credentials
        )
        env_file.write_text(content, encoding="utf-8")
        result.env_file = env_file
        result.steps_completed.append(f"Created .env")
    else:
        result.warnings.append(".env already exists (use --force to overwrite)")
        result.env_file = env_file

    # Step 6: Generate example case
    cases_dir = root / "cases"
    example_case = cases_dir / "example-001.yaml"
    if not example_case.exists() or force:
        agent_id = None
        alias_id = None
        agent_name = None
        if discovered["agents"]:
            first_agent = discovered["agents"][0]
            agent_id = first_agent["id"]
            agent_name = first_agent.get("name")
            if first_agent.get("aliases"):
                alias_id = first_agent["aliases"][0]["id"]

        content = generate_example_case(
            agent_id=agent_id,
            agent_name=agent_name,
            alias_id=alias_id,
        )
        example_case.write_text(content, encoding="utf-8")
        result.first_case = example_case
        result.steps_completed.append(f"Created example case")
    else:
        result.warnings.append("Example case already exists")
        result.first_case = example_case

    result.artifacts_dir = root / "artifacts"
    result.success = True
    return result


def require_credentials(
    region: str | None = None,
    profile: str | None = None,
    command: str = "this command",
) -> CredentialStatus:
    """Check credentials and exit with helpful message if invalid.

    Use at the start of any command that needs AWS.
    """
    creds = check_credentials(region=region, profile=profile)

    if not creds.valid:
        print(f"❌ AWS credentials required for {command}", file=sys.stderr)
        print(f"   Error: {creds.error}", file=sys.stderr)
        if creds.fix_command:
            print(f"   Fix: {creds.fix_command}", file=sys.stderr)
        sys.exit(1)

    return creds
