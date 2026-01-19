# ITK Infrastructure Setup - ALL IN ONE (Fixed for no-hang)
# Run with: $env:AWS_PROFILE='itk-mfa'; .\setup-quick.ps1

$ErrorActionPreference = "Stop"
$REGION = "us-east-1"

Write-Host "ITK Infrastructure Setup" -ForegroundColor Cyan
Write-Host "========================" -ForegroundColor Cyan

$ACCOUNT_ID = aws sts get-caller-identity --query Account --output text
Write-Host "Account: $ACCOUNT_ID"

# 1. Create Lambda role
Write-Host "`n[1/8] Creating Lambda role..." -ForegroundColor Yellow
$trustPolicy = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam create-role --role-name itk-lambda-role --assume-role-policy-document $trustPolicy --output text 2>$null
aws iam attach-role-policy --role-name itk-lambda-role --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole --output text 2>$null

$bedrockPolicy = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["bedrock:InvokeModel"],"Resource":"*"}]}'
aws iam put-role-policy --role-name itk-lambda-role --policy-name BedrockInvoke --policy-document $bedrockPolicy --output text 2>$null
Write-Host "  Done: itk-lambda-role" -ForegroundColor Green

# 2. Create Agent role
Write-Host "[2/8] Creating Agent role..." -ForegroundColor Yellow
$agentTrust = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"bedrock.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam create-role --role-name itk-bedrock-agent-role --assume-role-policy-document $agentTrust --output text 2>$null

$agentPolicy = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["bedrock:InvokeModel","lambda:InvokeFunction","bedrock:InvokeAgent"],"Resource":"*"}]}'
aws iam put-role-policy --role-name itk-bedrock-agent-role --policy-name AgentPolicy --policy-document $agentPolicy --output text 2>$null
Write-Host "  Done: itk-bedrock-agent-role" -ForegroundColor Green

# 3. Wait for IAM propagation
Write-Host "[3/8] Waiting 10s for IAM..." -ForegroundColor Yellow
Start-Sleep -Seconds 10
Write-Host "  Done" -ForegroundColor Green

# 4. Package Lambda
Write-Host "[4/8] Packaging Lambda..." -ForegroundColor Yellow
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$lambdaDir = Join-Path $scriptDir "lambda\itk_haiku_invoker"
$zipPath = Join-Path $scriptDir "lambda.zip"
Push-Location $lambdaDir
Compress-Archive -Path "handler.py" -DestinationPath $zipPath -Force
Pop-Location
Write-Host "  Done: lambda.zip" -ForegroundColor Green

# 5. Create Lambda
Write-Host "[5/8] Creating Lambda function..." -ForegroundColor Yellow
$roleArn = "arn:aws:iam::${ACCOUNT_ID}:role/itk-lambda-role"
aws lambda create-function --function-name itk-haiku-invoker --runtime python3.12 --role $roleArn --handler handler.lambda_handler --zip-file fileb://$zipPath --timeout 30 --memory-size 256 --region $REGION --output text 2>$null
Write-Host "  Done: itk-haiku-invoker" -ForegroundColor Green

# 6. Wait for Lambda
Write-Host "[6/8] Waiting for Lambda active..." -ForegroundColor Yellow
Start-Sleep -Seconds 5
Write-Host "  Done" -ForegroundColor Green

# 7. Create SQS
Write-Host "[7/8] Creating SQS queue..." -ForegroundColor Yellow
$queueUrl = aws sqs create-queue --queue-name itk-test-queue --region $REGION --query QueueUrl --output text 2>$null
Write-Host "  Done: $queueUrl" -ForegroundColor Green

# 8. Save config
Write-Host "[8/8] Saving config..." -ForegroundColor Yellow
$envContent = @"
ITK_MODE=live
AWS_REGION=$REGION
AWS_PROFILE=itk-mfa
ITK_LAMBDA_FUNCTION=itk-haiku-invoker
ITK_SQS_QUEUE_URL=$queueUrl
ITK_LOG_GROUPS=/aws/lambda/itk-haiku-invoker
"@
$envPath = Join-Path (Split-Path -Parent $scriptDir) ".env.live"
$envContent | Out-File -FilePath $envPath -Encoding utf8
Write-Host "  Done: .env.live" -ForegroundColor Green

# Cleanup
Remove-Item $zipPath -ErrorAction SilentlyContinue

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "Lambda: itk-haiku-invoker"
Write-Host "Queue:  itk-test-queue"
Write-Host "Config: .env.live"
