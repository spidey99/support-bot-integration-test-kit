# Tier-3 Error Fixes

> **Exact error → Exact fix.** No guessing.

---

## AWS Credential Errors

### Error: `Unable to locate credentials`
```
botocore.exceptions.NoCredentialsError: Unable to locate credentials
```

**Fix:**
```bash
# Option A: SSO login
aws sso login --profile your-profile

# Option B: Check .env has credentials
cat .env | grep AWS

# Option C: Export directly
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...
```

---

### Error: `ExpiredToken` or `ExpiredTokenException`
```
botocore.exceptions.ClientError: ExpiredTokenException: The security token included in the request is expired
```

**Fix:**
```bash
# Re-authenticate
aws sso login --profile your-profile

# Or refresh session token and update .env
```

---

### Error: `InvalidClientTokenId`
```
An error occurred (InvalidClientTokenId) when calling the GetCallerIdentity operation
```

**Fix:**
```bash
# Your access key is wrong. Get new credentials.
# Do NOT keep retrying with bad credentials.
```

---

### Error: `AccessDenied`
```
An error occurred (AccessDenied) when calling the X operation
```

**Fix:**
```bash
# Check you have the right role
aws sts get-caller-identity

# If wrong role, re-authenticate with correct role
# If right role, you need IAM permissions added
```

---

## ITK CLI Errors

### Error: `Case file not found`
```
ERROR: Case file not found: cases/my-case.yaml
```

**Fix:**
```bash
# Check the file exists
ls cases/

# Use correct path (relative to current directory)
itk run --case cases/example-001.yaml --out artifacts/run-001/
```

---

### Error: `Invalid case YAML`
```
ERROR: Invalid case YAML: ...
```

**Fix:**
```bash
# Validate the case file first
itk validate --case cases/my-case.yaml

# Check YAML syntax
python -c "import yaml; yaml.safe_load(open('cases/my-case.yaml'))"
```

---

### Error: `Output directory already exists`
```
ERROR: Output directory already exists: artifacts/run-001/
```

**Fix:**
```bash
# Either remove it
rm -rf artifacts/run-001/

# Or use a new directory name
itk run --case ... --out artifacts/run-002/
```

---

### Error: `No spans found`
```
WARNING: No spans found in logs
```

**Fix:**
```bash
# 1. Wait for log ingestion (CloudWatch has ~30-60s delay)
sleep 60

# 2. Check log groups are correct
echo $ITK_LOG_GROUPS
cat .env | grep ITK_LOG_GROUPS

# 3. Verify logs exist manually
aws logs filter-log-events \
  --log-group-name /aws/lambda/your-function \
  --start-time $(date -d '5 minutes ago' +%s000)

# 4. Run audit to find logging gaps
itk audit --case cases/my-case.yaml --out artifacts/audit/
cat artifacts/audit/logging-gaps.md
```

---

### Error: `Queue URL not configured`
```
ERROR: ITK_SQS_QUEUE_URL not set
```

**Fix:**
```bash
# Add to .env
echo "ITK_SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789/qa-queue" >> .env

# Or export directly
export ITK_SQS_QUEUE_URL=https://sqs...
```

---

### Error: `Failed to publish to SQS`
```
ERROR: Failed to publish message to SQS: ...
```

**Fix:**
```bash
# 1. Check queue URL is correct
echo $ITK_SQS_QUEUE_URL

# 2. Check queue exists
aws sqs get-queue-attributes --queue-url $ITK_SQS_QUEUE_URL --attribute-names All

# 3. Check IAM permissions allow sqs:SendMessage

# 4. Check you're in the right region
echo $AWS_REGION
```

---

## Python/Import Errors

### Error: `ModuleNotFoundError: No module named 'itk'`
```
ModuleNotFoundError: No module named 'itk'
```

**Fix:**
```bash
# Install ITK
cd dropin/itk
pip install -e ".[dev]"

# Verify
python -c "import itk; print('OK')"
```

---

### Error: `command not found: itk`
```
bash: itk: command not found
```

**Fix:**
```bash
# Option A: Run via Python module
python -m itk --help

# Option B: Reinstall
pip install -e ".[dev]"

# Option C: Check PATH includes pip bin
echo $PATH | grep -E "\.local/bin|Scripts"
```

---

## File/Permission Errors

### Error: `Permission denied`
```
PermissionError: [Errno 13] Permission denied: 'artifacts/...'
```

**Fix:**
```bash
# Check ownership
ls -la artifacts/

# Fix permissions
chmod -R u+rwX artifacts/

# Or use a different output directory
itk run --case ... --out /tmp/itk-output/
```

---

### Error: `No such file or directory` (fixture)
```
ERROR: Fixture file not found: fixtures/logs/sample.jsonl
```

**Fix:**
```bash
# Check fixture exists
ls fixtures/logs/

# Use correct path
itk render-fixture --fixture fixtures/logs/sample_run_001.jsonl --out artifacts/render/
```

---

## CloudWatch Errors

### Error: `ResourceNotFoundException` (log group)
```
ResourceNotFoundException: The specified log group does not exist
```

**Fix:**
```bash
# List available log groups
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/

# Update .env with correct log group names
ITK_LOG_GROUPS=/aws/lambda/correct-function-name
```

---

### Error: `ThrottlingException`
```
ThrottlingException: Rate exceeded
```

**Fix:**
```bash
# Wait and retry
sleep 30

# For soak tests, reduce rate
# Edit .env:
ITK_SOAK_INTERVAL=5000  # 5 seconds between iterations
ITK_SOAK_MAX_INFLIGHT=1  # One at a time
```

---

## Safety Check Errors

### Error: `PRODUCTION ACCOUNT DETECTED`
```
🚨 PRODUCTION ACCOUNT DETECTED 🚨
Account ID matches production pattern
```

**Fix:**
```bash
# 1. STOP. Do not proceed.
# 2. Switch to QA account
aws sso login --profile qa-profile

# 3. Update .env if needed
# 4. Re-run safety check
python scripts/safety_check.py
```

---

### Error: `ITK_MODE is not 'live'`
```
WARNING: ITK_MODE is set to 'dev-fixtures', not 'live'
```

**Fix (if you want live mode):**
```bash
# Update .env
sed -i 's/ITK_MODE=dev-fixtures/ITK_MODE=live/' .env

# Or export
export ITK_MODE=live
```

**Note:** dev-fixtures mode is fine for offline testing with fixtures.

---

## Still Stuck?

1. **Run verbose mode:**
   ```bash
   itk run --case ... --out ... --verbose 2>&1 | tee debug.log
   ```

2. **Check the full error:**
   ```bash
   python -m itk run --case ... --out ... 2>&1
   ```

3. **Validate everything:**
   ```bash
   python scripts/safety_check.py --verbose
   itk validate --case cases/my-case.yaml
   ```

4. **Ask for help with context:**
   - Paste the exact error message
   - Include output of `aws sts get-caller-identity`
   - Include output of `cat .env | grep ITK`
