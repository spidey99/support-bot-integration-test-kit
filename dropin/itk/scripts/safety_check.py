#!/usr/bin/env python3
"""
ITK Safety Check Script

Run this BEFORE any AWS operation to verify:
1. Credentials are valid
2. You're NOT in a production account
3. .env is configured correctly
4. Required environment variables are set

Usage:
    python scripts/safety_check.py
    python scripts/safety_check.py --verbose
    python scripts/safety_check.py --strict  # Fail on warnings too
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


# =============================================================================
# CONFIGURATION - Customize these for your organization
# =============================================================================

# Account IDs that are PRODUCTION (will block execution)
PRODUCTION_ACCOUNT_PATTERNS = [
    r".*prod.*",  # Any account with 'prod' in the name/alias
    # Add specific production account IDs:
    # "123456789012",
    # "987654321098",
]

# Patterns in queue URLs that indicate PRODUCTION
PRODUCTION_QUEUE_PATTERNS = [
    r".*prod.*",
    r".*production.*",
    r".*prd.*",
]

# Patterns that indicate SAFE (QA/staging)
SAFE_PATTERNS = [
    r".*qa.*",
    r".*staging.*",
    r".*dev.*",
    r".*test.*",
    r".*sandbox.*",
]

# Required environment variables for live mode
REQUIRED_ENV_VARS = [
    "ITK_SQS_QUEUE_URL",
    "ITK_LOG_GROUPS",
]

# =============================================================================
# CHECK FUNCTIONS
# =============================================================================


def check_aws_credentials(verbose: bool = False) -> tuple[bool, str, dict]:
    """Check if AWS credentials are valid and get account info."""
    try:
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode != 0:
            return False, f"AWS credentials invalid: {result.stderr.strip()}", {}
        
        import json
        identity = json.loads(result.stdout)
        
        if verbose:
            print(f"  Account: {identity.get('Account')}")
            print(f"  ARN: {identity.get('Arn')}")
            print(f"  UserId: {identity.get('UserId')}")
        
        return True, "AWS credentials valid", identity
        
    except FileNotFoundError:
        return False, "AWS CLI not found. Install: pip install awscli", {}
    except subprocess.TimeoutExpired:
        return False, "AWS credential check timed out", {}
    except Exception as e:
        return False, f"AWS credential check failed: {e}", {}


def check_not_production(identity: dict, verbose: bool = False) -> tuple[bool, str]:
    """Verify we're not in a production account."""
    account_id = identity.get("Account", "")
    arn = identity.get("Arn", "").lower()
    
    # Check against production patterns
    for pattern in PRODUCTION_ACCOUNT_PATTERNS:
        if re.match(pattern, account_id) or re.match(pattern, arn):
            return False, f"🚨 PRODUCTION ACCOUNT DETECTED: {account_id}"
    
    # Check for safe patterns (optional, just informational)
    is_safe = any(re.match(p, arn) for p in SAFE_PATTERNS)
    
    if verbose:
        if is_safe:
            print(f"  ✓ Account appears to be QA/staging")
        else:
            print(f"  ⚠ Could not confirm QA/staging (verify manually)")
    
    return True, f"Account {account_id} is not in production blocklist"


def check_env_file(verbose: bool = False) -> tuple[bool, str, dict]:
    """Check .env file exists and has required values."""
    # Look for .env in current dir or parent
    env_paths = [
        Path(".env"),
        Path("../.env"),
        Path(os.environ.get("ITK_ENV_FILE", ".env")),
    ]
    
    env_file = None
    for p in env_paths:
        if p.exists():
            env_file = p
            break
    
    if not env_file:
        return False, ".env file not found. Copy .env.example to .env", {}
    
    if verbose:
        print(f"  Found: {env_file.absolute()}")
    
    # Parse env file
    env_vars = {}
    try:
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip()
    except Exception as e:
        return False, f"Failed to read .env: {e}", {}
    
    if verbose:
        for key in ["ITK_MODE", "ITK_SQS_QUEUE_URL", "ITK_LOG_GROUPS", "AWS_REGION"]:
            val = env_vars.get(key, os.environ.get(key, "<not set>"))
            # Mask sensitive values
            if "URL" in key and val != "<not set>":
                val = val[:50] + "..." if len(val) > 50 else val
            print(f"  {key}={val}")
    
    return True, f".env file found: {env_file}", env_vars


def check_itk_mode(env_vars: dict, verbose: bool = False) -> tuple[bool, str]:
    """Check ITK_MODE setting."""
    mode = env_vars.get("ITK_MODE", os.environ.get("ITK_MODE", ""))
    
    if not mode:
        return False, "ITK_MODE not set. Add ITK_MODE=live to .env"
    
    if mode == "dev-fixtures":
        # This is a warning, not an error - might be intentional
        return True, f"ITK_MODE={mode} (offline mode - no AWS calls)"
    
    if mode == "live":
        return True, f"ITK_MODE={mode} (live AWS calls enabled)"
    
    return False, f"ITK_MODE={mode} is not recognized (use 'live' or 'dev-fixtures')"


def check_queue_not_production(env_vars: dict, verbose: bool = False) -> tuple[bool, str]:
    """Check that SQS queue URL doesn't look like production."""
    queue_url = env_vars.get("ITK_SQS_QUEUE_URL", os.environ.get("ITK_SQS_QUEUE_URL", ""))
    
    if not queue_url:
        # Might be using a different entrypoint
        return True, "ITK_SQS_QUEUE_URL not set (may be using different entrypoint)"
    
    queue_lower = queue_url.lower()
    
    for pattern in PRODUCTION_QUEUE_PATTERNS:
        if re.match(pattern, queue_lower):
            return False, f"🚨 PRODUCTION QUEUE DETECTED in URL: {queue_url}"
    
    # Check for safe patterns
    is_safe = any(re.match(p, queue_lower) for p in SAFE_PATTERNS)
    
    if verbose:
        if is_safe:
            print(f"  ✓ Queue URL appears to be QA/staging")
        else:
            print(f"  ⚠ Could not confirm QA/staging queue (verify manually)")
    
    return True, "Queue URL is not in production blocklist"


def check_required_vars(env_vars: dict, verbose: bool = False) -> tuple[bool, str]:
    """Check that required environment variables are set."""
    mode = env_vars.get("ITK_MODE", os.environ.get("ITK_MODE", "live"))
    
    # In dev-fixtures mode, we don't need AWS vars
    if mode == "dev-fixtures":
        return True, "Dev-fixtures mode - AWS vars not required"
    
    missing = []
    for var in REQUIRED_ENV_VARS:
        if not env_vars.get(var) and not os.environ.get(var):
            missing.append(var)
    
    if missing:
        return False, f"Missing required variables: {', '.join(missing)}"
    
    return True, "All required environment variables are set"


# =============================================================================
# MAIN
# =============================================================================


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ITK Safety Check - Run before any AWS operation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/safety_check.py           # Basic check
  python scripts/safety_check.py --verbose # Show details
  python scripts/safety_check.py --strict  # Fail on warnings
        """,
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()

    print("=" * 60)
    print("ITK SAFETY CHECK")
    print("=" * 60)
    print()

    checks = []
    identity = {}
    env_vars = {}

    # Check 1: AWS credentials
    print("1. Checking AWS credentials...")
    ok, msg, identity = check_aws_credentials(args.verbose)
    checks.append(("AWS Credentials", ok, msg))
    print(f"   {'✅' if ok else '❌'} {msg}")
    print()

    # Check 2: Not production (only if creds work)
    if identity:
        print("2. Checking account is not production...")
        ok, msg = check_not_production(identity, args.verbose)
        checks.append(("Not Production", ok, msg))
        print(f"   {'✅' if ok else '🚨'} {msg}")
        print()
    else:
        print("2. Skipping production check (no credentials)")
        print()

    # Check 3: .env file
    print("3. Checking .env configuration...")
    ok, msg, env_vars = check_env_file(args.verbose)
    checks.append((".env File", ok, msg))
    print(f"   {'✅' if ok else '❌'} {msg}")
    print()

    # Check 4: ITK_MODE
    print("4. Checking ITK_MODE...")
    ok, msg = check_itk_mode(env_vars, args.verbose)
    is_warning = "dev-fixtures" in msg
    checks.append(("ITK_MODE", ok, msg, is_warning))
    symbol = "⚠️" if is_warning else ("✅" if ok else "❌")
    print(f"   {symbol} {msg}")
    print()

    # Check 5: Queue URL not production
    print("5. Checking queue URL is not production...")
    ok, msg = check_queue_not_production(env_vars, args.verbose)
    checks.append(("Queue URL", ok, msg))
    print(f"   {'✅' if ok else '🚨'} {msg}")
    print()

    # Check 6: Required variables
    print("6. Checking required variables...")
    ok, msg = check_required_vars(env_vars, args.verbose)
    checks.append(("Required Vars", ok, msg))
    print(f"   {'✅' if ok else '❌'} {msg}")
    print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    errors = [c for c in checks if not c[1]]
    warnings = [c for c in checks if len(c) > 3 and c[3]]  # Has warning flag
    
    if errors:
        print()
        print("❌ FAILED - Do not proceed until these are fixed:")
        for name, ok, msg, *_ in errors:
            print(f"   • {name}: {msg}")
        print()
        return 1
    
    if warnings and args.strict:
        print()
        print("⚠️ WARNINGS (--strict mode):")
        for name, ok, msg, *_ in warnings:
            print(f"   • {name}: {msg}")
        print()
        return 1
    
    if warnings:
        print()
        print("⚠️ WARNINGS (non-blocking):")
        for name, ok, msg, *_ in warnings:
            print(f"   • {name}: {msg}")
    
    print()
    print("✅ All checks passed - Safe to proceed")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
