# Rollback & Recovery Procedures

> **Purpose**: What to do when things go wrong during Tier-3 operations.
> **When to use**: Test failures, wrong environment access, stuck processes.

---

## Quick Reference: Recovery by Scenario

| Scenario | Severity | Action |
|----------|----------|--------|
| Test failed, no side effects | Low | Analyze, fix, retry |
| Published to wrong queue | Medium | Check DLQ, may need manual cleanup |
| Ran against production | High | **STOP**, assess impact, escalate |
| Credentials exposed in artifacts | High | Rotate credentials immediately |
| PII in artifacts | High | Delete artifacts, check redaction |
| Process hung/stuck | Low | Kill process, clean up |

---

## Scenario 1: Test Failed (No Side Effects)

**Symptoms:**
- Exit code non-zero
- Error message in output
- Missing artifacts

**Recovery:**

1. **Check error message**
   ```bash
   # Re-run with verbose output
   itk run --case cases/<case>.yaml --out artifacts/debug/ --verbose
   ```

2. **Check artifacts for clues**
   ```bash
   ls artifacts/debug/
   cat artifacts/debug/report.md
   ```

3. **Triage using prompt**
   - Use `docs/prompts/itk-triage-failed-run.prompt.md`

4. **Clean up and retry**
   ```bash
   rm -rf artifacts/debug/
   itk run --case cases/<case>.yaml --out artifacts/run-001/
   ```

**No rollback needed** — test failure doesn't affect AWS resources.

---

## Scenario 2: Published to Wrong Queue

**Symptoms:**
- Messages appeared in unexpected queue
- Wrong correlation IDs in logs
- Unintended processing triggered

**Recovery:**

1. **Stop further execution**
   ```bash
   # Kill any running ITK processes
   pkill -f "itk run"
   ```

2. **Identify the damage**
   ```bash
   # Check how many messages were sent
   aws sqs get-queue-attributes \
     --queue-url $WRONG_QUEUE_URL \
     --attribute-names ApproximateNumberOfMessages
   ```

3. **Check Dead Letter Queue**
   ```bash
   # If messages failed processing, they're in DLQ
   aws sqs get-queue-attributes \
     --queue-url $DLQ_URL \
     --attribute-names ApproximateNumberOfMessages
   ```

4. **Purge queue if safe** (QA only!)
   ```bash
   # ⚠️ DANGER: Only in QA. Deletes ALL messages.
   aws sqs purge-queue --queue-url $WRONG_QUEUE_URL
   ```

5. **Fix configuration**
   ```bash
   # Correct the .env
   nano .env
   # Verify: ITK_SQS_QUEUE_URL points to correct queue
   ```

6. **Re-run pre-flight**
   - Complete `docs/tier3-preflight-checklist.md`

---

## Scenario 3: Accidentally Ran Against Production

**Symptoms:**
- Account ID in output is production account
- Queue URL contains `prod`
- Unexpected data in production systems

### 🚨 IMMEDIATE ACTIONS

1. **STOP all operations immediately**
   ```bash
   pkill -f "itk"
   ```

2. **Do NOT run any more commands**

3. **Document what happened**
   ```markdown
   ## Incident Report
   
   **Time**: [timestamp]
   **What ran**: [command]
   **Duration**: [how long before stopped]
   **Correlation IDs**: [list any you know]
   ```

4. **Assess impact**
   - How many messages were sent?
   - What data was accessed?
   - Were any writes performed?

5. **Escalate to team**
   - Notify relevant team members
   - Share incident report
   - Follow organization's incident process

### Post-incident

1. **Review how it happened**
   - Check `.env` — was it misconfigured?
   - Check AWS profile — wrong default?
   - Check pre-flight — was it skipped?

2. **Prevent recurrence**
   - Add production account to block list
   - Implement additional safeguards
   - Update pre-flight checklist

---

## Scenario 4: Credentials Exposed in Artifacts

**Symptoms:**
- AWS keys visible in `spans.jsonl`
- Secrets in `report.md` or `trace.html`
- API keys in payloads

### 🚨 IMMEDIATE ACTIONS

1. **Delete artifacts immediately**
   ```bash
   rm -rf artifacts/<run-id>/
   ```

2. **Rotate credentials**
   - If AWS keys: Rotate via IAM console
   - If API keys: Rotate in respective service
   - If passwords: Change immediately

3. **Check if committed to git**
   ```bash
   git status
   git log --oneline -5
   # If committed, follow git history cleanup
   ```

4. **Update redaction config**
   ```bash
   # Add to .env
   ITK_REDACT_KEYS=aws_access_key_id,aws_secret_access_key,password,api_key
   ```

5. **Re-run with redaction**
   ```bash
   itk run --case cases/<case>.yaml --out artifacts/new/ --redact
   ```

---

## Scenario 5: PII in Artifacts

**Symptoms:**
- Names, emails, phone numbers in output
- Social security numbers
- Healthcare or financial data

### 🚨 IMMEDIATE ACTIONS

1. **Delete artifacts**
   ```bash
   rm -rf artifacts/<run-id>/
   ```

2. **Check if committed**
   ```bash
   git status
   # If committed, must rewrite history
   ```

3. **Update redaction patterns**
   ```bash
   # Add to .env
   ITK_REDACT_PATTERNS=email,phone,ssn,name
   ```

4. **Report if required**
   - Follow organization's data incident policy
   - May need to report to compliance

---

## Scenario 6: Process Hung/Stuck

**Symptoms:**
- ITK command not completing
- No output for extended time
- Terminal unresponsive

**Recovery:**

1. **Check if still running**
   ```bash
   ps aux | grep itk
   ```

2. **Kill gracefully**
   ```bash
   # Find PID
   pgrep -f "itk run"
   
   # Send SIGTERM
   kill <pid>
   ```

3. **Kill forcefully if needed**
   ```bash
   kill -9 <pid>
   ```

4. **Clean up partial artifacts**
   ```bash
   rm -rf artifacts/<run-id>/
   ```

5. **Check for resource locks**
   ```bash
   # Check for stale lock files
   find . -name "*.lock" -type f
   ```

6. **Retry with timeout**
   ```bash
   timeout 300 itk run --case cases/<case>.yaml --out artifacts/retry/
   ```

---

## Scenario 7: CloudWatch Throttling

**Symptoms:**
- "Rate exceeded" errors
- Partial log results
- Queries timing out

**Recovery:**

1. **Back off immediately**
   ```bash
   # Wait before retrying
   sleep 60
   ```

2. **Reduce query scope**
   ```bash
   # Smaller time window
   ITK_LOG_QUERY_WINDOW_SECONDS=300
   
   # Fewer log groups at once
   ITK_LOG_GROUPS=/aws/lambda/single-function
   ```

3. **Check quotas**
   ```bash
   aws service-quotas get-service-quota \
     --service-code logs \
     --quota-code L-32C48598
   ```

4. **Use exponential backoff**
   ```bash
   # If ITK supports it
   itk run --case cases/<case>.yaml --retry-backoff exponential
   ```

---

## Prevention Checklist

To avoid needing these procedures:

- [ ] Always complete pre-flight checklist
- [ ] Always verify account ID before running
- [ ] Always use `--out` with unique run ID
- [ ] Always configure redaction keys
- [ ] Never skip the queue URL check
- [ ] Never run without checking ITK_MODE
- [ ] Never commit `.env` files
- [ ] Never commit artifacts with secrets

---

## Emergency Contacts

Document your team's escalation path:

```markdown
## Escalation Path

**Level 1** (test failures, minor issues):
- Self-service using this guide

**Level 2** (wrong environment, data issues):
- Team lead: [name/contact]
- On-call: [rotation info]

**Level 3** (production impact, security):
- Incident commander: [name/contact]
- Security team: [contact]
```
