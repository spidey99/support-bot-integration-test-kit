"""ITK test configuration and fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add src to path for imports
SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the fixtures directory path."""
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def cases_dir() -> Path:
    """Return the cases directory path."""
    return Path(__file__).parent.parent / "cases"


@pytest.fixture
def schemas_dir() -> Path:
    """Return the schemas directory path."""
    return Path(__file__).parent.parent / "schemas"


@pytest.fixture
def sample_fixture_path(fixtures_dir: Path) -> Path:
    """Return the path to sample_run_001.jsonl."""
    return fixtures_dir / "logs" / "sample_run_001.jsonl"


@pytest.fixture
def examples_dir() -> Path:
    """Return the path to the examples directory."""
    return Path(__file__).parent.parent / "examples"


@pytest.fixture
def example_case_path(examples_dir: Path) -> Path:
    """Return the path to example-001.yaml in examples dir."""
    return examples_dir / "example-001.yaml"
