"""Playwright UI tests for hierarchical suite report.

These tests validate the xUnit-style suite report with:
- Collapsible test groups
- Expandable test rows with mini diagrams
- Modal overlay for full trace viewer
- Keyboard navigation

Run with:
    pytest tests/ui/test_suite_report.py --headed --browser chromium -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Skip if playwright not installed
pytest.importorskip("playwright")

from playwright.sync_api import Page, expect


@pytest.fixture(scope="module")
def suite_artifacts(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate suite report artifacts for testing."""
    from itk.report.suite_runner import run_suite
    from itk.report.hierarchical_report import write_hierarchical_report
    from itk.config import load_config, set_config

    out_dir = tmp_path_factory.mktemp("suite-artifacts")
    cases_dir = Path(__file__).parent.parent.parent / "cases"

    # Configure for dev-fixtures mode
    config = load_config(mode="dev-fixtures")
    set_config(config)

    # Run suite
    suite = run_suite(
        cases_dir=cases_dir,
        out_dir=out_dir,
        suite_name="Test Suite",
    )

    # Write hierarchical report
    write_hierarchical_report(suite, out_dir)

    return out_dir


@pytest.fixture
def js_errors() -> list[str]:
    """Collect JavaScript errors during test."""
    return []


class TestSuiteReportHierarchy:
    """UI tests for hierarchical suite report structure."""

    def test_report_loads_without_js_errors(
        self,
        page: Page,
        suite_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify suite report loads without JavaScript errors."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))

        html_path = suite_artifacts / "index.html"
        assert html_path.exists(), f"index.html not found at {html_path}"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")

        assert len(js_errors) == 0, f"JavaScript errors: {js_errors}"

    def test_summary_cards_visible(
        self,
        page: Page,
        suite_artifacts: Path,
    ) -> None:
        """Verify summary cards are rendered."""
        html_path = suite_artifacts / "index.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")

        # Check summary section exists
        summary = page.locator(".summary")
        expect(summary).to_be_visible()

        # Check individual cards
        cards = page.locator(".summary-card")
        expect(cards.first).to_be_visible()

        # Should have at least total/passed/failed cards
        assert cards.count() >= 4

    def test_test_groups_rendered(
        self,
        page: Page,
        suite_artifacts: Path,
    ) -> None:
        """Verify test groups (suites) are rendered."""
        html_path = suite_artifacts / "index.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")

        groups = page.locator(".test-group")
        expect(groups.first).to_be_visible()

        # Each group should have a header
        headers = page.locator(".group-header")
        expect(headers.first).to_be_visible()

    def test_test_rows_rendered(
        self,
        page: Page,
        suite_artifacts: Path,
    ) -> None:
        """Verify test rows are rendered inside groups."""
        html_path = suite_artifacts / "index.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")

        rows = page.locator(".test-row")
        expect(rows.first).to_be_visible()

        # Each row should have status, name, duration
        first_row = rows.first
        expect(first_row.locator(".test-status")).to_be_visible()
        expect(first_row.locator(".test-name")).to_be_visible()
        expect(first_row.locator(".test-duration")).to_be_visible()


class TestSuiteReportCollapsible:
    """UI tests for collapsible sections."""

    def test_collapse_group(
        self,
        page: Page,
        suite_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify test group can be collapsed."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))

        html_path = suite_artifacts / "index.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")

        group = page.locator(".test-group").first
        header = group.locator(".group-header")
        tests = group.locator(".group-tests")

        # Initially expanded (tests visible)
        expect(tests).to_be_visible()

        # Click to collapse
        header.click()
        page.wait_for_timeout(100)

        # Group should have collapsed class
        expect(group).to_have_class(re.compile(r"collapsed"))

        # Click again to expand
        header.click()
        page.wait_for_timeout(100)

        # Should not have collapsed class
        expect(group).not_to_have_class(re.compile(r"collapsed"))

        assert len(js_errors) == 0, f"JS errors: {js_errors}"

    def test_expand_test_row(
        self,
        page: Page,
        suite_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify test row can be expanded to show details."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))

        html_path = suite_artifacts / "index.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")

        row = page.locator(".test-row").first
        header = row.locator(".test-header")
        details = row.locator(".test-details")

        # Initially collapsed (details hidden)
        expect(details).to_be_hidden()

        # Click to expand
        header.click()
        page.wait_for_timeout(100)

        # Details should be visible
        expect(details).to_be_visible()

        # Should have expanded class
        expect(row).to_have_class(re.compile(r"expanded"))

        # Click again to collapse
        header.click()
        page.wait_for_timeout(100)

        expect(details).to_be_hidden()

        assert len(js_errors) == 0, f"JS errors: {js_errors}"

    def test_expand_all_collapse_all(
        self,
        page: Page,
        suite_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify expand all / collapse all buttons work."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))

        html_path = suite_artifacts / "index.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")

        # Find expand/collapse buttons
        expand_btn = page.get_by_text("Expand All")
        collapse_btn = page.get_by_text("Collapse All")

        # Click expand all
        expand_btn.click()
        page.wait_for_timeout(200)

        # All test rows should be expanded
        expanded_rows = page.locator(".test-row.expanded")
        all_rows = page.locator(".test-row")
        assert expanded_rows.count() == all_rows.count()

        # Click collapse all
        collapse_btn.click()
        page.wait_for_timeout(200)

        # All groups should be collapsed
        collapsed_groups = page.locator(".test-group.collapsed")
        all_groups = page.locator(".test-group")
        assert collapsed_groups.count() == all_groups.count()

        # No test rows should be expanded
        expanded_rows = page.locator(".test-row.expanded")
        assert expanded_rows.count() == 0

        assert len(js_errors) == 0, f"JS errors: {js_errors}"


class TestSuiteReportModal:
    """UI tests for modal trace viewer."""

    def test_open_modal(
        self,
        page: Page,
        suite_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify modal opens when clicking View Full Trace."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))

        html_path = suite_artifacts / "index.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")

        # Expand a test row to see the button
        row = page.locator(".test-row").first
        row.locator(".test-header").click()
        page.wait_for_timeout(100)

        # Find and click the modal button
        modal_btn = row.locator(".open-modal-btn")
        if modal_btn.is_visible():
            modal_btn.click()
            page.wait_for_timeout(200)

            # Modal should be open
            modal = page.locator("#trace-modal")
            expect(modal).to_have_class(re.compile(r"open"))

            # Iframe should exist
            iframe = page.locator("#trace-iframe")
            expect(iframe).to_be_visible()

        assert len(js_errors) == 0, f"JS errors: {js_errors}"

    def test_close_modal_button(
        self,
        page: Page,
        suite_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify modal closes when clicking close button."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))

        html_path = suite_artifacts / "index.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")

        # Expand and open modal
        row = page.locator(".test-row").first
        row.locator(".test-header").click()
        page.wait_for_timeout(100)

        modal_btn = row.locator(".open-modal-btn")
        if modal_btn.is_visible():
            modal_btn.click()
            page.wait_for_timeout(200)

            # Click close button
            close_btn = page.locator(".modal-close")
            close_btn.click()
            page.wait_for_timeout(100)

            # Modal should be closed
            modal = page.locator("#trace-modal")
            expect(modal).not_to_have_class(re.compile(r"open"))

        assert len(js_errors) == 0, f"JS errors: {js_errors}"

    def test_close_modal_escape(
        self,
        page: Page,
        suite_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify modal closes when pressing Escape."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))

        html_path = suite_artifacts / "index.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")

        # Expand and open modal
        row = page.locator(".test-row").first
        row.locator(".test-header").click()
        page.wait_for_timeout(100)

        modal_btn = row.locator(".open-modal-btn")
        if modal_btn.is_visible():
            modal_btn.click()
            page.wait_for_timeout(200)

            # Press Escape
            page.keyboard.press("Escape")
            page.wait_for_timeout(100)

            # Modal should be closed
            modal = page.locator("#trace-modal")
            expect(modal).not_to_have_class(re.compile(r"open"))

        assert len(js_errors) == 0, f"JS errors: {js_errors}"


class TestSuiteReportFilters:
    """UI tests for filter functionality."""

    def test_filter_buttons(
        self,
        page: Page,
        suite_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify filter buttons work."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))

        html_path = suite_artifacts / "index.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")

        # Initially "All" is active
        all_btn = page.locator('.filter-btn[data-filter="all"]')
        expect(all_btn).to_have_class(re.compile(r"active"))

        # Click passed filter
        passed_btn = page.locator('.filter-btn[data-filter="passed"]')
        passed_btn.click()
        page.wait_for_timeout(100)

        expect(passed_btn).to_have_class(re.compile(r"active"))
        expect(all_btn).not_to_have_class(re.compile(r"active"))

        assert len(js_errors) == 0, f"JS errors: {js_errors}"

    def test_search_filter(
        self,
        page: Page,
        suite_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify search input filters tests."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))

        html_path = suite_artifacts / "index.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")

        # Count initial visible tests
        initial_count = page.locator(".test-row:not(.hidden)").count()
        assert initial_count > 0

        # Search for specific text
        search = page.locator("#search")
        search.fill("sqs")
        page.wait_for_timeout(200)

        # Should have fewer or same visible tests
        filtered_count = page.locator(".test-row:not(.hidden)").count()
        assert filtered_count <= initial_count

        # Clear search
        search.fill("")
        page.wait_for_timeout(200)

        # Should be back to original count
        assert page.locator(".test-row:not(.hidden)").count() == initial_count

        assert len(js_errors) == 0, f"JS errors: {js_errors}"


class TestSuiteReportTheme:
    """UI tests for theme functionality."""

    def test_dark_mode_toggle(
        self,
        page: Page,
        suite_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify dark mode toggle works."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))

        html_path = suite_artifacts / "index.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")

        body = page.locator("body")

        # Initially light mode
        expect(body).not_to_have_attribute("data-theme", "dark")

        # Click theme toggle
        theme_btn = page.locator(".theme-btn")
        theme_btn.click()

        # Should be dark mode
        expect(body).to_have_attribute("data-theme", "dark")

        # Toggle back
        theme_btn.click()
        expect(body).not_to_have_attribute("data-theme", "dark")

        assert len(js_errors) == 0, f"JS errors: {js_errors}"
