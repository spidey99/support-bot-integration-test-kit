<!-- ITK_BEGIN -->
# ITK rules (Tier 3 / work repo)

You are working inside the work repo with AWS access.

## Non-negotiables
- Do NOT invent request formats. Cases must come from logs or explicit schemas.
- Every run must emit a sequence diagram and payload files.
- If a diagram step is missing, run `itk audit` and implement the required minimal logs.
- SQS is the **golden path** for integration testing (full async flow).
- Lambda direct is the **secondary fast-debug mode** (synchronous).

## Where ITK lives
- `tools/itk/src/itk/cli.py` - Main CLI entry point
- `tools/itk/src/itk/diagrams/mermaid_seq.py` - Mermaid rendering
- `tools/itk/src/itk/correlation/stitch_graph.py` - Span stitching
- `tools/itk/src/itk/logs/cloudwatch_fetch.py` - CloudWatch queries
- `tools/itk/src/itk/entrypoints/` - SQS, Lambda, Bedrock adapters
- `tools/itk/schemas/` - JSON schemas for cases, spans, config

## Definition of done
`itk run --case <id> --out artifacts/<run-id>` produces:
- `sequence.mmd` - Mermaid sequence diagram
- `spans.jsonl` - Normalized span data
- `payloads/*.json` - Request/response payloads
- `report.md` - Human-readable summary

## Commands

### Run a case (online)
```bash
itk run --case cases/example-001.yaml --out artifacts/run-001
```

### Run a case (offline with fixtures)
```bash
itk run --offline --case cases/example-001.yaml --out artifacts/run-001
```

### Audit logging gaps
```bash
itk audit --offline --case cases/example-001.yaml --out artifacts/audit-001
```

### Render fixture directly
```bash
itk render-fixture --fixture fixtures/logs/sample.jsonl --out artifacts/render-001
```

## Tips
- Use `itk audit --offline` to identify missing log fields before running online
- Check `logging-gaps.md` for recommended log format changes
- Correlation IDs to look for: `lambda_request_id`, `bedrock_session_id`, `itk_trace_id`, `xray_trace_id`

Explain changes like teaching a child.
<!-- ITK_END -->
