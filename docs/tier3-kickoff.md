# ITK Kickoff: Start Here

> **You are a Tier-3 coding agent.** Follow these instructions exactly.
> 
> 📍 **Location**: You should be in the work repo with ITK installed at `dropin/itk/`

---

## Step 0: Read This First

**Your mission**: Run integration tests against real AWS QA resources.

**Key rules**:
1. ✅ All tests run LIVE against real AWS (not mocks)
2. ✅ Always verify credentials before AWS calls
3. ✅ All outputs must be static files (viewable via `file://`)
4. ❌ Never use `--mode dev-fixtures` for real integration tests
5. ❌ Never run against production accounts

---

## Step 1: Verify ITK is Installed

Run this command:
```bash
itk --help
```

**Expected**: Help text showing available commands.

**If it fails**, run:
```bash
cd dropin/itk && pip install -e ".[dev]"
```

---

## Step 2: Run Safety Check

Run this command:
```bash
python dropin/itk/scripts/safety_check.py
```

**Expected**: `✅ All checks passed - Safe to proceed`

**If it fails**:
1. Read the error message carefully
2. Check `docs/tier3-error-fixes.md` for the exact fix
3. Fix the issue
4. Re-run the safety check
5. Do NOT proceed until it passes

---

## Step 3: Complete Pre-flight Checklist

Open `docs/tier3-preflight-checklist.md` and complete ALL items.

This is not optional. Complete it before every AWS operation.

---

## Step 4: Run Your First Test

```bash
itk run --mode dev-fixtures --case dropin/itk/cases/example-001.yaml --out artifacts/test-001/
```

**Expected**: Creates `artifacts/test-001/` with:
- `trace-viewer.html` — Interactive sequence diagram
- `timeline.html` — Waterfall timeline view
- `sequence.mmd` — Mermaid source
- `spans.jsonl` — Raw span data
- `report.md` — Summary with invariant results

**Verify**:
```bash
ls artifacts/test-001/
```

---

## Step 5: Open the Trace Viewer

```bash
# Windows
start artifacts/test-001/trace-viewer.html

# Mac
open artifacts/test-001/trace-viewer.html

# Linux
xdg-open artifacts/test-001/trace-viewer.html
```

You should see an interactive sequence diagram.

---

## What's Next?

Now follow the TODO items in order:

📋 **Open**: `dropin/itk/planning/TODO.md`

Start with `ITK-W-0001 — Environment setup` and work through each item.

---

## Quick Reference

| Task | Command |
|------|---------|
| Run a test case | `itk run --case X --out Y` |
| Run test suite | `itk suite --suite X --out Y` |
| Find logging gaps | `itk audit --case X --out Y` |
| Generate cases from logs | `itk derive --since 24h --out Y` |
| Scan codebase | `itk scan --repo . --out Y` |
| Validate a case | `itk validate --case X` |
| Compare two runs | `itk compare --a A --b B --out Y` |

---

## If You Get Stuck

1. **Check the cheatsheet**: `docs/tier3-cheatsheet.md`
2. **Look up the error**: `docs/tier3-error-fixes.md`
3. **Read the full guide**: `docs/tier3-agent-guide.md`
4. **Use a prompt**: `.github/prompts/itk-*.prompt.md`

---

## Files You Need to Know

```
docs/
├── tier3-kickoff.md          ← YOU ARE HERE
├── tier3-cheatsheet.md       ← Quick reference (one page)
├── tier3-error-fixes.md      ← Error → fix lookup
├── tier3-agent-guide.md      ← Full guide
├── tier3-preflight-checklist.md ← Complete before AWS ops
└── tier3-rollback-procedures.md ← What to do when things break

dropin/itk/
├── planning/TODO.md          ← Your task list
├── cases/                    ← Test case definitions
├── scripts/safety_check.py   ← Run before AWS calls
└── .env.example              ← Copy to .env

.github/prompts/
├── itk-triage-failed-run.prompt.md
├── itk-add-span-logging.prompt.md
├── itk-derive-test-from-logs.prompt.md
└── itk-add-new-entrypoint-adapter.prompt.md
```

---

## Ready?

✅ ITK installed  
✅ Safety check passed  
✅ Pre-flight complete  
✅ Test run successful  

**→ Go to `dropin/itk/planning/TODO.md` and start ITK-W-0001**
