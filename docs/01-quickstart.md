# Quickstart

## Zero-Config Bootstrap (Recommended)

The fastest way to go from "drop in" to "working tests":

```bash
cd dropin/itk
pip install -e ".[dev]"
itk bootstrap
```

`itk bootstrap` will:
- [ ] Check Python version (3.10+ required)
- [ ] Check if you're in a virtual environment (warns if not)
- [ ] Find or create a `.env` file
- [ ] Check for AWS credentials
- [ ] Auto-discover Bedrock agents and log groups
- [ ] Generate working configuration

### Getting AWS Credentials

#### From AWS CloudShell (easiest)

1. Open AWS Console and click the CloudShell icon (terminal icon in top nav)
2. Run this command:
   ```bash
   aws configure export-credentials --format env
   ```
3. Copy the output and paste into PowerShell (Windows) or terminal (Mac/Linux)

#### From AWS SSO Portal

1. Go to your AWS SSO portal and click "Command line or programmatic access"
2. Copy the `export` block (the one starting with `export AWS_ACCESS_KEY_ID=...`)
3. Paste directly into your `.env` file — ITK handles the `export` syntax

```bash
# .env file - paste exports directly
export AWS_ACCESS_KEY_ID="ASIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."
AWS_REGION=us-east-1
```

### Verify Setup

After bootstrap, view recent executions:

```bash
itk view --since 1h --out artifacts/history
```

Open `artifacts/history/index.html` in your browser.

## Shell Bootstrap Scripts

For one-command setup with virtual environment:

**Mac/Linux:**
```bash
cd dropin/itk
./scripts/bootstrap.sh
```

**Windows PowerShell:**
```powershell
cd dropin\itk
.\scripts\bootstrap.ps1
```

The bootstrap script will:
- [ ] Check Python version (3.10+ required)
- [ ] Create a virtual environment (`.venv`)
- [ ] Install ITK with dev dependencies
- [ ] Copy `.env.example` to `.env` if missing
- [ ] Verify the installation works

## Manual Installation

If you prefer manual setup:

```bash
cd dropin/itk
python -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Tier 2 (dev-fixtures mode - no AWS required)

Use fixtures to test the ITK engine without AWS credentials.

### Render a fixture directly
```bash
itk render-fixture --fixture fixtures/logs/sample_run_001.jsonl --out artifacts/render-001
```

### Run a case in dev-fixtures mode
```bash
itk run --mode dev-fixtures --case cases/example-001.yaml --out artifacts/run-001
```

### Audit logging gaps
```bash
itk audit --mode dev-fixtures --case cases/example-001.yaml --out artifacts/audit-001
```

## Tier 3 (work repo - with AWS access)

After copying the drop-in folder into the work repo:

### Run a case online (golden path: SQS)
```bash
itk run --case cases/my-case.yaml --out artifacts/run-001
```

### Derive cases from CloudWatch logs
```bash
itk derive --entrypoint sqs_event --since 24h --out cases/derived/
```

### Audit logging gaps with live data
```bash
itk audit --case cases/my-case.yaml --out artifacts/audit-001
```

## Entrypoint Types

| Type | Mode | Use Case |
|------|------|----------|
| `sqs_event` | `publish_sqs` | **Golden path** - Full async flow through SQS |
| `sqs_event` | `invoke_lambda` | Fast debug - Synchronous Lambda invocation |
| `lambda_invoke` | - | Direct Lambda invocation |
| `bedrock_invoke_agent` | - | Bedrock Agent with trace enabled |

## Output Artifacts

After running a case, check the output directory:

| File | Description |
|------|-------------|
| `trace-viewer.html` | **Primary** - Interactive SVG sequence diagram with pan/zoom |
| `timeline.html` | Waterfall timeline visualization with critical path |
| `sequence.mmd` | Mermaid sequence diagram (GitHub-compatible) |
| `sequence.html` | Legacy Mermaid-rendered HTML diagram |
| `thumbnail.svg` | Mini sequence preview for suite report |
| `timeline-thumbnail.svg` | Mini timeline preview |
| `spans.jsonl` | All spans in JSONL format |
| `report.md` | Human-readable summary with invariant results |
| `payloads/*.json` | Request/response payloads per span |
| `logging-gaps.md` | (audit only) Missing log fields report |

## Suite Report

Run multiple cases and generate a hierarchical report:

```bash
itk suite --cases-dir cases/ --out artifacts/suite-run/
```

Open `artifacts/suite-run/index.html` to see:
- Summary cards (total, passed, warning, failed, error)
- Collapsible test groups
- Expandable test rows with mini diagrams
- Modal viewers for Sequence and Timeline
- Status filters: ✅ Passed, ⚠️ Warning, ❌ Failed, 💥 Error

## Historical Execution Viewer

View and analyze past executions from CloudWatch logs:

```bash
# View last hour of executions
itk view --since 1h --out artifacts/history/

# View last 24 hours, filter to errors only
itk view --since 24h --filter errors --out artifacts/errors/

# Specify log groups explicitly
itk view --since 1h --log-groups /aws/lambda/my-func,/aws/lambda/other-func --out out/

# Offline mode with local JSONL file
itk view --since 1h --logs-file logs.jsonl --out out/
```

Open `artifacts/history/index.html` to see a gallery of all executions with:
- Timestamp, status, duration, span count
- Component badges showing what systems were involved
- Filter buttons: All, Passed, Warnings, Errors
- Click "View" to open trace viewer for any execution
- Click "Timeline" to see waterfall view

Each execution generates its own subdirectory with:
- `trace-viewer.html` - Interactive sequence diagram
- `timeline.html` - Waterfall timeline visualization
- `spans.jsonl` - Raw span data
- `thumbnail.svg` - Mini preview for gallery

## Format Options

Export specific formats with `--format`:

```bash
# HTML only
itk render-fixture --fixture fixtures/logs/sample_run_001.jsonl --out out --format html

# Mermaid only
itk render-fixture --fixture fixtures/logs/sample_run_001.jsonl --out out --format mermaid

# JSON spans
itk render-fixture --fixture fixtures/logs/sample_run_001.jsonl --out out --format json

# SVG diagrams (sequence + timeline)
itk render-fixture --fixture fixtures/logs/sample_run_001.jsonl --out out --format svg

# All formats (default)
itk render-fixture --fixture fixtures/logs/sample_run_001.jsonl --out out --format all
```

## Live Preview Server

Serve artifacts with auto-opening browser:

```bash
# Serve artifacts directory
itk serve artifacts/run-001

# Custom port
itk serve artifacts/run-001 --port 9000

# No auto-browser
itk serve artifacts/run-001 --no-browser

# Watch mode (re-renders on source changes)
itk serve artifacts/run-001 --watch
```

## Troubleshooting

### AWS Session Token Expired

**Symptom:** `ExpiredTokenException` or "AWS session token has expired"

**Fix:**
```bash
aws sso login  # If using SSO
# Or re-export temporary credentials from AWS Console
```

### Pre-flight Checks Failed

ITK runs automatic pre-flight checks in live mode. To bypass (not recommended):

```bash
itk run --case cases/my-case.yaml --out out --skip-preflight
```

### No Spans Parsed from Logs

**Symptom:** "Parsed 0 spans from 100 log events"

**Possible causes:**
- [ ] Log format doesn't match ITK span schema
- [ ] Wrong time window (check `--since`)
- [ ] Wrong log groups configured

**Debug steps:**
1. Check raw logs: look for JSON with `service`, `operation`, `timestamp` fields
2. Run with verbose output to see diagnostic stats
3. Try `itk derive` to see what ITK detects in your logs

### Fixture Not Found

**Symptom:** "No fixture found for case 'my-case'"

**Fix options:**
1. Run in live mode first to capture real logs:
   ```bash
   itk run --case cases/my-case.yaml --mode live --out out
   ```
2. Create a fixture from YAML definition:
   ```bash
   itk generate-fixture --definition fixtures/defs/my-def.yaml --out cases/my-case.jsonl
   ```
3. Derive from CloudWatch logs:
   ```bash
   itk derive --entrypoint bedrock_invoke_agent --since 24h --out derived/
   ```

### Agent Invocation Timeout

**Symptom:** "Agent invocation timed out after 60s"

**Possible causes:**
- [ ] Complex prompt causing long processing
- [ ] Agent stuck in loop
- [ ] Network issues

**Workarounds:**
- Simplify the test prompt
- Check agent execution in Bedrock Console
- Increase timeout (not yet configurable via CLI)

### Log Groups Not Found

**Symptom:** "Log group(s) not found"

**Fix:**
```bash
# Discover available log groups
itk discover

# Apply discovered config to .env
itk discover --apply
```
