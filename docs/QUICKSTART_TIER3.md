# ITK Quick Start: Adding to Your Work Repo

> **See also:** [08-agent-setup-guide.md](08-agent-setup-guide.md) - a step-by-step version designed for AI coding agents.

---

## TL;DR - Just Run These Commands

```bash
# 1. From your work repo root, download ITK
git clone https://github.com/spidey99/support-bot-integration-test-kit.git _itk_temp
cp -r _itk_temp/dropin/itk tools/itk
rm -rf _itk_temp

# 2. Create virtual environment with Python 3.11+
cd tools/itk
python3.11 -m venv .venv           # IMPORTANT: Use Python 3.11 or newer!
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1

# 3. Verify Python version and install
python --version                    # Should show Python 3.11.x or higher
pip install -e ".[dev]"

# 4. Test it works (offline mode, no AWS needed)
itk run --mode dev-fixtures --case cases/example-001.yaml --out artifacts/test-001/

# 5. Open the result
start artifacts/test-001/trace-viewer.html   # Windows
# open artifacts/test-001/trace-viewer.html  # Mac
```

**Done!** You now have ITK installed. See below for AWS setup and the Tier 3 agent.

---

> **Time**: 5-10 minutes  
> **You need**: **Python 3.11+**, AWS CLI configured, QA account access  
> **You DON'T need**: Any AWS access for Steps 1-3 (offline mode)

---

# Step 1 of 8: Download ITK

**Run this from your work repo root:**

```bash
git clone https://github.com/spidey99/support-bot-integration-test-kit.git _itk_temp
cp -r _itk_temp/dropin/itk tools/itk
rm -rf _itk_temp
```

### You should see:

```
Cloning into '_itk_temp'...
```

Then a new `tools/itk/` folder in your repo.

### Didn't work?

| Problem | Fix |
|---------|-----|
| `git: command not found` | Install Git: https://git-scm.com/downloads |
| Permission denied | Run terminal as admin, or check folder permissions |
| Folder already exists | Delete it first: `rm -rf tools/itk` |

---

# Step 2 of 8: Install ITK

**First, set up a Python 3.11+ virtual environment:**

```bash
cd tools/itk

# Create virtual environment with Python 3.11 or newer
python3.11 -m venv .venv           # Use python3.11, python3.12, etc.

# Activate the virtual environment
source .venv/bin/activate          # Linux/macOS
# .\.venv\Scripts\Activate.ps1     # Windows PowerShell
# .\.venv\Scripts\activate.bat     # Windows CMD

# Verify Python version (MUST be 3.11+)
python --version                    # Should show Python 3.11.x or higher

# Install ITK
pip install -e ".[dev]"
```

### You should see:

```
Successfully installed itk-0.1.0
```

(Version number may vary)

**Now verify it:**

```bash
itk --help
```

### You should see:

```
Usage: itk [OPTIONS] COMMAND [ARGS]...

  Integration Test Kit CLI

Commands:
  run       Run a single test case
  suite     Run all cases in a directory
  soak      Run repeated iterations of a test
  ...
```

### Didn't work?

| Problem | Fix |
|---------|-----|
| `itk: command not found` | Close and reopen terminal, or run: `python -m itk --help` |
| `pip: command not found` | Use `pip3` instead of `pip` |
| Python version error | Need Python 3.11+. Check: `python --version` |
| `python3.11: command not found` | Install Python 3.11: see table below |
| `SyntaxError` or import errors | Wrong Python version. Recreate venv with Python 3.11+ |

**Installing Python 3.11+ if needed:**

| OS | Command |
|----|---------|
| Ubuntu/Debian | `sudo apt update && sudo apt install python3.11 python3.11-venv` |
| macOS (Homebrew) | `brew install python@3.11` |
| Windows | Download from https://www.python.org/downloads/ |
| Amazon Linux | `sudo yum install python3.11` |

---

# Step 3 of 8: First Test (Offline - No AWS!)

This runs with fake data to prove ITK works:

```bash
itk run --mode dev-fixtures --case cases/example-001.yaml --out artifacts/test-001/
```

### You should see:

```
[PASS] example-001
```

And files created in `artifacts/test-001/`

**Open the trace viewer:**

```bash
# Windows
start artifacts/test-001/trace-viewer.html

# Mac
open artifacts/test-001/trace-viewer.html

# Linux
xdg-open artifacts/test-001/trace-viewer.html
```

### You should see:

A browser opens with an interactive trace diagram.

### Didn't work?

| Problem | Fix |
|---------|-----|
| File not found | Make sure you're in `tools/itk/` directory |
| Empty diagram | This is expected for fixture data - it's just a smoke test |

---

# Step 4 of 8: Configure for AWS

```bash
cp .env.example .env
```

Now edit `.env` with your favorite editor:

```bash
code .env      # VS Code
notepad .env   # Windows
vim .env       # Terminal
```

### Fill in these values:

```bash
# Start with this - means "use real AWS"
ITK_MODE=live

# Your region
AWS_REGION=us-east-1

# Your Lambda log groups (ask your team if unsure)
ITK_LOG_GROUPS=/aws/lambda/my-function-1,/aws/lambda/my-function-2

# Your QA SQS queue (ask your team if unsure)
ITK_SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789/my-qa-queue
```

### Don't know these values?

Ask your team lead, or check your AWS console:
- **Log Groups**: CloudWatch > Log groups > copy the names
- **SQS URL**: SQS > Queues > click your queue > copy the URL

---

# Step 5 of 8: Safety Check (IMPORTANT!)

```bash
aws sts get-caller-identity
```

### You should see:

```json
{
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/yourname"
}
```

## STOP! Read the Account Number!

| Account matches... | Do this |
|--------------------|---------|
| Your QA/staging account | Continue to Step 6 |
| Production account | **STOP. Switch profiles first.** |
| Unknown account | **STOP. Ask your team.** |

### Switch AWS profile if needed:

```bash
# List your profiles
aws configure list-profiles

# Switch to QA profile
export AWS_PROFILE=qa        # Mac/Linux
$env:AWS_PROFILE = "qa"      # Windows PowerShell
set AWS_PROFILE=qa           # Windows CMD
```

---

# Step 6 of 8: First Live Test

Now run a real test against AWS:

```bash
itk run --case cases/example-001.yaml --out artifacts/live-001/
```

### You should see:

```
[PASS] example-001
```

Or `[WARN]` or `[FAIL]` with details.

**Open the result:**

```bash
start artifacts/live-001/trace-viewer.html
```

### Didn't work?

| Problem | Fix |
|---------|-----|
| Access denied | Check AWS credentials (Step 5) |
| Timeout | Your log groups might be wrong in `.env` |
| No spans found | The test case might not match your system yet |

---

# Step 6.5: Discover Correlation Chains (Optional)

If your logs don't have a single trace ID that spans all components (common with Slack-based bots), use correlation discovery:

```bash
# First, export logs to JSONL (or use logs from itk view)
itk discover-correlations --logs artifacts/live-001/logs.jsonl --out artifacts/correlations/
```

### You should see:

```
Discovered 1 correlation chain(s):

Chain 1: lambda → slack → bedrock
  Entries: 6
  Components: 3
  Bridge values:
    1768927632.159269... → slack, bedrock, lambda
```

This finds log entries that belong together by:
- **Slack timestamps** (`ts`, `thread_id`) used as `session_id` in Bedrock
- **Channel IDs** (`C07GVLMH5EG`) shared across components
- **UUIDs** (request IDs, message IDs) linking services

**Outputs:**
- `correlation_chains.json` - Full chain data with bridge values
- `components_detected.json` - What components were found
- `correlation_summary.txt` - Human-readable summary

---

# Step 7 of 8: Set Up AI Instructions (Optional)

This helps Copilot/Claude understand ITK:

```bash
# From your work repo root (not tools/itk/)
cd ../..

# Copy the instructions
cp -r tools/itk/_merge_to_repo_root/.github/instructions/* .github/instructions/
```

---

# Step 8 of 8: Kick Off the Tier 3 Agent

When using an AI coding agent (GitHub Copilot, Claude, etc.) in your work repo:

### Copy This Entire Block and Paste Into Chat:

```
I'm working with the Integration Test Kit (ITK) in this repo.

ITK is installed at: tools/itk/
Documentation is at: tools/itk/docs/

I need you to help me run integration tests against our AWS QA environment.

Before ANY AWS operations, you must:
1. Run: aws sts get-caller-identity
2. Verify this is the QA account (NOT production)
3. Run: cd tools/itk && python scripts/safety_check.py

Key commands (run from tools/itk/):
- itk run --case cases/X.yaml --out artifacts/Y/
- itk suite --cases-dir cases/ --out artifacts/suite/
- itk soak --case cases/X.yaml --out artifacts/soak/ --iterations N
- itk audit --case cases/X.yaml --out artifacts/audit/

Documentation to reference:
- tools/itk/docs/tier3-cheatsheet.md   (quick reference)
- tools/itk/docs/tier3-error-fixes.md  (troubleshooting)
- tools/itk/planning/TODO.md           (task list)

Start by running the safety check.
```

**That's it!** The agent will take it from there.

---

# Quick Reference Card

Print this out or keep it open in another tab:

## Commands You'll Use Most

| What you want | Command |
|---------------|---------|
| Run one test | `itk run --case cases/X.yaml --out artifacts/Y/` |
| Run all tests | `itk suite --cases-dir cases/ --out artifacts/suite/` |
| Stress test | `itk soak --case cases/X.yaml --out artifacts/soak/ --iterations 50` |
| Find logging gaps | `itk audit --case cases/X.yaml --out artifacts/audit/` || **Find correlation chains** | `itk discover-correlations --logs file.jsonl --out artifacts/corr/` |
## Status Meanings

| You see | It means | Do this |
|---------|----------|---------|
| `[PASS]` | Everything worked | Nothing, you're good |
| `[WARN]` | Passed but with retries | Look at the trace - might be flaky |
| `[FAIL]` | Test assertions failed | Open trace-viewer.html to debug |
| `[ERR!]` | Something crashed | Check the error message |

## Soak Test Numbers

| Metric | Good | Investigate if... |
|--------|------|-------------------|
| Pass Rate | 100% | Below 95% |
| Consistency | Above 90% | Below 50% (means lots of retries) |
| Throttle Events | 0 | Any - you're hitting rate limits |

---

# Something Went Wrong?

## "itk: command not found"

```bash
# Option 1: Reinstall
cd tools/itk
pip install -e ".[dev]"

# Option 2: Run directly
python -m itk --help
```

## "Access Denied" or "Credentials" errors

```bash
# Check your AWS setup
aws sts get-caller-identity

# If that fails, configure AWS:
aws configure
```

## "No spans found" or empty diagram

Your test case doesn't match what's in the logs yet. This is normal when starting. Run:

```bash
itk audit --case cases/example-001.yaml --out artifacts/audit/
```

This shows what logging is missing.

## "TimeoutError" or slow tests

Your log groups might be huge. Add time bounds:

```bash
itk run --case cases/X.yaml --out artifacts/Y/ --start-time "2024-01-15T00:00:00Z"
```

## Still stuck?

1. Check: [docs/tier3-error-fixes.md](tier3-error-fixes.md)
2. Ask your team lead
3. Open an issue on the ITK repo

---

# Where Things Live

```
your-work-repo/
|
+-- tools/itk/           <-- You are here
    |-- .env             <-- Your config (edit this)
    |-- cases/           <-- Test definitions (edit these)
    |-- artifacts/       <-- Output goes here (don't commit)
    |
    +-- docs/
        |-- tier3-cheatsheet.md      <-- Print this
        |-- tier3-error-fixes.md     <-- When things break
        +-- prompts/                 <-- Copy-paste for AI
```

---

# You're Done!

**Next steps:**
1. Run `itk suite --cases-dir cases/ --out artifacts/suite/` to test everything
2. Open `artifacts/suite/index.html` to see the dashboard
3. Check `tools/itk/planning/TODO.md` for your task list

**Questions?** Ask the Tier 3 agent - that's what it's there for.
