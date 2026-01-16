# Cases

Test case YAML files validated by `schemas/itk.case.schema.json`.

## Example Cases

| Case | Purpose |
|------|---------|
| `example-001.yaml` | Generic template example |
| `sqs_basic_message.yaml` | SQS message flow (happy path) |
| `sqs_retry_scenario.yaml` | SQS with retries (tests warning status) |
| `agent_gatekeeper_basic.yaml` | Bedrock agent invocation |
| `agent_model_invocation.yaml` | Model invocation within agent |
| `lambda_direct_invoke.yaml` | Direct Lambda invocation |

## Demo Cases

| Case | Purpose |
|------|---------|
| `demo-failure-001.yaml` | Demonstrates FAILED status (`no_error_spans` invariant) |
| `demo-warning-001.yaml` | Demonstrates WARNING status (retries present) |

## Tier 3 Derived Cases

When ITK runs in live mode, `itk derive` generates cases from CloudWatch logs:
- Output: `cases/derived/*.yaml`
- These represent real production paths for regression testing
