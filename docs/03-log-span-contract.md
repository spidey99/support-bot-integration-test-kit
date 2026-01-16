# Log / span contract (minimal)

The kit can work with messy logs, but it works *best* when boundaries emit a single JSON line.

If your logger only captures WARN+, emit these at WARN:
- handler start
- handler end
- each retry attempt
- final outcome

Format (example):

```json
{
  "itk": "span",
  "itkTraceId": "itk-...",
  "component": "lambda:action-foo",
  "operation": "InvokeModel",
  "attempt": 1,
  "request": {"...": "..."},
  "response": {"...": "..."},
  "error": null
}
```

The auditor will tell you which boundaries are missing critical fields.
