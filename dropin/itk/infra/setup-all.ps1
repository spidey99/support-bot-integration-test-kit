# ITK Infrastructure Setup - ALL IN ONE
# Creates the complete test infrastructure in one go

$ErrorActionPreference = "Stop"
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ITK Test Infrastructure Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Verify AWS access
Write-Host "Verifying AWS access..." -ForegroundColor Yellow
$identity = aws sts get-caller-identity --output json | ConvertFrom-Json
Write-Host "  Account: $($identity.Account)" -ForegroundColor Green
Write-Host "  User: $($identity.Arn)" -ForegroundColor Green

# Confirm
Write-Host ""
Write-Host "This will create:" -ForegroundColor Yellow
Write-Host "  - IAM roles (itk-lambda-role, itk-bedrock-agent-role)"
Write-Host "  - Lambda function (itk-haiku-invoker)"
Write-Host "  - Bedrock agents (itk-supervisor, itk-worker)"
Write-Host "  - SQS queue (itk-test-queue)"
Write-Host ""
$confirm = Read-Host "Continue? (y/n)"
if ($confirm -ne "y") {
    Write-Host "Aborted." -ForegroundColor Red
    exit 1
}

# Run each setup script
Write-Host "`n"

# Step 1: IAM
Write-Host "Step 1/4: Setting up IAM roles..." -ForegroundColor Cyan
& "$SCRIPT_DIR\setup-iam.ps1"

# Step 2: Lambda
Write-Host "`nStep 2/4: Deploying Lambda..." -ForegroundColor Cyan
& "$SCRIPT_DIR\setup-lambda.ps1"

# Step 3: Agents
Write-Host "`nStep 3/4: Creating Bedrock Agents..." -ForegroundColor Cyan
& "$SCRIPT_DIR\setup-agents.ps1"

# Step 4: SQS
Write-Host "`nStep 4/4: Creating SQS Queue..." -ForegroundColor Cyan
& "$SCRIPT_DIR\setup-sqs.ps1"

# Done!
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Your test infrastructure is ready:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  SQS Queue ──▶ Supervisor Agent ──▶ Worker Agent ──▶ Lambda ──▶ Claude 3.5 Haiku"
Write-Host ""
Write-Host "Configuration saved to: dropin/itk/.env.live" -ForegroundColor Yellow
Write-Host ""
Write-Host "To test:" -ForegroundColor Cyan
Write-Host "  cd dropin/itk"
Write-Host "  cp .env.live .env"
Write-Host "  itk run --mode live --case cases/example-001.yaml --out artifacts/live-test/"
Write-Host ""
