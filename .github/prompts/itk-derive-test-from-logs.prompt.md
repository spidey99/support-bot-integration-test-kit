# ITK Prompt: Derive Test Cases from Production Logs

> **Use this prompt when**: You need to create test cases based on real traffic patterns.

---

## Context to Gather First

Before using this prompt, collect:

1. **Time range** of logs to analyze (e.g., last 24 hours)
2. **Log group names** where your Lambdas write
3. **Types of requests** you want to capture (success, errors, edge cases)

---

## Prompt Template

Copy and fill in:

```
I need to derive ITK test cases from production/QA CloudWatch logs.

## Time Range
From: <start time, e.g., 2024-01-14T00:00:00Z>
To: <end time, e.g., 2024-01-15T00:00:00Z>
Or: Last <N> hours

## Log Groups
<list log groups, comma-separated>

## Request Types to Capture
- [ ] Successful happy-path requests
- [ ] Error cases (which error types?)
- [ ] Edge cases (specify)
- [ ] High-latency requests (threshold?)
- [ ] Retry scenarios

## Filtering Criteria
- User types: <all / specific segments>
- Request types: <all / specific operations>
- Exclude: <patterns to ignore>

## Output Requirements
- Number of cases to generate: <e.g., 10-20>
- Include expected outcomes: <yes/no>
- Anonymize PII: <yes - always>

Please:
1. Show me the CloudWatch Logs Insights query
2. Show me how to run itk derive
3. Show me the expected case YAML format
4. Explain how to curate/filter the results
```

---

## Step-by-Step: Deriving Cases

### Step 1: Query CloudWatch for Representative Requests

```bash
# Using AWS CLI
aws logs start-query \
  --log-group-names /aws/lambda/orchestrator /aws/lambda/processor \
  --start-time $(date -d '24 hours ago' +%s) \
  --end-time $(date +%s) \
  --query-string '
    fields @timestamp, @message
    | filter @message like /span_id/
    | filter @message like /"phase":"entry"/
    | sort @timestamp desc
    | limit 100
  '

# Get query results
aws logs get-query-results --query-id <query-id-from-above>
```

### Step 2: Use ITK Derive Command

```bash
# Derive cases from last 24 hours
itk derive --since 24h --out cases/derived/

# Derive from specific time range
itk derive --from 2024-01-14T00:00:00Z --to 2024-01-15T00:00:00Z --out cases/derived/

# Derive only error cases
itk derive --since 24h --filter-status error --out cases/derived-errors/
```

### Step 3: Review Generated Cases

```bash
# List generated cases
ls cases/derived/

# Review a case
cat cases/derived/case-001.yaml
```

### Step 4: Curate the Cases

Not all derived cases are useful. Keep cases that:

- ✅ Represent common user paths
- ✅ Cover error handling scenarios
- ✅ Exercise different code branches
- ✅ Have clear expected outcomes

Remove cases that:

- ❌ Are duplicates of existing cases
- ❌ Have incomplete data
- ❌ Are one-off anomalies
- ❌ Contain PII that wasn't redacted

---

## Case YAML Format

Derived cases should follow this structure:

```yaml
# cases/derived/checkout-flow-001.yaml
id: checkout-flow-001
name: Successful checkout with standard cart
description: |
  Derived from production logs on 2024-01-15.
  Represents typical checkout flow with 2-3 items.

# Where the request enters the system
entrypoint:
  type: sqs_event
  queue: orders-queue

# The request payload (anonymized)
input:
  action: checkout
  cart_id: "{{generated_uuid}}"
  items:
    - sku: "SAMPLE-001"
      quantity: 2
  # PII removed, replaced with placeholders
  customer_id: "{{customer_id}}"

# Expected behavior
expected:
  status: success
  components:
    - orchestrator
    - payment-processor
    - inventory-service
  max_latency_ms: 5000

# Invariants to check
invariants:
  - no_error_spans
  - max_retry_count: 2
  - required_components:
      - orchestrator
      - payment-processor

# Metadata
metadata:
  derived_from: production
  derived_at: 2024-01-15T10:30:00Z
  original_request_id: "abc-123-redacted"
```

---

## CloudWatch Logs Insights Queries

### Find Successful Requests

```sql
fields @timestamp, @message
| filter @message like /span_id/
| filter @message like /"phase":"exit"/
| filter @message like /"status":"success"/
| sort @timestamp desc
| limit 50
```

### Find Error Requests

```sql
fields @timestamp, @message
| filter @message like /span_id/
| filter @message like /"phase":"error"/
| sort @timestamp desc
| limit 50
```

### Find High-Latency Requests

```sql
fields @timestamp, @message
| filter @message like /span_id/
| filter @message like /"phase":"exit"/
| parse @message /"latency_ms":(?<latency>\d+)/
| filter latency > 3000
| sort latency desc
| limit 50
```

### Find Retry Scenarios

```sql
fields @timestamp, @message
| filter @message like /span_id/
| filter @message like /retry/
| sort @timestamp desc
| limit 50
```

---

## Anonymization Rules

Before committing derived cases, ensure:

1. **Remove all PII:**
   - Names → `{{customer_name}}`
   - Emails → `{{email}}`
   - Phone numbers → `{{phone}}`
   - Addresses → `{{address}}`
   - IP addresses → `0.0.0.0`

2. **Replace identifiers:**
   - Real user IDs → `{{customer_id}}`
   - Real order IDs → `{{order_id}}`
   - Real session IDs → `{{session_id}}`

3. **Keep operational data:**
   - Error types (no messages with PII)
   - Timing information
   - Component names
   - Status codes

---

## Example: Complete Derivation Workflow

```bash
# 1. Run derivation
itk derive --since 24h --out cases/derived/

# 2. See what was generated
ls cases/derived/
# Output: case-001.yaml case-002.yaml ... case-015.yaml

# 3. Validate all cases
for f in cases/derived/*.yaml; do
  itk validate --case "$f"
done

# 4. Test one case offline
itk run --mode dev-fixtures --case cases/derived/case-001.yaml --out artifacts/derived-test/

# 5. Review and curate
# Open each case, decide keep/delete/modify

# 6. Move keepers to main cases directory
mv cases/derived/case-003.yaml cases/smoke-checkout-001.yaml
mv cases/derived/case-007.yaml cases/error-payment-timeout-001.yaml

# 7. Delete the rest
rm -rf cases/derived/

# 8. Run final validation
itk validate --case cases/smoke-checkout-001.yaml
itk validate --case cases/error-payment-timeout-001.yaml
```

---

## Tips for Good Cases

1. **One scenario per case** - Don't combine multiple test scenarios
2. **Clear naming** - `smoke-checkout-001.yaml` not `case-001.yaml`
3. **Document the source** - Note when/where it was derived from
4. **Add expected outcomes** - What should happen?
5. **Include invariants** - What must be true for the test to pass?
