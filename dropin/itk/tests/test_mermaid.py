"""Tests for Mermaid sequence diagram rendering."""
from __future__ import annotations

from itk.diagrams.mermaid_seq import render_mermaid_sequence
from itk.trace.span_model import Span
from itk.trace.trace_model import Trace


class TestMermaidSequence:
    """Tests for Mermaid diagram generation."""

    def test_basic_diagram_structure(self) -> None:
        """Verify basic diagram has correct structure."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="entrypoint:sqs",
                    operation="Start",
                )
            ]
        )

        result = render_mermaid_sequence(trace)

        assert result.startswith("sequenceDiagram")
        assert "participant entrypoint_sqs as entrypoint:sqs" in result

    def test_multiple_participants(self) -> None:
        """Verify multiple components become participants."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="entrypoint:sqs",
                    operation="Start",
                ),
                Span(
                    span_id="s2",
                    parent_span_id="s1",
                    component="lambda:handler",
                    operation="Process",
                ),
                Span(
                    span_id="s3",
                    parent_span_id="s2",
                    component="agent:supervisor",
                    operation="Invoke",
                ),
            ]
        )

        result = render_mermaid_sequence(trace)

        assert "participant entrypoint_sqs as entrypoint:sqs" in result
        assert "participant lambda_handler as lambda:handler" in result
        assert "participant agent_supervisor as agent:supervisor" in result

    def test_arrows_between_components(self) -> None:
        """Verify arrows are drawn from parent to child component."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="entrypoint:sqs",
                    operation="Start",
                ),
                Span(
                    span_id="s2",
                    parent_span_id="s1",
                    component="lambda:handler",
                    operation="Process",
                ),
            ]
        )

        result = render_mermaid_sequence(trace)

        # Arrow from entrypoint to lambda
        assert "entrypoint_sqs->>lambda_handler: Process" in result

    def test_payload_notes(self) -> None:
        """Verify notes are added for request/response payloads."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="lambda:handler",
                    operation="Invoke",
                    request={"input": "test"},
                    response={"output": "result"},
                )
            ]
        )

        result = render_mermaid_sequence(trace)

        assert "Note over" in result
        assert "req=payloads/s1.request.json" in result
        assert "res=payloads/s1.response.json" in result

    def test_retry_loop_block(self) -> None:
        """Verify loop block is created for retry attempts."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="lambda:handler",
                    operation="CallAPI",
                    attempt=1,
                ),
                Span(
                    span_id="s2",
                    parent_span_id=None,
                    component="lambda:handler",
                    operation="CallAPI",
                    attempt=2,
                ),
            ]
        )

        result = render_mermaid_sequence(trace)

        assert "loop Retries" in result
        assert "end" in result
        assert "[attempt 1]" in result
        assert "[attempt 2]" in result

    def test_error_note(self) -> None:
        """Verify ERROR note is added for error spans."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="lambda:handler",
                    operation="FailOp",
                    error={"message": "Something went wrong"},
                )
            ]
        )

        result = render_mermaid_sequence(trace)

        assert "ERROR" in result

    def test_correlation_id_notes(self) -> None:
        """Verify correlation IDs are included in notes."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="lambda:handler",
                    operation="Op",
                    lambda_request_id="12345678-abcd",
                    bedrock_session_id="sess-abcdef12",
                )
            ]
        )

        result = render_mermaid_sequence(trace)

        assert "λ:12345678" in result  # Lambda prefix + truncated ID
        assert "br:sess-abc" in result  # Bedrock prefix + truncated ID

    def test_component_name_escaping(self) -> None:
        """Verify special characters in component names are escaped."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="lambda:my-func.handler/v2",
                    operation="Op",
                )
            ]
        )

        result = render_mermaid_sequence(trace)

        # Should have safe participant ID
        assert "lambda_my_func_handler_v2" in result
        # Should have original name as label
        assert "lambda:my-func.handler/v2" in result
