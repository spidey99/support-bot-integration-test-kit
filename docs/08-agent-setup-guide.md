# Agent Setup Guide

> **Purpose:** Hand this document to any coding agent (Copilot, Claude, etc.) to set up ITK in a new project. Works for both fresh clones and existing repos.

You are setting up the Integration Test Kit (ITK) to visualize and test Bedrock Agent executions. Follow these steps exactly in order. Run each command and wait for it to complete before moving to the next step.

**CRITICAL RULES:**
1. Always show the user command output and explain what happened
2. If any command fails, stop and help the user fix it before continuing
3. **NEVER proceed with placeholder values** - if `.env` has commented-out values (`#`), `FIXME`, or angle brackets (`<placeholder>`), STOP and get real credentials first
4. Real AWS resource IDs look like: `WYEP3TYH1A` (agent ID), `/aws/lambda/itk-haiku-invoker` (log group)
5. **NEVER duplicate key names in values** - WRONG: `ITK_LOG_GROUPS=ITK_LOG_GROUPS=/aws/...` RIGHT: `ITK_LOG_GROUPS=/aws/...`
6. Do NOT copy `.env.example` directly - it has placeholder values that will fail

---

## Phase 0: Get AWS Credentials

Before starting, ensure you have AWS credentials in your terminal.

**From AWS CloudShell (easiest):**
1. Open AWS Console → click CloudShell icon (terminal in top nav)
2. Run: `aws configure export-credentials --format env`
3. Copy the output and paste into your local PowerShell/terminal

**Or from AWS SSO Portal:**
1. Click "Command line or programmatic access"
2. Copy the environment variables block and paste into terminal

---

## Phase 1: Install ITK

**Option A: If the `dropin/itk` folder already exists in your project:**
```powershell
cd dropin/itk
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

**Option B: Clone from GitHub (fresh project):**
```powershell
git clone https://github.com/spidey99/support-bot-integration-test-kit.git itk-source
Copy-Item -Recurse itk-source/dropin/itk ./itk
cd itk
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

---

## Phase 1.5: Verify Installation (Offline - No AWS Required)

Before connecting to AWS, verify ITK installed correctly:

```powershell
itk render-fixture --fixture fixtures/logs/sample_run_001.jsonl --out artifacts/test
```

- [ ] Check: Command completes without errors
- [ ] Check: `artifacts/test/trace-viewer.html` exists
- [ ] Check: Open the HTML file in a browser - you should see a sequence diagram

If this fails, fix the Python installation before proceeding.

---

## Phase 2: Bootstrap with AWS

Run bootstrap to discover resources and create config:

```powershell
itk bootstrap
```

**STOP if bootstrap shows ⚠️ for credentials or 0 resources discovered.**

You MUST have valid AWS credentials before continuing. Do NOT proceed with placeholder values.

To fix credential issues:
- Get fresh credentials from CloudShell: `aws configure export-credentials --format env`
- Paste the `export AWS_...` lines into your terminal
- Run `itk bootstrap` again

After successful bootstrap, verify `.env` contains REAL values (not placeholders):
```ini
# ❌ WRONG - these are placeholders, NOT real values:
# ITK_LOG_GROUPS=  # commented out = not set
# ITK_BEDROCK_AGENT_ID=<your-agent-id>  # angle brackets = placeholder

# ✅ CORRECT - real values look like:
ITK_LOG_GROUPS=/aws/lambda/my-actual-function-name
ITK_BEDROCK_AGENT_ID=ABC123XYZ
```

To find values manually (only if auto-discovery fails):
- Agent ID: AWS Console → Bedrock → Agents → click your agent → copy Agent ID
- Log groups: AWS Console → CloudWatch → Log groups → find Lambda logs

---

## Phase 3: View Historical Executions

View the last hour of executions from CloudWatch:

```powershell
itk view --since 1h --out artifacts/history
```

Open `artifacts/history/index.html` in your browser.

- [ ] Check: Gallery shows past executions with timestamps
- [ ] Check: Clicking "View" opens a sequence diagram

---

## Phase 4: Create Tests from Logs (Optional)

Derive test cases from CloudWatch logs:

```powershell
itk derive --entrypoint bedrock_invoke_agent --since 24h --out cases/derived
```

List the generated cases:

```powershell
Get-ChildItem cases/derived/*.yaml
```

---

## Phase 5: Run Tests

Run a derived test case:

```powershell
itk run --case cases/derived/<pick-one>.yaml --out artifacts/run1
```

Or run all derived cases as a suite:

```powershell
itk suite --cases-dir cases/derived --out artifacts/suite
```

---

## Success Criteria

- [ ] `itk render-fixture` works offline (Phase 1.5)
- [ ] `itk bootstrap` shows ✅ for AWS credentials (NOT ⚠️)
- [ ] `.env` contains real values (no `#` comments, no `<placeholders>`)
- [ ] `artifacts/history/index.html` shows past executions
- [ ] Sequence diagrams render correctly in browser

---

## Troubleshooting

### "Parsed 0 spans from N log events"

Your logs exist but ITK can't find span fields. Check that your Lambda logs include structured JSON with at least one of:
- `component` (or `span_type`, `type`, `source`, `service`)
- `operation` (or `op`, `action`, `method`, `function`, `handler`)

### "ExpiredTokenException"

AWS credentials expired. Get fresh credentials from CloudShell and paste into terminal.

### Bootstrap finds 0 log groups

- Ensure Lambda functions have executed at least once (log groups don't exist until first invocation)
- Check AWS_REGION matches where your resources are deployed
