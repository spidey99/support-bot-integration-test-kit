# Prompt: Triage Failed Test Run

> **Use this prompt** when an ITK test run failed and you need to
> understand why and determine next steps.

---

## Prerequisites

- [ ] You have the failed run's artifact directory
- [ ] You have access to CloudWatch logs
- [ ] You know which case file was used

---

## Prompt Template

Copy and fill in the blanks:

```
An ITK test run failed. I need to triage.

**Case file**: cases/[name].yaml
**Artifacts directory**: artifacts/[run-id]/
**Error message**: [paste error or "unknown"]
**Symptom**: [timeout / assertion failed / no spans / empty diagram / other]
**Status**: [✅ passed / ⚠️ warning / ❌ failed / 💥 error]

Steps:
1. List artifacts: ls artifacts/[run-id]/
2. Check report: cat artifacts/[run-id]/report.md
3. Open trace viewer: start artifacts/[run-id]/trace-viewer.html
4. Check spans: head artifacts/[run-id]/spans.jsonl
5. If diagram exists, check gaps
6. If no spans, check CloudWatch directly
7. Determine root cause and suggest fix
```

---

## Status Types

| Status | Icon | Meaning |
|--------|------|---------|
| Passed | ✅ | All invariants passed, no errors, no retries |
| Warning | ⚠️ | Passed but with retries or error spans detected |
| Failed | ❌ | One or more invariants failed |
| Error | 💥 | Test execution error (exception during run) |

**Note**: Warning status indicates success with non-happy-path behavior — investigate retries or error spans.

---

## Example Invocation

```
An ITK test run failed. I need to triage.

**Case file**: cases/happy-path-001.yaml
**Artifacts directory**: artifacts/run-42/
**Error message**: "AssertionError: expected 3 spans, got 1"
**Symptom**: assertion failed
**Status**: ❌ failed

Steps:
1. List artifacts: ls artifacts/run-42/
2. Check report: cat artifacts/run-42/report.md
3. Open trace viewer: start artifacts/run-42/trace-viewer.html
4. Check spans: head artifacts/run-42/spans.jsonl
5. If diagram exists, check gaps
6. If no spans, check CloudWatch directly
7. Determine root cause and suggest fix
```

---

## Expected Agent Actions

### Phase 1: Gather Evidence

```bash
# List what we have
ls -la artifacts/<run-id>/

# Read the report
cat artifacts/<run-id>/report.md

# Check raw spans
cat artifacts/<run-id>/spans.jsonl | head -20

# Check sequence diagram source
cat artifacts/<run-id>/sequence.mmd
```

### Phase 2: Analyze by Symptom

**If "no spans found":**
```bash
# Check logs directly
aws logs start-query \
  --log-group-name "/aws/lambda/your-function" \
  --query-string "fields @timestamp, @message | sort @timestamp desc | limit 20"
```

**If "assertion failed":**
```bash
# Check expected vs actual in case file
cat cases/<name>.yaml | grep -A 20 "expected:"

# Compare to spans
cat artifacts/<run-id>/spans.jsonl
```

**If "empty diagram":**
```bash
# Run audit to find gaps
itk audit --case cases/<name>.yaml --out artifacts/audit/
cat artifacts/audit/logging-gaps.md
```

**If "timeout":**
```bash
# Check for long-running queries
# Check AWS quotas
aws service-quotas list-service-quotas --service-code logs
```

### Phase 3: Determine Root Cause

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| No spans | Logs not ingested yet | Wait 60s, retry |
| No spans | Wrong log group | Check `ITK_LOG_GROUPS` |
| No spans | Missing logging | Run `itk audit`, add logs |
| Wrong count | Race condition | Add synchronization spans |
| Wrong count | Filter too narrow | Expand correlation window |
| Empty diagram | No boundary logs | Add entry/exit span logs |
| Timeout | Large log volume | Narrow time window |
| Timeout | AWS throttling | Backoff and retry |

---

## Triage Checklist

```markdown
## Triage Report

**Run ID**: _______________
**Case**: _______________
**Timestamp**: _______________

### Evidence Gathered
- [ ] Artifacts directory listed
- [ ] Report.md reviewed
- [ ] Spans.jsonl checked
- [ ] Sequence.mmd examined
- [ ] CloudWatch queried directly (if needed)

### Root Cause
Category: [ ] Config error / [ ] Logging gap / [ ] Race condition / [ ] AWS issue / [ ] Test error

Description:
> [describe what went wrong]

### Recommended Fix
1. [step 1]
2. [step 2]
3. [step 3]

### Verification
After fix, run:
```
itk run --case cases/<name>.yaml --out artifacts/<new-run-id>/
```
```

---

## Common Patterns

### Pattern: Flaky due to timing

**Symptom**: Test passes sometimes, fails sometimes
**Cause**: Logs not yet ingested when query runs
**Fix**: 
1. Add `ITK_LOG_DELAY_SECONDS=30` to .env
2. Or use `--wait 30` flag when running

### Pattern: Missing middle spans

**Symptom**: Entry and exit spans present, middle missing
**Cause**: Internal calls don't have logging
**Fix**:
1. Run `itk audit`
2. Add span logging to internal calls
3. Re-deploy and re-test

### Pattern: Duplicate correlation IDs

**Symptom**: More spans than expected
**Cause**: Correlation ID reused across requests
**Fix**:
1. Ensure correlation IDs are unique per request
2. Or narrow time window filter

---

## What Success Looks Like

```
## Triage Report

**Run ID**: run-42
**Case**: happy-path-001.yaml
**Timestamp**: 2024-01-15T10:30:00Z

### Root Cause
Category: [x] Logging gap

Description:
> The orchestrator Lambda calls bedrock-agent but doesn't log a span
> for that boundary. Entry/exit spans exist but the call is invisible.

### Recommended Fix
1. Add span logging to orchestrator when calling Bedrock
2. Re-deploy orchestrator Lambda
3. Re-run test

### Verification
itk run --case cases/happy-path-001.yaml --out artifacts/run-43/
```
