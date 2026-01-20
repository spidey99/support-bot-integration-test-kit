# prove_it_e2e.ps1 - Full E2E test with isolated infrastructure
#
# This script:
# 1. Takes AWS credentials as input (export format from CloudShell)
# 2. Stands up isolated test infrastructure via Terraform
# 3. Invokes the Lambda to generate logs
# 4. Runs the full ITK setup flow in a fresh directory
# 5. Validates ITK can discover, view, and test against the logs
# 6. Tears down infrastructure (always, even on failure)
#
# KNOWN LIMITATION (TODO):
# Currently invokes a Lambda directly instead of a Bedrock Agent.
# ITK is designed to trace agent flows:
#   Agent Invoke → Action Group Lambda → CloudWatch Logs
# This E2E test shortcuts to:
#   Lambda Invoke → CloudWatch Logs
# A proper E2E would create an ephemeral Bedrock Agent, but agent creation
# takes several minutes which makes the test slow. For now, we validate
# the Lambda→Logs→ITK flow, which covers most of the ITK codebase.
#
# Usage:
#   .\scripts\prove_it_e2e.ps1 -Credentials @"
#   export AWS_ACCESS_KEY_ID=AKIA...
#   export AWS_SECRET_ACCESS_KEY=...
#   export AWS_SESSION_TOKEN=...
#   "@
#
# Or from a file:
#   .\scripts\prove_it_e2e.ps1 -CredentialsFile path\to\creds.txt

param(
    [string]$Credentials,
    [string]$CredentialsFile,
    [string]$Region = "us-east-1",
    [switch]$KeepInfra,  # Don't destroy infra after test (for debugging)
    [switch]$KeepTestDir  # Don't delete test directory
)

$ErrorActionPreference = "Stop"
$script:TestsPassed = 0
$script:TestsFailed = 0
$script:InfraCreated = $false
$script:TerraformDir = $null
$script:TestDir = $null

# Get script and repo locations
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ItkRoot = (Get-Item $ScriptDir).Parent.FullName
$RepoRoot = (Get-Item $ItkRoot).Parent.Parent.FullName
$TerraformE2E = Join-Path $ItkRoot "infra\terraform-e2e"

function Write-Step {
    param([string]$Message)
    Write-Host "`n" -NoNewline
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host "  $Message" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor Cyan
}

function Write-SubStep {
    param([string]$Message)
    Write-Host "`n→ $Message" -ForegroundColor Yellow
}

function Write-Pass {
    param([string]$Message)
    Write-Host "  ✅ $Message" -ForegroundColor Green
    $script:TestsPassed++
}

function Write-Fail {
    param([string]$Message)
    Write-Host "  ❌ $Message" -ForegroundColor Red
    $script:TestsFailed++
}

function Write-Info {
    param([string]$Message)
    Write-Host "  [i] $Message" -ForegroundColor Gray
}

function Parse-Credentials {
    param([string]$CredText)
    
    $creds = @{}
    foreach ($line in $CredText -split "`n") {
        $line = $line.Trim()
        if ($line -match "^export\s+(\w+)=(.+)$") {
            $key = $Matches[1]
            $value = $Matches[2].Trim('"', "'")
            $creds[$key] = $value
        }
        elseif ($line -match "^(\w+)=(.+)$") {
            $key = $Matches[1]
            $value = $Matches[2].Trim('"', "'")
            $creds[$key] = $value
        }
    }
    return $creds
}

function Cleanup {
    Write-Step "Cleanup"
    
    if ($script:InfraCreated -and -not $KeepInfra) {
        Write-SubStep "Destroying Terraform infrastructure..."
        Push-Location $script:TerraformDir
        try {
            terraform destroy -auto-approve 2>&1 | Out-Null
            Write-Pass "Infrastructure destroyed"
        }
        catch {
            Write-Fail "Failed to destroy infrastructure: $_"
            Write-Info "Manual cleanup may be required in $script:TerraformDir"
        }
        finally {
            Pop-Location
        }
    }
    elseif ($KeepInfra) {
        Write-Info "Infrastructure preserved (-KeepInfra flag)"
        Write-Info "Terraform dir: $script:TerraformDir"
    }
    
    if ($script:TestDir -and (Test-Path $script:TestDir) -and -not $KeepTestDir) {
        Remove-Item -Recurse -Force $script:TestDir -ErrorAction SilentlyContinue
        Write-Info "Test directory cleaned up"
    }
    elseif ($KeepTestDir -and $script:TestDir) {
        Write-Info "Test directory preserved: $script:TestDir"
    }
}

# Ensure cleanup runs even on error
trap {
    Write-Host "`n`n❌ ERROR: $_" -ForegroundColor Red
    Cleanup
    exit 1
}

# ============================================================================
# BANNER
# ============================================================================

Write-Host @"

╔══════════════════════════════════════════════════════════════════════════════╗
║                     ITK E2E "Prove It" Test                                  ║
║                                                                              ║
║  Full end-to-end test with isolated infrastructure                          ║
║  Terraform → Lambda → Logs → ITK Bootstrap → View → Validate                ║
╚══════════════════════════════════════════════════════════════════════════════╝

"@ -ForegroundColor Yellow

# ============================================================================
# PHASE 1: PARSE CREDENTIALS
# ============================================================================

Write-Step "Phase 1: Parse Credentials"

# Get credentials from parameter or file
if ($CredentialsFile -and (Test-Path $CredentialsFile)) {
    $Credentials = Get-Content $CredentialsFile -Raw
    Write-Info "Loaded credentials from file: $CredentialsFile"
}

if (-not $Credentials) {
    Write-Fail "No credentials provided"
    Write-Host @"

Usage:
  .\scripts\prove_it_e2e.ps1 -Credentials `@"
  export AWS_ACCESS_KEY_ID=AKIA...
  export AWS_SECRET_ACCESS_KEY=...
  export AWS_SESSION_TOKEN=...
  "`@

Or from a file:
  .\scripts\prove_it_e2e.ps1 -CredentialsFile path\to\creds.txt

Get credentials from AWS CloudShell:
  aws configure export-credentials --format env

"@ -ForegroundColor Yellow
    exit 1
}

$creds = Parse-Credentials -CredText $Credentials

if (-not $creds["AWS_ACCESS_KEY_ID"]) {
    Write-Fail "Could not parse AWS_ACCESS_KEY_ID from credentials"
    exit 1
}

Write-Pass "Parsed AWS_ACCESS_KEY_ID: $($creds["AWS_ACCESS_KEY_ID"].Substring(0, 8))..."
Write-Pass "Parsed AWS_SECRET_ACCESS_KEY: ****"
if ($creds["AWS_SESSION_TOKEN"]) {
    Write-Pass "Parsed AWS_SESSION_TOKEN: ****"
}

# Set environment variables for Terraform and AWS CLI
$env:AWS_ACCESS_KEY_ID = $creds["AWS_ACCESS_KEY_ID"]
$env:AWS_SECRET_ACCESS_KEY = $creds["AWS_SECRET_ACCESS_KEY"]
if ($creds["AWS_SESSION_TOKEN"]) {
    $env:AWS_SESSION_TOKEN = $creds["AWS_SESSION_TOKEN"]
}
$env:AWS_REGION = $Region
$env:AWS_DEFAULT_REGION = $Region

# Validate credentials work
Write-SubStep "Validating credentials with STS..."
try {
    $stsOutput = aws sts get-caller-identity --output json 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Credentials expired or invalid"
        Write-Host "  STS Error: $stsOutput" -ForegroundColor Red
        Write-Host "`n  Get fresh credentials from AWS CloudShell:" -ForegroundColor Yellow
        Write-Host "    aws configure export-credentials --format env" -ForegroundColor Cyan
        exit 1
    }
    $identity = $stsOutput | ConvertFrom-Json
    Write-Pass "Credentials valid - Account: $($identity.Account)"
}
catch {
    Write-Fail "Credentials invalid: $_"
    exit 1
}

# ============================================================================
# PHASE 2: TERRAFORM - STAND UP ISOLATED INFRA
# ============================================================================

Write-Step "Phase 2: Terraform - Stand Up Isolated Infrastructure"

# Copy terraform-e2e to temp location (so we can run in parallel if needed)
$script:TerraformDir = Join-Path $env:TEMP "itk-e2e-tf-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Copy-Item -Recurse $TerraformE2E $script:TerraformDir
Write-Info "Terraform working dir: $script:TerraformDir"

Push-Location $script:TerraformDir
try {
    Write-SubStep "Terraform init..."
    $initOutput = terraform init -input=false 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Terraform init failed"
        Write-Host $initOutput
        exit 1
    }
    Write-Pass "Terraform initialized"
    
    Write-SubStep "Terraform apply..."
    $applyOutput = terraform apply -auto-approve -input=false -var="aws_region=$Region" 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Terraform apply failed"
        Write-Host $applyOutput
        exit 1
    }
    $script:InfraCreated = $true
    Write-Pass "Infrastructure created"
    
    # Get outputs
    $lambdaName = (terraform output -raw lambda_function_name)
    $logGroup = (terraform output -raw lambda_log_group)
    $uniqueName = (terraform output -raw unique_name)
    
    Write-Pass "Lambda: $lambdaName"
    Write-Pass "Log group: $logGroup"
}
finally {
    Pop-Location
}

# ============================================================================
# PHASE 3: INVOKE LAMBDA TO GENERATE LOGS
# ============================================================================

Write-Step "Phase 3: Invoke Lambda to Generate Logs"

Write-SubStep "Invoking Lambda 3 times to generate log data..."
$traceIds = @()

for ($i = 1; $i -le 3; $i++) {
    $traceId = "e2e-test-$(Get-Date -Format 'HHmmss')-$i"
    $payload = @{
        trace_id = $traceId
        prompt = "Count from 1 to $i in words."
    } | ConvertTo-Json -Compress
    
    $payloadFile = Join-Path $env:TEMP "e2e-payload-$i.json"
    $payload | Set-Content $payloadFile -Encoding UTF8
    
    $responseFile = Join-Path $env:TEMP "e2e-response-$i.json"
    
    aws lambda invoke --function-name $lambdaName --payload "fileb://$payloadFile" $responseFile 2>&1 | Out-Null
    
    if ($LASTEXITCODE -eq 0) {
        $response = Get-Content $responseFile -Raw | ConvertFrom-Json
        $body = $response.body | ConvertFrom-Json
        Write-Pass "Invocation $i - trace_id: $traceId"
        $traceIds += $traceId
    }
    else {
        Write-Fail "Invocation $i failed"
    }
    
    Start-Sleep -Seconds 1
}

Write-SubStep "Waiting 30 seconds for CloudWatch log propagation..."
Start-Sleep -Seconds 30

# VALIDATE logs actually exist before claiming success
Write-SubStep "Validating logs exist in CloudWatch..."
$logStreams = aws logs describe-log-streams --log-group-name $logGroup --order-by LastEventTime --descending --limit 1 --region $Region 2>&1 | Out-String
if ($logStreams -match '"logStreamName"') {
    # Get actual log events
    $streamName = ($logStreams | ConvertFrom-Json).logStreams[0].logStreamName
    $logEvents = aws logs get-log-events --log-group-name $logGroup --log-stream-name $streamName --limit 10 --region $Region 2>&1 | Out-String
    
    if ($logEvents -match 'span_id') {
        $eventCount = ([regex]::Matches($logEvents, 'span_id')).Count
        Write-Pass "Validated: Found $eventCount span log entries in CloudWatch"
    }
    else {
        Write-Fail "Logs exist but no span entries found - Lambda may not be emitting ITK spans"
    }
}
else {
    Write-Fail "No log streams found in $logGroup - Lambda invocations may have failed silently"
}

# ============================================================================
# PHASE 4: FRESH DIRECTORY - DERPY AGENT FLOW
# ============================================================================

Write-Step "Phase 4: Fresh Directory - Derpy Agent Flow"

$script:TestDir = Join-Path $env:TEMP "itk-e2e-test-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
New-Item -ItemType Directory -Path $script:TestDir | Out-Null
Write-Info "Test directory: $script:TestDir"

# Simulate: Copy dropin folder (like user would after clone)
Write-SubStep "Copying dropin/itk folder..."
$targetItk = Join-Path $script:TestDir "itk"
Copy-Item -Recurse $ItkRoot $targetItk
Write-Pass "Copied ITK to test directory"

# Create venv and install
Write-SubStep "Creating virtual environment..."
Push-Location $targetItk
try {
    python -m venv .venv 2>&1 | Out-Null
    Write-Pass "Created .venv"
    
    Write-SubStep "Installing ITK..."
    & .\.venv\Scripts\Activate.ps1
    $pipOutput = pip install -e ".[dev]" 2>&1 | Out-String
    if ($pipOutput -match "Successfully installed") {
        Write-Pass "Installed ITK"
    }
    else {
        Write-Fail "pip install may have failed"
        Write-Host $pipOutput
    }
    
    # Verify ITK works
    $helpOutput = itk --help 2>&1 | Out-String
    if ($helpOutput -match "usage:") {
        Write-Pass "ITK CLI is available"
    }
    else {
        Write-Fail "ITK CLI not working"
    }
}
finally {
    Pop-Location
}

# ============================================================================
# PHASE 5: PASTE CREDENTIALS INTO .ENV (AS USER WOULD)
# ============================================================================

Write-Step "Phase 5: Paste Credentials into .env"

$envFile = Join-Path $targetItk ".env"

# Write credentials in export format (exactly as user would paste from CloudShell)
$envContent = @"
# AWS Credentials (pasted from aws configure export-credentials --format env)
export AWS_ACCESS_KEY_ID=$($creds["AWS_ACCESS_KEY_ID"])
export AWS_SECRET_ACCESS_KEY=$($creds["AWS_SECRET_ACCESS_KEY"])
export AWS_SESSION_TOKEN=$($creds["AWS_SESSION_TOKEN"])
AWS_REGION=$Region

# Log groups to use (will be set by bootstrap)
"@
$envContent | Set-Content $envFile -Encoding UTF8

Write-Pass "Created .env with credentials (export format)"

# ============================================================================
# PHASE 6: RUN ITK BOOTSTRAP
# ============================================================================

Write-Step "Phase 6: Run ITK Bootstrap"

Push-Location $targetItk
try {
    & .\.venv\Scripts\Activate.ps1
    
    Write-SubStep "Running itk bootstrap..."
    $bootstrapOutput = itk bootstrap --force 2>&1 | Out-String
    Write-Host $bootstrapOutput
    
    if ($bootstrapOutput -match "Bootstrap complete") {
        Write-Pass "Bootstrap completed"
    }
    else {
        Write-Fail "Bootstrap may have failed"
    }
    
    # Verify credentials were preserved
    $envAfter = Get-Content $envFile -Raw
    if ($envAfter -match $creds["AWS_ACCESS_KEY_ID"]) {
        Write-Pass "Credentials preserved in .env"
    }
    else {
        Write-Fail "Credentials were lost from .env!"
    }
    
    # Check if log group was discovered
    if ($envAfter -match $logGroup -or $bootstrapOutput -match "log groups") {
        Write-Pass "Log group discovery ran"
    }
}
finally {
    Pop-Location
}

# ============================================================================
# PHASE 7: RUN ITK VIEW
# ============================================================================

Write-Step "Phase 7: Run ITK View"

Push-Location $targetItk
try {
    & .\.venv\Scripts\Activate.ps1
    
    # Manually set log group in .env since bootstrap may have found different ones
    $envContent = Get-Content $envFile -Raw
    if ($envContent -notmatch [regex]::Escape($logGroup)) {
        Add-Content $envFile "`nITK_LOG_GROUPS=$logGroup"
        Write-Info "Added E2E log group to .env"
    }
    
    # Use --since 15m to account for Logs Insights indexing delays on new log groups
    Write-SubStep "Running itk view --since 15m..."
    $viewOutput = itk view --since 15m --log-groups $logGroup --out artifacts/e2e-view 2>&1 | Out-String
    Write-Host $viewOutput
    
    # If 0 events, diagnose why
    if ($viewOutput -match "Fetched 0 log events") {
        Write-Fail "ITK view found 0 events - diagnosing..."
        
        # Check if logs exist via direct API (not Logs Insights)
        $directCheck = aws logs get-log-events --log-group-name $logGroup --log-stream-name (aws logs describe-log-streams --log-group-name $logGroup --order-by LastEventTime --descending --limit 1 --query "logStreams[0].logStreamName" --output text --region $Region) --limit 5 --region $Region 2>&1 | Out-String
        
        if ($directCheck -match "span_id") {
            Write-Host "  [!] Logs exist (verified via get-log-events) but Logs Insights can't find them" -ForegroundColor Yellow
            Write-Host "  [!] This is a known CloudWatch Logs Insights indexing delay on new log groups" -ForegroundColor Yellow
            Write-Host "  [!] BUG: ITK should fall back to get-log-events for new log groups" -ForegroundColor Red
        }
        else {
            Write-Host "  [!] Logs genuinely don't exist - Lambda logging may have failed" -ForegroundColor Red
        }
    }
    
    if ($viewOutput -match "Parsed (\d+) spans") {
        $spanCount = $Matches[1]
        if ([int]$spanCount -gt 0) {
            Write-Pass "Found $spanCount spans"
        }
        else {
            Write-Fail "No spans found (expected at least 6 from 3 invocations)"
        }
    }
    
    if ($viewOutput -match "Found (\d+) distinct executions") {
        $execCount = $Matches[1]
        if ([int]$execCount -ge 3) {
            Write-Pass "Found $execCount executions"
        }
        else {
            Write-Info "Found $execCount executions (expected 3)"
        }
    }
    
    # Check artifacts were created
    $galleryPath = Join-Path $targetItk "artifacts\e2e-view\index.html"
    if (Test-Path $galleryPath) {
        Write-Pass "Gallery created: artifacts/e2e-view/index.html"
    }
    else {
        Write-Fail "Gallery not created"
    }
}
finally {
    Pop-Location
}

# ============================================================================
# PHASE 8: RUN DEV-FIXTURES MODE
# ============================================================================

Write-Step "Phase 8: Run Dev-Fixtures Mode"

Push-Location $targetItk
try {
    & .\.venv\Scripts\Activate.ps1
    
    # Use render-fixture on the bundled sample fixture (doesn't require a case file)
    Write-SubStep "Running itk render-fixture (dev-fixtures validation)..."
    $runOutput = itk render-fixture --fixture fixtures/logs/sample_run_001.jsonl --out artifacts/dev-fixtures-test 2>&1 | Out-String
    Write-Host $runOutput
    
    # Check for successful artifact generation
    $traceViewer = Join-Path $targetItk "artifacts/dev-fixtures-test/trace-viewer.html"
    if (Test-Path $traceViewer) {
        Write-Pass "Dev-fixtures mode works - trace-viewer.html created"
    }
    elseif ($runOutput -match "Generated" -or $runOutput -match "trace-viewer") {
        Write-Pass "Dev-fixtures mode works"
    }
    else {
        Write-Fail "Dev-fixtures mode failed - no artifacts created"
    }
}
finally {
    Pop-Location
}

# ============================================================================
# CLEANUP & SUMMARY
# ============================================================================

Cleanup

Write-Host "`n"
$totalTests = $script:TestsPassed + $script:TestsFailed
$passRate = if ($totalTests -gt 0) { [math]::Round(($script:TestsPassed / $totalTests) * 100) } else { 0 }

if ($script:TestsFailed -eq 0) {
    Write-Host "╔══════════════════════════════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║                         ✅ ALL TESTS PASSED                                  ║" -ForegroundColor Green
    Write-Host "║                                                                              ║" -ForegroundColor Green
    Write-Host "║  Passed: $($script:TestsPassed.ToString().PadRight(3))    Failed: $($script:TestsFailed.ToString().PadRight(3))    Rate: $passRate%                              ║" -ForegroundColor Green
    Write-Host "╚══════════════════════════════════════════════════════════════════════════════╝" -ForegroundColor Green
    exit 0
}
else {
    Write-Host "╔══════════════════════════════════════════════════════════════════════════════╗" -ForegroundColor Red
    Write-Host "║                         ❌ SOME TESTS FAILED                                 ║" -ForegroundColor Red
    Write-Host "║                                                                              ║" -ForegroundColor Red
    Write-Host "║  Passed: $($script:TestsPassed.ToString().PadRight(3))    Failed: $($script:TestsFailed.ToString().PadRight(3))    Rate: $passRate%                              ║" -ForegroundColor Red
    Write-Host "╚══════════════════════════════════════════════════════════════════════════════╝" -ForegroundColor Red
    exit 1
}
