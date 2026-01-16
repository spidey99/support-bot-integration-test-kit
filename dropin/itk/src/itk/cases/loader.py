"""Load and validate ITK case YAML files."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

try:
    from jsonschema import Draft202012Validator, ValidationError
except ImportError:
    Draft202012Validator = None  # type: ignore[assignment,misc]
    ValidationError = Exception  # type: ignore[assignment,misc]


@dataclass(frozen=True)
class EntrypointConfig:
    """Entrypoint configuration from case YAML."""

    type: str  # sqs_event | lambda_invoke | bedrock_invoke_agent | http
    target: dict[str, Any]
    payload: dict[str, Any]


@dataclass(frozen=True)
class InvariantSpec:
    """An expected invariant to check."""

    name: str
    params: dict[str, Any]


@dataclass(frozen=True)
class CaseConfig:
    """A parsed ITK case configuration."""

    id: str
    name: str
    entrypoint: EntrypointConfig
    invariants: list[InvariantSpec]
    notes: dict[str, Any]
    fixture_path: Optional[Path] = None  # Optional: path to fixture for offline mode


def _find_schema_path() -> Optional[Path]:
    """Locate itk.case.schema.json relative to this file."""
    # Traverse upward to find schemas directory
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "schemas" / "itk.case.schema.json"
        if candidate.exists():
            return candidate
    return None


def validate_case_against_schema(data: dict[str, Any]) -> list[str]:
    """Validate case data against JSON schema. Returns list of errors (empty if valid)."""
    if Draft202012Validator is None:
        return []  # Skip validation if jsonschema not available

    schema_path = _find_schema_path()
    if schema_path is None:
        return ["Could not locate itk.case.schema.json"]

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for error in validator.iter_errors(data):
        errors.append(f"{error.json_path}: {error.message}")
    return errors


def load_case(path: Path) -> CaseConfig:
    """Load a case YAML file and return a validated CaseConfig."""
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)

    # Validate against schema
    errors = validate_case_against_schema(data)
    if errors:
        raise ValueError(f"Case validation failed:\n" + "\n".join(errors))

    entrypoint_data = data["entrypoint"]
    entrypoint = EntrypointConfig(
        type=entrypoint_data["type"],
        target=entrypoint_data.get("target", {}),
        payload=entrypoint_data.get("payload", {}),
    )

    invariants: list[InvariantSpec] = []
    expected = data.get("expected", {})
    for inv in expected.get("invariants", []):
        invariants.append(InvariantSpec(name=inv["name"], params=inv.get("params", {})))

    notes = data.get("notes", {})

    # Check for offline fixture path in notes or dedicated field
    fixture_path: Optional[Path] = None
    if "fixture" in data:
        fixture_path = path.parent / data["fixture"]
    elif "fixture_path" in notes:
        fixture_path = path.parent / notes["fixture_path"]

    return CaseConfig(
        id=data["id"],
        name=data["name"],
        entrypoint=entrypoint,
        invariants=invariants,
        notes=notes,
        fixture_path=fixture_path,
    )
