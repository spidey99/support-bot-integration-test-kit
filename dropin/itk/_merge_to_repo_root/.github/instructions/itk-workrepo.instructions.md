---
applyTo: "dropin/itk/**,tools/itk/**"
---

# ITK Rules (Tier-3 Work Repo Agent)

You are a Tier-3 agent working in the work repo with live AWS access.

## 🚨 Critical Safety Rules

1. **ALWAYS run safety check first**: `python dropin/itk/scripts/safety_check.py`
2. **NEVER run against production**: If account ID looks like prod, STOP immediately
3. **NEVER use dev-fixtures mode for real tests**: `--mode dev-fixtures` is for offline only
4. **NEVER invent request formats**: Use `itk derive` or existing cases
5. **ALWAYS verify AWS credentials**: `aws sts get-caller-identity` before any test

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

# Audit logging gaps
itk audit --case cases/example.yaml --out artifacts/audit/

# Derive cases from CloudWatch logs
itk derive --since 24h --out cases/derived/

# Run test suite
itk suite --suite suites/smoke.yaml --out artifacts/smoke/

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
- `trace-viewer.html` — Interactive diagram
- `sequence.mmd` — Mermaid source
- `spans.jsonl` — Raw span data
- `report.md` — Summary with invariant results
- `payloads/*.json` — Request/response payloads

## 🛠️ When Things Break

1. **Error message?** → Check `docs/tier3-error-fixes.md`
2. **Empty diagram?** → Run `itk audit`, check logging-gaps.md
3. **AWS error?** → Run `python dropin/itk/scripts/safety_check.py --verbose`
4. **Test failed?** → Use prompt: `.github/prompts/itk-triage-failed-run.prompt.md`

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
