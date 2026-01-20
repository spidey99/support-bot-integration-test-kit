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

## Agent Version Targeting

Bedrock Agents support versioned aliases, allowing you to test against specific agent versions:

```yaml
entrypoint:
  type: bedrock_invoke_agent
  target:
    agent_id: XXXXXXXXXX
    agent_alias_id: TSTALIASID  # Test alias (draft version)
```

### Alias Types

| Alias | Purpose |
|-------|---------|
| `TSTALIASID` | Built-in test alias - always points to DRAFT version |
| Custom alias | User-created, points to specific prepared version |

### Testing Version Upgrades

To test a new agent version before promoting to production:

1. **Prepare** the new agent version in Bedrock console
2. **Create test alias** pointing to new version
3. **Update test case** to use new alias:
   ```yaml
   target:
     agent_alias_id: "NEW_VERSION_ALIAS"
   ```
4. **Run ITK suite** against new version
5. **Compare** results with baseline (`itk compare`)
6. **Promote** alias to production if tests pass

### A/B Testing Pattern

Run the same test against multiple versions to compare behavior:

```yaml
# cases/v1-greeting.yaml
id: greeting-v1
entrypoint:
  target:
    agent_alias_id: PROD_ALIAS_V1

# cases/v2-greeting.yaml  
id: greeting-v2
entrypoint:
  target:
    agent_alias_id: CANDIDATE_ALIAS_V2
```

Then compare outputs:
```bash
itk run --case cases/v1-greeting.yaml --out artifacts/v1/
itk run --case cases/v2-greeting.yaml --out artifacts/v2/
itk compare artifacts/v1/ artifacts/v2/ --out artifacts/comparison/
```
