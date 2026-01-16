# ITK: Add a New Entrypoint Adapter

Use this prompt when you need to add support for a new entrypoint type (beyond SQS, Lambda direct, and Bedrock Agent).

## Overview

ITK supports multiple entrypoint types for triggering test flows:
- `sqs_event` - Publish to SQS queue (golden path) or invoke Lambda with SQS-shaped event
- `lambda_invoke` - Direct Lambda invocation
- `bedrock_invoke_agent` - Bedrock Agent invocation with trace

## Adding a New Adapter

### 1. Create the adapter module

Create a new file in `src/itk/entrypoints/`:

```python
# src/itk/entrypoints/my_new_entrypoint.py
"""My new entrypoint adapter.

Description of what this entrypoint does and when to use it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class MyNewTarget:
    """Configuration for the new entrypoint."""
    
    # Required fields
    endpoint_url: str
    
    # Optional fields
    region: Optional[str] = None


class MyNewAdapter:
    """Adapter for the new entrypoint type."""
    
    def __init__(
        self,
        target: MyNewTarget,
        offline: bool = False,
    ):
        self._target = target
        self._offline = offline
        self._client: Any = None
    
    def _validate_target(self) -> None:
        """Validate the target configuration."""
        if not self._target.endpoint_url:
            raise ValueError("endpoint_url is required")
    
    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Invoke the entrypoint with the given payload."""
        self._validate_target()
        
        if self._offline:
            # Return mock result for offline testing
            return {"status": "offline", "mock": True}
        
        # Implement actual invocation using boto3 or other client
        raise NotImplementedError("Implement in Tier 3")
```

### 2. Update the case schema

Add the new entrypoint type to `schemas/itk.case.schema.json`:

```json
{
  "entrypoint": {
    "properties": {
      "type": {
        "enum": ["sqs_event", "lambda_invoke", "bedrock_invoke_agent", "my_new_type"]
      }
    }
  }
}
```

### 3. Wire into the CLI

Update `src/itk/cli.py` to handle the new entrypoint type in online mode:

```python
from itk.entrypoints.my_new_entrypoint import MyNewAdapter, MyNewTarget

# In _cmd_run():
if case.entrypoint.type == "my_new_type":
    target = MyNewTarget(
        endpoint_url=case.entrypoint.target.get("endpoint_url"),
        region=case.entrypoint.target.get("region"),
    )
    adapter = MyNewAdapter(target, offline=offline)
    result = adapter.invoke(case.entrypoint.payload)
```

### 4. Add tests

Create tests in `tests/test_entrypoints/test_my_new.py`:

```python
def test_offline_returns_mock():
    adapter = MyNewAdapter(target, offline=True)
    result = adapter.invoke({})
    assert result["mock"] is True
```

### 5. Add a case example

Create an example case in `cases/`:

```yaml
id: example-my-new-001
name: Example using new entrypoint
entrypoint:
  type: my_new_type
  target:
    endpoint_url: "https://example.com/api"
  payload:
    data: "test"
expected:
  invariants:
    - name: has_spans
```

### 6. Document the adapter

Update `README_WORK_REPO.md` with usage instructions.

## Checklist

- [ ] Adapter module with offline mock support
- [ ] Schema updated with new type
- [ ] CLI wired for online mode
- [ ] Unit tests for offline mode
- [ ] Example case YAML
- [ ] Documentation updated
