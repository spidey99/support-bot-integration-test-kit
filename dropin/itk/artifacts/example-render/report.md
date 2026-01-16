# ITK Run Report

## Summary
- **Spans**: 3
- **Components**: 3

## Spans

| Span ID | Component | Operation | Has Request | Has Response |
|---------|-----------|-----------|-------------|--------------|
| span-001 | entrypoint:sqs_event | InvokeLambda | ✅ | ✅ |
| span-002 | agent:gatekeeper | InvokeAgent | ✅ | ✅ |
| span-003 | lambda:actionGroupFoo | InvokeModel | ✅ | ✅ |

## Artifacts
- `spans.jsonl`: Raw span data
- `payloads/`: Request/response JSON files
- `sequence.mmd`: Mermaid sequence diagram
