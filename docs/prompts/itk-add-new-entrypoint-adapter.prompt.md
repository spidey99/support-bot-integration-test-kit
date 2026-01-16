# Prompt: Add New Entrypoint Adapter

> **Use this prompt** when you need to add support for a new type of
> Lambda entrypoint (e.g., API Gateway, EventBridge, Step Functions).

---

## Prerequisites

- [ ] You know the event schema for the new entrypoint
- [ ] You have an example event payload (JSON)
- [ ] You know the correlation ID extraction logic

---

## Prompt Template

Copy and fill in the blanks:

```
I need to add a new ITK entrypoint adapter.

**Entrypoint type**: [api-gateway / eventbridge / step-functions / other]
**Event source**: [describe where events come from]
**Correlation ID field**: [path to correlation ID in event, e.g., "headers.x-correlation-id"]

Example event payload:
```json
{
  // paste example event here
}
```

Steps:
1. Create adapter file: src/itk/entrypoints/[name]_event.py
2. Implement event_matches() — returns True if event is this type
3. Implement extract_correlation_id() — returns the correlation ID
4. Implement normalize_event() — returns standardized event dict
5. Add adapter to __init__.py exports
6. Write tests in tests/entrypoints/test_[name]_event.py
7. Add fixture: fixtures/events/[name]_event_001.json
```

---

## Example Invocation

```
I need to add a new ITK entrypoint adapter.

**Entrypoint type**: api-gateway
**Event source**: API Gateway HTTP API v2
**Correlation ID field**: headers.x-request-id

Example event payload:
```json
{
  "version": "2.0",
  "routeKey": "POST /support",
  "rawPath": "/support",
  "headers": {
    "x-request-id": "abc-123-def",
    "content-type": "application/json"
  },
  "body": "{\"query\": \"help me\"}",
  "isBase64Encoded": false
}
```

Steps:
1. Create adapter file: src/itk/entrypoints/api_gateway_event.py
2. Implement event_matches() — checks for "version": "2.0" and "routeKey"
3. Implement extract_correlation_id() — returns headers["x-request-id"]
4. Implement normalize_event() — returns standardized dict
5. Add to __init__.py
6. Write tests
7. Add fixture
```

---

## Expected Agent Actions

1. Create `src/itk/entrypoints/<name>_event.py`:
   ```python
   from dataclasses import dataclass
   from typing import Any
   
   @dataclass
   class <Name>Event:
       raw: dict[str, Any]
       
       @classmethod
       def event_matches(cls, event: dict) -> bool:
           # Detection logic here
           ...
       
       def extract_correlation_id(self) -> str | None:
           # Extraction logic here
           ...
       
       def normalize_event(self) -> dict[str, Any]:
           # Normalization logic here
           ...
   ```

2. Add exports to `src/itk/entrypoints/__init__.py`

3. Create test file with:
   - Test detection works
   - Test correlation ID extraction
   - Test normalization
   - Test with fixture

4. Add fixture event file

---

## Adapter Template

```python
"""Adapter for [EntrypointType] events."""

from dataclasses import dataclass
from typing import Any


@dataclass
class <Name>Event:
    """Wraps a [EntrypointType] event for ITK processing."""
    
    raw: dict[str, Any]
    
    @classmethod
    def event_matches(cls, event: dict) -> bool:
        """Return True if event is a [EntrypointType] event."""
        # TODO: Implement detection logic
        return False
    
    def extract_correlation_id(self) -> str | None:
        """Extract correlation ID from event."""
        # TODO: Implement extraction logic
        return None
    
    def normalize_event(self) -> dict[str, Any]:
        """Return standardized event representation."""
        return {
            "type": "<name>-event",
            "correlation_id": self.extract_correlation_id(),
            "raw": self.raw,
            # TODO: Add type-specific fields
        }
```

---

## What Success Looks Like

```
✅ Created src/itk/entrypoints/api_gateway_event.py
✅ Added exports to __init__.py
✅ Created tests/entrypoints/test_api_gateway_event.py
✅ Created fixtures/events/api_gateway_event_001.json
✅ All tests pass

New adapter recognizes event type: True
Correlation ID extracted: abc-123-def
```
