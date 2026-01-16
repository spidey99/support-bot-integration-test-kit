# Tier-3 Agent Guide

> **You are Tier-3**: A coding agent in the work repo with AWS access.
> Your job is to run LIVE integration tests against real QA resources.

---

## Golden Rules

```
┌─────────────────────────────────────────────────────────────┐
│  1. NEVER mock AWS calls in integration tests               │
│  2. NEVER use --mode dev-fixtures for real test runs        │
│  3. ALWAYS verify credentials before running tests          │
│  4. ALWAYS check pre-flight checklist before AWS calls      │
│  5. ALWAYS produce static artifacts (viewable via file://)  │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start (Your First Live Run)

### Step 1: Verify Environment

```bash
# Check AWS credentials work
aws sts get-caller-identity

# Check you can read CloudWatch
aws logs describe-log-groups --limit 5

# Check .env exists and has ITK_MODE=live
cat .env | grep ITK_MODE
```

**Expected output**: Account ID, log groups list, `ITK_MODE=live`

**If it fails**: Stop. Fix credentials first. See [Troubleshooting](#troubleshooting).

### Step 2: Run Pre-flight Checklist

Before ANY test run, verify:

- [ ] AWS credentials valid (not expired)
- [ ] `.env` has `ITK_MODE=live`
- [ ] `ITK_SQS_QUEUE_URL` points to QA queue (not prod!)
- [ ] `ITK_LOG_GROUPS` lists correct CloudWatch log groups
- [ ] Artifacts directory is writable

### Step 3: Run a Simple Test

```bash
# Pick an existing case
itk run --case cases/example-001.yaml --out artifacts/run-001/
```

### Step 4: Check Artifacts

```bash
# Verify files were created
ls artifacts/run-001/
# Expected: trace-viewer.html, timeline.html, spans.jsonl, report.md, sequence.mmd, payloads/

# Open trace viewer in browser
start artifacts/run-001/trace-viewer.html  # Windows
open artifacts/run-001/trace-viewer.html   # Mac
xdg-open artifacts/run-001/trace-viewer.html  # Linux
```

---

## Common Tasks

### Task A: Run a Test Case

**When**: You have a case YAML and want to execute it.

```bash
itk run --case cases/<case-name>.yaml --out artifacts/<run-id>/
```

**Outputs**:
- `trace-viewer.html` — Interactive SVG sequence diagram
- `timeline.html` — Waterfall timeline view
- `spans.jsonl` — Raw span data
- `report.md` — Summary with invariant results
- `payloads/*.json` — Request/response payloads

### Task B: Run a Test Suite

**When**: You want to run multiple cases together.

```bash
itk suite --cases-dir cases/ --out artifacts/smoke-001/
```

**Outputs**:
- `index.html` — Suite report with all runs (✅ Passed, ⚠️ Warning, ❌ Failed, 💥 Error)
- `<case-id>/` — Per-case artifacts (trace-viewer.html, timeline.html, etc.)

### Task C: Audit Logging Gaps

**When**: Diagrams are incomplete or missing spans.

```bash
itk audit --case cases/<case-name>.yaml --out artifacts/audit/
```

**Outputs**:
- `logging-gaps.md` — What to add to your code

**Then**: Add the suggested logging and re-run the test.

### Task D: Derive Cases from Logs

**When**: You want to create test cases from real production/QA traffic.

```bash
itk derive --since 24h --out cases/derived/
```

**Outputs**:
- `cases/derived/*.yaml` — Generated case files

**Then**: Review, curate, and add expected outcomes.

### Task E: Scan Codebase for Coverage

**When**: You want to find untested components.

```bash
itk scan --repo . --out artifacts/scan/
```

**Outputs**:
- `coverage_report.md` — What's missing
- `skeleton_cases/*.yaml` — Generated stubs (with `--generate-skeletons`)

### Task F: Run Soak Test

**When**: You want to stress-test a case repeatedly to find flaky behavior.

```bash
# Run 50 iterations with per-iteration drill-down
itk soak --case cases/<case-name>.yaml --out artifacts/soak-001/ --iterations 50 --detailed
```

**Outputs**:
- `soak-report.html` — Dashboard with consistency metrics
- `soak-result.json` — Programmatic access to results
- `iterations/NNNN/<case-name>/` — Per-iteration artifacts (with `--detailed`)

**Key Metrics to Check**:

| Metric | Good | Bad | Action |
|--------|------|-----|--------|
| Pass Rate | 100% | <95% | Investigate failed iterations |
| Consistency Score | >90% | <50% | Too many retries — LLM non-determinism |
| Throttle Events | 0 | >0 | Reduce rate, increase interval |
| Avg Retries | 0-0.1 | >1.0 | System is flaky, check error spans |

**Interpreting Results**:
- **100% pass + 0% consistency** = All passes needed retries (hidden flakiness)
- **High warning rate** = System works but not happy path
- Click any iteration row to drill-down into that run's trace-viewer

---

## Pre-flight Checklist

**Copy this checklist before every AWS operation:**

```markdown
## Pre-flight Check (copy and fill in)

- [ ] **Credentials**: `aws sts get-caller-identity` shows correct account
- [ ] **Environment**: `.env` has `ITK_MODE=live`
- [ ] **Target**: `ITK_SQS_QUEUE_URL` is QA, not prod
- [ ] **Logs**: `ITK_LOG_GROUPS` points to correct log groups
- [ ] **Output**: `--out` directory exists or will be created
- [ ] **Case**: Case file exists and is valid YAML

Account ID: _______________
Environment: qa / staging / prod (circle one — should be QA)
```

---

## What To Do When Things Go Wrong

### Problem: "Credentials expired"

```bash
# Re-authenticate
aws sso login --profile your-profile
# Or refresh keys manually
```

### Problem: "No spans found"

1. Check the time window: logs may not be ingested yet
2. Wait 60 seconds and re-run
3. Check `ITK_LOG_GROUPS` includes all relevant log groups
4. Run `itk audit` to find logging gaps

### Problem: "Test passed but diagram is empty"

1. Run `itk audit` to identify missing boundary logs
2. Add suggested logging to your Lambda/handler code
3. Re-deploy and re-run test

### Problem: "Throttled by AWS"

1. Wait and retry with longer intervals
2. Reduce `ITK_SOAK_MAX_INFLIGHT` if running soak tests
3. Check AWS quotas for CloudWatch Logs Insights

### Problem: "Wrong environment (hit prod!)"

**STOP IMMEDIATELY.**

1. Do not run more tests
2. Check `.env` — ensure `ITK_SQS_QUEUE_URL` is QA
3. Verify account ID matches QA account
4. Report to team if prod was impacted

---

## Rollback Procedures

### If a test published bad data to SQS:

1. Messages will be processed by Lambda — you cannot un-send them
2. Check DLQ for failed messages
3. If necessary, manually purge the queue (QA only!)

```bash
# DANGER: Only in QA. Purges all messages.
aws sqs purge-queue --queue-url $ITK_SQS_QUEUE_URL
```

### If a test triggered unexpected behavior:

1. Check CloudWatch logs for errors
2. Check Bedrock traces for agent issues
3. Document what happened for debugging

### If artifacts contain PII:

1. Delete the artifacts directory immediately
2. Check redaction settings: `ITK_REDACT_KEYS` in `.env`
3. Re-run with proper redaction

```bash
# Delete artifacts
rm -rf artifacts/<run-id>/

# Verify redaction is configured
grep ITK_REDACT_KEYS .env
```

---

## Things You Should NEVER Do

| ❌ Never | Why |
|----------|-----|
| Use `--mode dev-fixtures` for real tests | Tests must hit live resources |
| Run against prod queue URL | Could impact production |
| Commit `.env` with secrets | Secrets must stay local |
| Skip pre-flight checklist | Prevents costly mistakes |
| Ignore throttling errors | Could hit AWS limits |
| Store PII in artifacts | Security/compliance risk |

---

## Things You Should ALWAYS Do

| ✅ Always | Why |
|-----------|-----|
| Run pre-flight checklist | Catches config errors early |
| Check account ID before tests | Ensures you're in QA |
| Review artifacts after runs | Validates test worked |
| Use `--out` with unique run ID | Keeps artifacts organized |
| Configure redaction keys | Protects sensitive data |
| Run `itk audit` when diagrams are sparse | Identifies logging gaps |

---

## Troubleshooting

### "Command not found: itk"

```bash
# Ensure ITK is installed
pip install -e .

# Or run via module
python -m itk run --help
```

### "No such file: cases/..."

```bash
# Check available cases
ls cases/

# Validate case file
itk validate --case cases/<name>.yaml
```

### "Invalid YAML"

```bash
# Validate the case
itk validate --case cases/<name>.yaml

# Check for common issues:
# - Tabs instead of spaces
# - Missing colons
# - Unclosed quotes
```

### "AWS timeout"

1. Check internet connectivity
2. Check AWS region is correct
3. Try smaller query window: `ITK_LOG_QUERY_WINDOW_SECONDS=300`

---

## Getting Help

1. **Check this guide first** — Most issues are covered above
2. **Check the error message** — Usually tells you what's wrong
3. **Check `.env` configuration** — Most problems are config issues
4. **Run `itk validate`** — Validates case/fixture files
5. **Run `itk audit`** — Identifies logging gaps

If still stuck, document:
- Command you ran
- Error message (full text)
- `.env` settings (redact secrets)
- AWS account ID and region
