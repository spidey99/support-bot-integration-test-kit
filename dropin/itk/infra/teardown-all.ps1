# ITK Infrastructure Teardown - Delete All Resources
# Run this to clean up all ITK test infrastructure

$ErrorActionPreference = "Continue"
$ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$REGION = "us-east-1"

Write-Host "Tearing down ITK test infrastructure..." -ForegroundColor Yellow
Write-Host "Account: $ACCOUNT_ID" -ForegroundColor Gray

# ============================================================
# 1. Delete SQS Queue
# ============================================================
Write-Host "`n[1/5] Deleting SQS Queue..." -ForegroundColor Yellow
$queueUrl = aws sqs get-queue-url --queue-name itk-test-queue --region $REGION --query QueueUrl --output text 2>$null
if ($queueUrl) {
    aws sqs delete-queue --queue-url $queueUrl --region $REGION 2>$null
    Write-Host "  Deleted: itk-test-queue" -ForegroundColor Green
} else {
    Write-Host "  Not found: itk-test-queue" -ForegroundColor Gray
}

# ============================================================
# 2. Delete Bedrock Agents
# ============================================================
Write-Host "`n[2/5] Deleting Bedrock Agents..." -ForegroundColor Yellow

# Get agent IDs
$agents = aws bedrock-agent list-agents --region $REGION --output json 2>$null | ConvertFrom-Json
foreach ($agent in $agents.agentSummaries) {
    if ($agent.agentName -like "itk-*") {
        # Delete aliases first
        $aliases = aws bedrock-agent list-agent-aliases --agent-id $agent.agentId --region $REGION --output json 2>$null | ConvertFrom-Json
        foreach ($alias in $aliases.agentAliasSummaries) {
            if ($alias.agentAliasName -ne "TSTALIASID") {
                aws bedrock-agent delete-agent-alias `
                    --agent-id $agent.agentId `
                    --agent-alias-id $alias.agentAliasId `
                    --region $REGION 2>$null | Out-Null
                Write-Host "  Deleted alias: $($agent.agentName)/$($alias.agentAliasName)" -ForegroundColor Green
            }
        }
        
        # Delete agent
        aws bedrock-agent delete-agent --agent-id $agent.agentId --region $REGION 2>$null | Out-Null
        Write-Host "  Deleted agent: $($agent.agentName)" -ForegroundColor Green
    }
}

# ============================================================
# 3. Delete Lambda
# ============================================================
Write-Host "`n[3/5] Deleting Lambda functions..." -ForegroundColor Yellow
aws lambda delete-function --function-name itk-haiku-invoker --region $REGION 2>$null
Write-Host "  Deleted: itk-haiku-invoker" -ForegroundColor Green

# ============================================================
# 4. Delete IAM Roles
# ============================================================
Write-Host "`n[4/5] Deleting IAM roles..." -ForegroundColor Yellow

# Lambda role
aws iam delete-role-policy --role-name itk-lambda-role --policy-name BedrockInvokePolicy 2>$null
aws iam detach-role-policy --role-name itk-lambda-role --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole 2>$null
aws iam delete-role --role-name itk-lambda-role 2>$null
Write-Host "  Deleted: itk-lambda-role" -ForegroundColor Green

# Agent role
aws iam delete-role-policy --role-name itk-bedrock-agent-role --policy-name BedrockAgentPolicy 2>$null
aws iam delete-role --role-name itk-bedrock-agent-role 2>$null
Write-Host "  Deleted: itk-bedrock-agent-role" -ForegroundColor Green

# ============================================================
# 5. Delete CloudWatch Log Groups
# ============================================================
Write-Host "`n[5/5] Deleting CloudWatch Log Groups..." -ForegroundColor Yellow
aws logs delete-log-group --log-group-name /aws/lambda/itk-haiku-invoker --region $REGION 2>$null
Write-Host "  Deleted: /aws/lambda/itk-haiku-invoker" -ForegroundColor Green

# ============================================================
# Done
# ============================================================
Write-Host "`n✅ Teardown complete!" -ForegroundColor Green
Write-Host "All ITK test resources have been deleted."
