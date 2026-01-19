# ITK Infrastructure Setup - Lambda Function
# Run after setup-iam.ps1

$ErrorActionPreference = "Stop"
$ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$REGION = "us-east-1"
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Deploying ITK Lambda functions..." -ForegroundColor Cyan

# ============================================================
# 1. Package the Lambda
# ============================================================
Write-Host "`n[1/3] Packaging Lambda code..." -ForegroundColor Yellow

$lambdaDir = Join-Path $SCRIPT_DIR "lambda\itk_haiku_invoker"
$zipPath = Join-Path $SCRIPT_DIR "lambda\itk-haiku-invoker.zip"

# Create zip file
Push-Location $lambdaDir
Compress-Archive -Path "handler.py" -DestinationPath $zipPath -Force
Pop-Location

Write-Host "  Created: itk-haiku-invoker.zip" -ForegroundColor Green

# ============================================================
# 2. Create or Update Lambda
# ============================================================
Write-Host "`n[2/3] Deploying Lambda function..." -ForegroundColor Yellow

$roleArn = "arn:aws:iam::${ACCOUNT_ID}:role/itk-lambda-role"

# Check if function exists
$functionExists = $false
try {
    aws lambda get-function --function-name itk-haiku-invoker 2>$null | Out-Null
    $functionExists = $true
} catch {}

if ($functionExists) {
    # Update existing function
    aws lambda update-function-code `
        --function-name itk-haiku-invoker `
        --zip-file fileb://$zipPath `
        --region $REGION | Out-Null
    Write-Host "  Updated: itk-haiku-invoker" -ForegroundColor Green
} else {
    # Create new function
    aws lambda create-function `
        --function-name itk-haiku-invoker `
        --runtime python3.12 `
        --role $roleArn `
        --handler handler.lambda_handler `
        --zip-file fileb://$zipPath `
        --timeout 30 `
        --memory-size 256 `
        --region $REGION `
        --description "ITK test Lambda - wraps Claude 3.5 Haiku" | Out-Null
    Write-Host "  Created: itk-haiku-invoker" -ForegroundColor Green
}

# ============================================================
# 3. Wait for Lambda to be active
# ============================================================
Write-Host "`n[3/3] Waiting for Lambda to be active..." -ForegroundColor Yellow

$maxWait = 30
$waited = 0
while ($waited -lt $maxWait) {
    $state = aws lambda get-function --function-name itk-haiku-invoker --query "Configuration.State" --output text --region $REGION
    if ($state -eq "Active") {
        break
    }
    Start-Sleep -Seconds 2
    $waited += 2
}

# Cleanup
Remove-Item $zipPath -ErrorAction SilentlyContinue

Write-Host "`n✅ Lambda deployed successfully!" -ForegroundColor Green
Write-Host "   Function: itk-haiku-invoker"
Write-Host "   Runtime: Python 3.12"
Write-Host "   Region: $REGION"

# Test invocation
Write-Host "`nTesting Lambda..." -ForegroundColor Yellow
$testPayload = '{"prompt": "Say hello in exactly 5 words."}'
$testResult = aws lambda invoke `
    --function-name itk-haiku-invoker `
    --payload $testPayload `
    --region $REGION `
    --cli-binary-format raw-in-base64-out `
    response.json 2>&1

$response = Get-Content response.json | ConvertFrom-Json
Remove-Item response.json -ErrorAction SilentlyContinue

if ($response.statusCode -eq 200) {
    Write-Host "  Test passed! Response: $($response.body.message)" -ForegroundColor Green
} else {
    Write-Host "  Test failed: $($response | ConvertTo-Json)" -ForegroundColor Red
}

Write-Host "`nNext: Run setup-agents.ps1" -ForegroundColor Cyan
