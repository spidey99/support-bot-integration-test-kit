"""Tests for fixture generation."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from itk.fixtures import (
    generate_span_id,
    generate_timestamp,
    span_from_dict,
    generate_fixture_from_yaml,
    generate_fixture_file,
    expand_template,
    TEMPLATES,
)
from itk.trace.span_model import Span


class TestGenerateSpanId:
    """Tests for span ID generation."""

    def test_generates_unique_ids(self) -> None:
        ids = {generate_span_id() for _ in range(100)}
        assert len(ids) == 100  # All unique

    def test_id_format(self) -> None:
        span_id = generate_span_id()
        assert len(span_id) == 8
        assert all(c in "0123456789abcdef-" for c in span_id)


class TestGenerateTimestamp:
    """Tests for timestamp generation."""

    def test_generates_iso_format(self) -> None:
        ts = generate_timestamp()
        assert ts.endswith("Z")
        assert "T" in ts

    def test_offset_increases_time(self) -> None:
        ts1 = generate_timestamp(offset_ms=0)
        ts2 = generate_timestamp(offset_ms=1000)
        assert ts1 < ts2


class TestSpanFromDict:
    """Tests for span_from_dict function."""

    def test_creates_span_with_defaults(self) -> None:
        defaults = {"component": "lambda:default", "operation": "Invoke"}
        span = span_from_dict({}, defaults)
        assert span.component == "lambda:default"
        assert span.operation == "Invoke"
        assert span.span_id is not None

    def test_data_overrides_defaults(self) -> None:
        defaults = {"component": "lambda:default"}
        data = {"component": "lambda:override"}
        span = span_from_dict(data, defaults)
        assert span.component == "lambda:override"

    def test_preserves_optional_fields(self) -> None:
        data = {
            "component": "lambda:test",
            "operation": "Invoke",
            "request": {"key": "value"},
            "error": {"message": "boom"},
        }
        span = span_from_dict(data, {})
        assert span.request == {"key": "value"}
        assert span.error == {"message": "boom"}


class TestGenerateFixtureFromYaml:
    """Tests for YAML fixture generation."""

    def test_simple_fixture(self) -> None:
        yaml_content = """
spans:
  - component: "lambda:test"
    operation: "Invoke"
"""
        spans = generate_fixture_from_yaml(yaml_content)
        assert len(spans) == 1
        assert spans[0].component == "lambda:test"

    def test_defaults_applied(self) -> None:
        yaml_content = """
defaults:
  itk_trace_id: "trace-001"

spans:
  - component: "lambda:test"
    operation: "Invoke"
"""
        spans = generate_fixture_from_yaml(yaml_content)
        assert spans[0].itk_trace_id == "trace-001"

    def test_prev_reference(self) -> None:
        yaml_content = """
spans:
  - component: "lambda:parent"
    operation: "Invoke"
  - component: "lambda:child"
    operation: "Invoke"
    parent_span_id: "{{prev}}"
"""
        spans = generate_fixture_from_yaml(yaml_content)
        assert len(spans) == 2
        assert spans[1].parent_span_id == spans[0].span_id

    def test_auto_timestamps(self) -> None:
        yaml_content = """
defaults:
  auto_timestamps: true

spans:
  - component: "lambda:test"
    operation: "Invoke"
"""
        spans = generate_fixture_from_yaml(yaml_content)
        assert spans[0].ts_start is not None
        assert spans[0].ts_end is not None
        assert spans[0].ts_start < spans[0].ts_end

    def test_multiple_spans(self) -> None:
        yaml_content = """
spans:
  - component: "lambda:a"
    operation: "Invoke"
  - component: "lambda:b"
    operation: "Invoke"
  - component: "lambda:c"
    operation: "Invoke"
"""
        spans = generate_fixture_from_yaml(yaml_content)
        assert len(spans) == 3


class TestGenerateFixtureFile:
    """Tests for file-based fixture generation."""

    def test_generates_jsonl_file(self) -> None:
        yaml_content = """
spans:
  - component: "lambda:test"
    operation: "Invoke"
    request:
      message: "hello"
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = Path(tmpdir) / "definition.yaml"
            output_path = Path(tmpdir) / "fixture.jsonl"

            yaml_path.write_text(yaml_content)
            count = generate_fixture_file(yaml_path, output_path)

            assert count == 1
            assert output_path.exists()

            # Verify JSONL content
            content = output_path.read_text()
            data = json.loads(content.strip())
            assert data["component"] == "lambda:test"
            assert data["request"]["message"] == "hello"


class TestExpandTemplate:
    """Tests for template expansion."""

    def test_lambda_template(self) -> None:
        result = expand_template("lambda_invoke", name="my-function")
        assert result["component"] == "lambda:my-function"
        assert result["operation"] == "InvokeLambda"

    def test_bedrock_agent_template(self) -> None:
        result = expand_template("bedrock_agent", name="supervisor")
        assert result["component"] == "agent:supervisor"

    def test_unknown_template_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown template"):
            expand_template("nonexistent")


class TestTemplates:
    """Tests for built-in templates."""

    def test_all_templates_have_required_fields(self) -> None:
        for name, template in TEMPLATES.items():
            assert "component" in template, f"Template {name} missing component"
            assert "operation" in template, f"Template {name} missing operation"
