# ITK: Run a Single Case

Use this prompt to run a single integration test case against deployed QA resources.

## Prerequisites
- ITK installed: `pip install -e tools/itk[dev]`
- AWS credentials configured for QA environment
- Case YAML file with valid target configuration (not placeholder values)

## Quick Start

**Offline mode** (for testing without AWS):
```bash
itk run --mode dev-fixtures --case cases/example-001.yaml --out artifacts/run-001
```

**Online mode** (requires AWS credentials):
```bash
itk run --case cases/my-case.yaml --out artifacts/run-001
```

## What Happens

### Offline Mode (`--mode dev-fixtures`)
1. Loads the case YAML
2. Finds the fixture file (from `fixture:` field or sibling `.jsonl`)
3. Parses fixture logs into spans
4. Runs invariant checks
5. Renders sequence diagram
6. Writes artifacts to output directory

### Online Mode (Tier 3)
1. Validates the case YAML against schema
2. Replays the entrypoint (SQS publish or Lambda invoke)
3. Waits for processing (configurable timeout)
4. Pulls CloudWatch logs for the time window
5. Correlates logs using IDs (lambda_request_id, session_id, etc.)
6. Builds spans from correlated events
7. Optionally merges Bedrock traces for enhanced detail
8. Runs invariant checks
9. Renders sequence diagram
10. Writes all artifacts

## Output Artifacts

After running, check the output directory:

| File | Description |
|------|-------------|
| `trace-viewer.html` | **Primary** - Interactive SVG sequence diagram |
| `timeline.html` | Waterfall timeline visualization |
| `sequence.mmd` | Mermaid sequence diagram (GitHub-compatible) |
| `spans.jsonl` | All spans in JSONL format |
| `report.md` | Human-readable summary with invariant results |
| `payloads/*.json` | Request/response payloads per span |

## Troubleshooting

**"No fixture found"** - Add a `fixture:` field to your case YAML pointing to a `.jsonl` file.

**"target_arn_or_url has placeholder value"** - Replace `REPLACE_ME` with actual Lambda ARN or SQS URL.

**Missing spans** - Run `itk audit --case ... --mode dev-fixtures --out ...` to identify logging gaps.

## Golden Path: SQS

For most comprehensive testing, use SQS as the entrypoint:

```yaml
entrypoint:
  type: sqs_event
  target:
    mode: publish_sqs  # Full async flow
    target_arn_or_url: "https://sqs.REGION.amazonaws.com/ACCOUNT/QUEUE_NAME"
```

For faster iteration during development, use Lambda direct:

```yaml
entrypoint:
  type: sqs_event
  target:
    mode: invoke_lambda  # Synchronous, faster feedback
    target_arn_or_url: "arn:aws:lambda:REGION:ACCOUNT:function:FUNCTION_NAME"
```
