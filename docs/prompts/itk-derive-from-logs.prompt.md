# Prompt: Derive Test Cases from Logs

> **Use this prompt** when you want to generate test case YAML files from
> real CloudWatch logs captured during QA/staging traffic.

---

## Prerequisites

- [ ] AWS credentials are valid
- [ ] `.env` has `ITK_MODE=live`
- [ ] `ITK_LOG_GROUPS` points to the correct log groups
- [ ] You have a time window with known traffic

---

## Prompt Template

Copy and fill in the blanks:

```
I need to derive ITK test cases from recent CloudWatch logs.

**Time window**: last [24h / 6h / 1h]
**Correlation ID** (if known): [correlation-id or "any"]
**Entrypoint type**: [bedrock-agent / sqs-event / lambda-direct]
**Output directory**: cases/derived/

Steps:
1. Run pre-flight checklist
2. Execute: itk derive --since [time] --out cases/derived/
3. List generated files
4. Show me the first generated case for review

If no spans found:
- Try a longer time window
- Check ITK_LOG_GROUPS includes all log groups
- Run `itk audit` to identify logging gaps
```

---

## Example Invocation

```
I need to derive ITK test cases from recent CloudWatch logs.

**Time window**: last 24h
**Correlation ID**: any
**Entrypoint type**: sqs-event
**Output directory**: cases/derived/

Steps:
1. Run pre-flight checklist
2. Execute: itk derive --since 24h --out cases/derived/
3. List generated files
4. Show me the first generated case for review
```

---

## Expected Agent Actions

1. Verify credentials: `aws sts get-caller-identity`
2. Verify config: `cat .env | grep ITK_`
3. Run command: `itk derive --since 24h --out cases/derived/`
4. List output: `ls cases/derived/`
5. Show sample: `cat cases/derived/<first-file>.yaml`

---

## What Success Looks Like

```
✅ Pre-flight: Account 123456789012, ITK_MODE=live
✅ Derive: Found 12 correlation IDs
✅ Output: Generated 12 case files

Generated cases:
- cases/derived/case-abc123.yaml
- cases/derived/case-def456.yaml
...

First case:
---
meta:
  id: case-abc123
  derived_from: cloudwatch
  correlation_id: abc123...
entrypoint:
  type: sqs-event
  ...
```

---

## What Failure Looks Like (and fixes)

| Error | Fix |
|-------|-----|
| "No spans found" | Expand time window or check log groups |
| "Credentials expired" | Run `aws sso login` |
| "Throttled" | Wait and retry with smaller window |
| "Invalid log group" | Check `ITK_LOG_GROUPS` in .env |
