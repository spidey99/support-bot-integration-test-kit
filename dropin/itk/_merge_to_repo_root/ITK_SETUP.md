# ITK Work Repo Setup

## Quick Setup

```bash
# 1. Create virtual environment with Python 3.11+ (REQUIRED)
python3.11 -m venv .venv              # Use python3.11, python3.12, etc.
source .venv/bin/activate             # Linux/macOS
# .\.venv\Scripts\Activate.ps1        # Windows PowerShell

# 2. Verify Python version (must be 3.11+)
python --version

# 3. Install ITK (editable mode for dev)
pip install -e dropin/itk[dev]

# 4. Copy .env.example and fill in values
cp dropin/itk/.env.example .env
# Edit .env with your AWS targets

# 5. Verify setup
itk --help
```

> **⚠️ Important:** ITK requires Python 3.11 or newer. Using an older version 
> will cause `SyntaxError` or `ModuleNotFoundError` errors.

## Installing Python 3.11+ (if needed)

| OS | Command |
|----|---------|
| Ubuntu/Debian | `sudo apt update && sudo apt install python3.11 python3.11-venv` |
| macOS (Homebrew) | `brew install python@3.11` |
| Windows | Download from https://www.python.org/downloads/ |
| Amazon Linux | `sudo yum install python3.11` |

## Configuration

ITK uses a `.env` file for configuration. Key settings:

| Variable | Description | Example |
|----------|-------------|---------|
| `ITK_MODE` | Execution mode | `live` or `dev-fixtures` |
| `ITK_SQS_QUEUE_URL` | SQS queue for test messages | `https://sqs.us-east-1.amazonaws.com/123/qa-queue` |
| `ITK_LOG_GROUPS` | CloudWatch log groups (comma-separated) | `/aws/lambda/func1,/aws/lambda/func2` |
| `ITK_AWS_REGION` | AWS region | `us-east-1` |

### Branch-Specific Targets

Since your QA environments are per-branch, you can use a resolver script:

```bash
# Set in .env
ITK_RESOLVER_CMD="python scripts/resolve_itk_targets.py --branch $(git branch --show-current)"
```

## VS Code Tasks

If you merged `.vscode/tasks.json`, use `Ctrl+Shift+P` → "Tasks: Run Task" to access:

- **ITK: Run Case (live)** — Run a test against deployed AWS
- **ITK: Run Case (dev-fixtures)** — Run with fixture data (no AWS)
- **ITK: Audit Logging Gaps** — Find missing span logs
- **ITK: Scan Codebase** — Find untested components
- **ITK: Pre-flight Check** — Verify AWS creds and config

## Common Workflows

### Run a Test Case

```bash
# With fixtures (no AWS)
itk run --mode dev-fixtures --case dropin/itk/cases/example-001.yaml --out artifacts/run-001/

# Against live AWS
itk run --mode live --case dropin/itk/cases/smoke-001.yaml --out artifacts/run-002/
```

### Audit Logging Gaps

```bash
itk audit --mode dev-fixtures --case dropin/itk/cases/example-001.yaml --out artifacts/audit/
# Check artifacts/audit/logging-gaps.md for suggestions
```

### Scan for Coverage Gaps

```bash
itk scan --repo . --out artifacts/scan/ --generate-skeletons
# Check artifacts/scan/coverage_report.md
```

### Compare Runs

```bash
itk compare --a artifacts/run-001/ --b artifacts/run-002/ --out artifacts/compare/
```

## Viewing Results

All artifacts are static HTML/Markdown viewable via `file://`:

```bash
# Open trace viewer
start artifacts/run-001/trace-viewer.html   # Windows
open artifacts/run-001/trace-viewer.html    # Mac
xdg-open artifacts/run-001/trace-viewer.html  # Linux
```

## GitLab CI Integration

See `.gitlab/itk.yml` for CI job templates. Add to your `.gitlab-ci.yml`:

```yaml
include:
  - local: '.gitlab/itk.yml'
```

## Troubleshooting

### Python Version Errors (SyntaxError, ModuleNotFoundError)
```bash
# Check Python version
python --version

# If below 3.11, recreate virtual environment:
deactivate
rm -rf .venv
python3.11 -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .\.venv\Scripts\Activate.ps1  # Windows
pip install -e dropin/itk[dev]
```

### "Credentials expired"
```bash
# Re-authenticate and update .env
# Your flow: SSO auth → pick account/role → copy export script → add to .env
```

### "No spans found"
1. Wait 60 seconds for log ingestion
2. Check `ITK_LOG_GROUPS` includes all Lambda log groups
3. Run `itk audit` to find logging gaps

### "Command not found: itk"
```bash
# First, ensure virtual environment is activated
source .venv/bin/activate   # Linux/macOS
# .\.venv\Scripts\Activate.ps1  # Windows

# Then install or reinstall
pip install -e dropin/itk[dev]

# Or run via module
python -m itk --help
```
