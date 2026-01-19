# ITK Infrastructure Setup - SQS Queue
# Run after setup-agents.ps1 (optional)

$ErrorActionPreference = "Stop"
$ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$REGION = "us-east-1"

Write-Host "Creating SQS Queue for ITK testing..." -ForegroundColor Cyan

# ============================================================
# 1. Create SQS Queue
# ============================================================
Write-Host "`n[1/2] Creating SQS Queue..." -ForegroundColor Yellow

$queueUrl = aws sqs create-queue `
    --queue-name itk-test-queue `
    --attributes MessageRetentionPeriod=86400,VisibilityTimeout=60 `
    --region $REGION `
    --query QueueUrl `
    --output text

Write-Host "  Created: itk-test-queue" -ForegroundColor Green
Write-Host "  URL: $queueUrl" -ForegroundColor Gray

# ============================================================
# 2. Update .env.live with SQS info
# ============================================================
Write-Host "`n[2/2] Updating configuration..." -ForegroundColor Yellow

$envPath = Join-Path (Split-Path -Parent $PSScriptRoot) ".env.live"
if (Test-Path $envPath) {
    Add-Content -Path $envPath -Value ""
    Add-Content -Path $envPath -Value "# SQS Queue"
    Add-Content -Path $envPath -Value "ITK_SQS_QUEUE_URL=$queueUrl"
    Write-Host "  Updated: .env.live" -ForegroundColor Green
}

Write-Host "`n✅ SQS Queue created successfully!" -ForegroundColor Green
Write-Host "   Queue: itk-test-queue"
Write-Host "   URL: $queueUrl"

Write-Host "`n📋 Full architecture ready:" -ForegroundColor Cyan
Write-Host "   SQS (itk-test-queue)"
Write-Host "     └─▶ Supervisor Agent (itk-supervisor)"
Write-Host "           └─▶ Worker Agent (itk-worker)"
Write-Host "                 └─▶ Lambda (itk-haiku-invoker)"
Write-Host "                       └─▶ Claude 3.5 Haiku"
Write-Host ""
Write-Host "To test the full flow, use:" -ForegroundColor Yellow
Write-Host "  itk run --mode live --case cases/live-supervisor-001.yaml --out artifacts/live-test/"
