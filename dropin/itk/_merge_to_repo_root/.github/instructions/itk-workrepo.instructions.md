---
applyTo: "dropin/itk/**,tools/itk/**"
---

# ITK Rules (Tier-3 Work Repo Agent)

You are a Tier-3 agent working in the work repo with live AWS access.

## 🐍 Python Environment Setup (CRITICAL)

**ITK requires Python 3.11 or newer.** Using an older version causes errors.

Before running any ITK commands, verify or set up the Python environment:

```bash
# Check if virtual environment exists and has correct Python
if [ -d ".venv" ]; then
    source .venv/bin/activate
    python --version  # Must show 3.11+
else
    # Create virtual environment with Python 3.11+
    python3.11 -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"
fi
```

If `python --version` shows below 3.11:
```bash
# Recreate virtual environment with correct Python
deactivate
rm -rf .venv
python3.11 -m venv .venv   # Use python3.11, python3.12, etc.
source .venv/bin/activate
pip install -e ".[dev]"
```

## 🚨 Critical Safety Rules

1. **ALWAYS run safety check first**: `python dropin/itk/scripts/safety_check.py`
2. **NEVER run against production**: If account ID looks like prod, STOP immediately
3. **NEVER use dev-fixtures mode for real tests**: `--mode dev-fixtures` is for offline only
4. **NEVER invent request formats**: Use `itk derive` or existing cases
5. **ALWAYS verify AWS credentials**: `aws sts get-caller-identity` before any test
6. **ALWAYS use Python 3.11+**: Check with `python --version`

## 🚀 Before ANY AWS Operation

Complete this checklist (no exceptions):

```bash
# 1. Verify credentials
aws sts get-caller-identity

# 2. Confirm NOT production (must show qa/staging/dev)
aws sts get-caller-identity | grep Account

# 3. Run safety check
python dropin/itk/scripts/safety_check.py
```

If ANY of these fail, STOP and fix before proceeding.

## 📋 Quick Command Reference

```bash
# Run a test case (LIVE)
itk run --case cases/example.yaml --out artifacts/run-001/

# Run a test case (OFFLINE - fixtures only)
itk run --mode dev-fixtures --case cases/example.yaml --out artifacts/run-001/

# Run test suite
itk suite --cases-dir cases/ --out artifacts/smoke/

# Run soak test (50 iterations with drill-down)
itk soak --case cases/example.yaml --out artifacts/soak-001/ --iterations 50 --detailed

# Audit logging gaps
itk audit --case cases/example.yaml --out artifacts/audit/

# Derive cases from CloudWatch logs
itk derive --since 24h --out cases/derived/

# Validate case file
itk validate --case cases/example.yaml
```

## 📂 File Locations

- CLI: `dropin/itk/src/itk/cli.py`
- Entrypoints: `dropin/itk/src/itk/entrypoints/`
- Schemas: `dropin/itk/schemas/`
- Cases: `dropin/itk/cases/`
- Fixtures: `dropin/itk/fixtures/`
- TODO List: `dropin/itk/planning/TODO.md`

## ✅ Definition of Done

Every `itk run` must produce in the output directory:
- `trace-viewer.html` — Interactive SVG sequence diagram
- `timeline.html` — Waterfall timeline view
- `sequence.mmd` — Mermaid source
- `spans.jsonl` — Raw span data
- `report.md` — Summary with invariant results
- `payloads/*.json` — Request/response payloads

Every `itk soak` must produce:
- `soak-report.html` — Dashboard with consistency metrics
- `soak-result.json` — Programmatic access to results
- `iterations/NNNN/<case>/` — Per-iteration artifacts (with `--detailed`)

## 🔄 Soak Test Interpretation

| Metric | Good | Bad | Action |
|--------|------|-----|--------|
| Pass Rate | 100% | <95% | Investigate failed iterations |
| Consistency | >90% | <50% | Too many retries (LLM non-determinism) |
| Throttles | 0 | >0 | Reduce rate: `--initial-rate 0.5` |

**Key insight**: 100% pass + 0% consistency = All passes needed retries (hidden flakiness)

## 🛠️ When Things Break

1. **Error message?** → Check `docs/tier3-error-fixes.md`
2. **Empty diagram?** → Run `itk audit`, check logging-gaps.md
3. **AWS error?** → Run `python dropin/itk/scripts/safety_check.py --verbose`
4. **Test failed?** → Use prompt: `.github/prompts/itk-triage-failed-run.prompt.md`
5. **Soak issues?** → Use prompt: `.github/prompts/itk-run-soak-test.prompt.md`
6. **0% consistency?** → All passes had retries, drill-down to investigate

## ⛔ Never Do This

```bash
# ❌ Running without safety check
itk run --case ...  # WRONG - run safety_check.py first

# ❌ Using dev-fixtures for real integration tests
itk run --mode dev-fixtures --case production-test.yaml  # WRONG

# ❌ Hardcoding production URLs
ITK_SQS_QUEUE_URL=https://sqs.../prod-queue  # NEVER

# ❌ Guessing request formats
# Use itk derive or copy existing cases
```

## 📚 Documentation

- **Kickoff**: `docs/tier3-kickoff.md` — Start here
- **Cheatsheet**: `docs/tier3-cheatsheet.md` — Quick reference
- **Error fixes**: `docs/tier3-error-fixes.md` — Error → solution
- **Full guide**: `docs/tier3-agent-guide.md` — Complete docs
- **Pre-flight**: `docs/tier3-preflight-checklist.md` — Before AWS ops
