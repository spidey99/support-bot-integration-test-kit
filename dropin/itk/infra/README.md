# ITK Test Infrastructure

This folder contains scripts to create minimal AWS infrastructure for testing ITK live mode.

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  SQS Queue  │────▶│ Supervisor Agent │────▶│  Worker Agent   │────▶│ Lambda + Haiku   │
│             │     │  (itk-supervisor)│     │  (itk-worker)   │     │(itk-haiku-invoke)│
└─────────────┘     └──────────────────┘     └─────────────────┘     └──────────────────┘
```

## Setup Order

1. `setup-iam.ps1` - Create IAM roles and policies
2. `setup-lambda.ps1` - Deploy the Haiku invoker Lambda
3. `setup-agents.ps1` - Create Bedrock agents
4. `setup-sqs.ps1` - Create SQS queue with trigger

## Teardown

Run `teardown-all.ps1` to delete all resources.

## Cost Estimate

- Lambda: Free tier (1M requests/month)
- SQS: Free tier (1M requests/month)  
- Bedrock Agents: ~$0.01 per agent invocation
- Claude 3.5 Haiku: ~$0.25/M input tokens, $1.25/M output tokens

For ITK testing, expect < $1/month with light usage.
