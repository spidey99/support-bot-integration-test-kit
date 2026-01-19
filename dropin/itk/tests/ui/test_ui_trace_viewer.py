"""Playwright UI tests for trace viewer and timeline HTML outputs.

These tests run in HEADED mode (visible browser) to catch JavaScript errors
that would break the interface. Run with:

    pytest tests/ui/ --headed --browser chromium -v

Or for debugging with slow motion:

    pytest tests/ui/ --headed --browser chromium -v --slowmo 500
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# Skip if playwright not installed
pytest.importorskip("playwright")

from playwright.sync_api import Page, expect, ConsoleMessage


# Fixtures directory
FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "logs"
ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "artifacts" / "ui-test"


@pytest.fixture(scope="module")
def generated_artifacts(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate fresh artifacts for testing."""
    from itk.cli import _cmd_run
    from argparse import Namespace
    
    out_dir = tmp_path_factory.mktemp("artifacts")
    examples_dir = Path(__file__).parent.parent.parent / "examples"
    
    # Generate from example case (examples are reference only, not live tests)
    args = Namespace(
        case=str(examples_dir / "example-001.yaml"),
        out=str(out_dir),
        mode="dev-fixtures",
        env_file=None,
        no_redact=False,
    )
    _cmd_run(args)
    
    return out_dir


@pytest.fixture
def js_errors() -> list[str]:
    """Collect JavaScript errors during test."""
    return []


@pytest.fixture
def console_messages() -> list[ConsoleMessage]:
    """Collect all console messages during test."""
    return []


class TestTraceViewer:
    """UI tests for trace-viewer.html."""
    
    def test_trace_viewer_loads_without_js_errors(
        self, 
        page: Page, 
        generated_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify trace viewer loads without JavaScript errors."""
        # Collect JS errors
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        
        # Navigate to trace viewer
        html_path = generated_artifacts / "trace-viewer.html"
        assert html_path.exists(), f"trace-viewer.html not found at {html_path}"
        page.goto(f"file://{html_path}")
        
        # Wait for page to fully load
        page.wait_for_load_state("networkidle")
        
        # Check no JS errors occurred
        assert len(js_errors) == 0, f"JavaScript errors: {js_errors}"
    
    def test_trace_viewer_has_svg_diagram(
        self,
        page: Page,
        generated_artifacts: Path,
    ) -> None:
        """Verify SVG sequence diagram is rendered."""
        html_path = generated_artifacts / "trace-viewer.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        
        # Check SVG exists
        svg = page.locator("#diagram")
        expect(svg).to_be_visible()
        
        # Check it has content (participants and messages)
        participants = page.locator(".participant")
        expect(participants.first).to_be_visible()
        
        messages = page.locator(".message")
        expect(messages.first).to_be_visible()
    
    def test_zoom_controls_work(
        self,
        page: Page,
        generated_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify zoom controls are functional."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        
        html_path = generated_artifacts / "trace-viewer.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        
        # Click zoom in button
        zoom_in = page.locator(".zoom-btn").first
        expect(zoom_in).to_be_visible()
        zoom_in.click()
        
        # No JS errors should occur
        assert len(js_errors) == 0, f"Zoom caused JS errors: {js_errors}"
        
        # Click zoom out
        zoom_out = page.locator(".zoom-btn").nth(1)
        zoom_out.click()
        
        # Click fit
        fit_btn = page.locator(".zoom-btn").nth(2)
        fit_btn.click()
        
        # Click reset
        reset_btn = page.locator(".zoom-btn").nth(3)
        reset_btn.click()
        
        assert len(js_errors) == 0, f"JS errors after zoom operations: {js_errors}"
    
    def test_click_span_shows_details_panel(
        self,
        page: Page,
        generated_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify clicking a span opens the details panel."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        
        html_path = generated_artifacts / "trace-viewer.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        
        # Details panel should start collapsed
        details_panel = page.locator("#details-panel")
        expect(details_panel).to_have_class(re.compile(r"collapsed"))
        
        # Dispatch click event on SVG element (SVG g elements don't have .click())
        page.evaluate("""
            const msg = document.querySelector('.message');
            msg.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
        """)
        
        # Wait for panel to update
        page.wait_for_timeout(200)
        
        # Check no JS errors
        assert len(js_errors) == 0, f"Clicking span caused JS errors: {js_errors}"
        
        # Details panel should now be visible
        expect(details_panel).not_to_have_class(re.compile(r"collapsed"))
        
        # Check details content has data
        details_content = page.locator("#details-content")
        expect(details_content).to_contain_text("Operation")
        expect(details_content).to_contain_text("Component")
        expect(details_content).to_contain_text("Request")
    
    def test_close_details_panel(
        self,
        page: Page,
        generated_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify details panel can be closed."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        
        html_path = generated_artifacts / "trace-viewer.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        
        # Open details panel using dispatchEvent (SVG g elements)
        page.evaluate("""
            const msg = document.querySelector('.message');
            msg.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
        """)
        page.wait_for_timeout(200)
        
        # Close button
        close_btn = page.locator(".details-close")
        close_btn.click()
        
        # Panel should be collapsed
        details_panel = page.locator("#details-panel")
        expect(details_panel).to_have_class(re.compile(r"collapsed"))
        
        assert len(js_errors) == 0, f"JS errors: {js_errors}"
    
    def test_search_filters_spans(
        self,
        page: Page,
        generated_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify search input filters displayed spans."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        
        html_path = generated_artifacts / "trace-viewer.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        
        # Count initial messages
        messages = page.locator(".message:not(.hidden)")
        initial_count = messages.count()
        assert initial_count > 0, "No messages found"
        
        # Type in search box
        search_input = page.locator("#search")
        search_input.fill("InvokeLambda")
        
        # Wait a moment for filter to apply
        page.wait_for_timeout(200)
        
        # Should have fewer (or same) visible messages
        visible_count = page.locator(".message:not(.hidden)").count()
        assert visible_count <= initial_count
        
        # Clear search
        search_input.fill("")
        page.wait_for_timeout(200)
        
        # All messages visible again
        assert page.locator(".message:not(.hidden)").count() == initial_count
        
        assert len(js_errors) == 0, f"Search caused JS errors: {js_errors}"
    
    def test_keyboard_navigation(
        self,
        page: Page,
        generated_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify keyboard shortcuts work."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        
        html_path = generated_artifacts / "trace-viewer.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        
        # Press / to focus search
        page.keyboard.press("/")
        search_input = page.locator("#search")
        expect(search_input).to_be_focused()
        
        # Press Escape to unfocus
        page.keyboard.press("Escape")
        expect(search_input).not_to_be_focused()
        
        # Arrow down to select first span
        page.keyboard.press("ArrowDown")
        
        # Should have a selected message
        selected = page.locator(".message.selected")
        expect(selected).to_be_visible()
        
        assert len(js_errors) == 0, f"Keyboard nav caused JS errors: {js_errors}"
    
    def test_dark_mode_toggle(
        self,
        page: Page,
        generated_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify dark mode toggle works."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        
        html_path = generated_artifacts / "trace-viewer.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        
        body = page.locator("body")
        
        # Initially no dark theme
        expect(body).not_to_have_attribute("data-theme", "dark")
        
        # Click theme toggle
        theme_btn = page.locator(".theme-btn")
        theme_btn.click()
        
        # Should have dark theme
        expect(body).to_have_attribute("data-theme", "dark")
        
        # Toggle back
        theme_btn.click()
        expect(body).not_to_have_attribute("data-theme", "dark")
        
        assert len(js_errors) == 0, f"Theme toggle caused JS errors: {js_errors}"
    
    def test_filter_buttons(
        self,
        page: Page,
        generated_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify error/retry filter buttons work."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        
        html_path = generated_artifacts / "trace-viewer.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        
        # Click errors filter
        errors_btn = page.locator('[data-filter="errors"]')
        errors_btn.click()
        expect(errors_btn).to_have_class(re.compile(r"active"))
        
        # Click again to deactivate
        errors_btn.click()
        expect(errors_btn).not_to_have_class(re.compile(r"active"))
        
        # Click retries filter
        retries_btn = page.locator('[data-filter="retries"]')
        retries_btn.click()
        expect(retries_btn).to_have_class(re.compile(r"active"))
        
        assert len(js_errors) == 0, f"Filter buttons caused JS errors: {js_errors}"
    
    def test_copy_payload_button(
        self,
        page: Page,
        generated_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify copy payload button works (checks for no errors)."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        
        html_path = generated_artifacts / "trace-viewer.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        
        # Open details using dispatchEvent (SVG g elements)
        page.evaluate("""
            const msg = document.querySelector('.message');
            msg.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
        """)
        
        # Wait for details to render
        page.wait_for_timeout(200)
        
        # Find copy button and click
        copy_btn = page.locator(".copy-btn").first
        if copy_btn.is_visible():
            copy_btn.click()
            
            # Button should change text (may fail in some contexts due to clipboard permissions)
            # But at minimum, no JS errors should occur
        
        assert len(js_errors) == 0, f"Copy button caused JS errors: {js_errors}"


class TestTimeline:
    """UI tests for timeline.html."""
    
    def test_timeline_loads_without_js_errors(
        self,
        page: Page,
        generated_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify timeline loads without JavaScript errors."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        
        html_path = generated_artifacts / "timeline.html"
        assert html_path.exists(), f"timeline.html not found at {html_path}"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        
        assert len(js_errors) == 0, f"JavaScript errors: {js_errors}"
    
    def test_timeline_has_svg(
        self,
        page: Page,
        generated_artifacts: Path,
    ) -> None:
        """Verify timeline SVG is rendered."""
        html_path = generated_artifacts / "timeline.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        
        # Check SVG exists
        svg = page.locator("#timeline")
        expect(svg).to_be_visible()
        
        # Should have timeline rows
        rows = page.locator(".timeline-row")
        expect(rows.first).to_be_visible()
    
    def test_timeline_dark_mode(
        self,
        page: Page,
        generated_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify timeline dark mode toggle works."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        
        html_path = generated_artifacts / "timeline.html"
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        
        # Click theme toggle
        theme_btn = page.locator(".theme-btn")
        if theme_btn.is_visible():
            theme_btn.click()
            
            body = page.locator("body")
            expect(body).to_have_attribute("data-theme", "dark")
        
        assert len(js_errors) == 0, f"Theme toggle caused JS errors: {js_errors}"


class TestSequenceHTML:
    """UI tests for sequence.html (legacy renderer)."""
    
    def test_sequence_html_loads_without_js_errors(
        self,
        page: Page,
        generated_artifacts: Path,
        js_errors: list[str],
    ) -> None:
        """Verify sequence.html loads without JavaScript errors."""
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        
        html_path = generated_artifacts / "sequence.html"
        if html_path.exists():
            page.goto(f"file://{html_path}")
            page.wait_for_load_state("networkidle")
            
            assert len(js_errors) == 0, f"JavaScript errors: {js_errors}"
