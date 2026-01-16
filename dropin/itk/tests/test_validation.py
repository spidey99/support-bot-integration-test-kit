"""Tests for schema validation module."""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from itk.validation import (
    ValidationResult,
    ValidationError,
    validate_case,
    validate_fixture,
    validate_span_dict,
    validate_case_dict,
)


# ============================================================================
# Test ValidationResult dataclass
# ============================================================================


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result_summary(self) -> None:
        result = ValidationResult(valid=True, file_path="test.yaml")
        assert result.summary() == "✓ test.yaml: Valid"

    def test_invalid_result_summary_single_error(self) -> None:
        result = ValidationResult(
            valid=False,
            file_path="test.yaml",
            errors=[ValidationError(path="$.id", message="'id' is a required property")],
        )
        summary = result.summary()
        assert "✗ test.yaml: 1 error(s)" in summary
        assert "$.id - 'id' is a required property" in summary

    def test_invalid_result_summary_with_line_number(self) -> None:
        result = ValidationResult(
            valid=False,
            file_path="test.jsonl",
            errors=[
                ValidationError(
                    path="$.span_id",
                    message="'span_id' is a required property",
                    line_number=3,
                )
            ],
        )
        summary = result.summary()
        assert "Line 3:" in summary


# ============================================================================
# Test validate_case
# ============================================================================


class TestValidateCase:
    """Tests for validate_case function."""

    def test_valid_case(self, tmp_path: Path) -> None:
        case_file = tmp_path / "valid.yaml"
        case_file.write_text(
            """
id: test-001
name: Test Case
entrypoint:
  type: sqs_event
  target:
    queue_url: https://sqs.example.com
  payload:
    body: test
""",
            encoding="utf-8",
        )

        result = validate_case(case_file)
        assert result.valid
        assert len(result.errors) == 0

    def test_missing_required_field(self, tmp_path: Path) -> None:
        case_file = tmp_path / "invalid.yaml"
        case_file.write_text(
            """
id: test-001
# missing 'name' and 'entrypoint'
""",
            encoding="utf-8",
        )

        result = validate_case(case_file)
        assert not result.valid
        # Should have errors for missing required fields
        messages = [e.message for e in result.errors]
        assert any("name" in m and "required" in m for m in messages)
        assert any("entrypoint" in m and "required" in m for m in messages)

    def test_invalid_entrypoint_type(self, tmp_path: Path) -> None:
        case_file = tmp_path / "bad_type.yaml"
        case_file.write_text(
            """
id: test-001
name: Bad Type
entrypoint:
  type: invalid_type
  target: {}
  payload: {}
""",
            encoding="utf-8",
        )

        result = validate_case(case_file)
        assert not result.valid
        messages = [e.message for e in result.errors]
        assert any("invalid_type" in m or "enum" in m for m in messages)

    def test_file_not_found(self, tmp_path: Path) -> None:
        result = validate_case(tmp_path / "nonexistent.yaml")
        assert not result.valid
        assert any("not found" in e.message for e in result.errors)

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        case_file = tmp_path / "broken.yaml"
        case_file.write_text("key: [unclosed bracket", encoding="utf-8")

        result = validate_case(case_file)
        assert not result.valid
        assert any("YAML" in e.message for e in result.errors)


# ============================================================================
# Test validate_fixture
# ============================================================================


class TestValidateFixture:
    """Tests for validate_fixture function."""

    def test_valid_fixture(self, tmp_path: Path) -> None:
        fixture_file = tmp_path / "valid.jsonl"
        spans = [
            {
                "span_id": "span-001",
                "component": "lambda:handler",
                "operation": "invoke",
            },
            {
                "span_id": "span-002",
                "parent_span_id": "span-001",
                "component": "agent:supervisor",
                "operation": "process",
            },
        ]
        fixture_file.write_text(
            "\n".join(json.dumps(s) for s in spans), encoding="utf-8"
        )

        result = validate_fixture(fixture_file)
        assert result.valid
        assert len(result.errors) == 0

    def test_missing_required_field(self, tmp_path: Path) -> None:
        fixture_file = tmp_path / "invalid.jsonl"
        spans = [
            {"span_id": "span-001", "component": "lambda:handler"},  # missing 'operation'
        ]
        fixture_file.write_text(
            "\n".join(json.dumps(s) for s in spans), encoding="utf-8"
        )

        result = validate_fixture(fixture_file)
        assert not result.valid
        assert result.errors[0].line_number == 1
        assert "operation" in result.errors[0].message

    def test_invalid_json_line(self, tmp_path: Path) -> None:
        fixture_file = tmp_path / "broken.jsonl"
        fixture_file.write_text(
            '{"span_id": "s1", "component": "c", "operation": "o"}\n'
            "not valid json\n"
            '{"span_id": "s2", "component": "c", "operation": "o"}',
            encoding="utf-8",
        )

        result = validate_fixture(fixture_file)
        assert not result.valid
        # Line 2 should have the JSON error
        assert any(e.line_number == 2 for e in result.errors)
        assert any("Invalid JSON" in e.message for e in result.errors)

    def test_empty_fixture(self, tmp_path: Path) -> None:
        fixture_file = tmp_path / "empty.jsonl"
        fixture_file.write_text("", encoding="utf-8")

        result = validate_fixture(fixture_file)
        assert not result.valid
        assert any("empty" in e.message.lower() for e in result.errors)

    def test_file_not_found(self, tmp_path: Path) -> None:
        result = validate_fixture(tmp_path / "nonexistent.jsonl")
        assert not result.valid
        assert any("not found" in e.message for e in result.errors)

    def test_multiple_invalid_lines(self, tmp_path: Path) -> None:
        fixture_file = tmp_path / "multi_error.jsonl"
        fixture_file.write_text(
            '{"component": "c", "operation": "o"}\n'  # missing span_id
            '{"span_id": "s", "operation": "o"}\n'  # missing component
            '{"span_id": "s", "component": "c"}',  # missing operation
            encoding="utf-8",
        )

        result = validate_fixture(fixture_file)
        assert not result.valid
        # Should have errors from all 3 lines
        line_numbers = {e.line_number for e in result.errors}
        assert 1 in line_numbers
        assert 2 in line_numbers
        assert 3 in line_numbers


# ============================================================================
# Test validate_span_dict
# ============================================================================


class TestValidateSpanDict:
    """Tests for validate_span_dict function."""

    def test_valid_span(self) -> None:
        span = {
            "span_id": "test-span",
            "component": "lambda:handler",
            "operation": "invoke",
        }
        result = validate_span_dict(span)
        assert result.valid

    def test_full_span(self) -> None:
        span = {
            "span_id": "test-span",
            "parent_span_id": "parent-span",
            "component": "agent:supervisor",
            "operation": "process",
            "ts_start": "2024-01-01T00:00:00Z",
            "ts_end": "2024-01-01T00:00:01Z",
            "attempt": 1,
            "itk_trace_id": "trace-001",
            "request": {"key": "value"},
            "response": {"status": "ok"},
        }
        result = validate_span_dict(span)
        assert result.valid

    def test_invalid_span(self) -> None:
        span = {"component": "lambda:handler"}  # missing span_id and operation
        result = validate_span_dict(span)
        assert not result.valid
        messages = [e.message for e in result.errors]
        assert any("span_id" in m for m in messages)
        assert any("operation" in m for m in messages)


# ============================================================================
# Test validate_case_dict
# ============================================================================


class TestValidateCaseDict:
    """Tests for validate_case_dict function."""

    def test_valid_case(self) -> None:
        case = {
            "id": "test-001",
            "name": "Test Case",
            "entrypoint": {
                "type": "sqs_event",
                "target": {"queue_url": "https://example.com"},
                "payload": {"body": "test"},
            },
        }
        result = validate_case_dict(case)
        assert result.valid

    def test_invalid_case(self) -> None:
        case = {"name": "No ID"}  # missing id and entrypoint
        result = validate_case_dict(case)
        assert not result.valid


# ============================================================================
# Test schema loading edge cases
# ============================================================================


class TestSchemaLoading:
    """Tests for schema loading behavior."""

    def test_case_validation_loads_schema(self, tmp_path: Path) -> None:
        """Verify case validation uses the real schema from schemas/."""
        case_file = tmp_path / "test.yaml"
        case_file.write_text(
            """
id: valid-001
name: Schema Test
entrypoint:
  type: http
  target:
    url: https://example.com
  payload:
    body: test
""",
            encoding="utf-8",
        )
        result = validate_case(case_file)
        assert result.valid

    def test_fixture_validation_loads_schema(self, tmp_path: Path) -> None:
        """Verify fixture validation uses the real schema from schemas/."""
        fixture_file = tmp_path / "test.jsonl"
        fixture_file.write_text(
            json.dumps(
                {
                    "span_id": "s1",
                    "component": "model:claude-3-sonnet",
                    "operation": "invoke_model",
                    "parent_span_id": None,
                }
            ),
            encoding="utf-8",
        )
        result = validate_fixture(fixture_file)
        assert result.valid
