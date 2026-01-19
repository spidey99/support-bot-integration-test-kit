# Log Field Glossary

This document explains every field in the ITK span schema. Use this when implementing structured logging in your services.

## Quick Reference

| Field | Required | Purpose |
|-------|----------|---------|
| `span_id` | ✅ Yes | Unique identifier for this span |
| `component` | ✅ Yes | Type of service/component |
| `operation` | ✅ Yes | Specific operation performed |
| `parent_span_id` | No | Links to calling span |
| `ts_start` | No | When operation started |
| `ts_end` | No | When operation completed |
| `attempt` | No | Retry attempt number |
| `itk_trace_id` | No | Custom trace ID |
| `lambda_request_id` | No | AWS Lambda request ID |
| `xray_trace_id` | No | AWS X-Ray trace ID |
| `sqs_message_id` | No | SQS message ID |
| `bedrock_session_id` | No | Bedrock session ID |
| `request` | No | Input payload |
| `response` | No | Output payload |
| `error` | No | Error details if failed |

---

## Required Fields

### `span_id`

**Type:** `string`  
**Required:** Yes

A unique identifier for this span. Every log entry must have a distinct `span_id`.

**How to generate:**
```python
import uuid
span_id = f"span-{uuid.uuid4().hex[:12]}"
# Example: "span-abc123def456"
```

**Why it matters:**
- Links parent/child relationships
- Enables deduplication in log aggregation
- Required for trace reconstruction

---

### `component`

**Type:** `string`  
**Required:** Yes

The type of service or component that generated this span.

**Standard values:**

| Value | Description |
|-------|-------------|
| `lambda` | AWS Lambda function |
| `sqs` | SQS queue operation |
| `bedrock_agent` | Bedrock Agent invocation |
| `bedrock_model` | Bedrock model invocation (Claude, etc.) |
| `dynamodb` | DynamoDB operation |
| `s3` | S3 operation |
| `http_client` | Outbound HTTP request |
| `step_functions` | Step Functions state machine |
| `eventbridge` | EventBridge rule/event |

**Custom components:** You can add custom component types. Use lowercase with underscores.

---

### `operation`

**Type:** `string`  
**Required:** Yes

The specific operation performed by the component.

**Examples by component:**

| Component | Common Operations |
|-----------|-------------------|
| `lambda` | `Invoke`, `InvokeAsync` |
| `sqs` | `SendMessage`, `ReceiveMessage`, `DeleteMessage` |
| `bedrock_agent` | `InvokeAgent` |
| `bedrock_model` | `InvokeModel`, `InvokeModelWithResponseStream` |
| `dynamodb` | `GetItem`, `PutItem`, `Query`, `Scan`, `UpdateItem` |
| `s3` | `GetObject`, `PutObject`, `ListObjects` |
| `http_client` | `GET`, `POST`, `PUT`, `DELETE` |

---

## Optional Fields

### `parent_span_id`

**Type:** `string | null`  
**Required:** No

The `span_id` of the calling span. Use this to build the call hierarchy.

**Rules:**
- Set to `null` for root spans (entry points like Lambda handler)
- Set to the caller's `span_id` for child operations

**Example:**
```
Lambda handler (parent_span_id: null)
  └── Bedrock invoke (parent_span_id: "span-lambda-123")
        └── Model call (parent_span_id: "span-bedrock-456")
```

---

### `ts_start`

**Type:** `string | null`  
**Required:** No (but strongly recommended)

ISO 8601 timestamp when the operation started.

**Format:** `YYYY-MM-DDTHH:mm:ss.sssZ`

**Example:** `"2026-01-17T10:00:00.000Z"`

**How to generate:**
```python
from datetime import datetime, timezone
ts_start = datetime.now(timezone.utc).isoformat()
```

---

### `ts_end`

**Type:** `string | null`  
**Required:** No (but strongly recommended)

ISO 8601 timestamp when the operation completed.

**Why it matters:**
- Duration = `ts_end` - `ts_start`
- Enables latency analysis
- Required for accurate sequence diagrams

---

### `attempt`

**Type:** `integer | null`  
**Required:** No

The retry attempt number for this operation.

**Values:**
- `1` = First attempt
- `2` = First retry
- `3` = Second retry
- etc.

**Why it matters:**
- Identifies retry storms
- Helps debug intermittent failures
- Audit shows if retries are logged

---

### `itk_trace_id`

**Type:** `string | null`  
**Required:** No

A custom trace ID that you pass through your entire request flow.

**How to use:**
1. Generate at entry point (API Gateway, SQS trigger, etc.)
2. Pass through all downstream calls
3. Log with every span

**Example flow:**
```
API Gateway → Lambda A → SQS → Lambda B → Bedrock
   └── all spans share same itk_trace_id
```

---

### `lambda_request_id`

**Type:** `string | null`  
**Required:** No (but essential for Lambda)

The AWS Lambda request ID from `context.aws_request_id`.

**Why it matters:**
- Correlates logs to specific Lambda invocation
- Links to CloudWatch Logs Insights queries
- Required for live mode log fetching

**How to capture:**
```python
def handler(event, context):
    request_id = context.aws_request_id
    # Include in all log entries
```

---

### `xray_trace_id`

**Type:** `string | null`  
**Required:** No

AWS X-Ray trace ID when X-Ray tracing is enabled.

**Format:** `1-{unix_epoch}-{96_bit_identifier}`

**Example:** `"1-5759e988-bd862e3fe1be46a994272793"`

**How to capture:**
```python
import os
xray_trace_id = os.environ.get("_X_AMZN_TRACE_ID", "").split(";")[0].replace("Root=", "")
```

---

### `sqs_message_id`

**Type:** `string | null`  
**Required:** No

The SQS message ID when processing a queue message.

**How to capture:**
```python
def handler(event, context):
    for record in event["Records"]:
        message_id = record["messageId"]
```

---

### `bedrock_session_id`

**Type:** `string | null`  
**Required:** No

Bedrock agent session ID for multi-turn conversations.

**Why it matters:**
- Groups related agent interactions
- Enables session replay
- Required for conversation context

---

### `request`

**Type:** `object | null`  
**Required:** No

The input payload sent to the operation.

**Guidelines:**
- [ ] Include relevant request parameters
- [ ] Redact sensitive data (passwords, tokens, PII)
- [ ] Keep payload size reasonable (< 10KB recommended)

**Example:**
```json
{
  "agentId": "WYEP3TYH1A",
  "inputText": "What is ticket status?",
  "sessionId": "sess-001"
}
```

---

### `response`

**Type:** `object | null`  
**Required:** No

The output received from the operation.

**Guidelines:**
- [ ] Include relevant response data
- [ ] Redact PII (names, emails, phone numbers)
- [ ] Truncate large responses if needed

**Example:**
```json
{
  "completion": "Ticket is in progress",
  "tokens_used": 150
}
```

---

### `error`

**Type:** `object | null`  
**Required:** No

Error details if the operation failed.

**Recommended structure:**
```json
{
  "code": "ThrottlingException",
  "message": "Rate exceeded",
  "retryable": true
}
```

**Fields:**
- `code`: Error code or exception class name
- `message`: Human-readable error message
- `retryable`: Whether the error is transient

---

## Best Practices Checklist

- [ ] Always include the three required fields: `span_id`, `component`, `operation`
- [ ] Add timestamps (`ts_start`, `ts_end`) for latency analysis
- [ ] Set `parent_span_id` to build call hierarchies
- [ ] Include `lambda_request_id` in Lambda functions
- [ ] Pass `itk_trace_id` through all services for end-to-end tracing
- [ ] Log `attempt` number for retry-able operations
- [ ] Redact sensitive data from `request` and `response`
- [ ] Capture `error` details with error code and retryability

---

## Example: Complete Span Log Entry

```json
{
  "span_id": "span-abc123",
  "parent_span_id": "span-parent-789",
  "component": "bedrock_agent",
  "operation": "InvokeAgent",
  "ts_start": "2026-01-17T10:00:00.000Z",
  "ts_end": "2026-01-17T10:00:01.234Z",
  "attempt": 1,
  "itk_trace_id": "trace-xyz789",
  "lambda_request_id": "12345678-1234-1234-1234-123456789abc",
  "bedrock_session_id": "sess-001",
  "request": {
    "agentId": "WYEP3TYH1A",
    "inputText": "What is ticket status?"
  },
  "response": {
    "completion": "Ticket ABC-123 is in progress."
  },
  "error": null
}
```

---

## See Also

- [log-schema-example.json](log-schema-example.json) — Annotated example file
- [03-log-span-contract.md](03-log-span-contract.md) — Log contract overview
- `schemas/itk.span.schema.json` — JSON Schema definition
