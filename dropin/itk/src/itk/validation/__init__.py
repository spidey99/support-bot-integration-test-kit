"""Schema validation for ITK case files and fixture JSONL."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import yaml


@dataclass
class ValidationError:
    """A single validation error."""
    
    path: str
    message: str
    line_number: int | None = None  # For JSONL files


@dataclass
class ValidationResult:
    """Result of validating a file."""
    
    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    file_path: str = ""
    
    def summary(self) -> str:
        """Return a human-readable summary."""
        if self.valid:
            return f"✓ {self.file_path}: Valid"
        lines = [f"✗ {self.file_path}: {len(self.errors)} error(s)"]
        for err in self.errors:
            if err.line_number is not None:
                lines.append(f"  Line {err.line_number}: {err.path} - {err.message}")
            else:
                lines.append(f"  {err.path} - {err.message}")
        return "\n".join(lines)


def _get_schema_dir() -> Path:
    """Get the directory containing schemas."""
    # schemas/ is a sibling to src/ in the itk package
    return Path(__file__).parent.parent.parent.parent / "schemas"


def _load_schema(schema_name: str) -> dict[str, Any]:
    """Load a JSON schema by name."""
    schema_path = _get_schema_dir() / schema_name
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _format_path(path: list[Any]) -> str:
    """Format a jsonschema path as a dotted string."""
    if not path:
        return "$"
    parts = ["$"]
    for p in path:
        if isinstance(p, int):
            parts.append(f"[{p}]")
        else:
            parts.append(f".{p}")
    return "".join(parts)


def validate_case(case_path: str | Path) -> ValidationResult:
    """Validate a case YAML file against itk.case.schema.json.
    
    Args:
        case_path: Path to the case YAML file.
        
    Returns:
        ValidationResult with any errors found.
    """
    case_path = Path(case_path)
    result = ValidationResult(valid=True, file_path=str(case_path))
    
    # Check file exists
    if not case_path.exists():
        result.valid = False
        result.errors.append(ValidationError(
            path="$",
            message=f"File not found: {case_path}"
        ))
        return result
    
    # Load case YAML
    try:
        content = case_path.read_text(encoding="utf-8")
        case_data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        result.valid = False
        result.errors.append(ValidationError(
            path="$",
            message=f"Invalid YAML: {e}"
        ))
        return result
    
    # Load schema
    try:
        schema = _load_schema("itk.case.schema.json")
    except FileNotFoundError as e:
        result.valid = False
        result.errors.append(ValidationError(
            path="$",
            message=str(e)
        ))
        return result
    
    # Validate against schema
    validator = jsonschema.Draft202012Validator(schema)
    errors = list(validator.iter_errors(case_data))
    
    if errors:
        result.valid = False
        for err in errors:
            result.errors.append(ValidationError(
                path=_format_path(list(err.absolute_path)),
                message=err.message
            ))
    
    return result


def validate_fixture(fixture_path: str | Path) -> ValidationResult:
    """Validate a fixture JSONL file against itk.span.schema.json.
    
    Each line is validated as a separate span.
    
    Args:
        fixture_path: Path to the fixture JSONL file.
        
    Returns:
        ValidationResult with any errors found.
    """
    fixture_path = Path(fixture_path)
    result = ValidationResult(valid=True, file_path=str(fixture_path))
    
    # Check file exists
    if not fixture_path.exists():
        result.valid = False
        result.errors.append(ValidationError(
            path="$",
            message=f"File not found: {fixture_path}"
        ))
        return result
    
    # Load schema
    try:
        schema = _load_schema("itk.span.schema.json")
    except FileNotFoundError as e:
        result.valid = False
        result.errors.append(ValidationError(
            path="$",
            message=str(e)
        ))
        return result
    
    validator = jsonschema.Draft202012Validator(schema)
    
    # Read and validate each line
    try:
        content = fixture_path.read_text(encoding="utf-8")
    except Exception as e:
        result.valid = False
        result.errors.append(ValidationError(
            path="$",
            message=f"Cannot read file: {e}"
        ))
        return result
    
    lines = content.strip().split("\n") if content.strip() else []
    
    if not lines:
        result.valid = False
        result.errors.append(ValidationError(
            path="$",
            message="Fixture file is empty",
            line_number=0
        ))
        return result
    
    for line_num, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
            
        # Parse JSON
        try:
            span_data = json.loads(line)
        except json.JSONDecodeError as e:
            result.valid = False
            result.errors.append(ValidationError(
                path="$",
                message=f"Invalid JSON: {e}",
                line_number=line_num
            ))
            continue
        
        # Validate span against schema
        errors = list(validator.iter_errors(span_data))
        if errors:
            result.valid = False
            for err in errors:
                result.errors.append(ValidationError(
                    path=_format_path(list(err.absolute_path)),
                    message=err.message,
                    line_number=line_num
                ))
    
    return result


def validate_span_dict(span: dict[str, Any]) -> ValidationResult:
    """Validate a single span dictionary against itk.span.schema.json.
    
    Useful for programmatic validation without file I/O.
    
    Args:
        span: Span dictionary to validate.
        
    Returns:
        ValidationResult with any errors found.
    """
    result = ValidationResult(valid=True, file_path="<dict>")
    
    try:
        schema = _load_schema("itk.span.schema.json")
    except FileNotFoundError as e:
        result.valid = False
        result.errors.append(ValidationError(path="$", message=str(e)))
        return result
    
    validator = jsonschema.Draft202012Validator(schema)
    errors = list(validator.iter_errors(span))
    
    if errors:
        result.valid = False
        for err in errors:
            result.errors.append(ValidationError(
                path=_format_path(list(err.absolute_path)),
                message=err.message
            ))
    
    return result


def validate_case_dict(case: dict[str, Any]) -> ValidationResult:
    """Validate a single case dictionary against itk.case.schema.json.
    
    Useful for programmatic validation without file I/O.
    
    Args:
        case: Case dictionary to validate.
        
    Returns:
        ValidationResult with any errors found.
    """
    result = ValidationResult(valid=True, file_path="<dict>")
    
    try:
        schema = _load_schema("itk.case.schema.json")
    except FileNotFoundError as e:
        result.valid = False
        result.errors.append(ValidationError(path="$", message=str(e)))
        return result
    
    validator = jsonschema.Draft202012Validator(schema)
    errors = list(validator.iter_errors(case))
    
    if errors:
        result.valid = False
        for err in errors:
            result.errors.append(ValidationError(
                path=_format_path(list(err.absolute_path)),
                message=err.message
            ))
    
    return result
