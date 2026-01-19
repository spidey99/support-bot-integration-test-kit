# ITK Bootstrap Script for Windows PowerShell
# Usage: .\scripts\bootstrap.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== ITK Bootstrap ===" -ForegroundColor Cyan
Write-Host ""

# Check Python version
Write-Host "Checking Python version..."
try {
    $pythonVersionOutput = python --version 2>&1
    if ($pythonVersionOutput -match "Python (\d+)\.(\d+)") {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
            Write-Host "ERROR: Python 3.10+ required, found Python $major.$minor" -ForegroundColor Red
            Write-Host "  Please install Python 3.10 or later from python.org"
            exit 1
        }
        Write-Host "  Found Python $major.$minor " -NoNewline
        Write-Host "[OK]" -ForegroundColor Green
    } else {
        throw "Could not parse Python version"
    }
} catch {
    Write-Host "ERROR: Python not found. Please install Python 3.10 or later." -ForegroundColor Red
    Write-Host "  Download from: https://www.python.org/downloads/"
    exit 1
}

# Determine ITK root (parent of scripts folder)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ItkRoot = Split-Path -Parent $ScriptDir

Write-Host ""
Write-Host "ITK root: $ItkRoot"
Set-Location $ItkRoot

# Create virtual environment
Write-Host ""
Write-Host "Creating virtual environment..."
if (Test-Path ".venv") {
    Write-Host "  .venv already exists, reusing it."
} else {
    python -m venv .venv
    Write-Host "  Created .venv " -NoNewline
    Write-Host "[OK]" -ForegroundColor Green
}

# Activate virtual environment
Write-Host ""
Write-Host "Activating virtual environment..."
& .\.venv\Scripts\Activate.ps1
Write-Host "  Activated " -NoNewline
Write-Host "[OK]" -ForegroundColor Green

# Upgrade pip
Write-Host ""
Write-Host "Upgrading pip..."
python -m pip install --upgrade pip -q
Write-Host "  pip upgraded " -NoNewline
Write-Host "[OK]" -ForegroundColor Green

# Install ITK with dev dependencies
Write-Host ""
Write-Host "Installing ITK (this may take a minute)..."
pip install -e ".[dev]" -q
Write-Host "  ITK installed " -NoNewline
Write-Host "[OK]" -ForegroundColor Green

# Verify installation
Write-Host ""
Write-Host "Verifying installation..."
try {
    python -m itk --help | Out-Null
    Write-Host "  itk --help works " -NoNewline
    Write-Host "[OK]" -ForegroundColor Green
} catch {
    Write-Host "ERROR: ITK installation verification failed." -ForegroundColor Red
    Write-Host "  Try running: pip install -e .[dev]"
    exit 1
}

# Check for .env file
Write-Host ""
if (Test-Path ".env") {
    Write-Host ".env file found " -NoNewline
    Write-Host "[OK]" -ForegroundColor Green
} else {
    if (Test-Path ".env.example") {
        Write-Host "No .env file found. Copying from .env.example..."
        Copy-Item ".env.example" ".env"
        Write-Host "  Created .env from .env.example " -NoNewline
        Write-Host "[OK]" -ForegroundColor Green
        Write-Host "  IMPORTANT: Edit .env with your configuration values." -ForegroundColor Yellow
    } else {
        Write-Host "WARNING: No .env or .env.example found." -ForegroundColor Yellow
        Write-Host "  Create .env before running live mode tests."
    }
}

# Summary
Write-Host ""
Write-Host "===================================" -ForegroundColor Cyan
Write-Host "SUCCESS: ITK is ready!" -ForegroundColor Green
Write-Host "===================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Activate the venv: " -NoNewline
Write-Host ".\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host "  2. Edit .env with your AWS configuration (for live mode)"
Write-Host "  3. Run a test: " -NoNewline
Write-Host "itk run --case cases/example-001.yaml --out artifacts/test/" -ForegroundColor Yellow
Write-Host "  4. Check the CLI: " -NoNewline
Write-Host "itk --help" -ForegroundColor Yellow
Write-Host ""
