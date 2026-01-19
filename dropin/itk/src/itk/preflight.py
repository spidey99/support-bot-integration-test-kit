"""Pre-flight checks and diagnostics for ITK.

This module provides early validation and clear error messages to catch
common issues BEFORE running tests, saving time and frustration.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CheckResult:
    """Result of a single pre-flight check."""

    name: str
    passed: bool
    message: str
    fix: str | None = None
    details: str | None = None


@dataclass
class PreflightResult:
    """Result of all pre-flight checks."""

    checks: list[CheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        """True if all checks passed."""
        return all(c.passed for c in self.checks)

    @property
    def critical_failed(self) -> bool:
        """True if any critical check failed."""
        critical_names = {"aws_credentials", "log_groups_exist", "agent_accessible"}
        return any(not c.passed for c in self.checks if c.name in critical_names)

    def print_summary(self, file=None) -> None:
        """Print check results."""
        file = file or sys.stderr
        for check in self.checks:
            icon = "✅" if check.passed else "❌"
            print(f"{icon} {check.name}: {check.message}", file=file)
            if not check.passed:
                if check.details:
                    print(f"   Details: {check.details}", file=file)
                if check.fix:
                    print(f"   Fix: {check.fix}", file=file)


def check_aws_credentials(region: str | None = None, profile: str | None = None) -> CheckResult:
    """Check AWS credentials are valid and not expired."""
    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError, TokenRetrievalError
    except ImportError:
        return CheckResult(
            name="aws_credentials",
            passed=False,
            message="boto3 not installed",
            fix="pip install boto3",
        )

    session_kwargs: dict[str, Any] = {}
    if region:
        session_kwargs["region_name"] = region
    if profile:
        session_kwargs["profile_name"] = profile

    try:
        session = boto3.Session(**session_kwargs)
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        return CheckResult(
            name="aws_credentials",
            passed=True,
            message=f"Valid ({identity['Account']})",
            details=identity.get("Arn", ""),
        )
    except NoCredentialsError:
        return CheckResult(
            name="aws_credentials",
            passed=False,
            message="No credentials configured",
            fix="aws configure  # or set AWS_PROFILE",
        )
    except TokenRetrievalError as e:
        return CheckResult(
            name="aws_credentials",
            passed=False,
            message="Token retrieval failed",
            fix=f"aws sso login --profile {profile}" if profile else "Refresh your SSO session",
            details=str(e)[:100],
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code == "ExpiredTokenException":
            return CheckResult(
                name="aws_credentials",
                passed=False,
                message="Session token expired",
                fix=f"aws sso login --profile {profile}" if profile else "Refresh your credentials",
            )
        return CheckResult(
            name="aws_credentials",
            passed=False,
            message=f"AWS error: {error_code}",
            details=str(e)[:100],
        )
    except Exception as e:
        return CheckResult(
            name="aws_credentials",
            passed=False,
            message=f"Unexpected error: {type(e).__name__}",
            details=str(e)[:100],
        )


def check_log_groups_exist(log_groups: list[str], region: str | None = None) -> CheckResult:
    """Check that specified log groups exist in CloudWatch."""
    if not log_groups:
        return CheckResult(
            name="log_groups_exist",
            passed=False,
            message="No log groups configured",
            fix="Run 'itk discover --apply' or set ITK_LOG_GROUPS in .env",
        )

    try:
        import boto3
    except ImportError:
        return CheckResult(
            name="log_groups_exist",
            passed=False,
            message="boto3 not installed",
        )

    try:
        logs = boto3.client("logs", region_name=region)
        existing = set()
        missing = []

        for lg in log_groups:
            try:
                resp = logs.describe_log_groups(logGroupNamePrefix=lg, limit=1)
                groups = resp.get("logGroups", [])
                if any(g["logGroupName"] == lg for g in groups):
                    existing.add(lg)
                else:
                    missing.append(lg)
            except Exception:
                missing.append(lg)

        if not missing:
            return CheckResult(
                name="log_groups_exist",
                passed=True,
                message=f"All {len(log_groups)} log groups exist",
            )
        else:
            return CheckResult(
                name="log_groups_exist",
                passed=False,
                message=f"{len(missing)} log group(s) not found",
                details=", ".join(missing[:3]),
                fix="Check ITK_LOG_GROUPS in .env or run 'itk discover'",
            )
    except Exception as e:
        return CheckResult(
            name="log_groups_exist",
            passed=False,
            message="Failed to check log groups",
            details=str(e)[:100],
        )


def check_agent_accessible(agent_id: str, alias_id: str | None, region: str | None = None) -> CheckResult:
    """Check that the Bedrock agent is accessible."""
    if not agent_id:
        return CheckResult(
            name="agent_accessible",
            passed=False,
            message="No agent ID configured",
            fix="Set ITK_WORKER_AGENT_ID in .env",
        )

    try:
        import boto3
    except ImportError:
        return CheckResult(
            name="agent_accessible",
            passed=False,
            message="boto3 not installed",
        )

    try:
        bedrock = boto3.client("bedrock-agent", region_name=region)
        
        # Check agent exists
        resp = bedrock.get_agent(agentId=agent_id)
        agent_status = resp["agent"].get("agentStatus", "UNKNOWN")
        agent_name = resp["agent"].get("agentName", "Unknown")

        if agent_status != "PREPARED":
            return CheckResult(
                name="agent_accessible",
                passed=False,
                message=f"Agent '{agent_name}' is {agent_status}",
                fix="Prepare the agent in AWS console or use agent_version: 'draft'",
            )

        # Check alias if specified
        if alias_id:
            try:
                alias_resp = bedrock.get_agent_alias(agentId=agent_id, agentAliasId=alias_id)
                alias_status = alias_resp["agentAlias"].get("agentAliasStatus", "UNKNOWN")
                if alias_status != "PREPARED":
                    return CheckResult(
                        name="agent_accessible",
                        passed=False,
                        message=f"Alias {alias_id} is {alias_status}",
                    )
            except Exception as e:
                return CheckResult(
                    name="agent_accessible",
                    passed=False,
                    message=f"Alias {alias_id} not found",
                    details=str(e)[:50],
                )

        return CheckResult(
            name="agent_accessible",
            passed=True,
            message=f"Agent '{agent_name}' is ready",
        )

    except Exception as e:
        error_str = str(e)
        if "ResourceNotFoundException" in error_str:
            return CheckResult(
                name="agent_accessible",
                passed=False,
                message=f"Agent {agent_id} not found",
                fix="Check ITK_WORKER_AGENT_ID value",
            )
        if "AccessDeniedException" in error_str:
            return CheckResult(
                name="agent_accessible",
                passed=False,
                message="Access denied to agent",
                fix="Check IAM permissions for bedrock-agent:GetAgent",
            )
        return CheckResult(
            name="agent_accessible",
            passed=False,
            message="Failed to check agent",
            details=error_str[:100],
        )


def run_preflight_checks(
    region: str | None = None,
    profile: str | None = None,
    log_groups: list[str] | None = None,
    agent_id: str | None = None,
    alias_id: str | None = None,
) -> PreflightResult:
    """Run all pre-flight checks."""
    result = PreflightResult()

    # Always check credentials first
    result.checks.append(check_aws_credentials(region=region, profile=profile))

    # Only check resources if credentials passed
    if result.checks[0].passed:
        if log_groups:
            result.checks.append(check_log_groups_exist(log_groups, region=region))

        if agent_id:
            result.checks.append(check_agent_accessible(agent_id, alias_id, region=region))

    return result
