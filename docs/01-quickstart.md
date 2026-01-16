# Quickstart

## Installation

```bash
cd dropin/itk
pip install -e ".[dev]"
```

## Tier 2 (dev-fixtures mode - no AWS required)

Use fixtures to test the ITK engine without AWS credentials.

### Render a fixture directly
```bash
itk render-fixture --fixture fixtures/logs/sample_run_001.jsonl --out artifacts/render-001
```

### Run a case in dev-fixtures mode
```bash
itk run --mode dev-fixtures --case cases/example-001.yaml --out artifacts/run-001
```

### Audit logging gaps
```bash
itk audit --mode dev-fixtures --case cases/example-001.yaml --out artifacts/audit-001
```

## Tier 3 (work repo - with AWS access)

After copying the drop-in folder into the work repo:

### Run a case online (golden path: SQS)
```bash
itk run --case cases/my-case.yaml --out artifacts/run-001
```

### Derive cases from CloudWatch logs
```bash
itk derive --entrypoint sqs_event --since 24h --out cases/derived/
```

### Audit logging gaps with live data
```bash
itk audit --case cases/my-case.yaml --out artifacts/audit-001
```

## Entrypoint Types

| Type | Mode | Use Case |
|------|------|----------|
| `sqs_event` | `publish_sqs` | **Golden path** - Full async flow through SQS |
| `sqs_event` | `invoke_lambda` | Fast debug - Synchronous Lambda invocation |
| `lambda_invoke` | - | Direct Lambda invocation |
| `bedrock_invoke_agent` | - | Bedrock Agent with trace enabled |

## Output Artifacts

After running a case, check the output directory:

| File | Description |
|------|-------------|
| `sequence.mmd` | Mermaid sequence diagram |
| `trace-viewer.html` | Interactive HTML diagram viewer |
| `timeline.html` | Timeline visualization with critical path |
| `spans.jsonl` | All spans in JSONL format |
| `report.md` | Human-readable summary with invariant results |
| `payloads/*.json` | Request/response payloads per span |
| `logging-gaps.md` | (audit only) Missing log fields report |

## Format Options

Export specific formats with `--format`:

```bash
# HTML only
itk render-fixture --fixture fixtures/logs/sample_run_001.jsonl --out out --format html

# Mermaid only
itk render-fixture --fixture fixtures/logs/sample_run_001.jsonl --out out --format mermaid

# JSON spans
itk render-fixture --fixture fixtures/logs/sample_run_001.jsonl --out out --format json

# SVG diagrams (sequence + timeline)
itk render-fixture --fixture fixtures/logs/sample_run_001.jsonl --out out --format svg

# All formats (default)
itk render-fixture --fixture fixtures/logs/sample_run_001.jsonl --out out --format all
```

## Live Preview Server

Serve artifacts with auto-opening browser:

```bash
# Serve artifacts directory
itk serve artifacts/run-001

# Custom port
itk serve artifacts/run-001 --port 9000

# No auto-browser
itk serve artifacts/run-001 --no-browser

# Watch mode (re-renders on source changes)
itk serve artifacts/run-001 --watch
```
