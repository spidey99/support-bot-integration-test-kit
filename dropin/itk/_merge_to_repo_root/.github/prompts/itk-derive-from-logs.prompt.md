# ITK: Derive Cases from CloudWatch Logs

Use this prompt when you need to create new test cases from production/QA CloudWatch logs.

## Prerequisites
- AWS credentials configured for the target environment
- CloudWatch Logs access to relevant log groups

## Steps

1. **Identify the log groups** containing your Lambda, Bedrock Agent, and SQS logs.

2. **Run the derive command** (not yet fully implemented - manual steps below):

```bash
# Example: Find recent successful requests
itk derive --entrypoint sqs_event --since 24h --out cases/derived
```

3. **Manual derivation** (until derive is fully implemented):

Query CloudWatch Logs Insights to find representative requests:

```sql
fields @timestamp, @message
| filter @message like /span_id/ or @message like /itk_trace_id/
| sort @timestamp desc
| limit 100
```

4. **Extract a case YAML** from the discovered events:

```yaml
id: derived-001
name: Derived from prod logs - [describe the scenario]
fixture: ../fixtures/logs/derived-001.jsonl  # Save filtered logs here
entrypoint:
  type: sqs_event
  target:
    mode: invoke_lambda
    target_arn_or_url: "arn:aws:lambda:REGION:ACCOUNT:function:FUNCTION_NAME"
  payload:
    Records:
      - messageId: "[from logs]"
        body:
          request:
            userMessage: "[from logs]"
expected:
  invariants:
    - name: has_spans
```

5. **Save the relevant log lines** as a JSONL fixture file.

6. **Validate offline**:

```bash
itk run --mode dev-fixtures --case cases/derived/derived-001.yaml --out artifacts/test-001
```

## Tips

- Look for `lambda_request_id`, `bedrock_session_id`, or `itk_trace_id` fields to correlate events
- Capture both happy-path and error scenarios
- Include at least one case with retry behavior (attempt > 1)
- Redact any PII before committing fixtures
