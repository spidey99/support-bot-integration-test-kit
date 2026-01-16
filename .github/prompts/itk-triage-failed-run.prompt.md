# ITK Prompt: Triage a Failed Test Run

> **Use this prompt when**: A test run failed and you need to diagnose why.

---

## Context to Gather First

Before using this prompt, collect:

1. **The error message** (exact text)
2. **The report.md** from the failed run
3. **The sequence.mmd** or trace-viewer.html
4. **The logging-gaps.md** (if `itk audit` was run)

---

## Prompt Template

Copy and fill in:

```
I have a failed ITK test run. Help me diagnose and fix it.

## Error Message
<paste exact error here>

## Exit Code
<paste exit code, e.g., 1>

## Report Summary
<paste contents of artifacts/run-XXX/report.md>

## Sequence Diagram
<paste contents of artifacts/run-XXX/sequence.mmd OR describe what you see>

## Logging Gaps (if available)
<paste contents of logging-gaps.md, or "not available">

## What I Already Tried
<list any fixes you attempted>

## Environment
- ITK_MODE: <live or dev-fixtures>
- Account: <QA account ID, NOT production>
- Region: <AWS region>

Please:
1. Identify the most likely failure layer (SQS, Lambda, Bedrock, Logging, etc.)
2. Provide the top 3 possible causes
3. Give me the exact commands to run to fix it
4. If logging is the issue, show me the exact log statement to add
```

---

## Common Failure Patterns

### Pattern 1: Empty Sequence Diagram

**Symptom**: Diagram has no messages, or only shows entry point.

**Likely causes**:
1. Logs haven't ingested yet (wait 60 seconds)
2. Log groups not configured in ITK_LOG_GROUPS
3. Lambda isn't emitting span logs

**Fix checklist**:
```bash
# Check log groups
cat .env | grep ITK_LOG_GROUPS

# Verify logs exist
aws logs filter-log-events \
  --log-group-name /aws/lambda/YOUR_FUNCTION \
  --start-time $(date -d '10 minutes ago' +%s000) \
  --limit 10

# Run audit to find gaps
itk audit --case cases/your-case.yaml --out artifacts/audit/
cat artifacts/audit/logging-gaps.md
```

---

### Pattern 2: Timeout / No Response

**Symptom**: Test hangs or times out waiting for response.

**Likely causes**:
1. Lambda cold start took too long
2. Bedrock agent is slow
3. SQS message wasn't processed
4. Wrong queue URL

**Fix checklist**:
```bash
# Check SQS queue
aws sqs get-queue-attributes \
  --queue-url $ITK_SQS_QUEUE_URL \
  --attribute-names ApproximateNumberOfMessages

# Check Lambda errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/YOUR_FUNCTION \
  --filter-pattern "ERROR" \
  --start-time $(date -d '10 minutes ago' +%s000)

# Check DLQ
aws sqs get-queue-attributes \
  --queue-url $DLQ_URL \
  --attribute-names ApproximateNumberOfMessages
```

---

### Pattern 3: Wrong/Missing Payloads

**Symptom**: Payloads in artifacts don't match expected, or are empty.

**Likely causes**:
1. Request format doesn't match schema
2. Lambda returned error but no error logging
3. Correlation ID mismatch

**Fix checklist**:
```bash
# Validate the case format
itk validate --case cases/your-case.yaml

# Check payload files
ls artifacts/run-XXX/payloads/
cat artifacts/run-XXX/payloads/*.json

# Compare with expected schema
cat dropin/itk/schemas/itk.case.schema.json
```

---

### Pattern 4: Assertion Failed

**Symptom**: Report shows invariant failures.

**Likely causes**:
1. Expected component not in trace
2. Error span detected in success test
3. Retry count exceeded threshold

**Fix checklist**:
```bash
# Check which invariants failed
cat artifacts/run-XXX/report.md | grep -A5 "Invariant"

# Review the trace for issues
cat artifacts/run-XXX/spans.jsonl | python -m json.tool
```

---

## After Diagnosis

Once you identify the issue:

1. **If it's a logging gap**: Use `itk-add-span-logging.prompt.md`
2. **If it's a case format issue**: Use `itk-derive-test-from-logs.prompt.md`
3. **If it's an adapter issue**: Use `itk-add-new-entrypoint-adapter.prompt.md`
4. **If it's infrastructure**: Check AWS console / CloudWatch

---

## Example Diagnosis Session

```bash
# 1. Run the failed test again with verbose output
itk run --case cases/smoke-001.yaml --out artifacts/debug/ --verbose 2>&1 | tee debug.log

# 2. Check what we got
ls artifacts/debug/
cat artifacts/debug/report.md

# 3. Run audit
itk audit --case cases/smoke-001.yaml --out artifacts/audit/
cat artifacts/audit/logging-gaps.md

# 4. Check CloudWatch directly
aws logs filter-log-events \
  --log-group-name /aws/lambda/orchestrator \
  --start-time $(date -d '5 minutes ago' +%s000) \
  --limit 20
```
