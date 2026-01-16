# ITK — Work Repo Installation (Tier 3)

This folder is intended to be copied into the **work** repo.

## What this does
- Runs post-deploy integration tests against deployed QA resources
- Pulls CloudWatch logs using the same AWS creds the repo already uses
- Builds a stitched execution trace from many IDs (Lambda request id, Bedrock session id, SQS ids, X-Ray ids, etc.)
- Outputs a Mermaid sequence diagram + payload artifacts + invariant checks

## Install

1) Copy this folder into the work repo at: `tools/itk/` (recommended)

2) Install the package:
   ```bash
   cd tools/itk
   pip install -e ".[dev]"
   ```

3) Merge Copilot guidance into the repo root:
   - Copy: `tools/itk/_merge_to_repo_root/.github/*` into `<WORK_REPO>/.github/`
   - If `<WORK_REPO>/.github/copilot-instructions.md` exists, append `copilot-instructions.append.md` between the markers.

## Run (examples)

### Offline mode (no AWS required)
```bash
# Run a case with fixtures
itk run --mode dev-fixtures --case cases/example-001.yaml --out artifacts/run-001

# Audit logging gaps
itk audit --mode dev-fixtures --case cases/example-001.yaml --out artifacts/audit-001

# Run a full test suite
itk suite --mode dev-fixtures --cases-dir cases/ --out artifacts/suite-demo/
```

### Online mode (requires AWS credentials)
```bash
# Run a case against QA (golden path: SQS)
itk run --case cases/my-case.yaml --out artifacts/run-001

# Derive cases from CloudWatch logs (not yet implemented)
itk derive --entrypoint sqs_event --since 24h --out cases/derived
```

## Entrypoint Modes

**SQS is the golden path** for integration testing:

| Mode | Description | Use Case |
|------|-------------|----------|
| `publish_sqs` | Publish to SQS queue | Full async flow, most realistic |
| `invoke_lambda` | Direct Lambda invocation | Fast debug mode, synchronous |

Example case configuration:
```yaml
entrypoint:
  type: sqs_event
  target:
    mode: publish_sqs  # or invoke_lambda for fast debug
    target_arn_or_url: "https://sqs.REGION.amazonaws.com/ACCOUNT/QUEUE"
  payload:
    Records:
      - messageId: "..."
        body:
          request:
            userMessage: "hello"
```

## Output Artifacts

| File | Description |
|------|-------------|
| `trace-viewer.html` | **Primary** - Interactive SVG sequence diagram |
| `timeline.html` | Waterfall timeline visualization |
| `sequence.mmd` | Mermaid sequence diagram (GitHub-compatible) |
| `sequence.html` | Legacy Mermaid-rendered HTML diagram |
| `thumbnail.svg` | Mini sequence preview for suite report |
| `spans.jsonl` | All spans in JSONL format |
| `report.md` | Human-readable summary with invariant results |
| `payloads/*.json` | Request/response payloads |
| `logging-gaps.md` | (audit only) Missing fields report |

## Suite Report

When running `itk suite`, open `index.html` to see:
- Summary cards (total, passed, warning, failed, error)
- Status icons: ✅ Passed, ⚠️ Warning (retries/errors), ❌ Failed, 💥 Error
- Modal viewers for Sequence and Timeline diagrams
- Search and filter controls

## Minimal recommended change (optional but high value)

If acceptable, inject an `ITK_TRACE_ID` into:
- SQS message attributes
- Bedrock `sessionState.sessionAttributes`

Then log one JSON line at WARN at each boundary with that id:

```json
{
  "span_id": "unique-id",
  "component": "lambda:my-function",
  "operation": "InvokeLambda",
  "ts_start": "2026-01-15T12:00:00.000Z",
  "lambda_request_id": "aws-request-id",
  "itk_trace_id": "your-trace-id",
  "request": { ... }
}
```

## Correlation IDs

ITK uses these IDs to correlate events across log groups:

| ID | Source | Best For |
|----|--------|----------|
| `itk_trace_id` | Injected by ITK | Full correlation (if injected) |
| `lambda_request_id` | Lambda context | Lambda-to-Lambda calls |
| `bedrock_session_id` | Bedrock Agent | Agent orchestration |
| `xray_trace_id` | X-Ray header | Distributed tracing |
| `sqs_message_id` | SQS record | SQS event triggers |
