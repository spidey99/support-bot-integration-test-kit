# prove_it.ps1 - End-to-end simulation of agent setup flow
# 
# This script does EXACTLY what a derpy agent would do following agent-test-prompt.md
# Run this before pushing to verify the flow actually works.
#
# Usage:
#   .\scripts\prove_it.ps1 -CredentialsFile path\to\creds.txt
#   .\scripts\prove_it.ps1 -SkipCredentials  # For offline/fixture testing only
#
# The credentials file should contain the output of:
#   aws configure export-credentials --format env

param(
    [string]$CredentialsFile,
    [switch]$SkipCredentials,
    [switch]$KeepTestDir,
    [string]$TestDir = "$env:TEMP\itk-prove-it-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
)

$ErrorActionPreference = "Stop"
$script:TestsPassed = 0
$script:TestsFailed = 0

function Write-Step {
    param([string]$Message)
    Write-Host "`n=== $Message ===" -ForegroundColor Cyan
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

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if ($Condition) {
        Write-Pass $Message
    } else {
        Write-Fail $Message
        throw "Assertion failed: $Message"
    }
}

function Assert-Contains {
    param([string]$Content, [string]$Substring, [string]$Message)
    if ($Content -match [regex]::Escape($Substring)) {
        Write-Pass $Message
    } else {
        Write-Fail "$Message (expected to find: $Substring)"
        throw "Assertion failed: $Message"
    }
}

function Assert-NotContains {
    param([string]$Content, [string]$Substring, [string]$Message)
    if ($Content -notmatch [regex]::Escape($Substring)) {
        Write-Pass $Message
    } else {
        Write-Fail "$Message (should NOT contain: $Substring)"
        throw "Assertion failed: $Message"
    }
}

# ============================================================================
# SETUP
# ============================================================================

Write-Host @"

╔══════════════════════════════════════════════════════════════════════════════╗
║                         ITK "Prove It" Test                                  ║
║                                                                              ║
║  This simulates exactly what a derpy agent would do following the prompt.   ║
║  If this passes, the setup flow works.                                       ║
╚══════════════════════════════════════════════════════════════════════════════╝

"@ -ForegroundColor Yellow

Write-Step "Setup"
Write-Host "  Test directory: $TestDir"

# Get the repo root (parent of dropin/itk)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Get-Item $ScriptDir).Parent.Parent.Parent.FullName
Write-Host "  Repo root: $RepoRoot"

# Check for unpushed commits
$gitStatus = git -C $RepoRoot status -sb 2>&1
if ($gitStatus -match "ahead") {
    Write-Host ""
    Write-Host "  ⚠️  WARNING: You have unpushed commits!" -ForegroundColor Yellow
    Write-Host "  The test will use LOCAL code, but real users will clone from GitHub." -ForegroundColor Yellow
    Write-Host "  Consider pushing before running this test." -ForegroundColor Yellow
    Write-Host ""
}

# Create test directory
if (Test-Path $TestDir) {
    Remove-Item -Recurse -Force $TestDir
}
New-Item -ItemType Directory -Path $TestDir | Out-Null
Write-Pass "Created test directory"

# ============================================================================
# PHASE 1: INSTALL ITK (simulating git clone)
# ============================================================================

Write-Step "Phase 1: Install ITK"

# Copy dropin folder (simulating what user does after clone)
$SourceDropin = Join-Path $RepoRoot "dropin\itk"
$TargetItk = Join-Path $TestDir "itk"
Copy-Item -Recurse $SourceDropin $TargetItk
Assert-True (Test-Path $TargetItk) "Copied dropin folder"

# Verify no .env exists yet (should be gitignored)
$EnvFile = Join-Path $TargetItk ".env"
# Note: .env might exist if someone has it locally, that's OK for this test
# The real test is that bootstrap handles it correctly

# Create venv and install
Push-Location $TargetItk
try {
    python -m venv .venv
    Assert-True (Test-Path ".venv") "Created virtual environment"

    .\.venv\Scripts\Activate.ps1
    
    $pipOutput = pip install -e ".[dev]" 2>&1 | Out-String
    Assert-Contains $pipOutput "Successfully installed" "Installed ITK"
    
    # Verify itk command works
    $itkHelp = itk --help 2>&1 | Out-String
    Assert-Contains $itkHelp "usage:" "ITK CLI is available"
} finally {
    Pop-Location
}

# ============================================================================
# PHASE 2: BOOTSTRAP (first run - may have limited credentials)
# ============================================================================

Write-Step "Phase 2: First Bootstrap (may have limited credentials)"

Push-Location $TargetItk
try {
    .\.venv\Scripts\Activate.ps1
    
    $bootstrapOutput = itk bootstrap 2>&1 | Out-String
    Write-Host $bootstrapOutput
    
    # Should complete without crashing
    Assert-Contains $bootstrapOutput "Bootstrap complete" "Bootstrap completed"
    
    # Should create .env
    Assert-True (Test-Path ".env") ".env file created"
    
    # Should create starter case
    Assert-True (Test-Path "cases\my-first-test.yaml") "Starter case created"
    
    # .env should NOT have .env.example content (FIXME, etc)
    $envContent = Get-Content ".env" -Raw
    Assert-NotContains $envContent "FIXME" ".env has no FIXME placeholders"
    Assert-NotContains $envContent ".env.example" ".env has no .env.example references"
    
} finally {
    Pop-Location
}

# ============================================================================
# PHASE 3: PASTE CREDENTIALS (if provided)
# ============================================================================

if ($CredentialsFile -and (Test-Path $CredentialsFile)) {
    Write-Step "Phase 3: Paste Credentials"
    
    $creds = Get-Content $CredentialsFile -Raw
    
    # Simulate pasting creds into .env (prepend to existing content)
    Push-Location $TargetItk
    try {
        $existingEnv = Get-Content ".env" -Raw
        $newEnv = @"
# AWS Credentials (pasted from CloudShell)
$creds

$existingEnv
"@
        Set-Content ".env" $newEnv -Encoding UTF8
        Write-Pass "Pasted credentials into .env"
        
        # Re-run bootstrap with --force
        .\.venv\Scripts\Activate.ps1
        $bootstrapOutput = itk bootstrap --force 2>&1 | Out-String
        Write-Host $bootstrapOutput
        
        # Should discover resources
        if ($bootstrapOutput -match "Discovered: (\d+) log groups, (\d+) agents") {
            $logGroups = [int]$Matches[1]
            $agents = [int]$Matches[2]
            if ($logGroups -gt 0 -or $agents -gt 0) {
                Write-Pass "Discovered $logGroups log groups, $agents agents"
            } else {
                Write-Fail "No resources discovered (check credentials)"
            }
        }
        
        # Credentials should be PRESERVED in regenerated .env
        $envContent = Get-Content ".env" -Raw
        Assert-Contains $envContent "AWS_ACCESS_KEY_ID=" ".env has AWS_ACCESS_KEY_ID"
        Assert-Contains $envContent "AWS_SECRET_ACCESS_KEY=" ".env has AWS_SECRET_ACCESS_KEY"
        Assert-Contains $envContent "AWS_SESSION_TOKEN=" ".env has AWS_SESSION_TOKEN"
        
    } finally {
        Pop-Location
    }
    
    # ============================================================================
    # PHASE 4: VIEW HISTORICAL EXECUTIONS
    # ============================================================================
    
    Write-Step "Phase 4: View Historical Executions"
    
    Push-Location $TargetItk
    try {
        .\.venv\Scripts\Activate.ps1
        
        $viewOutput = itk view --since 24h --out artifacts/history 2>&1 | Out-String
        Write-Host $viewOutput
        
        # Should complete without error
        if ($viewOutput -match "Executions: (\d+)") {
            $executions = [int]$Matches[1]
            Write-Pass "Found $executions executions"
        } elseif ($viewOutput -match "No log events found") {
            Write-Pass "No logs in time window (OK if Lambda hasn't run recently)"
        } else {
            Write-Fail "Unexpected output from itk view"
        }
        
    } finally {
        Pop-Location
    }
    
} elseif (-not $SkipCredentials) {
    Write-Host ""
    Write-Host "  ⚠️  No credentials provided. Skipping live AWS tests." -ForegroundColor Yellow
    Write-Host "  To test with credentials, run:" -ForegroundColor Yellow
    Write-Host "    .\scripts\prove_it.ps1 -CredentialsFile path\to\creds.txt" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Create creds.txt by running in AWS CloudShell:" -ForegroundColor Yellow
    Write-Host "    aws configure export-credentials --format env > creds.txt" -ForegroundColor Yellow
    Write-Host ""
}

# ============================================================================
# PHASE 5: DEV-FIXTURES MODE (always runs)
# ============================================================================

Write-Step "Phase 5: Dev-Fixtures Mode (offline)"

Push-Location $TargetItk
try {
    .\.venv\Scripts\Activate.ps1
    
    # Run in dev-fixtures mode
    $runOutput = itk run --mode dev-fixtures --case cases/example-001.yaml --out artifacts/fixture-test 2>&1 | Out-String
    Write-Host $runOutput
    
    Assert-Contains $runOutput "Invariants: PASS" "Dev-fixtures run passed"
    Assert-True (Test-Path "artifacts/fixture-test/index.html") "Artifacts generated"
    
} finally {
    Pop-Location
}

# ============================================================================
# CLEANUP & SUMMARY
# ============================================================================

Write-Step "Summary"

if (-not $KeepTestDir) {
    Remove-Item -Recurse -Force $TestDir
    Write-Host "  Cleaned up test directory"
} else {
    Write-Host "  Test directory preserved: $TestDir"
}

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════════════════════╗" -ForegroundColor $(if ($script:TestsFailed -eq 0) { "Green" } else { "Red" })
Write-Host "║  Tests Passed: $($script:TestsPassed.ToString().PadLeft(3))                                                         ║" -ForegroundColor $(if ($script:TestsFailed -eq 0) { "Green" } else { "Red" })
Write-Host "║  Tests Failed: $($script:TestsFailed.ToString().PadLeft(3))                                                         ║" -ForegroundColor $(if ($script:TestsFailed -eq 0) { "Green" } else { "Red" })
Write-Host "╚══════════════════════════════════════════════════════════════════════════════╝" -ForegroundColor $(if ($script:TestsFailed -eq 0) { "Green" } else { "Red" })
Write-Host ""

if ($script:TestsFailed -gt 0) {
    exit 1
}
