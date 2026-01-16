# ITK Prompt: Add a New Entrypoint Adapter

> **Use this prompt when**: You need to support a new way of triggering tests (e.g., API Gateway, EventBridge, Step Functions).

---

## Context to Gather First

Before using this prompt, collect:

1. **The entrypoint type** (API Gateway, EventBridge, SNS, Step Functions, etc.)
2. **How the system currently handles** this entrypoint
3. **The event format** for this entrypoint
4. **How to invoke it programmatically**

---

## Prompt Template

Copy and fill in:

```
I need to add a new ITK entrypoint adapter for [ENTRYPOINT_TYPE].

## Entrypoint Type
<e.g., API Gateway REST, EventBridge, SNS, Step Functions>

## Event Format
<paste example event payload>

## How to Invoke
<AWS CLI command or SDK call to trigger this entrypoint>

## Expected Response
<what the entrypoint returns on success>

## Correlation IDs
- Where is trace_id? <field path in event>
- Where is request_id? <field path in event>
- Where is parent_span_id? <field path or N/A>

## Log Groups
<which CloudWatch log groups capture logs for this entrypoint>

Please:
1. Show me the adapter class/module structure
2. Show me how to register it in the CLI
3. Show me the case YAML format for this entrypoint
4. Show me a test case example
```

---

## Adapter Architecture

ITK entrypoint adapters follow this pattern:

```
src/itk/entrypoints/
├── __init__.py           # Registry of all adapters
├── base.py               # Base adapter class
├── sqs_event.py          # SQS adapter (golden path)
├── lambda_direct.py      # Direct Lambda invoke
├── bedrock_agent.py      # Bedrock agent invoke
└── your_new_adapter.py   # Your new adapter
```

---

## Base Adapter Interface

Every adapter must implement:

```python
# src/itk/entrypoints/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class InvokeResult:
    """Result from invoking an entrypoint."""
    success: bool
    response: Any
    correlation_id: str
    trace_id: str | None
    latency_ms: int
    error: str | None = None


class EntrypointAdapter(ABC):
    """Base class for all entrypoint adapters."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this adapter."""
        pass
    
    @abstractmethod
    def invoke(
        self,
        payload: dict,
        correlation_id: str,
        timeout_seconds: int = 30,
    ) -> InvokeResult:
        """
        Invoke the entrypoint with the given payload.
        
        Args:
            payload: The request payload
            correlation_id: ID to track this request
            timeout_seconds: Max wait time
            
        Returns:
            InvokeResult with response and metadata
        """
        pass
    
    @abstractmethod
    def validate_config(self) -> list[str]:
        """
        Validate that required configuration is present.
        
        Returns:
            List of error messages (empty if valid)
        """
        pass
```

---

## Example: API Gateway Adapter

```python
# src/itk/entrypoints/api_gateway.py
"""API Gateway REST entrypoint adapter."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import boto3

from .base import EntrypointAdapter, InvokeResult


class ApiGatewayAdapter(EntrypointAdapter):
    """Adapter for invoking via API Gateway REST API."""
    
    def __init__(self):
        self.api_id = os.environ.get("ITK_API_GATEWAY_ID")
        self.stage = os.environ.get("ITK_API_GATEWAY_STAGE", "qa")
        self.region = os.environ.get("AWS_REGION", "us-east-1")
        self._client = None
    
    @property
    def name(self) -> str:
        return "api_gateway"
    
    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client(
                "apigateway",
                region_name=self.region,
            )
        return self._client
    
    def invoke(
        self,
        payload: dict,
        correlation_id: str,
        timeout_seconds: int = 30,
    ) -> InvokeResult:
        """Invoke API Gateway endpoint."""
        start_time = time.time()
        
        try:
            # Build the request
            method = payload.get("method", "POST")
            path = payload.get("path", "/")
            body = payload.get("body", {})
            headers = payload.get("headers", {})
            
            # Add correlation headers
            headers["X-Correlation-ID"] = correlation_id
            headers["X-ITK-Test"] = "true"
            
            # Use requests or urllib for actual HTTP call
            # (API Gateway test-invoke is for testing only)
            import requests
            
            url = f"https://{self.api_id}.execute-api.{self.region}.amazonaws.com/{self.stage}{path}"
            
            response = requests.request(
                method=method,
                url=url,
                json=body,
                headers=headers,
                timeout=timeout_seconds,
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            return InvokeResult(
                success=response.status_code < 400,
                response={
                    "statusCode": response.status_code,
                    "body": response.text,
                    "headers": dict(response.headers),
                },
                correlation_id=correlation_id,
                trace_id=response.headers.get("X-Amzn-Trace-Id"),
                latency_ms=latency_ms,
                error=None if response.status_code < 400 else response.text,
            )
            
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return InvokeResult(
                success=False,
                response=None,
                correlation_id=correlation_id,
                trace_id=None,
                latency_ms=latency_ms,
                error=str(e),
            )
    
    def validate_config(self) -> list[str]:
        """Validate API Gateway configuration."""
        errors = []
        
        if not self.api_id:
            errors.append("ITK_API_GATEWAY_ID not set")
        
        if not self.stage:
            errors.append("ITK_API_GATEWAY_STAGE not set")
        
        return errors
```

---

## Register the Adapter

```python
# src/itk/entrypoints/__init__.py
"""Entrypoint adapter registry."""

from .api_gateway import ApiGatewayAdapter
from .base import EntrypointAdapter, InvokeResult
from .bedrock_agent import BedrockAgentAdapter
from .lambda_direct import LambdaDirectAdapter
from .sqs_event import SqsEventAdapter

# Registry of all available adapters
ADAPTERS: dict[str, type[EntrypointAdapter]] = {
    "sqs_event": SqsEventAdapter,
    "sqs": SqsEventAdapter,  # Alias
    "lambda_direct": LambdaDirectAdapter,
    "lambda": LambdaDirectAdapter,  # Alias
    "bedrock_agent": BedrockAgentAdapter,
    "bedrock": BedrockAgentAdapter,  # Alias
    "api_gateway": ApiGatewayAdapter,  # NEW
    "api": ApiGatewayAdapter,  # Alias
}


def get_adapter(name: str) -> EntrypointAdapter:
    """Get an adapter instance by name."""
    if name not in ADAPTERS:
        available = ", ".join(sorted(ADAPTERS.keys()))
        raise ValueError(f"Unknown adapter: {name}. Available: {available}")
    return ADAPTERS[name]()
```

---

## Case YAML for New Entrypoint

```yaml
# cases/api-gateway-checkout-001.yaml
id: api-gateway-checkout-001
name: Checkout via API Gateway
description: Test checkout flow through REST API

entrypoint:
  type: api_gateway
  # Adapter-specific config
  method: POST
  path: /v1/checkout

input:
  body:
    cart_id: "{{cart_id}}"
    payment_method: credit_card
  headers:
    Authorization: "Bearer {{test_token}}"
    Content-Type: application/json

expected:
  status: success
  response:
    statusCode: 200

invariants:
  - no_error_spans
  - required_components:
      - api-gateway
      - checkout-service
      - payment-processor
```

---

## Environment Variables

Add to `.env.example`:

```bash
# API Gateway (if using api_gateway entrypoint)
ITK_API_GATEWAY_ID=abc123def
ITK_API_GATEWAY_STAGE=qa
```

---

## Testing the Adapter

```bash
# 1. Set environment variables
export ITK_API_GATEWAY_ID=your-api-id
export ITK_API_GATEWAY_STAGE=qa

# 2. Validate config
python -c "
from itk.entrypoints import get_adapter
adapter = get_adapter('api_gateway')
errors = adapter.validate_config()
print('Errors:', errors if errors else 'None')
"

# 3. Run a test case
itk run --case cases/api-gateway-checkout-001.yaml --out artifacts/api-test/

# 4. Check results
cat artifacts/api-test/report.md
```

---

## Checklist for New Adapter

- [ ] Created adapter class in `src/itk/entrypoints/`
- [ ] Implemented `name`, `invoke`, `validate_config`
- [ ] Registered in `__init__.py` ADAPTERS dict
- [ ] Added environment variables to `.env.example`
- [ ] Created example case YAML
- [ ] Tested with `itk run`
- [ ] Documented in `docs/` if complex
