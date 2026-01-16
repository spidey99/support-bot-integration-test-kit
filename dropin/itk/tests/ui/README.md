# UI Tests for ITK

This directory contains Playwright-based UI tests that validate the HTML/JavaScript
outputs actually work in a real browser.

## Why Non-Headless?

These tests run in **headed mode** (visible browser window) by design:
- JavaScript errors that break functionality are immediately visible
- Prevents the "tested extensively and it's working" → nothing works loop
- Visual feedback during development

## Running UI Tests

### Basic run (headed, Chromium):
```bash
pytest tests/ui/ --headed --browser chromium -v
```

### With slow motion for debugging:
```bash
pytest tests/ui/ --headed --browser chromium -v --slowmo 500
```

### Headless (for CI - not recommended for local dev):
```bash
pytest tests/ui/ --browser chromium -v
```

## What's Tested

### trace-viewer.html
- Page loads without JavaScript errors
- SVG sequence diagram renders
- Zoom controls work (+, -, fit, reset)
- Clicking spans opens details panel
- Details panel shows request/response/error JSON
- Copy button works
- Search filters spans
- Keyboard navigation (/, Esc, arrows)
- Dark mode toggle
- Error/Retry filter buttons

### timeline.html
- Page loads without JavaScript errors
- Timeline SVG renders
- Dark mode toggle

### sequence.html (legacy)
- Page loads without JavaScript errors

## Adding New Tests

1. Add test methods to the appropriate class in `test_trace_viewer.py`
2. Always collect JS errors via the `js_errors` fixture
3. Use `expect()` assertions from Playwright
4. Include a `page.wait_for_load_state("networkidle")` after navigation

## Common Issues

### Browser Not Found
```bash
playwright install chromium
```

### Clipboard Tests Fail
Copy-to-clipboard may fail in some environments due to browser security policies.
The test only checks that no JS errors occur, not that clipboard actually works.
