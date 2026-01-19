#!/bin/bash
# ITK Bootstrap Script for Mac/Linux
# Usage: ./scripts/bootstrap.sh
set -e

echo "=== ITK Bootstrap ==="
echo ""

# Check Python version
echo "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1)
if [ -z "$PYTHON_VERSION" ]; then
    echo "ERROR: Python 3 not found. Please install Python 3.10 or later."
    echo "  macOS: brew install python@3.12"
    echo "  Ubuntu/Debian: sudo apt install python3.12 python3.12-venv"
    exit 1
fi

MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [ "$MAJOR" -lt 3 ] || { [ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]; }; then
    echo "ERROR: Python 3.10+ required, found Python $PYTHON_VERSION"
    echo "  Please install Python 3.10 or later."
    exit 1
fi
echo "  Found Python $PYTHON_VERSION ✓"

# Determine script directory (where bootstrap.sh lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ITK_ROOT="$(dirname "$SCRIPT_DIR")"

echo ""
echo "ITK root: $ITK_ROOT"
cd "$ITK_ROOT"

# Create virtual environment
echo ""
echo "Creating virtual environment..."
if [ -d ".venv" ]; then
    echo "  .venv already exists, reusing it."
else
    python3 -m venv .venv
    echo "  Created .venv ✓"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source .venv/bin/activate
echo "  Activated ✓"

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip -q
echo "  pip upgraded ✓"

# Install ITK with dev dependencies
echo ""
echo "Installing ITK (this may take a minute)..."
pip install -e ".[dev]" -q
echo "  ITK installed ✓"

# Verify installation
echo ""
echo "Verifying installation..."
if python -m itk --help > /dev/null 2>&1; then
    echo "  itk --help works ✓"
else
    echo "ERROR: ITK installation verification failed."
    echo "  Try running: pip install -e .[dev]"
    exit 1
fi

# Check for .env file
echo ""
if [ -f ".env" ]; then
    echo ".env file found ✓"
else
    if [ -f ".env.example" ]; then
        echo "No .env file found. Copying from .env.example..."
        cp .env.example .env
        echo "  Created .env from .env.example ✓"
        echo "  IMPORTANT: Edit .env with your configuration values."
    else
        echo "WARNING: No .env or .env.example found."
        echo "  Create .env before running live mode tests."
    fi
fi

# Summary
echo ""
echo "==================================="
echo "SUCCESS: ITK is ready!"
echo "==================================="
echo ""
echo "Next steps:"
echo "  1. Activate the venv: source .venv/bin/activate"
echo "  2. Edit .env with your AWS configuration (for live mode)"
echo "  3. Run a test: itk run --case cases/example-001.yaml --out artifacts/test/"
echo "  4. Check the CLI: itk --help"
echo ""
