# ITK Work Repo Setup

## Quick Setup

```bash
# 1. Install ITK (editable mode for dev)
pip install -e dropin/itk[dev]

# 2. Copy .env.example and fill in values
cp dropin/itk/.env.example .env
# Edit .env with your AWS targets

# 3. Verify setup
itk --help
```

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
pip install -e dropin/itk[dev]
# Or run via module
python -m itk --help
```
