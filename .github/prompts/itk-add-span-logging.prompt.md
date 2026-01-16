# ITK Prompt: Add Span Logging

> **Use this prompt when**: `itk audit` shows logging gaps that need to be filled.

---

## Context to Gather First

Before using this prompt, collect:

1. **The logging-gaps.md** from `itk audit` output
2. **The function/handler code** that needs logging
3. **The span schema** from `dropin/itk/schemas/itk.span.schema.json`

---

## Prompt Template

Copy and fill in:

```
I need to add ITK-compatible span logging to fill gaps identified by `itk audit`.

## Logging Gaps Report
<paste contents of logging-gaps.md>

## Current Code
<paste the function/handler that needs logging>

## Language
<Python / TypeScript / etc.>

## Logger Configuration
- Logger name: <e.g., structlog, logging, console>
- Log level for spans: <WARN recommended>
- Output format: <JSON required>

Please:
1. Show me the exact import statements needed
2. Show me the span log statements for ENTRY and EXIT
3. Include proper error handling with ERROR spans
4. Ensure correlation IDs are propagated
5. Keep the changes minimal (boundary logs only)
```

---

## Span Log Format (Required Fields)

Every span log MUST include:

```json
{
  "span_id": "unique-id",
  "parent_span_id": "parent-id-or-null",
  "component": "component-name",
  "operation": "operation-name",
  "phase": "entry|exit|error",
  "ts": "2024-01-15T10:30:00.000Z",
  "correlation": {
    "request_id": "lambda-request-id",
    "trace_id": "x-ray-trace-id"
  }
}
```

**For EXIT spans, also include:**
```json
{
  "status": "success|error",
  "latency_ms": 123
}
```

**For ERROR spans, also include:**
```json
{
  "error": {
    "type": "ErrorClassName",
    "message": "Error description"
  }
}
```

---

## Python Example: Lambda Handler

### Before (no span logging)

```python
def handler(event, context):
    result = process(event)
    return {"statusCode": 200, "body": result}
```

### After (with span logging)

```python
import json
import logging
import time
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARN)  # Spans at WARN level

def handler(event, context):
    span_id = str(uuid.uuid4())
    start_time = time.time()
    
    # ENTRY span
    logger.warning(json.dumps({
        "span_id": span_id,
        "parent_span_id": event.get("parent_span_id"),
        "component": "my-lambda",
        "operation": "handler",
        "phase": "entry",
        "ts": datetime.now(timezone.utc).isoformat(),
        "correlation": {
            "request_id": context.aws_request_id,
            "trace_id": event.get("trace_id")
        },
        "request": {
            "event_type": event.get("type"),
            # Include relevant request fields (NO PII)
        }
    }))
    
    try:
        result = process(event)
        
        # EXIT span (success)
        logger.warning(json.dumps({
            "span_id": span_id,
            "parent_span_id": event.get("parent_span_id"),
            "component": "my-lambda",
            "operation": "handler",
            "phase": "exit",
            "ts": datetime.now(timezone.utc).isoformat(),
            "status": "success",
            "latency_ms": int((time.time() - start_time) * 1000),
            "correlation": {
                "request_id": context.aws_request_id,
                "trace_id": event.get("trace_id")
            },
            "response": {
                "status_code": 200,
                # Include relevant response fields (NO PII)
            }
        }))
        
        return {"statusCode": 200, "body": result}
        
    except Exception as e:
        # ERROR span
        logger.warning(json.dumps({
            "span_id": span_id,
            "parent_span_id": event.get("parent_span_id"),
            "component": "my-lambda",
            "operation": "handler",
            "phase": "error",
            "ts": datetime.now(timezone.utc).isoformat(),
            "status": "error",
            "latency_ms": int((time.time() - start_time) * 1000),
            "correlation": {
                "request_id": context.aws_request_id,
                "trace_id": event.get("trace_id")
            },
            "error": {
                "type": type(e).__name__,
                "message": str(e)
            }
        }))
        raise
```

---

## Key Boundaries to Log

These are the most important places to add span logs:

| Boundary | Component | Operation |
|----------|-----------|-----------|
| Lambda handler entry/exit | `lambda-function-name` | `handler` |
| SQS message receive | `sqs-consumer` | `receive` |
| SQS message publish | `sqs-publisher` | `send` |
| Bedrock agent invoke | `bedrock-agent` | `invoke` |
| DynamoDB get/put | `dynamodb` | `get`/`put` |
| External API call | `http-client` | `request` |
| Internal service call | `service-name` | `method-name` |

---

## Correlation ID Propagation

Always propagate these IDs through the call chain:

```python
# Extract from incoming event
trace_id = event.get("trace_id") or context.get("trace_id")
parent_span_id = event.get("span_id")  # Caller's span becomes our parent

# Generate our span ID
span_id = str(uuid.uuid4())

# Pass to downstream calls
downstream_event = {
    **payload,
    "trace_id": trace_id,
    "parent_span_id": span_id,  # Our span is child's parent
}
```

---

## Minimal Logging Checklist

After adding logging, verify:

- [ ] ENTRY span logged at start of handler
- [ ] EXIT span logged on success (includes latency_ms)
- [ ] ERROR span logged on exception (includes error type/message)
- [ ] All spans have same span_id within one invocation
- [ ] parent_span_id links to caller's span_id
- [ ] correlation.request_id is the Lambda request ID
- [ ] No PII in logged fields
- [ ] Log level is WARN (so it survives log level filtering)

---

## Test Your Logging

```bash
# 1. Deploy the updated code
# 2. Run a test
itk run --case cases/example-001.yaml --out artifacts/test-logging/

# 3. Check the diagram improved
cat artifacts/test-logging/sequence.mmd

# 4. Re-run audit to verify gaps are filled
itk audit --case cases/example-001.yaml --out artifacts/audit-after/
cat artifacts/audit-after/logging-gaps.md
```
