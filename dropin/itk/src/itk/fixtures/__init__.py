"""Fixture generation for creating test data.

Generates JSONL fixture files from YAML span definitions,
useful for creating test cases without real log data.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from itk.trace.span_model import Span


def generate_span_id() -> str:
    """Generate a unique span ID."""
    return str(uuid.uuid4())[:8]


def generate_timestamp(
    base: Optional[datetime] = None,
    offset_ms: int = 0,
) -> str:
    """Generate an ISO timestamp."""
    if base is None:
        base = datetime.now(timezone.utc)
    ts = base + timedelta(milliseconds=offset_ms)
    return ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def span_from_dict(data: dict[str, Any], defaults: dict[str, Any]) -> Span:
    """Create a Span from a dictionary with defaults."""
    merged = {**defaults, **data}

    # Generate IDs if not provided
    if "span_id" not in merged or merged["span_id"] is None:
        merged["span_id"] = generate_span_id()

    # Required fields
    return Span(
        span_id=merged.get("span_id", generate_span_id()),
        parent_span_id=merged.get("parent_span_id"),
        component=merged.get("component", "lambda:unknown"),
        operation=merged.get("operation", "Invoke"),
        ts_start=merged.get("ts_start"),
        ts_end=merged.get("ts_end"),
        attempt=merged.get("attempt"),
        itk_trace_id=merged.get("itk_trace_id"),
        lambda_request_id=merged.get("lambda_request_id"),
        xray_trace_id=merged.get("xray_trace_id"),
        sqs_message_id=merged.get("sqs_message_id"),
        bedrock_session_id=merged.get("bedrock_session_id"),
        request=merged.get("request"),
        response=merged.get("response"),
        error=merged.get("error"),
    )


def generate_fixture_from_yaml(yaml_content: str) -> list[Span]:
    """Generate spans from YAML definition.

    YAML format:
    ```yaml
    defaults:
      itk_trace_id: "trace-001"

    spans:
      - component: "lambda:entrypoint"
        operation: "Invoke"
        request: { userMessage: "hello" }
        response: { result: "ok" }

      - component: "model:claude"
        operation: "InvokeModel"
        parent_span_id: "{{prev}}"  # references previous span
    ```
    """
    data = yaml.safe_load(yaml_content)

    defaults = data.get("defaults", {})
    span_defs = data.get("spans", [])

    # Generate base timestamp
    base_ts = datetime.now(timezone.utc)
    offset_ms = 0

    spans: list[Span] = []
    prev_span_id: Optional[str] = None

    for i, span_def in enumerate(span_defs):
        # Handle {{prev}} reference
        if span_def.get("parent_span_id") == "{{prev}}" and prev_span_id:
            span_def["parent_span_id"] = prev_span_id

        # Auto-generate timestamps if requested
        if span_def.get("auto_timestamps", defaults.get("auto_timestamps", False)):
            span_def["ts_start"] = generate_timestamp(base_ts, offset_ms)
            offset_ms += 100  # 100ms per span
            span_def["ts_end"] = generate_timestamp(base_ts, offset_ms)

        span = span_from_dict(span_def, defaults)
        spans.append(span)
        prev_span_id = span.span_id

    return spans


def generate_fixture_file(
    yaml_path: Path,
    output_path: Path,
) -> int:
    """Generate a JSONL fixture file from YAML definition.

    Args:
        yaml_path: Path to YAML definition file
        output_path: Path to write JSONL output

    Returns:
        Number of spans generated
    """
    yaml_content = yaml_path.read_text(encoding="utf-8")
    spans = generate_fixture_from_yaml(yaml_content)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        for span in spans:
            f.write(json.dumps(asdict(span), ensure_ascii=False) + "\n")

    return len(spans)


# Common span templates for quick fixture generation
TEMPLATES = {
    "lambda_invoke": {
        "component": "lambda:{{name}}",
        "operation": "InvokeLambda",
    },
    "bedrock_agent": {
        "component": "agent:{{name}}",
        "operation": "InvokeAgent",
    },
    "bedrock_model": {
        "component": "model:{{name}}",
        "operation": "InvokeModel",
    },
    "sqs_receive": {
        "component": "sqs:{{name}}",
        "operation": "ReceiveMessage",
    },
}


def expand_template(template_name: str, **kwargs: Any) -> dict[str, Any]:
    """Expand a span template with variables."""
    if template_name not in TEMPLATES:
        raise ValueError(f"Unknown template: {template_name}")

    template = TEMPLATES[template_name].copy()

    # Replace {{var}} placeholders
    for key, value in template.items():
        if isinstance(value, str):
            for var_name, var_value in kwargs.items():
                value = value.replace(f"{{{{{var_name}}}}}", str(var_value))
            template[key] = value

    return template
