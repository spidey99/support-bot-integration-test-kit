# ITK Error Codes Reference

When ITK encounters a problem, it displays a structured error message with:

1. **Error code** — A unique identifier (e.g., `ITK-E001`)
2. **Message** — A clear description of what went wrong
3. **Next step** — A specific command or action to fix the problem

## How to Read Error Messages

```
ITK-E001: Missing required environment variable: ITK_LOG_GROUP
Next step: Run `itk validate-env` to check which variables are missing
```

## Verbose Mode

For debugging, add `--verbose` to see the full Python traceback:

```bash
itk --verbose invoke case.yaml
```

---

## Error Code Categories

| Range | Category |
|-------|----------|
| E001–E099 | Configuration & Environment |
| E100–E199 | Input Validation |
| E200–E299 | AWS / Runtime Errors |
| E300–E399 | Internal Errors |

---

## Configuration & Environment Errors (E001–E099)

### ITK-E001: Missing Environment Variable

**Message:** `Missing required environment variable: {var_name}`

**What it means:** A required configuration value is not set in your environment or `.env` file.

**How to fix:**

- [ ] Run `itk validate-env` to see all missing variables
- [ ] Check that `.env` exists in your project root
- [ ] Add the missing variable to `.env`
- [ ] For AWS credentials, verify your profile is set correctly

**Common missing variables:**

| Variable | Purpose |
|----------|---------|
| `ITK_LOG_GROUP` | CloudWatch log group to fetch logs from |
| `ITK_LAMBDA_NAME` | Lambda function name for direct invocation |
| `ITK_QUEUE_URL` | SQS queue URL for queue-based invocation |
| `ITK_AWS_REGION` | AWS region (defaults to `us-east-1`) |

---

### ITK-E002: Invalid Configuration Value

**Message:** `Invalid value for {key}: {value}`

**What it means:** A configuration value exists but is not in the expected format.

**How to fix:**

- [ ] Run `itk show-config` to see current configuration
- [ ] Check the expected format in the schema
- [ ] Correct the value in your `.env` or config file

**Common issues:**

| Value | Expected Format |
|-------|-----------------|
| `ITK_POLL_TIMEOUT` | Integer (seconds), e.g., `30` |
| `ITK_LOG_GROUP` | Must start with `/`, e.g., `/aws/lambda/my-fn` |
| `ITK_QUEUE_URL` | Full SQS URL, e.g., `https://sqs.us-east-1.amazonaws.com/...` |

---

### ITK-E003: Configuration File Not Found

**Message:** `Configuration file not found: {path}`

**What it means:** ITK tried to load a configuration file that does not exist.

**How to fix:**

- [ ] Check that the file path is correct
- [ ] Run `itk quickstart` to create default configuration
- [ ] If using `--config`, verify the path is absolute or relative to current directory

---

### ITK-E004: Invalid YAML Syntax

**Message:** `Invalid YAML in {path}: {error}`

**What it means:** A YAML file contains syntax errors.

**How to fix:**

- [ ] Open the file and check for:
  - Missing colons after keys
  - Incorrect indentation (use spaces, not tabs)
  - Unquoted special characters
- [ ] Use a YAML validator: [yamllint.com](https://www.yamllint.com/)
- [ ] Run `itk validate <file>` to check against the schema

---

### ITK-E005: Schema Validation Failed

**Message:** `Schema validation failed: {errors}`

**What it means:** A case file or config file does not match the expected structure.

**How to fix:**

- [ ] Run `itk validate <file>` for detailed error messages
- [ ] Check the schema in `schemas/itk.case.schema.json`
- [ ] See examples in `cases/example-001.yaml`

**Common schema errors:**

| Error | Meaning |
|-------|---------|
| `'entrypoint' is required` | Case file needs an `entrypoint:` field |
| `'type' must be one of...` | Invalid entrypoint type |
| `Additional properties not allowed` | Typo in a field name |

---

### ITK-E010: .env File Not Found

**Message:** `.env file not found at {path}`

**What it means:** ITK expected a `.env` file but could not find it.

**How to fix:**

- [ ] Run `itk quickstart` to auto-create `.env` from template
- [ ] Copy `.env.example` to `.env` manually
- [ ] If `.env` is in a different location, set `ITK_ENV_PATH`

---

### ITK-E011: AWS Profile Not Found

**Message:** `AWS profile not found: {profile}`

**What it means:** The specified AWS profile does not exist in `~/.aws/credentials`.

**How to fix:**

- [ ] List available profiles: `aws configure list-profiles`
- [ ] Create the profile: `aws configure --profile {profile}`
- [ ] Check for typos in `AWS_PROFILE` or `ITK_AWS_PROFILE`

---

### ITK-E012: AWS Credentials Expired

**Message:** `AWS credentials expired for profile: {profile}`

**What it means:** Your AWS session token has expired (common with MFA).

**How to fix:**

- [ ] Refresh credentials: `aws sts get-caller-identity --profile {profile}`
- [ ] For MFA profiles, run your MFA refresh script
- [ ] Run `itk doctor` to check credential status

---

## Input Validation Errors (E100–E199)

### ITK-E101: Case File Not Found

**Message:** `Case file not found: {path}`

**What it means:** The specified test case file does not exist.

**How to fix:**

- [ ] Check the file path for typos
- [ ] List available cases: `ls cases/`
- [ ] Create a new case from template: `itk scaffold`

---

### ITK-E102: Invalid Entrypoint Type

**Message:** `Invalid entrypoint type: {type}`

**What it means:** The `entrypoint.type` value is not recognized.

**How to fix:**

- [ ] Check supported types: `lambda`, `sqs`, `bedrock-agent`
- [ ] Verify the spelling matches exactly (case-sensitive)

---

### ITK-E103: Missing Input Payload

**Message:** `No input payload provided for case: {case_id}`

**What it means:** The test case needs input data but none was provided.

**How to fix:**

- [ ] Add an `input:` section to your case file
- [ ] Or provide input via `--input` flag

---

### ITK-E110: Invalid JSON in Payload

**Message:** `Invalid JSON in payload: {error}`

**What it means:** Input or expected output contains malformed JSON.

**How to fix:**

- [ ] Validate JSON at [jsonlint.com](https://jsonlint.com/)
- [ ] Check for trailing commas (not allowed in JSON)
- [ ] Ensure strings are double-quoted

---

### ITK-E111: Fixture File Not Found

**Message:** `Fixture file not found: {path}`

**What it means:** A referenced fixture file does not exist.

**How to fix:**

- [ ] Check the path in your case file
- [ ] Verify fixture exists in `fixtures/` directory
- [ ] Paths should be relative to the project root

---

## AWS / Runtime Errors (E200–E299)

### ITK-E201: Lambda Invocation Failed

**Message:** `Lambda invocation failed: {error}`

**What it means:** The Lambda function could not be invoked.

**Common causes:**

- [ ] Function does not exist — check `ITK_LAMBDA_NAME`
- [ ] Permission denied — check IAM role
- [ ] Function timeout — check Lambda timeout setting
- [ ] Function error — check CloudWatch logs

**How to fix:**

- [ ] Run `itk discover` to find available Lambda functions
- [ ] Verify function exists: `aws lambda get-function --function-name {name}`
- [ ] Check permissions: `aws lambda get-policy --function-name {name}`

---

### ITK-E202: SQS Send Failed

**Message:** `Failed to send SQS message: {error}`

**What it means:** Could not send a message to the SQS queue.

**Common causes:**

- [ ] Queue does not exist
- [ ] Permission denied
- [ ] Queue URL is malformed

**How to fix:**

- [ ] Run `itk discover` to find available queues
- [ ] Verify queue: `aws sqs get-queue-attributes --queue-url {url} --attribute-names All`

---

### ITK-E203: CloudWatch Logs Fetch Failed

**Message:** `Failed to fetch CloudWatch logs: {error}`

**What it means:** Could not retrieve logs from CloudWatch.

**Common causes:**

- [ ] Log group does not exist
- [ ] No logs in the specified time window
- [ ] Permission denied

**How to fix:**

- [ ] Verify log group exists: `aws logs describe-log-groups --log-group-name-prefix {name}`
- [ ] Check time range is correct
- [ ] Run `itk doctor` to verify CloudWatch permissions

---

### ITK-E204: Bedrock Agent Invocation Failed

**Message:** `Bedrock agent invocation failed: {error}`

**What it means:** Could not invoke the Bedrock agent.

**Common causes:**

- [ ] Agent ID or alias is incorrect
- [ ] Agent is not in PREPARED state
- [ ] Permission denied

**How to fix:**

- [ ] Run `itk discover` to find available agents
- [ ] Check agent status in AWS Console
- [ ] Verify IAM permissions for `bedrock:InvokeAgent`

---

### ITK-E210: Rate Limit Exceeded

**Message:** `AWS rate limit exceeded. Retrying in {seconds}s...`

**What it means:** Too many requests were sent to AWS in a short time.

**How to fix:**

- [ ] Wait and retry automatically (ITK will back off)
- [ ] Reduce request rate in config: `ITK_RATE_LIMIT=0.5`
- [ ] For bulk operations, use `--rate-limit` flag

---

### ITK-E211: Timeout Waiting for Response

**Message:** `Timeout after {seconds}s waiting for {resource}`

**What it means:** An operation took longer than the configured timeout.

**How to fix:**

- [ ] Increase timeout: `ITK_POLL_TIMEOUT=60`
- [ ] Check if the resource is healthy
- [ ] For slow operations, use `--timeout` flag

---

### ITK-E220: Access Denied

**Message:** `Access denied: {operation} on {resource}`

**What it means:** Your AWS credentials do not have permission for this operation.

**How to fix:**

- [ ] Run `itk doctor` to check permissions
- [ ] Verify IAM role/user has required policies
- [ ] Check resource-based policies on the target

---

## Internal Errors (E300–E399)

### ITK-E301: Unexpected Response Format

**Message:** `Unexpected response format from {source}`

**What it means:** An AWS service returned data in an unexpected format.

**How to fix:**

- [ ] Check if you're using the latest ITK version
- [ ] Report the issue with `--verbose` output
- [ ] Check if the AWS service has changed its API

---

### ITK-E302: Correlation Failed

**Message:** `Could not correlate logs: {reason}`

**What it means:** ITK could not match logs to a specific invocation.

**Common causes:**

- [ ] Missing request ID in logs
- [ ] Time window too narrow
- [ ] Log format not recognized

**How to fix:**

- [ ] Widen the time window with `--after` / `--before`
- [ ] Ensure logs include request ID
- [ ] Check log format matches expected pattern

---

### ITK-E303: Internal Error

**Message:** `Internal error: {details}`

**What it means:** An unexpected error occurred within ITK.

**How to fix:**

- [ ] Run with `--verbose` to see the full traceback
- [ ] Report the issue with:
  - Error message
  - Command that caused it
  - Verbose output

---

## Quick Troubleshooting Commands

| Problem | Command |
|---------|---------|
| Check all environment variables | `itk validate-env` |
| Check AWS connectivity | `itk doctor` |
| Find AWS resources | `itk discover` |
| See current configuration | `itk show-config` |
| Get full error traceback | `itk --verbose <command>` |

---

## Getting Help

If you cannot resolve an error:

1. Run the command with `--verbose` to capture the full traceback
2. Check the relevant section in this document
3. Run `itk doctor` to validate your environment
4. Search existing issues or create a new one with:
   - The error code and message
   - The command you ran
   - The `--verbose` output
   - Your ITK version (`itk --version`)
