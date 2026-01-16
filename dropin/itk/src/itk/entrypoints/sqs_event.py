"""SQS event entrypoint adapter.

This module provides utilities for triggering test flows via SQS message publishing.
SQS is the "golden path" for integration testing as it exercises the full async flow.

Tier 2 (offline): Validates configuration and provides mock responses
Tier 3 (online): Actually publishes to SQS or invokes Lambda directly
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# Note: boto3 import is deferred to runtime to avoid issues in offline mode


@dataclass(frozen=True)
class SqsEventTarget:
    """Configuration for an SQS-shaped event target."""

    mode: str  # "publish_sqs" (golden path) or "invoke_lambda" (fast debug)
    target_arn_or_url: str
    region: Optional[str] = None


@dataclass
class SqsPublishResult:
    """Result of publishing an SQS message."""

    message_id: str
    sequence_number: Optional[str] = None
    md5_of_body: Optional[str] = None
    timestamp: str = ""


@dataclass
class LambdaInvokeResult:
    """Result of directly invoking a Lambda function."""

    request_id: str
    status_code: int
    payload: dict[str, Any] = field(default_factory=dict)
    function_error: Optional[str] = None


class SqsEventAdapter:
    """Adapter for triggering test flows via SQS-shaped events.

    Supports two modes:
    - publish_sqs: Publish to an SQS queue (golden path, full async flow)
    - invoke_lambda: Direct Lambda invocation (fast debug mode)
    """

    def __init__(
        self,
        target: SqsEventTarget,
        offline: bool = False,
    ):
        """Initialize the SQS event adapter.

        Args:
            target: Target configuration
            offline: If True, operations return mock responses
        """
        self._target = target
        self._offline = offline
        self._sqs_client: Any = None
        self._lambda_client: Any = None

    def _validate_target(self) -> None:
        """Validate the target configuration."""
        if self._target.mode not in ("publish_sqs", "invoke_lambda"):
            raise ValueError(
                f"Invalid mode '{self._target.mode}'. "
                "Must be 'publish_sqs' or 'invoke_lambda'."
            )

        if not self._target.target_arn_or_url:
            raise ValueError("target_arn_or_url is required")

        if self._target.target_arn_or_url == "REPLACE_ME":
            raise ValueError(
                "target_arn_or_url has placeholder value 'REPLACE_ME'. "
                "Configure the actual target ARN/URL in the case YAML."
            )

    def _get_sqs_client(self) -> Any:
        """Get or create the boto3 SQS client."""
        if self._offline:
            raise NotImplementedError("SQS operations not available in offline mode")

        if self._sqs_client is None:
            import boto3

            self._sqs_client = boto3.client("sqs", region_name=self._target.region)
        return self._sqs_client

    def _get_lambda_client(self) -> Any:
        """Get or create the boto3 Lambda client."""
        if self._offline:
            raise NotImplementedError("Lambda operations not available in offline mode")

        if self._lambda_client is None:
            import boto3

            self._lambda_client = boto3.client("lambda", region_name=self._target.region)
        return self._lambda_client

    def replay(
        self,
        payload: dict[str, Any],
        itk_trace_id: Optional[str] = None,
    ) -> SqsPublishResult | LambdaInvokeResult:
        """Replay an SQS-shaped event to the target.

        In publish_sqs mode: Publishes the payload to the SQS queue
        In invoke_lambda mode: Directly invokes the Lambda with SQS event shape

        Args:
            payload: The event payload (typically contains Records array)
            itk_trace_id: Optional ITK trace ID to inject for correlation

        Returns:
            SqsPublishResult or LambdaInvokeResult depending on mode
        """
        self._validate_target()

        # Inject ITK trace ID if provided
        enriched_payload = self._inject_trace_id(payload, itk_trace_id)

        if self._target.mode == "publish_sqs":
            return self._publish_to_sqs(enriched_payload, itk_trace_id)
        else:
            return self._invoke_lambda(enriched_payload)

    def _inject_trace_id(
        self,
        payload: dict[str, Any],
        itk_trace_id: Optional[str],
    ) -> dict[str, Any]:
        """Inject ITK trace ID into payload for correlation."""
        if not itk_trace_id:
            return payload

        # Deep copy to avoid mutating original
        enriched = json.loads(json.dumps(payload))

        # Try to inject into message attributes (for SQS)
        if "Records" in enriched:
            for record in enriched.get("Records", []):
                if "messageAttributes" not in record:
                    record["messageAttributes"] = {}
                record["messageAttributes"]["itk_trace_id"] = {
                    "DataType": "String",
                    "StringValue": itk_trace_id,
                }

        return enriched

    def _publish_to_sqs(
        self,
        payload: dict[str, Any],
        itk_trace_id: Optional[str],
    ) -> SqsPublishResult:
        """Publish message to SQS queue."""
        if self._offline:
            # Return mock result in offline mode
            return SqsPublishResult(
                message_id=f"offline-{uuid.uuid4()}",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        client = self._get_sqs_client()

        # Extract message body from payload
        # Assume payload is the message body, or extract from Records[0].body
        if "Records" in payload and payload["Records"]:
            message_body = payload["Records"][0].get("body", payload)
        else:
            message_body = payload

        # Build message attributes
        message_attributes: dict[str, Any] = {}
        if itk_trace_id:
            message_attributes["itk_trace_id"] = {
                "DataType": "String",
                "StringValue": itk_trace_id,
            }

        response = client.send_message(
            QueueUrl=self._target.target_arn_or_url,
            MessageBody=json.dumps(message_body),
            MessageAttributes=message_attributes,
        )

        return SqsPublishResult(
            message_id=response["MessageId"],
            sequence_number=response.get("SequenceNumber"),
            md5_of_body=response.get("MD5OfMessageBody"),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _invoke_lambda(self, payload: dict[str, Any]) -> LambdaInvokeResult:
        """Invoke Lambda function directly with SQS event shape."""
        if self._offline:
            # Return mock result in offline mode
            return LambdaInvokeResult(
                request_id=f"offline-{uuid.uuid4()}",
                status_code=200,
                payload={"statusCode": 200, "body": "offline mock response"},
            )

        client = self._get_lambda_client()

        response = client.invoke(
            FunctionName=self._target.target_arn_or_url,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )

        # Parse response payload
        response_payload = {}
        if "Payload" in response:
            payload_bytes = response["Payload"].read()
            if payload_bytes:
                response_payload = json.loads(payload_bytes)

        return LambdaInvokeResult(
            request_id=response["ResponseMetadata"]["RequestId"],
            status_code=response["StatusCode"],
            payload=response_payload,
            function_error=response.get("FunctionError"),
        )


# Backward compatibility alias
def replay_sqs_shaped_event(
    *,
    target: SqsEventTarget,
    payload: dict[str, Any],
    itk_trace_id: Optional[str] = None,
) -> dict[str, Any]:
    """Replay an SQS-shaped event (backward compatibility wrapper).

    Raises NotImplementedError - use SqsEventAdapter instead.
    """
    raise NotImplementedError(
        "replay_sqs_shaped_event is deprecated. "
        "Use SqsEventAdapter(target, offline=False).replay() in Tier 3."
    )
