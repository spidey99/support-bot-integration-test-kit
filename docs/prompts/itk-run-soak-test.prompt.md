# Prompt: Run Soak Test

> Use this prompt when you need to stress-test a case to find flaky behavior or LLM non-determinism.

---

## Context

You need to run a soak test to repeatedly execute a test case and analyze consistency.

## Pre-flight (MUST complete first)

```bash
# 1. Verify AWS credentials
aws sts get-caller-identity
# Expected: Shows QA account ID (NOT production)

# 2. Verify .env is configured
cat .env | grep ITK_MODE
# Expected: ITK_MODE=live
```

## Run the Soak Test

```bash
# Run 50 iterations with per-iteration artifacts
itk soak --case cases/<CASE_NAME>.yaml --out artifacts/soak-<RUN_ID>/ --iterations 50 --detailed
```

Replace:
- `<CASE_NAME>` with your test case filename
- `<RUN_ID>` with a unique identifier (e.g., `001`, timestamp)

## Check the Results

```bash
# Open the soak report
start artifacts/soak-<RUN_ID>/soak-report.html  # Windows
open artifacts/soak-<RUN_ID>/soak-report.html   # Mac
```

## Interpret the Metrics

| Metric | What to look for |
|--------|------------------|
| **Pass Rate** | Should be 100%. If <95%, investigate failed iterations. |
| **Consistency Score** | Should be >90%. If <50%, too many retries happening. |
| **Warning Rate** | Passes with retries. High = flaky system. |
| **Throttle Events** | Should be 0. If >0, reduce rate next run. |

### Key Insight

**100% Pass Rate + 0% Consistency = PROBLEM**

This means every test passed, but only after retries. The LLM or system is non-deterministic.

## Drill-down into Specific Iterations

1. In soak-report.html, find the iteration table
2. Click "Trace" or "Timeline" for any iteration
3. Opens that iteration's trace-viewer.html
4. Look for error spans, retry patterns

## If Throttling Occurred

Re-run with lower rate:

```bash
itk soak --case cases/<CASE_NAME>.yaml --out artifacts/soak-<RUN_ID>-retry/ --iterations 50 --initial-rate 0.5
```

## Report Summary Format

After analyzing, report:

```
Soak Test Results: <CASE_NAME>
- Iterations: 50
- Pass Rate: XX%
- Consistency Score: XX%
- Throttle Events: N
- Key Finding: <one sentence summary>
- Action: <next step if any>
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| All iterations show "warning" | Check retry patterns — LLM may be flaky |
| Throttle events > 0 | Reduce `--initial-rate` to 0.5 or lower |
| Consistency is 0% | Every pass needed retries — investigate error spans |
| Duration varies wildly | Check for timeout patterns or slow external calls |
