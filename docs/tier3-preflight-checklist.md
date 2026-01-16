# Pre-flight Checklist

> **Purpose**: Complete this checklist before ANY AWS operation.
> **Time**: ~1 minute
> **When**: Before every test run, log query, or resource access.

---

## Quick Version (Copy-Paste)

```markdown
## Pre-flight Check ✈️

**Date/Time**: _______________
**Task**: _______________

### Credentials
- [ ] `aws sts get-caller-identity` → Account: _______________
- [ ] Account is QA/staging (NOT production)
- [ ] Credentials not expired

### Configuration  
- [ ] `.env` exists
- [ ] `ITK_MODE=live` (not dev-fixtures)
- [ ] `ITK_SQS_QUEUE_URL` is QA queue
- [ ] `ITK_LOG_GROUPS` lists correct groups

### Output
- [ ] `--out` directory specified
- [ ] Directory writable
- [ ] Enough disk space

### Case (if running test)
- [ ] Case file exists
- [ ] Case file valid YAML: `itk validate --case <file>`

✅ Ready to proceed
```

---

## Detailed Checklist

### 1. AWS Credentials

#### Check credentials are valid

```bash
aws sts get-caller-identity
```

**Expected output:**
```json
{
    "UserId": "AROAXXXXXXXXXXXXXXXXX:user@example.com",
    "Account": "123456789012",
    "Arn": "arn:aws:sts::123456789012:assumed-role/..."
}
```

**Verify:**
- [ ] Command succeeds (not "expired" or "invalid")
- [ ] Account ID matches QA account (not production!)
- [ ] ARN shows expected role/user

#### If credentials expired:

```bash
# For SSO
aws sso login --profile your-profile

# For IAM
# Refresh keys manually or use aws configure
```

---

### 2. Environment Configuration

#### Check .env exists and is configured

```bash
cat .env | grep -E "^ITK_"
```

**Expected settings:**
```
ITK_MODE=live
ITK_SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/qa-queue
ITK_LOG_GROUPS=/aws/lambda/qa-orchestrator,/aws/lambda/qa-processor
ITK_AWS_REGION=us-east-1
```

**Verify:**
- [ ] `ITK_MODE=live` (NOT `dev-fixtures`)
- [ ] `ITK_SQS_QUEUE_URL` contains `qa` or `staging` (NOT `prod`)
- [ ] `ITK_LOG_GROUPS` lists all relevant log groups
- [ ] `ITK_AWS_REGION` matches your target region

#### DANGER: Production indicators

**🚨 STOP if you see ANY of these:**
- Queue URL contains `prod`, `production`, `prd`
- Log group contains `prod`, `production`, `prd`
- Account ID is the production account

---

### 3. Target Resources

#### Verify queue is accessible

```bash
aws sqs get-queue-attributes \
  --queue-url $ITK_SQS_QUEUE_URL \
  --attribute-names QueueArn
```

**Verify:**
- [ ] Command succeeds
- [ ] ARN shows QA account ID
- [ ] Queue name contains `qa` or `staging`

#### Verify log groups exist

```bash
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/lambda/qa-" \
  --limit 5
```

**Verify:**
- [ ] Log groups found
- [ ] Names match `ITK_LOG_GROUPS` setting

---

### 4. Output Directory

#### Check artifacts directory

```bash
# Ensure directory is writable
mkdir -p artifacts/test-run/
touch artifacts/test-run/.write-test
rm artifacts/test-run/.write-test
echo "✅ Directory writable"
```

**Verify:**
- [ ] No permission errors
- [ ] Sufficient disk space: `df -h .`

---

### 5. Case Validation (if running test)

#### Validate case file

```bash
itk validate --case cases/<your-case>.yaml
```

**Verify:**
- [ ] Validation passes (exit code 0)
- [ ] No schema errors
- [ ] No warnings about missing fields

---

## Environment Safety Matrix

| Setting | QA (Safe) | Prod (DANGER) |
|---------|-----------|---------------|
| Account ID | 123456789012 | 987654321098 |
| Queue URL | `*-qa-*`, `*-staging-*` | `*-prod-*`, `*-prd-*` |
| Log Groups | `/aws/lambda/qa-*` | `/aws/lambda/prod-*` |

**Before proceeding, confirm you are in the SAFE column.**

---

## Quick Commands Reference

```bash
# Full pre-flight in one go
aws sts get-caller-identity && \
grep ITK_MODE .env && \
grep ITK_SQS_QUEUE_URL .env | grep -v prod && \
echo "✅ Pre-flight passed"
```

---

## What To Do If Check Fails

| Check | Failure | Action |
|-------|---------|--------|
| Credentials | Expired | Run `aws sso login` |
| Credentials | Wrong account | Switch profile: `export AWS_PROFILE=qa` |
| ITK_MODE | Not `live` | Edit `.env`, set `ITK_MODE=live` |
| Queue URL | Points to prod | **STOP**. Edit `.env` to QA queue |
| Log Groups | Not found | Verify log group names, update `.env` |
| Directory | Not writable | Check permissions, create parent dirs |
| Case file | Invalid | Run `itk validate`, fix errors |

---

## Checklist Complete?

If all checks pass:
```
✅ Pre-flight complete. Safe to proceed.
```

If any check fails:
```
❌ Pre-flight failed. DO NOT proceed until fixed.
```
