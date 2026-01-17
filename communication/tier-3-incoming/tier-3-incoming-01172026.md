# ITK CLI Handler Implementation Guidance (Safe, Company-Agnostic)

**Date:** 2026-01-16
**Author:** [REDACTED]
**Status:** Draft

---

## Objective

Provide actionable, company-agnostic guidance for implementing CLI subcommand handlers in a Python-based test case derivation tool (ITK). This document is safe for public sharing and contains no real data or proprietary information.

---

## Context Summary

- **Project:** Python CLI for test case derivation from log data
- **Current State:**
- CLI entrypoint exists with argument parsing and subcommand stubs
- .env credential loading, log group config, and log extraction logic are in place
- Debugging and dependency issues resolved
- No real logic implemented for CLI subcommand handlers (_cmd_* functions)
- **Goal:** Implement robust, testable handler functions for each CLI subcommand

---

## CLI Handler Implementation Plan

### 1. Handler Function Contract
- Each handler (_cmd_*) should accept parsed arguments and perform the subcommand's core logic
- Handlers should:
- Validate input arguments
- Load required configuration (e.g., from .env or config files)
- Call utility modules for business logic (do not inline complex logic)
- Handle and log exceptions with clear error messages
- Return exit codes or results as appropriate

### 2. Example Handler Skeleton
```python
def _cmd_example(args):
"""Handler for the 'example' subcommand."""
try:
# Validate arguments
if not args.input:
print("Error: --input is required")
return 1
# Load config
config = load_config()
# Call business logic
result = do_example_task(args.input, config)
print(f"Success: {result}")
return 0
except Exception as e:
print(f"Fatal error: {e}")
return 2
```

### 3. Logging and Debugging
- Use print statements or the logging module for traceability
- Log at key steps: argument parsing, config loading, before/after major actions, on exceptions
- Avoid logging sensitive data

### 4. Testing
- Write unit tests for each handler using mock arguments and config
- Test error paths (missing args, bad config, exceptions)
- Use sample/made-up log data for integration tests

### 5. Safety and Data Handling
- Never hardcode or log real credentials, tokens, or PII
- Use only made-up, safe sample data in tests and documentation
- Document all assumptions and input formats

---

## Example: Made-Up CLI Subcommands

- `itk derive --log-file sample.log` # Derive test cases from a log file
- `itk run --case test-case.yaml` # Run a test case
- `itk audit --log-group fake-group` # Audit logs for missing fields

---

## Sample .env (Safe Example)
```
AWS_ACCESS_KEY_ID=FAKEKEY1234567890
AWS_SECRET_ACCESS_KEY=FAKESECRET1234567890
ITK_LOG_GROUPS=fake-log-group-1,fake-log-group-2
```

---

## Implementation Checklist
- [ ] Define handler contract for each subcommand
- [ ] Implement argument validation and config loading
- [ ] Integrate with utility modules for business logic
- [ ] Add robust error handling and logging
- [ ] Write unit and integration tests with made-up data
- [ ] Review for safety and data hygiene

---

## References
- Python argparse documentation
- Python logging best practices
- Example open-source CLI tools (e.g., AWS CLI, kubectl)

---

*This document contains only safe, made-up data and generic implementation guidance. No company or proprietary information is present.*

---

## Appendix: Required Changes Made During Debugging

This section documents all changes made to the ITK CLI and environment to enable successful test case derivation and CLI execution during recent troubleshooting. All examples use made-up data and generic descriptions.

### 1. Debug Logging
- Added print statements after every line in .env loading, import, and main/argparse sections of the CLI entrypoint (cli.py) to trace execution and pinpoint failures.

### 2. Environment and Imports
- Patched sys.path in the bootstrap script to ensure all modules are importable regardless of working directory.
- Added explicit import and loading of python-dotenv in the bootstrap script to guarantee .env variables are loaded before any AWS or log logic runs.

### 3. Dependency Installation
- Installed missing dependencies (e.g., PyYAML) in the Python environment to unblock YAML parsing and config loading.

### 4. CLI Handler Stubs
- Added stubs for all missing _cmd_* handler functions in the CLI entrypoint to unblock argparse subcommand execution and surface further missing dependencies.

### 5. Output Formats
- Defined OUTPUT_FORMATS in the CLI module to resolve missing constant errors and clarify supported output types.

### 6. Error Handling
- Improved error handling in CLI and utility modules to print clear messages on import/config failures, missing arguments, or AWS errors.

### 7. Test Data and Artifacts
- Used only made-up log group names, credentials, and test case files in all .env, CLI, and test artifacts.

---

*This appendix is for implementation context only. No real or sensitive data is included.*

---

## Including a Masked Example Log in ITK Artifacts

When preparing artifacts to be passed back to ITK (for debugging, support, or demonstration), always include a fully masked example log file. This helps others understand the log structure without exposing any sensitive or real data.

- Use the provided EXAMPLE_MASKED_LOG.json as a template.
- Place the file in the artifact bundle alongside other outputs (e.g., test cases, reports).
- Clearly label the file as an example with all specific values masked or anonymized.

**Purpose:**
- Enables safe sharing and troubleshooting of log-driven workflows
- Documents the expected log schema for future users or maintainers

*Never include real logs or unmasked data in shared artifacts.*

---

## Example Scripts: Pulling Agent ID, Alias, and Version

Below are safe, generic example scripts for retrieving agent identifiers, aliases, and versions. These are templates only and use made-up data and field names.

### Python Example (boto3 pattern)
```python
import boto3

def list_agents():
# Use a made-up service name for illustration; replace with actual if needed
client = boto3.client("bedrock-agent", region_name="us-east-1")
response = client.list_agents() # Placeholder; use the real API call
for agent in response.get("Agents", []):
print(f"ID: {agent['Id']}, Alias: {agent.get('Alias', 'N/A')}, Version: {agent.get('Version', 'N/A')}")

if __name__ == "__main__":
list_agents()
```

### Shell Example
```sh
# Example: List agent info (replace with real CLI/tool as needed)
echo "ID: agent-123, Alias: test-alias, Version: v1.0.0"
```

*Replace service names, field names, and commands with those appropriate for your environment. Do not use real credentials or identifiers in shared scripts.*

