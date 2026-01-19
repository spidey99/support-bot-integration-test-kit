# ITK Infrastructure Setup - IAM Roles
# Run this first to create necessary IAM roles

$ErrorActionPreference = "Stop"
$ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$REGION = "us-east-1"

Write-Host "Creating IAM roles for ITK test infrastructure..." -ForegroundColor Cyan
Write-Host "Account: $ACCOUNT_ID" -ForegroundColor Gray

# ============================================================
# 1. Lambda Execution Role
# ============================================================
Write-Host "`n[1/3] Creating Lambda execution role..." -ForegroundColor Yellow

$lambdaTrustPolicy = @"
{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "lambda.amazonaws.com"},
        "Action": "sts:AssumeRole"
    }]
}
"@

$lambdaTrustPolicy | Out-File -FilePath "lambda-trust.json" -Encoding utf8

aws iam create-role `
    --role-name itk-lambda-role `
    --assume-role-policy-document file://lambda-trust.json `
    --description "ITK test Lambda execution role" 2>$null

# Attach basic execution + Bedrock invoke
aws iam attach-role-policy `
    --role-name itk-lambda-role `
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Create inline policy for Bedrock model invoke
$bedrockPolicy = @"
{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Action": [
            "bedrock:InvokeModel",
            "bedrock:InvokeModelWithResponseStream"
        ],
        "Resource": "arn:aws:bedrock:${REGION}::foundation-model/*"
    }]
}
"@

$bedrockPolicy | Out-File -FilePath "bedrock-policy.json" -Encoding utf8

aws iam put-role-policy `
    --role-name itk-lambda-role `
    --policy-name BedrockInvokePolicy `
    --policy-document file://bedrock-policy.json

Write-Host "  Created: itk-lambda-role" -ForegroundColor Green

# ============================================================
# 2. Bedrock Agent Role
# ============================================================
Write-Host "`n[2/3] Creating Bedrock Agent role..." -ForegroundColor Yellow

$agentTrustPolicy = @"
{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "bedrock.amazonaws.com"},
        "Action": "sts:AssumeRole",
        "Condition": {
            "StringEquals": {"aws:SourceAccount": "${ACCOUNT_ID}"},
            "ArnLike": {"aws:SourceArn": "arn:aws:bedrock:${REGION}:${ACCOUNT_ID}:agent/*"}
        }
    }]
}
"@

$agentTrustPolicy | Out-File -FilePath "agent-trust.json" -Encoding utf8

aws iam create-role `
    --role-name itk-bedrock-agent-role `
    --assume-role-policy-document file://agent-trust.json `
    --description "ITK test Bedrock Agent role" 2>$null

# Agent needs to invoke models and call Lambda
$agentPolicy = @"
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            "Resource": "arn:aws:bedrock:${REGION}::foundation-model/*"
        },
        {
            "Effect": "Allow",
            "Action": "lambda:InvokeFunction",
            "Resource": "arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:itk-*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeAgent",
                "bedrock:GetAgent",
                "bedrock:ListAgents"
            ],
            "Resource": "arn:aws:bedrock:${REGION}:${ACCOUNT_ID}:agent/*"
        }
    ]
}
"@

$agentPolicy | Out-File -FilePath "agent-policy.json" -Encoding utf8

aws iam put-role-policy `
    --role-name itk-bedrock-agent-role `
    --policy-name BedrockAgentPolicy `
    --policy-document file://agent-policy.json

Write-Host "  Created: itk-bedrock-agent-role" -ForegroundColor Green

# ============================================================
# 3. Wait for role propagation
# ============================================================
Write-Host "`n[3/3] Waiting for IAM role propagation (10 seconds)..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Cleanup temp files
Remove-Item lambda-trust.json, bedrock-policy.json, agent-trust.json, agent-policy.json -ErrorAction SilentlyContinue

Write-Host "`n✅ IAM roles created successfully!" -ForegroundColor Green
Write-Host "   - itk-lambda-role"
Write-Host "   - itk-bedrock-agent-role"
Write-Host "`nNext: Run setup-lambda.ps1" -ForegroundColor Cyan
