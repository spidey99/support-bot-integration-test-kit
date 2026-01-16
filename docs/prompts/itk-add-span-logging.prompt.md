# Prompt: Add Span Logging to Code

> **Use this prompt** when you need to add ITK-compatible span logging
> to Lambda handlers or other code to improve test diagram completeness.

---

## Prerequisites

- [ ] You've run `itk audit` and have a logging-gaps.md report
- [ ] You know which boundaries are missing spans
- [ ] You have access to the source code

---

## Prompt Template

Copy and fill in the blanks:

```
I need to add ITK-compatible span logging to improve test coverage.

**Source file**: [path to Lambda handler or module]
**Missing boundaries** (from itk audit):
- [boundary 1: e.g., "call to Bedrock agent"]
- [boundary 2: e.g., "SQS message publish"]
- [boundary 3: e.g., "DynamoDB query"]

**Correlation ID source**: [where to get correlation_id, e.g., "event.correlation_id"]

Steps:
1. Read the source file
2. Identify where each boundary occurs
3. Add span logging before/after each boundary
4. Ensure correlation_id is threaded through
5. Show me the diff
```

---

## Example Invocation

```
I need to add ITK-compatible span logging to improve test coverage.

**Source file**: src/handlers/orchestrator.py
**Missing boundaries** (from itk audit):
- call to Bedrock agent (invoke_agent)
- SQS message publish (send_message)
- DynamoDB query (get_item)

**Correlation ID source**: event["headers"]["x-correlation-id"]

Steps:
1. Read src/handlers/orchestrator.py
2. Find invoke_agent, send_message, get_item calls
3. Add span logging around each
4. Thread correlation_id through
5. Show me the diff
```

---

## Span Logging Pattern

ITK expects JSON logs with this structure:

```python
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def log_span(
    correlation_id: str,
    span_type: str,  # "entry" | "exit" | "call" | "return"
    component: str,  # "orchestrator" | "bedrock-agent" | "dynamodb" etc
    operation: str,  # "invoke" | "query" | "publish" etc
    **extra
):
    """Log an ITK-compatible span."""
    span = {
        "itk_span": True,
        "correlation_id": correlation_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "span_type": span_type,
        "component": component,
        "operation": operation,
        **extra
    }
    logger.info(json.dumps(span))
```

---

## Where to Add Spans

### Pattern: External Service Call

```python
# BEFORE
response = bedrock_client.invoke_agent(...)

# AFTER
log_span(correlation_id, "call", "bedrock-agent", "invoke",
         agent_id=agent_id, session_id=session_id)
response = bedrock_client.invoke_agent(...)
log_span(correlation_id, "return", "bedrock-agent", "invoke",
         status="success", response_size=len(response))
```

### Pattern: Lambda Entry/Exit

```python
def handler(event, context):
    correlation_id = event.get("correlation_id") or str(uuid.uuid4())
    
    # Entry span
    log_span(correlation_id, "entry", "orchestrator", "handle",
             event_type=event.get("type"))
    
    try:
        result = process(event, correlation_id)
        
        # Success exit span
        log_span(correlation_id, "exit", "orchestrator", "handle",
                 status="success")
        return result
        
    except Exception as e:
        # Error exit span
        log_span(correlation_id, "exit", "orchestrator", "handle",
                 status="error", error=str(e))
        raise
```

### Pattern: Queue Publish

```python
# BEFORE
sqs.send_message(QueueUrl=url, MessageBody=body)

# AFTER
log_span(correlation_id, "call", "sqs", "send_message",
         queue=queue_name, message_size=len(body))
response = sqs.send_message(QueueUrl=url, MessageBody=body)
log_span(correlation_id, "return", "sqs", "send_message",
         message_id=response["MessageId"])
```

### Pattern: Database Query

```python
# BEFORE
item = table.get_item(Key={"pk": pk})

# AFTER
log_span(correlation_id, "call", "dynamodb", "get_item",
         table=table_name, key=pk)
item = table.get_item(Key={"pk": pk})
log_span(correlation_id, "return", "dynamodb", "get_item",
         found=bool(item.get("Item")))
```

---

## Span Types Reference

| span_type | When to use |
|-----------|-------------|
| `entry` | Start of a Lambda handler or function boundary |
| `exit` | End of a Lambda handler or function boundary |
| `call` | About to call an external service |
| `return` | Just received response from external service |
| `emit` | Publishing event/message (fire-and-forget) |
| `receive` | Received event/message from queue |

---

## Thread Correlation ID

**Critical**: The correlation ID must flow through the entire request.

```python
# Option 1: Pass explicitly
def process(event, correlation_id):
    do_thing_1(correlation_id)
    do_thing_2(correlation_id)

# Option 2: Context variable (for complex call graphs)
from contextvars import ContextVar
correlation_id_var: ContextVar[str] = ContextVar("correlation_id")

def get_correlation_id() -> str:
    return correlation_id_var.get()

def handler(event, context):
    correlation_id_var.set(event.get("correlation_id") or str(uuid.uuid4()))
    ...
```

---

## What Success Looks Like

After adding span logging and re-running tests:

```
✅ itk audit shows no logging gaps
✅ Sequence diagram shows all boundaries
✅ Span count matches expected

Before: 2 spans (entry, exit)
After: 8 spans (entry, bedrock-call, bedrock-return, 
               sqs-call, sqs-return, dynamo-call, 
               dynamo-return, exit)
```

---

## Verification Steps

1. Deploy the updated code
2. Run the test: `itk run --case cases/<name>.yaml --out artifacts/new/`
3. Check span count: `wc -l artifacts/new/spans.jsonl`
4. View diagram: open `artifacts/new/trace.html`
5. Re-run audit: `itk audit --case cases/<name>.yaml`
