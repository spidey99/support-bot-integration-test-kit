# Test case format

A test case is YAML, validated by `schemas/itk.case.schema.json`.

Key idea: **never invent request formats**. Cases should be **derived from logs**.

## Minimal fields

- `id` - Unique case identifier
- `name` - Human-readable name
- `entrypoint.type` - One of: `sqs_event | lambda_invoke | bedrock_invoke_agent | http`
- `entrypoint.target` - Where to send the request
- `entrypoint.payload` - Raw JSON payload
- `expected.invariants` - Structural checks (not exact model text)

## Bedrock Agent Example

```yaml
id: agent-hello
name: Basic agent greeting test
entrypoint:
  type: bedrock_invoke_agent
  target:
    agent_id: XXXXXXXXXX      # Your Bedrock Agent ID
    agent_alias_id: TSTALIASID # Alias ID (TSTALIASID for test alias)
  payload:
    inputText: "Hello, what can you help me with?"
    sessionId: "test-session-001"
    enableTrace: true
expected:
  invariants:
    - name: has_spans
```

## SQS Event Example

```yaml
id: sqs-trigger-001
name: SQS message triggers Lambda
entrypoint:
  type: sqs_event
  target:
    mode: invoke_lambda
    target_arn_or_url: "arn:aws:lambda:us-east-1:123456789012:function:MyFunction"
  payload:
    Records:
      - messageId: "00000000-0000-0000-0000-000000000000"
        body:
          request:
            userMessage: "hello"
expected:
  invariants:
    - name: has_spans
```

## Lambda Invoke Example

```yaml
id: lambda-direct-001
name: Direct Lambda invocation
entrypoint:
  type: lambda_invoke
  target:
    function_name: "my-function"
  payload:
    action: "process"
    data: { "key": "value" }
expected:
  invariants:
    - name: has_spans
```
