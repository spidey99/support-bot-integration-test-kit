"""Lambda direct invocation adapter.

This module provides utilities for directly invoking Lambda functions for testing.
This is a "fast debug" mode alternative to the SQS golden path - useful when you
want synchronous invocation and immediate response without the SQS queue.

Tier 2 (offline): Validates configuration and provides mock responses
Tier 3 (online): Actually invokes Lambda functions
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# Note: boto3 import is deferred to runtime to avoid issues in offline mode


@dataclass(frozen=True)
class LambdaTarget:
    """Configuration for a Lambda function target."""

    function_name_or_arn: str
    region: Optional[str] = None
    qualifier: Optional[str] = None  # Alias or version


@dataclass
class LambdaInvokeResponse:
    """Response from a Lambda invocation."""

    request_id: str
    status_code: int
    payload: dict[str, Any] = field(default_factory=dict)
    log_result: Optional[str] = None
    function_error: Optional[str] = None
    executed_version: Optional[str] = None
    timestamp: str = ""


class LambdaDirectAdapter:
    """Adapter for direct Lambda function invocations.

    This is the "fast debug" mode - synchronous invocation with immediate response.
    Use SqsEventAdapter for the full async flow (golden path).
    """

    def __init__(
        self,
        target: LambdaTarget,
        offline: bool = False,
    ):
        """Initialize the Lambda direct adapter.

        Args:
            target: Target configuration
            offline: If True, operations return mock responses
        """
        self._target = target
        self._offline = offline
        self._client: Any = None

    def _validate_target(self) -> None:
        """Validate the target configuration."""
        if not self._target.function_name_or_arn:
            raise ValueError("function_name_or_arn is required")

        if self._target.function_name_or_arn == "REPLACE_ME":
            raise ValueError(
                "function_name_or_arn has placeholder value 'REPLACE_ME'. "
                "Configure the actual Lambda ARN/name in the case YAML."
            )

    def _get_client(self) -> Any:
        """Get or create the boto3 Lambda client."""
        if self._offline:
            raise NotImplementedError("Lambda operations not available in offline mode")

        if self._client is None:
            import boto3

            self._client = boto3.client("lambda", region_name=self._target.region)
        return self._client

    def invoke(
        self,
        payload: dict[str, Any],
        invocation_type: str = "RequestResponse",
        log_type: str = "Tail",
    ) -> LambdaInvokeResponse:
        """Invoke the Lambda function.

        Args:
            payload: The event payload to send to the function
            invocation_type: "RequestResponse" (sync) or "Event" (async)
            log_type: "Tail" to get last 4KB of logs, or "None"

        Returns:
            LambdaInvokeResponse with invocation results
        """
        self._validate_target()

        if self._offline:
            # Return mock result in offline mode
            return LambdaInvokeResponse(
                request_id=f"offline-{uuid.uuid4()}",
                status_code=200,
                payload={"statusCode": 200, "body": "offline mock response"},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        client = self._get_client()

        # Build invocation parameters
        invoke_params: dict[str, Any] = {
            "FunctionName": self._target.function_name_or_arn,
            "InvocationType": invocation_type,
            "Payload": json.dumps(payload),
        }

        if log_type != "None":
            invoke_params["LogType"] = log_type

        if self._target.qualifier:
            invoke_params["Qualifier"] = self._target.qualifier

        response = client.invoke(**invoke_params)

        # Parse response payload
        response_payload = {}
        if "Payload" in response:
            payload_bytes = response["Payload"].read()
            if payload_bytes:
                try:
                    response_payload = json.loads(payload_bytes)
                except json.JSONDecodeError:
                    response_payload = {"raw": payload_bytes.decode("utf-8", errors="replace")}

        # Decode log result if present
        log_result = None
        if "LogResult" in response:
            import base64

            log_result = base64.b64decode(response["LogResult"]).decode("utf-8")

        return LambdaInvokeResponse(
            request_id=response["ResponseMetadata"]["RequestId"],
            status_code=response["StatusCode"],
            payload=response_payload,
            log_result=log_result,
            function_error=response.get("FunctionError"),
            executed_version=response.get("ExecutedVersion"),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def invoke_async(self, payload: dict[str, Any]) -> LambdaInvokeResponse:
        """Invoke the Lambda function asynchronously.

        The function will be triggered but this returns immediately
        without waiting for completion.

        Args:
            payload: The event payload to send to the function

        Returns:
            LambdaInvokeResponse (status_code 202 indicates accepted)
        """
        return self.invoke(payload, invocation_type="Event", log_type="None")


# Backward compatibility alias
def invoke_lambda(
    *,
    target: LambdaTarget,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Invoke a Lambda function (backward compatibility wrapper).

    Raises NotImplementedError - use LambdaDirectAdapter instead.
    """
    raise NotImplementedError(
        "invoke_lambda is deprecated. "
        "Use LambdaDirectAdapter(target, offline=False).invoke() in Tier 3."
    )
