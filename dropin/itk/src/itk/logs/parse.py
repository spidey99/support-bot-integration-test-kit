from __future__ import annotations

import json
from pathlib import Path

from itk.trace.span_model import Span


def load_fixture_jsonl_as_spans(path: Path) -> list[Span]:
    """Load JSONL fixture lines that already resemble the Span model.

    This is intentionally simple so Tier 2 can build deterministic tests.
    Tier 3 will add CloudWatch parsing and heuristics.
    """
    spans: list[Span] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        spans.append(
            Span(
                span_id=obj["span_id"],
                parent_span_id=obj.get("parent_span_id"),
                component=obj["component"],
                operation=obj["operation"],
                ts_start=obj.get("ts_start"),
                ts_end=obj.get("ts_end"),
                attempt=obj.get("attempt"),
                itk_trace_id=obj.get("itk_trace_id"),
                lambda_request_id=obj.get("lambda_request_id"),
                xray_trace_id=obj.get("xray_trace_id"),
                sqs_message_id=obj.get("sqs_message_id"),
                bedrock_session_id=obj.get("bedrock_session_id"),
                request=obj.get("request"),
                response=obj.get("response"),
                error=obj.get("error"),
            )
        )
    return spans
