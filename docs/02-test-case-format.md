# Test case format

A test case is YAML, validated by `schemas/itk.case.schema.json`.

Key idea: **never invent request formats**. Cases should be **derived from logs**.

Minimal fields:
- `id`
- `name`
- `entrypoint.type` (sqs_event | lambda_invoke | bedrock_invoke_agent | http)
- `entrypoint.target`
- `entrypoint.payload` (raw JSON payload)
- `expected.invariants` (structural checks, not exact model text)
