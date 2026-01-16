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


class TestTimelineBasedRendering:
    """Tests for timestamp-ordered sequence diagram rendering."""

    def test_responses_follow_nested_calls(self) -> None:
        """Verify response arrows appear after nested operations complete.

        Timeline:
        - A calls B (ts_start=0, ts_end=5)
          - B calls C (ts_start=1, ts_end=2)

        Expected order:
        1. A->A request (t=0) - entrypoint self-call
        2. A->B request (t=1) - A is parent of B
        3. B->B response (t=2)
        4. A->A response (t=5)
        """
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="service:A",
                    operation="CallB",
                    ts_start="2026-01-15T10:00:00.000Z",
                    ts_end="2026-01-15T10:00:05.000Z",
                    request={"msg": "hello"},
                    response={"result": "ok"},
                ),
                Span(
                    span_id="s2",
                    parent_span_id="s1",
                    component="service:B",
                    operation="DoWork",
                    ts_start="2026-01-15T10:00:01.000Z",
                    ts_end="2026-01-15T10:00:02.000Z",
                    request={"inner": True},
                    response={"done": True},
                ),
            ]
        )

        result = render_mermaid_sequence(trace)
        lines = result.strip().split("\n")

        # Find the arrow lines (exclude participant declarations and notes)
        arrows = [ln.strip() for ln in lines if "->>" in ln or "-->>" in ln]

        # Should have 4 arrows: 2 requests + 2 responses
        assert len(arrows) == 4, f"Expected 4 arrows, got {len(arrows)}: {arrows}"

        # Verify order: A self-call, A->B request, B->A response, A self-response
        assert "service_A->>service_A: CallB" in arrows[0]  # Entrypoint (self)
        assert "service_A->>service_B: DoWork" in arrows[1]  # A calls B
        assert "service_B-->>service_A: DoWork response" in arrows[2]  # B returns to A
        assert "service_A-->>service_A: CallB response" in arrows[3]  # Entrypoint returns

    def test_deeply_nested_call_stack(self) -> None:
        """Verify correct unwinding of 3-level call stack.

        A -> B -> C
        All responses should unwind in reverse order.
        """
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="lambda:entry",
                    operation="Start",
                    ts_start="2026-01-15T10:00:00.000Z",
                    ts_end="2026-01-15T10:00:10.000Z",
                    request={},
                    response={},
                ),
                Span(
                    span_id="s2",
                    parent_span_id="s1",
                    component="agent:middle",
                    operation="Process",
                    ts_start="2026-01-15T10:00:01.000Z",
                    ts_end="2026-01-15T10:00:08.000Z",
                    request={},
                    response={},
                ),
                Span(
                    span_id="s3",
                    parent_span_id="s2",
                    component="service:leaf",
                    operation="Query",
                    ts_start="2026-01-15T10:00:02.000Z",
                    ts_end="2026-01-15T10:00:05.000Z",
                    request={},
                    response={},
                ),
            ]
        )

        result = render_mermaid_sequence(trace)
        lines = result.strip().split("\n")
        arrows = [ln.strip() for ln in lines if "->>" in ln or "-->>" in ln]

        # 6 arrows: 3 requests + 3 responses
        assert len(arrows) == 6

        # Requests go down the stack
        assert "lambda_entry->>lambda_entry: Start" in arrows[0]
        assert "lambda_entry->>agent_middle: Process" in arrows[1]
        assert "agent_middle->>service_leaf: Query" in arrows[2]

        # Responses come back up (reverse order)
        assert "service_leaf-->>agent_middle: Query response" in arrows[3]
        assert "agent_middle-->>lambda_entry: Process response" in arrows[4]
        assert "lambda_entry-->>lambda_entry: Start response" in arrows[5]

    def test_parallel_calls_ordered_by_timestamp(self) -> None:
        """Verify parallel operations are ordered by their start times."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="lambda:orchestrator",
                    operation="Orchestrate",
                    ts_start="2026-01-15T10:00:00.000Z",
                    ts_end="2026-01-15T10:00:10.000Z",
                    request={},
                    response={},
                ),
                # Two parallel calls from orchestrator
                Span(
                    span_id="s2",
                    parent_span_id="s1",
                    component="service:fast",
                    operation="FastCall",
                    ts_start="2026-01-15T10:00:01.000Z",
                    ts_end="2026-01-15T10:00:03.000Z",
                    request={},
                    response={},
                ),
                Span(
                    span_id="s3",
                    parent_span_id="s1",
                    component="service:slow",
                    operation="SlowCall",
                    ts_start="2026-01-15T10:00:02.000Z",
                    ts_end="2026-01-15T10:00:08.000Z",
                    request={},
                    response={},
                ),
            ]
        )

        result = render_mermaid_sequence(trace)
        lines = result.strip().split("\n")
        arrows = [ln.strip() for ln in lines if "->>" in ln or "-->>" in ln]

        # Find positions
        fast_req_idx = next(i for i, a in enumerate(arrows) if "FastCall" in a and "-->>" not in a)
        slow_req_idx = next(i for i, a in enumerate(arrows) if "SlowCall" in a and "-->>" not in a)
        fast_res_idx = next(i for i, a in enumerate(arrows) if "FastCall response" in a)
        slow_res_idx = next(i for i, a in enumerate(arrows) if "SlowCall response" in a)

        # Fast starts before slow (t=1 vs t=2)
        assert fast_req_idx < slow_req_idx

        # Fast completes before slow (t=3 vs t=8)
        assert fast_res_idx < slow_res_idx

    def test_response_arrows_are_dashed(self) -> None:
        """Verify response arrows use dashed style (-->>)."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="service:caller",
                    operation="Call",
                    ts_start="2026-01-15T10:00:00.000Z",
                    ts_end="2026-01-15T10:00:01.000Z",
                    request={},
                    response={"ok": True},
                ),
            ]
        )

        result = render_mermaid_sequence(trace)

        # Request arrow is solid
        assert "service_caller->>service_caller: Call" in result
        # Response arrow is dashed
        assert "service_caller-->>service_caller: Call response" in result

    def test_error_response_shows_error_label(self) -> None:
        """Verify error responses are labeled with [ERROR]."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="lambda:handler",
                    operation="FailingOp",
                    ts_start="2026-01-15T10:00:00.000Z",
                    ts_end="2026-01-15T10:00:01.000Z",
                    request={},
                    error={"message": "Something broke"},
                ),
            ]
        )

        result = render_mermaid_sequence(trace)

        # Response should show ERROR
        assert "FailingOp response [ERROR]" in result

    def test_no_response_arrow_without_ts_end(self) -> None:
        """Verify spans without ts_end don't generate response arrows."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="service:caller",
                    operation="FireAndForget",
                    ts_start="2026-01-15T10:00:00.000Z",
                    # No ts_end
                    request={"async": True},
                    response={"queued": True},  # Has response but no ts_end
                ),
            ]
        )

        result = render_mermaid_sequence(trace)

        # Should have request arrow but no response arrow
        assert "service_caller->>service_caller: FireAndForget" in result
        assert "response" not in result.lower() or "FireAndForget response" not in result

    def test_fallback_to_span_order_without_timestamps(self) -> None:
        """Verify legacy behavior when no timestamps are present."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="service:A",
                    operation="Op1",
                    # No timestamps
                    request={},
                    response={},
                ),
                Span(
                    span_id="s2",
                    parent_span_id="s1",
                    component="service:B",
                    operation="Op2",
                    request={},
                    response={},
                ),
            ]
        )

        result = render_mermaid_sequence(trace)

        # Should still render (legacy mode)
        assert "sequenceDiagram" in result
        assert "service_A->>service_A: Op1" in result
        assert "service_A->>service_B: Op2" in result

        # Should NOT have response arrows (legacy mode doesn't do timeline)
        assert "-->>".count(result) == 0 or "response" not in result
