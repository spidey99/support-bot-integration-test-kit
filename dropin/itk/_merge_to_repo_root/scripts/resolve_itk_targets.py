#!/usr/bin/env python3
"""Resolve ITK targets for the current branch deployment.

This script outputs JSON matching itk.targets.schema.json.
Configure in .env as: ITK_RESOLVER_CMD="python scripts/resolve_itk_targets.py"

Customize this script for your infrastructure's naming conventions.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def get_current_branch() -> str:
    """Get the current git branch name."""
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or "main"


def sanitize_branch_name(branch: str) -> str:
    """Sanitize branch name for use in resource names.
    
    Customize this for your naming conventions.
    """
    # Common patterns: feature/abc -> abc, fix/xyz -> xyz
    if "/" in branch:
        branch = branch.split("/")[-1]
    
    # Replace invalid characters
    return branch.replace("-", "").replace("_", "").lower()[:20]


def resolve_targets(branch: str, region: str = "us-east-1") -> dict:
    """Resolve AWS targets for a branch deployment.
    
    Customize this function for your infrastructure's naming patterns.
    """
    # Sanitize branch for resource naming
    branch_slug = sanitize_branch_name(branch)
    
    # Example: qa-{branch}-* naming pattern
    # Adjust these patterns to match your CDK/IaC output
    
    # For main/prod branch
    if branch in ("main", "master", "prod"):
        prefix = "prod"
    else:
        prefix = f"qa-{branch_slug}"
    
    # Build targets based on your naming conventions
    # These are EXAMPLES - customize for your setup
    targets = {
        "aws_region": region,
        "sqs_queue_url": f"https://sqs.{region}.amazonaws.com/ACCOUNT_ID/{prefix}-support-queue",
        "log_groups": [
            f"/aws/lambda/{prefix}-orchestrator",
            f"/aws/lambda/{prefix}-processor",
            f"/aws/lambda/{prefix}-bedrock-handler",
        ],
        "lambda_function_name": f"{prefix}-orchestrator",
        # Add more targets as needed for your setup
    }
    
    return targets


def resolve_from_cloudformation(stack_name: str, region: str = "us-east-1") -> dict:
    """Alternative: resolve targets from CloudFormation stack outputs.
    
    Useful if your CDK exports values with standard names.
    """
    import boto3
    
    cfn = boto3.client("cloudformation", region_name=region)
    
    try:
        response = cfn.describe_stacks(StackName=stack_name)
        outputs = {
            o["OutputKey"]: o["OutputValue"]
            for o in response["Stacks"][0].get("Outputs", [])
        }
        
        # Map CloudFormation outputs to ITK targets
        # Customize these output key names for your CDK
        return {
            "aws_region": region,
            "sqs_queue_url": outputs.get("SupportQueueUrl"),
            "log_groups": [
                outputs.get("OrchestratorLogGroup"),
                outputs.get("ProcessorLogGroup"),
            ],
            "lambda_function_name": outputs.get("OrchestratorFunctionName"),
        }
    except Exception as e:
        print(f"Failed to get stack outputs: {e}", file=sys.stderr)
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve ITK targets for branch deployment"
    )
    parser.add_argument(
        "--branch",
        help="Branch name (default: current git branch)",
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region (default: us-east-1)",
    )
    parser.add_argument(
        "--from-cfn",
        metavar="STACK_NAME",
        help="Resolve from CloudFormation stack outputs instead",
    )
    
    args = parser.parse_args()
    
    branch = args.branch or get_current_branch()
    
    if args.from_cfn:
        targets = resolve_from_cloudformation(args.from_cfn, args.region)
    else:
        targets = resolve_targets(branch, args.region)
    
    # Output JSON for ITK to consume
    print(json.dumps(targets, indent=2))


if __name__ == "__main__":
    main()
