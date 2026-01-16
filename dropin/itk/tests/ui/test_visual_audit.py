"""Visual audit tests - captures screenshots of all UI states for review."""
from __future__ import annotations

import pytest
import shutil
from pathlib import Path
from playwright.sync_api import Page, expect

# Output directory for screenshots
SCREENSHOTS_DIR = Path(__file__).parent.parent.parent / "artifacts" / "visual-audit"


@pytest.fixture(scope="module", autouse=True)
def setup_screenshots_dir():
    """Clean and recreate screenshots directory."""
    # Remove old screenshots to avoid stale artifacts
    if SCREENSHOTS_DIR.exists():
        shutil.rmtree(SCREENSHOTS_DIR)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


class TestTraceViewerVisualAudit:
    """Visual audit of trace-viewer.html."""

    @pytest.fixture(autouse=True)
    def setup(self, page: Page):
        """Load trace viewer before each test."""
        html_path = Path(__file__).parent.parent.parent / "artifacts" / "suite-demo" / "agent_gatekeeper_basic" / "trace-viewer.html"
        if not html_path.exists():
            pytest.skip("Demo artifacts not generated")
        page.goto(f"file:///{html_path.as_posix()}")
        page.wait_for_load_state("networkidle")
        self.page = page

    def test_01_initial_load(self):
        """Capture initial load state."""
        self.page.screenshot(path=SCREENSHOTS_DIR / "trace-viewer-01-initial.png", full_page=True)

    def test_02_span_selected(self):
        """Capture state with span selected and details panel open."""
        # Click on a message to select it
        messages = self.page.locator(".message")
        if messages.count() > 1:
            messages.nth(1).click()
            self.page.wait_for_timeout(300)
        self.page.screenshot(path=SCREENSHOTS_DIR / "trace-viewer-02-span-selected.png", full_page=True)

    def test_03_search_active(self):
        """Capture search results state."""
        search = self.page.locator("#search")
        search.fill("Invoke")
        self.page.wait_for_timeout(300)
        self.page.screenshot(path=SCREENSHOTS_DIR / "trace-viewer-03-search-active.png", full_page=True)

    def test_04_errors_filter(self):
        """Capture errors filter state."""
        self.page.locator("#search").fill("")  # Clear search
        errors_btn = self.page.locator("button:has-text('Errors')")
        if errors_btn.count() > 0:
            errors_btn.click()
            self.page.wait_for_timeout(200)
        self.page.screenshot(path=SCREENSHOTS_DIR / "trace-viewer-04-errors-filter.png", full_page=True)

    def test_05_dark_mode(self):
        """Capture dark mode state."""
        # Find and click dark mode toggle
        dark_toggle = self.page.locator("[onclick*='toggleDarkMode'], button:has-text('🌙'), .dark-toggle")
        if dark_toggle.count() > 0:
            dark_toggle.first.click()
            self.page.wait_for_timeout(200)
        self.page.screenshot(path=SCREENSHOTS_DIR / "trace-viewer-05-dark-mode.png", full_page=True)

    def test_06_zoomed_in(self):
        """Capture zoomed in view."""
        # Click zoom in button multiple times for visible effect
        zoom_in = self.page.locator("button:has-text('+')")
        if zoom_in.count() > 0:
            for _ in range(4):
                zoom_in.click()
                self.page.wait_for_timeout(100)
        self.page.screenshot(path=SCREENSHOTS_DIR / "trace-viewer-06-zoomed-in.png", full_page=True)


class TestSuiteReportVisualAudit:
    """Visual audit of suite report (index.html)."""

    @pytest.fixture(autouse=True)
    def setup(self, page: Page):
        """Load suite report before each test."""
        html_path = Path(__file__).parent.parent.parent / "artifacts" / "suite-demo" / "index.html"
        if not html_path.exists():
            pytest.skip("Demo artifacts not generated")
        page.goto(f"file:///{html_path.as_posix()}")
        page.wait_for_load_state("networkidle")
        self.page = page

    def test_01_initial_load(self):
        """Capture initial hierarchical report view."""
        self.page.screenshot(path=SCREENSHOTS_DIR / "suite-report-01-initial.png", full_page=True)

    def test_02_group_collapsed(self):
        """Capture view with a group collapsed."""
        # Find and click a group header to collapse
        group_headers = self.page.locator(".group-header")
        if group_headers.count() > 0:
            group_headers.first.click()
            self.page.wait_for_timeout(200)
        self.page.screenshot(path=SCREENSHOTS_DIR / "suite-report-02-group-collapsed.png", full_page=True)

    def test_03_test_expanded(self):
        """Capture view with test details expanded."""
        # Re-expand group if collapsed, then expand a test row
        group_headers = self.page.locator(".group-header.collapsed")
        if group_headers.count() > 0:
            group_headers.first.click()
            self.page.wait_for_timeout(200)
        
        test_rows = self.page.locator(".test-row")
        if test_rows.count() > 0:
            test_rows.first.click()
            self.page.wait_for_timeout(300)
        self.page.screenshot(path=SCREENSHOTS_DIR / "suite-report-03-test-expanded.png", full_page=True)

    def test_04_modal_open(self):
        """Capture modal trace viewer overlay."""
        # Expand a test if not already
        expanded_details = self.page.locator(".test-details:visible")
        if expanded_details.count() == 0:
            test_rows = self.page.locator(".test-row")
            if test_rows.count() > 0:
                test_rows.first.click()
                self.page.wait_for_timeout(300)
        
        # Click view trace button
        view_trace_btn = self.page.locator("button:has-text('View Full Trace'), a:has-text('View Full Trace')")
        if view_trace_btn.count() > 0:
            view_trace_btn.first.click()
            self.page.wait_for_timeout(500)
        self.page.screenshot(path=SCREENSHOTS_DIR / "suite-report-04-modal-open.png", full_page=True)

    def test_05_search_filtered(self):
        """Capture search filter results."""
        # Close modal if open
        modal_close = self.page.locator("button.modal-close")
        if modal_close.count() > 0 and modal_close.first.is_visible():
            modal_close.first.click()
            self.page.wait_for_timeout(200)
        
        search = self.page.locator("#search, input[type='search'], input[placeholder*='search' i]")
        if search.count() > 0:
            search.first.fill("sqs")
            self.page.wait_for_timeout(300)
        self.page.screenshot(path=SCREENSHOTS_DIR / "suite-report-05-search-filtered.png", full_page=True)

    def test_06_dark_mode(self):
        """Capture dark mode state."""
        # Clear search
        search = self.page.locator("#search, input[type='search']")
        if search.count() > 0:
            search.first.fill("")
        
        # Toggle dark mode
        dark_toggle = self.page.locator("[onclick*='toggleTheme'], button:has-text('🌙'), .theme-toggle")
        if dark_toggle.count() > 0:
            dark_toggle.first.click()
            self.page.wait_for_timeout(200)
        self.page.screenshot(path=SCREENSHOTS_DIR / "suite-report-06-dark-mode.png", full_page=True)


class TestSequenceDiagramVisualAudit:
    """Visual audit of standalone sequence.html."""

    @pytest.fixture(autouse=True)
    def setup(self, page: Page):
        """Load sequence diagram before each test."""
        html_path = Path(__file__).parent.parent.parent / "artifacts" / "suite-demo" / "sqs_retry_scenario" / "sequence.html"
        if not html_path.exists():
            pytest.skip("Demo artifacts not generated")
        page.goto(f"file:///{html_path.as_posix()}")
        page.wait_for_load_state("networkidle")
        self.page = page

    def test_01_initial_load(self):
        """Capture initial mermaid diagram view."""
        self.page.wait_for_timeout(500)  # Wait for mermaid render
        self.page.screenshot(path=SCREENSHOTS_DIR / "sequence-01-initial.png", full_page=True)


class TestTimelineViewVisualAudit:
    """Visual audit of timeline.html."""

    @pytest.fixture(autouse=True)
    def setup(self, page: Page):
        """Load timeline before each test."""
        html_path = Path(__file__).parent.parent.parent / "artifacts" / "suite-demo" / "agent_gatekeeper_basic" / "timeline.html"
        if not html_path.exists():
            pytest.skip("Demo artifacts not generated")
        page.goto(f"file:///{html_path.as_posix()}")
        page.wait_for_load_state("networkidle")
        self.page = page

    def test_01_initial_load(self):
        """Capture initial timeline view."""
        self.page.screenshot(path=SCREENSHOTS_DIR / "timeline-01-initial.png", full_page=True)

    def test_02_span_hover(self):
        """Capture span hover tooltip."""
        spans = self.page.locator(".span-bar, rect[data-span-id]")
        if spans.count() > 0:
            spans.first.hover()
            self.page.wait_for_timeout(300)
        self.page.screenshot(path=SCREENSHOTS_DIR / "timeline-02-span-hover.png", full_page=True)


class TestSoakReportVisualAudit:
    """Visual audit of soak-report.html."""

    @pytest.fixture(autouse=True)
    def setup(self, page: Page):
        """Load soak report before each test."""
        html_path = Path(__file__).parent.parent.parent / "artifacts" / "soak-demo" / "soak-report.html"
        if not html_path.exists():
            pytest.skip("Soak demo artifacts not generated (run: itk soak --case cases/demo-warning-001.yaml --out artifacts/soak-demo --iterations 15)")
        page.goto(f"file:///{html_path.as_posix()}")
        page.wait_for_load_state("networkidle")
        self.page = page

    def test_01_initial_load(self):
        """Capture initial soak report view."""
        self.page.screenshot(path=SCREENSHOTS_DIR / "soak-report-01-initial.png", full_page=True)

    def test_02_consistency_breakdown(self):
        """Capture consistency breakdown section."""
        # Scroll to ensure consistency section is visible
        consistency = self.page.locator(".consistency-breakdown, .breakdown-bar")
        if consistency.count() > 0:
            consistency.first.scroll_into_view_if_needed()
            self.page.wait_for_timeout(200)
        self.page.screenshot(path=SCREENSHOTS_DIR / "soak-report-02-consistency.png", full_page=True)

    def test_03_iteration_grid(self):
        """Capture iteration grid with cell hover."""
        grid = self.page.locator(".iteration-grid")
        if grid.count() > 0:
            grid.first.scroll_into_view_if_needed()
            cells = self.page.locator(".iteration-cell")
            if cells.count() > 0:
                cells.first.hover()
                self.page.wait_for_timeout(200)
        self.page.screenshot(path=SCREENSHOTS_DIR / "soak-report-03-iteration-grid.png", full_page=True)

    def test_04_iteration_table(self):
        """Capture iteration details table."""
        table = self.page.locator(".iteration-table, table")
        if table.count() > 0:
            table.first.scroll_into_view_if_needed()
            self.page.wait_for_timeout(200)
        self.page.screenshot(path=SCREENSHOTS_DIR / "soak-report-04-iteration-table.png", full_page=True)

    def test_05_filter_warnings(self):
        """Capture view with 'Warnings Only' filter active."""
        filter_btn = self.page.locator("button:has-text('Warnings Only'), [data-filter='warnings']")
        if filter_btn.count() > 0:
            filter_btn.first.click()
            self.page.wait_for_timeout(200)
        self.page.screenshot(path=SCREENSHOTS_DIR / "soak-report-05-filter-warnings.png", full_page=True)

    def test_06_filter_retries(self):
        """Capture view with 'Has Retries' filter active."""
        filter_btn = self.page.locator("button:has-text('Has Retries'), [data-filter='retries']")
        if filter_btn.count() > 0:
            filter_btn.first.click()
            self.page.wait_for_timeout(200)
        self.page.screenshot(path=SCREENSHOTS_DIR / "soak-report-06-filter-retries.png", full_page=True)

    def test_07_sorted_by_duration(self):
        """Capture table sorted by duration."""
        # Reset filter first
        all_btn = self.page.locator("button:has-text('All'), [data-filter='all']")
        if all_btn.count() > 0:
            all_btn.first.click()
            self.page.wait_for_timeout(100)
        
        # Click duration header to sort
        duration_header = self.page.locator("th:has-text('Duration')")
        if duration_header.count() > 0:
            duration_header.first.click()
            self.page.wait_for_timeout(200)
        self.page.screenshot(path=SCREENSHOTS_DIR / "soak-report-07-sorted-duration.png", full_page=True)

    def test_08_dark_mode(self):
        """Capture dark mode state."""
        dark_toggle = self.page.locator("[onclick*='toggleTheme'], button:has-text('Dark'), .theme-toggle, [onclick*='darkMode']")
        if dark_toggle.count() > 0:
            dark_toggle.first.click()
            self.page.wait_for_timeout(200)
        self.page.screenshot(path=SCREENSHOTS_DIR / "soak-report-08-dark-mode.png", full_page=True)
