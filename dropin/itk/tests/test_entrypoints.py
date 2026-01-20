"""Tests for entrypoint adapters and dispatch logic.

These tests validate:
- Entrypoint type dispatch in _run_live_mode
- Adapter initialization and validation
- Offline mode mock responses
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestEntrypointDispatch:
    """Test that _run_live_mode correctly dispatches to entrypoint handlers."""

    @pytest.fixture
    def mock_case(self) -> MagicMock:
        """Create a mock case object."""
        case = MagicMock()
        case.entrypoint = MagicMock()
        case.entrypoint.target = {}
        case.entrypoint.payload = {}
        return case

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create a mock config object."""
        config = MagicMock()
        config.targets = MagicMock()
        config.targets.log_groups = []
        return config

    def test_dispatch_bedrock_invoke_agent(self, mock_case: MagicMock, mock_config: MagicMock) -> None:
        """Verify bedrock_invoke_agent dispatches to _run_bedrock_agent."""
        from itk.cli import _run_live_mode
        
        mock_case.entrypoint.type = "bedrock_invoke_agent"
        
        with patch("itk.cli._run_bedrock_agent") as mock_handler:
            mock_handler.return_value = (MagicMock(), {})
            
            # Create a case file path for the function call
            from itk.cli import load_case
            with patch("itk.cli.load_case", return_value=mock_case):
                _run_live_mode(Path("test.yaml"), mock_config)
            
            mock_handler.assert_called_once_with(mock_case, mock_config)

    def test_dispatch_lambda_invoke(self, mock_case: MagicMock, mock_config: MagicMock) -> None:
        """Verify lambda_invoke dispatches to _run_lambda_invoke."""
        from itk.cli import _run_live_mode
        
        mock_case.entrypoint.type = "lambda_invoke"
        
        with patch("itk.cli._run_lambda_invoke") as mock_handler:
            mock_handler.return_value = (MagicMock(), {})
            
            with patch("itk.cli.load_case", return_value=mock_case):
                _run_live_mode(Path("test.yaml"), mock_config)
            
            mock_handler.assert_called_once_with(mock_case, mock_config)

    def test_dispatch_sqs_event(self, mock_case: MagicMock, mock_config: MagicMock) -> None:
        """Verify sqs_event dispatches to _run_sqs_event."""
        from itk.cli import _run_live_mode
        
        mock_case.entrypoint.type = "sqs_event"
        
        with patch("itk.cli._run_sqs_event") as mock_handler:
            mock_handler.return_value = (MagicMock(), {})
            
            with patch("itk.cli.load_case", return_value=mock_case):
                _run_live_mode(Path("test.yaml"), mock_config)
            
            mock_handler.assert_called_once_with(mock_case, mock_config)

    def test_dispatch_http_not_implemented(self, mock_case: MagicMock, mock_config: MagicMock) -> None:
        """Verify http entrypoint raises NotImplementedError."""
        from itk.cli import _run_live_mode
        
        mock_case.entrypoint.type = "http"
        
        with patch("itk.cli.load_case", return_value=mock_case):
            with pytest.raises(NotImplementedError, match="http"):
                _run_live_mode(Path("test.yaml"), mock_config)

    def test_dispatch_unknown_type_raises(self, mock_case: MagicMock, mock_config: MagicMock) -> None:
        """Verify unknown entrypoint type raises ValueError."""
        from itk.cli import _run_live_mode
        
        mock_case.entrypoint.type = "unknown_type"
        
        with patch("itk.cli.load_case", return_value=mock_case):
            with pytest.raises(ValueError, match="Unknown entrypoint type"):
                _run_live_mode(Path("test.yaml"), mock_config)


class TestSqsEventAdapter:
    """Test the SQS event adapter."""

    def test_validate_target_mode(self) -> None:
        """Test that invalid mode raises ValueError."""
        from itk.entrypoints.sqs_event import SqsEventAdapter, SqsEventTarget
        
        target = SqsEventTarget(
            mode="invalid_mode",
            target_arn_or_url="arn:aws:sqs:us-east-1:123456789:queue",
        )
        adapter = SqsEventAdapter(target, offline=True)
        
        with pytest.raises(ValueError, match="Invalid mode"):
            adapter._validate_target()

    def test_validate_target_missing_arn(self) -> None:
        """Test that missing ARN raises ValueError."""
        from itk.entrypoints.sqs_event import SqsEventAdapter, SqsEventTarget
        
        target = SqsEventTarget(
            mode="publish_sqs",
            target_arn_or_url="",
        )
        adapter = SqsEventAdapter(target, offline=True)
        
        with pytest.raises(ValueError, match="target_arn_or_url is required"):
            adapter._validate_target()

    def test_validate_target_placeholder(self) -> None:
        """Test that REPLACE_ME placeholder raises ValueError."""
        from itk.entrypoints.sqs_event import SqsEventAdapter, SqsEventTarget
        
        target = SqsEventTarget(
            mode="publish_sqs",
            target_arn_or_url="REPLACE_ME",
        )
        adapter = SqsEventAdapter(target, offline=True)
        
        with pytest.raises(ValueError, match="placeholder value"):
            adapter._validate_target()

    def test_valid_target_passes(self) -> None:
        """Test that valid target passes validation."""
        from itk.entrypoints.sqs_event import SqsEventAdapter, SqsEventTarget
        
        target = SqsEventTarget(
            mode="invoke_lambda",
            target_arn_or_url="arn:aws:lambda:us-east-1:123456789:function:MyFunction",
        )
        adapter = SqsEventAdapter(target, offline=True)
        
        # Should not raise
        adapter._validate_target()


class TestLambdaDirectAdapter:
    """Test the Lambda direct adapter."""

    def test_validate_target_missing_function(self) -> None:
        """Test that missing function ARN raises ValueError."""
        from itk.entrypoints.lambda_direct import LambdaDirectAdapter, LambdaTarget
        
        target = LambdaTarget(function_name_or_arn="")
        adapter = LambdaDirectAdapter(target, offline=True)
        
        with pytest.raises(ValueError, match="function_name_or_arn is required"):
            adapter._validate_target()

    def test_validate_target_placeholder(self) -> None:
        """Test that REPLACE_ME placeholder raises ValueError."""
        from itk.entrypoints.lambda_direct import LambdaDirectAdapter, LambdaTarget
        
        target = LambdaTarget(function_name_or_arn="REPLACE_ME")
        adapter = LambdaDirectAdapter(target, offline=True)
        
        with pytest.raises(ValueError, match="placeholder value"):
            adapter._validate_target()

    def test_offline_invoke_returns_mock(self) -> None:
        """Test that offline mode returns mock response."""
        from itk.entrypoints.lambda_direct import LambdaDirectAdapter, LambdaTarget
        
        target = LambdaTarget(
            function_name_or_arn="arn:aws:lambda:us-east-1:123456789:function:MyFunction"
        )
        adapter = LambdaDirectAdapter(target, offline=True)
        
        response = adapter.invoke(payload={"test": "data"})
        
        assert response.status_code == 200
        assert "offline" in response.request_id
        assert "offline mock response" in str(response.payload)


class TestBedrockAgentAdapter:
    """Test the Bedrock Agent adapter."""

    def test_validate_target_missing_agent_id(self) -> None:
        """Test that missing agent ID raises ValueError."""
        from itk.entrypoints.bedrock_agent import BedrockAgentAdapter, BedrockAgentTarget
        
        target = BedrockAgentTarget(agent_id="")
        adapter = BedrockAgentAdapter(target, offline=True)
        
        with pytest.raises(ValueError, match="agent_id is required"):
            adapter._validate_target()

    def test_validate_target_placeholder(self) -> None:
        """Test that REPLACE_ME placeholder raises ValueError."""
        from itk.entrypoints.bedrock_agent import BedrockAgentAdapter, BedrockAgentTarget
        
        target = BedrockAgentTarget(agent_id="REPLACE_ME", agent_alias_id="TESTALIAS")
        adapter = BedrockAgentAdapter(target, offline=True)
        
        with pytest.raises(ValueError, match="placeholder value"):
            adapter._validate_target()

    def test_offline_invoke_returns_mock(self) -> None:
        """Test that offline mode returns mock response."""
        from itk.entrypoints.bedrock_agent import BedrockAgentAdapter, BedrockAgentTarget
        
        target = BedrockAgentTarget(
            agent_id="ABCDEF1234",
            agent_alias_id="TESTALIAS",
        )
        adapter = BedrockAgentAdapter(target, offline=True)
        
        response = adapter.invoke(input_text="Hello")
        
        assert response.completion  # Has a response
        assert response.session_id  # Has session ID
        assert isinstance(response.traces, list)
