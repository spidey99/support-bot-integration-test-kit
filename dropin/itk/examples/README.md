# Example Cases

These are **reference examples** for documentation purposes. They are NOT meant to be run as tests.

To run ITK against live infrastructure:
1. Use `itk derive` to generate cases from your CloudWatch logs
2. Or copy an example to `cases/` and customize for your setup

## Files

- `example-001.yaml` - Basic SQS entrypoint structure
- `demo-failure-001.yaml` - Shows what a failing invariant looks like
- `demo-warning-001.yaml` - Shows warning conditions (errors/retries)
