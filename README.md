# Support Bot Integration Test Kit (ITK)

[![Tests](https://img.shields.io/badge/tests-461%20passed-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue)]()

**ITK** is a drop-in integration testing toolkit for AWS-based support bot systems using Bedrock Agents, Lambda, and SQS.

It produces **static HTML artifacts** (sequence diagrams, timelines, reports) viewable via `file://` - no server required.

---

## Quick Start for Developers

**Want to add ITK to your work repo?** See [QUICKSTART_TIER3.md](docs/QUICKSTART_TIER3.md) for the 5-minute setup.

---

## What ITK Does

| Feature | Description |
|---------|-------------|
| **Trace Viewer** | Interactive SVG sequence diagrams with zoom, search, filters |
| **Timeline View** | Waterfall visualization showing span durations |
| **Suite Reports** | Hierarchical test reports with pass/warning/fail status |
| **Soak Testing** | Stress testing with consistency metrics and drill-down |
| **Log Gap Audit** | Identifies missing boundary logs in your codebase |
| **Case Derivation** | Generate test cases from CloudWatch logs |

## Architecture: Three Tiers

```
+---------------------------------------------------------------------+
|  TIER 1: Architecture (this README)                                 |
|  Defines schemas, artifacts, and the drop-in structure              |
+---------------------------------------------------------------------+
|  TIER 2: Offline Development (this repo)                            |
|  Implements CLI, rendering, correlation - tested with fixtures      |
|  NO AWS access                                                       |
+---------------------------------------------------------------------+
|  TIER 3: Live Execution (your work repo)                            |
|  Runs real integration tests against AWS QA resources               |
|  Uses the drop-in kit from dropin/itk/                              |
+---------------------------------------------------------------------+
```

## Repository Structure

```
support-bot-integration-test-kit/
|-- docs/                         # Documentation
|   |-- QUICKSTART_TIER3.md       # Developer quick start
|   |-- tier3-*.md                # Tier 3 agent guidance
|   +-- prompts/                  # Copilot prompts for common tasks
|-- dropin/itk/                   # The drop-in kit
|   |-- src/itk/                  # CLI and core modules
|   |-- cases/                    # Example test cases
|   |-- fixtures/                 # Sample fixture data
|   |-- planning/                 # Tier 3 TODO and roadmap
|   +-- _merge_to_repo_root/      # Copilot instructions to merge
+-- planning/                     # Tier 2 development planning
```

## Quickstart: Tier 2 (Offline Development)

If you're developing ITK itself (not using it in a work repo):

```bash
# Clone and setup
git clone https://github.com/spidey99/support-bot-integration-test-kit.git
cd support-bot-integration-test-kit/dropin/itk

# Create virtual environment with Python 3.11+
# IMPORTANT: ITK requires Python 3.11 or newer
python3.11 -m venv .venv              # Use python3.11, python3.12, etc.
source .venv/bin/activate             # Windows: .venv\Scripts\activate

# Verify Python version (must be 3.11+)
python --version                      # Should show Python 3.11.x or higher

# Install ITK
pip install -e ".[dev]"

# Run with fixtures (no AWS)
itk run --mode dev-fixtures --case cases/example-001.yaml --out artifacts/demo/

# Open the trace viewer
open artifacts/demo/trace-viewer.html
```

> **⚠️ Python Version Note:** If you see errors like `SyntaxError` or `ModuleNotFoundError`, 
> verify you're using Python 3.11 or newer. Run `python --version` inside your virtual 
> environment to confirm.

## Quickstart: Tier 3 (Work Repo Integration)

**Full instructions**: [docs/QUICKSTART_TIER3.md](docs/QUICKSTART_TIER3.md)

**TL;DR**:
```bash
# 1. Copy ITK to your work repo
cp -r dropin/itk /path/to/work-repo/tools/itk

# 2. Install
cd /path/to/work-repo/tools/itk && pip install -e ".[dev]"

# 3. Configure
cp .env.example .env && vim .env  # Fill in AWS values

# 4. Run
itk run --case cases/example-001.yaml --out artifacts/run-001/
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `itk run` | Run a single test case |
| `itk suite` | Run multiple cases, generate suite report |
| `itk soak` | Stress test with consistency metrics |
| `itk audit` | Find logging gaps in your traces |
| `itk derive` | Generate cases from CloudWatch logs |
| `itk scan` | Analyze codebase for test coverage |
| `itk validate` | Validate case/fixture YAML files |
| `itk compare` | Compare two test runs |
| `itk serve` | Local preview server with auto-refresh |

## Output Artifacts

Every test run produces:

| File | Description |
|------|-------------|
| `trace-viewer.html` | Interactive SVG sequence diagram |
| `timeline.html` | Waterfall timeline visualization |
| `sequence.mmd` | Mermaid source (GitHub-compatible) |
| `spans.jsonl` | Raw span data in JSONL format |
| `report.md` | Summary with invariant results |
| `payloads/*.json` | Request/response payloads |

## Test Status Icons

| Icon | Status | Meaning |
|------|--------|---------|
| Pass | Passed | All invariants passed, no errors, no retries |
| Warn | Warning | Passed but with retries or error spans |
| Fail | Failed | One or more invariants failed |
| Error | Error | Test execution error |
| Skip | Skipped | Test was skipped |

## Documentation

- [QUICKSTART_TIER3.md](docs/QUICKSTART_TIER3.md) - Developer quick start
- [tier3-cheatsheet.md](docs/tier3-cheatsheet.md) - One-page reference
- [tier3-agent-guide.md](docs/tier3-agent-guide.md) - Full Tier 3 guide
- [tier3-error-fixes.md](docs/tier3-error-fixes.md) - Error to solution lookup

## License

MIT
