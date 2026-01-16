"""Tests for span model and schema validation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from itk.trace.span_model import Span


class TestSpanModel:
    """Tests for the Span dataclass."""

    def test_span_minimal_fields(self) -> None:
        """Verify Span can be created with minimal required fields."""
        span = Span(
            span_id="test-001",
            parent_span_id=None,
            component="test:component",
            operation="TestOp",
        )

        assert span.span_id == "test-001"
        assert span.component == "test:component"
        assert span.operation == "TestOp"
        assert span.request is None
        assert span.response is None

    def test_span_with_all_fields(self) -> None:
        """Verify Span can be created with all fields."""
        span = Span(
            span_id="test-002",
            parent_span_id="test-001",
            component="lambda:my-func",
            operation="InvokeLambda",
            ts_start="2026-01-15T12:00:00.000Z",
            ts_end="2026-01-15T12:00:01.000Z",
            attempt=1,
            itk_trace_id="itk-123",
            lambda_request_id="req-456",
            xray_trace_id="xray-789",
            sqs_message_id="sqs-abc",
            bedrock_session_id="br-def",
            request={"input": "hello"},
            response={"output": "world"},
            error=None,
        )

        assert span.parent_span_id == "test-001"
        assert span.ts_start == "2026-01-15T12:00:00.000Z"
        assert span.request == {"input": "hello"}
        assert span.response == {"output": "world"}


class TestSpanSchemaValidation:
    """Tests for span schema validation."""

    def test_spans_jsonl_validates_against_schema(
        self, fixtures_dir: Path, schemas_dir: Path
    ) -> None:
        """Verify sample fixture spans validate against the schema."""
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            pytest.skip("jsonschema not installed")

        schema_path = schemas_dir / "itk.span.schema.json"
        schema = json.loads(schema_path.read_text())
        validator = Draft202012Validator(schema)

        fixture_path = fixtures_dir / "logs" / "sample_run_001.jsonl"
        for line in fixture_path.read_text().strip().split("\n"):
            obj = json.loads(line)
            errors = list(validator.iter_errors(obj))
            assert not errors, f"Schema validation failed: {errors}"
