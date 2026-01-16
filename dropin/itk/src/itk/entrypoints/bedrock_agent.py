"""Bedrock Agent invocation adapter.

This module provides utilities for invoking Bedrock Agents with trace enabled.
Used for testing agent-based workflows and capturing trace data for analysis.

Tier 2 (offline): Validates configuration and provides mock responses
Tier 3 (online): Actually invokes Bedrock Agents
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

# Note: boto3 import is deferred to runtime to avoid issues in offline mode


@dataclass(frozen=True)
class BedrockAgentTarget:
    """Configuration for a Bedrock Agent target."""

    agent_id: str
    agent_alias_id: str
    region: Optional[str] = None


@dataclass
class BedrockAgentResponse:
    """Response from a Bedrock Agent invocation."""

    session_id: str
    completion: str
    traces: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""


class BedrockAgentAdapter:
    """Adapter for Bedrock Agent invocations with trace support.

    Invokes agents with enableTrace=True to capture orchestration traces
    for ITK analysis and sequence diagram generation.
    """

    def __init__(
        self,
        target: BedrockAgentTarget,
        offline: bool = False,
    ):
        """Initialize the Bedrock Agent adapter.

        Args:
            target: Target configuration
            offline: If True, operations return mock responses
        """
        self._target = target
        self._offline = offline
        self._client: Any = None

    def _validate_target(self) -> None:
        """Validate the target configuration."""
        if not self._target.agent_id:
            raise ValueError("agent_id is required")

        if not self._target.agent_alias_id:
            raise ValueError("agent_alias_id is required")

        if self._target.agent_id == "REPLACE_ME" or self._target.agent_alias_id == "REPLACE_ME":
            raise ValueError(
                "agent_id or agent_alias_id has placeholder value 'REPLACE_ME'. "
                "Configure the actual values in the case YAML."
            )

    def _get_client(self) -> Any:
        """Get or create the boto3 bedrock-agent-runtime client."""
        if self._offline:
            raise NotImplementedError("Bedrock operations not available in offline mode")

        if self._client is None:
            import boto3

            self._client = boto3.client(
                "bedrock-agent-runtime",
                region_name=self._target.region,
            )
        return self._client

    def invoke(
        self,
        input_text: str,
        session_id: Optional[str] = None,
        session_attributes: Optional[dict[str, str]] = None,
        prompt_session_attributes: Optional[dict[str, str]] = None,
        enable_trace: bool = True,
    ) -> BedrockAgentResponse:
        """Invoke the Bedrock Agent.

        Args:
            input_text: The user input to send to the agent
            session_id: Optional session ID (generated if not provided)
            session_attributes: Optional session state attributes
            prompt_session_attributes: Optional prompt-level attributes
            enable_trace: Whether to capture trace data (default True)

        Returns:
            BedrockAgentResponse with completion and traces
        """
        self._validate_target()

        # Generate session ID if not provided
        if session_id is None:
            session_id = str(uuid.uuid4())

        if self._offline:
            # Return mock result in offline mode
            return BedrockAgentResponse(
                session_id=session_id,
                completion="offline mock response",
                traces=[
                    {
                        "orchestrationTrace": {
                            "rationale": {"text": "Mock rationale for offline testing"}
                        }
                    }
                ],
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        client = self._get_client()

        # Build session state if attributes provided
        session_state: dict[str, Any] = {}
        if session_attributes:
            session_state["sessionAttributes"] = session_attributes
        if prompt_session_attributes:
            session_state["promptSessionAttributes"] = prompt_session_attributes

        # Invoke the agent
        invoke_params: dict[str, Any] = {
            "agentId": self._target.agent_id,
            "agentAliasId": self._target.agent_alias_id,
            "sessionId": session_id,
            "inputText": input_text,
            "enableTrace": enable_trace,
        }

        if session_state:
            invoke_params["sessionState"] = session_state

        response = client.invoke_agent(**invoke_params)

        # Process the streaming response
        completion_parts: list[str] = []
        traces: list[dict[str, Any]] = []
        citations: list[dict[str, Any]] = []

        for event in response.get("completion", []):
            # Handle different event types in the stream
            if "chunk" in event:
                chunk = event["chunk"]
                if "bytes" in chunk:
                    completion_parts.append(chunk["bytes"].decode("utf-8"))
                if "attribution" in chunk:
                    citations.extend(chunk["attribution"].get("citations", []))

            if "trace" in event:
                traces.append(event["trace"])

        return BedrockAgentResponse(
            session_id=session_id,
            completion="".join(completion_parts),
            traces=traces,
            citations=citations,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def invoke_with_retries(
        self,
        input_text: str,
        session_id: Optional[str] = None,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> tuple[BedrockAgentResponse, int]:
        """Invoke the agent with automatic retries on failure.

        Args:
            input_text: The user input
            session_id: Optional session ID
            max_retries: Maximum number of retry attempts
            **kwargs: Additional arguments for invoke()

        Returns:
            Tuple of (response, attempt_count)
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, max_retries + 1):
            try:
                response = self.invoke(
                    input_text=input_text,
                    session_id=session_id,
                    **kwargs,
                )
                return response, attempt
            except Exception as e:
                last_error = e
                # Could add exponential backoff here
                continue

        if last_error:
            raise last_error
        raise RuntimeError("Unexpected error in invoke_with_retries")


# Backward compatibility alias
def invoke_agent_with_trace(
    *,
    target: BedrockAgentTarget,
    input_text: str,
    session_attrs: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Invoke a Bedrock Agent with trace (backward compatibility wrapper).

    Raises NotImplementedError - use BedrockAgentAdapter instead.
    """
    raise NotImplementedError(
        "invoke_agent_with_trace is deprecated. "
        "Use BedrockAgentAdapter(target, offline=False).invoke() in Tier 3."
    )
