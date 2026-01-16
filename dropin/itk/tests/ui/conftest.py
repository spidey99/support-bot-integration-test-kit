"""Pytest configuration for UI tests.

Run UI tests with:
    pytest tests/ui/ --headed --browser chromium -v

For debugging with slow motion:
    pytest tests/ui/ --headed --browser chromium -v --slowmo 500
"""
from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "ui: mark test as UI test (requires browser)"
    )


# Apply 'ui' marker to all tests in this directory
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Add 'ui' marker to all tests in ui/ directory."""
    for item in items:
        if "ui" in str(item.fspath):
            item.add_marker(pytest.mark.ui)
