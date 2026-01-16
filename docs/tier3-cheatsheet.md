# Tier-3 Cheatsheet

> **One page. Everything you need. No scrolling.**

---

## 🚀 First 10 Commands (In Order)

```bash
# 1. Install ITK
cd dropin/itk && pip install -e ".[dev]"

# 2. Copy env template
cp .env.example ../.env

# 3. Edit .env with your AWS values (REQUIRED)
# Open .env and fill in ITK_SQS_QUEUE_URL, ITK_LOG_GROUPS, AWS_REGION

# 4. Verify AWS credentials work
aws sts get-caller-identity

# 5. Verify it's NOT production (MUST show qa/staging account)
aws sts get-caller-identity | grep Account

# 6. Run safety check
python scripts/safety_check.py

# 7. Validate a case file
itk validate --case cases/example-001.yaml

# 8. Run your first test (dev-fixtures mode - no AWS)
itk run --mode dev-fixtures --case cases/example-001.yaml --out artifacts/test-001/

# 9. Check it worked
ls artifacts/test-001/

# 10. Open the trace viewer
start artifacts/test-001/trace-viewer.html
```

---

## 🌳 Decision Tree

```
START HERE
    │
    ▼
┌─────────────────────────────────┐
│ Do you have AWS credentials?    │
└─────────────────────────────────┘
    │           │
   YES          NO
    │           │
    ▼           ▼
┌─────────┐  ┌─────────────────────────────┐
│ Run:    │  │ STOP. Get creds first.      │
│ aws sts │  │ See: docs/tier3-guide.md    │
│ get-... │  │ section "Troubleshooting"   │
└─────────┘  └─────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Is it QA/staging account?       │
│ (NOT production)                │
└─────────────────────────────────┘
    │           │
   YES          NO
    │           │
    ▼           ▼
┌─────────┐  ┌─────────────────────────────┐
│Continue │  │ 🚨 STOP IMMEDIATELY 🚨      │
└─────────┘  │ Wrong account. Fix .env     │
             │ See: tier3-rollback.md      │
             └─────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Is .env configured?             │
└─────────────────────────────────┘
    │           │
   YES          NO
    │           │
    ▼           ▼
┌─────────┐  ┌─────────────────────────────┐
│Continue │  │ Run: cp .env.example .env   │
└─────────┘  │ Then edit .env              │
             └─────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ What do you want to do?         │
└─────────────────────────────────┘
    │
    ├──► Run a test case ──► itk run --case X --out Y
    │
    ├──► Run test suite ──► itk suite --suite X --out Y
    │
    ├──► Find logging gaps ──► itk audit --case X --out Y
    │
    ├──► Generate cases from logs ──► itk derive --since 24h --out Y
    │
    └──► Scan codebase coverage ──► itk scan --repo . --out Y
```

---

## ✅ Success Checks

After each command, verify it worked:

| Command | Success Check | Expected |
|---------|---------------|----------|
| `pip install -e ".[dev]"` | `itk --help` | Shows help text |
| `aws sts get-caller-identity` | Exit code 0 | JSON with Account |
| `python scripts/safety_check.py` | Exit code 0 | "✅ All checks passed" |
| `itk validate --case X` | Exit code 0 | "✅ Valid" |
| `itk run --case X --out Y` | `ls Y/` | trace-viewer.html exists |
| `itk audit --case X --out Y` | `cat Y/logging-gaps.md` | File exists |

---

## 🚫 Never Do These

```bash
# ❌ WRONG: Using dev-fixtures for real integration tests
itk run --mode dev-fixtures --case cases/production-test.yaml --out ...

# ❌ WRONG: Running without checking account first
itk run --case ... --out ...  # Before aws sts get-caller-identity

# ❌ WRONG: Hardcoding production URLs
ITK_SQS_QUEUE_URL=https://sqs.../prod-queue  # NEVER

# ❌ WRONG: Skipping pre-flight
itk run ...  # Without completing tier3-preflight-checklist.md

# ❌ WRONG: Inventing request formats
# Don't guess what payloads look like. Use derive or existing cases.
```

---

## 📂 Where Things Are

```
dropin/itk/
├── .env.example          ← Copy to .env, fill in values
├── cases/                ← Test case definitions
├── fixtures/             ← Sample log data (offline testing)
├── artifacts/            ← Output goes here
├── scripts/
│   └── safety_check.py   ← Run before any AWS operation
└── src/itk/
    └── cli.py            ← Main CLI

docs/
├── tier3-cheatsheet.md   ← YOU ARE HERE
├── tier3-agent-guide.md  ← Full guide (read if stuck)
├── tier3-error-fixes.md  ← Error → solution table
└── tier3-preflight-checklist.md ← Complete before AWS ops
```

---

## 🆘 Stuck?

1. **Error message?** → Check `docs/tier3-error-fixes.md`
2. **Don't know what to do?** → Follow decision tree above
3. **AWS issue?** → Run `python scripts/safety_check.py`
4. **Test failed?** → Use prompt: `.github/prompts/itk-triage-failed-run.prompt.md`
5. **Missing logs?** → Run `itk audit` first
