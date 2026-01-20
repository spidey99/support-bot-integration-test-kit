# TODO (Tier 3 — Work Repo Agent)

> **REMEMBER**: All test execution is LIVE. Never use mocks. Never use dev-fixtures mode for real tests.

---

## BUGS DISCOVERED IN E2E TESTING

### ITK-BUG-0001 — Logs Insights fails on new log groups (OPEN)
- **Symptom**: `itk view` returns 0 log events even though logs exist
- **Root cause**: CloudWatch Logs Insights has an indexing delay for newly-created log groups. Direct API (`get-log-events`) works immediately, but Logs Insights queries (`start_query`) fail until indexed.
- **Workaround**: Wait longer (minutes, not seconds)
- **Fix needed**: ITK should detect when Logs Insights returns 0 on a log group that exists, and fall back to `filter_log_events` or `get_log_events` API
- **File**: `dropin/itk/src/itk/logs/cloudwatch_fetch.py`

### ITK-BUG-0002 — E2E test uses Lambda-only flow (OPEN)
- **Symptom**: E2E test validates Lambda→Logs→ITK but not Agent→Lambda→Logs→ITK
- **Root cause**: Creating ephemeral Bedrock Agents takes minutes, making E2E slow
- **Workaround**: Use existing `itk-supervisor` agent for full-flow tests
- **Fix options**:
  1. Add Bedrock Agent to E2E terraform (accept slower test)
  2. Create a separate "full E2E" test that uses persistent agents
  3. Make agent creation faster (cache, or pre-create ephemeral pool)
- **File**: `dropin/itk/infra/terraform-e2e/main.tf`

---

## ITK-W-0001 — Environment setup
- [ ] Copy `.env.example` to `.env`
- [ ] Fill in real values:
  - `AWS_REGION`, `AWS_PROFILE` or access keys
  - `ITK_SQS_QUEUE_URL` (QA queue)
  - `ITK_LOG_GROUPS` (comma-separated CloudWatch log group names)
  - `ITK_BEDROCK_AGENT_ID`, `ITK_BEDROCK_AGENT_ALIAS_ID`
- [ ] Verify credential chain works: `aws sts get-caller-identity`
- [ ] Test CloudWatch access: `aws logs describe-log-groups`

## ITK-W-0002 — Resolver configuration
- [ ] Create resolver script that outputs `targets.json`
- [ ] Configure `ITK_RESOLVER_CMD` in `.env`
- [ ] Run resolver: `itk resolve` or pre-run hook
- [ ] Verify `targets.json` has correct queue URLs, log groups, etc.

## ITK-W-0003 — First live run
- [ ] Pick a simple case from `cases/`
- [ ] Run: `itk run --case cases/example.yaml --out artifacts/run-001/`
- [ ] Verify artifacts created:
  - `trace-viewer.html` — opens in browser, shows sequence
  - `spans.jsonl` — contains span data
  - `report.md` — summary
- [ ] If diagram is incomplete, proceed to ITK-W-0004

## ITK-W-0004 — Fix logging gaps
- [ ] Run: `itk audit --case cases/example.yaml --out artifacts/audit/`
- [ ] Review `logging-gaps.md` for missing boundary logs
- [ ] Add minimal WARN-level JSON span logs at:
  - Lambda handler entry/exit
  - Bedrock agent invoke entry/exit
  - SQS message receive
  - Error catch blocks
- [ ] Re-run case, verify improved diagram

## ITK-W-0005 — Derive cases from production logs
- [ ] Run: `itk derive --since 24h --out cases/derived/`
- [ ] Review generated case YAMLs
- [ ] Curate: keep representative paths, remove duplicates
- [ ] Add expected outcomes to cases

## ITK-W-0006 — Build test suite
- [ ] Create `suites/smoke.yaml` with top 5-10 cases
- [ ] Run: `itk suite --suite suites/smoke.yaml --out artifacts/smoke/`
- [ ] Review `index.html` report
- [ ] Iterate on cases until suite is green

## ITK-W-0007 — CI integration
- [ ] Add ITK workflow to `.github/workflows/` or equivalent
- [ ] Configure to run on PR and merge to main
- [ ] Set up artifact upload for test reports
- [ ] Optional: add compare mode to fail on regressions

## ITK-W-0008 — Soak testing
- [ ] Configure soak parameters in `.env`:
  - `ITK_SOAK_ITERATIONS` (number of iterations) or `ITK_SOAK_DURATION` (time-based)
  - `ITK_SOAK_INITIAL_RATE` (default: 1.0 req/s)
- [ ] Run soak with detailed artifacts:
  ```bash
  itk soak --case cases/<case>.yaml --out artifacts/soak-001/ --iterations 50 --detailed
  ```
- [ ] Open soak report: `artifacts/soak-001/soak-report.html`
- [ ] Review metrics:
  - **Pass Rate**: Should be 100% for stable systems
  - **Consistency Score**: Clean passes ÷ total passes (reveals LLM non-determinism)
  - **Warning Rate**: Passes with retries (high = flaky)
- [ ] Drill-down: Click iteration grid or table rows → opens trace-viewer.html
- [ ] Monitor for throttling: If throttle events > 0, increase interval or reduce rate

## ITK-W-0009 — Soak report interpretation
- [ ] Understand the metrics:
  - **0% Consistency + 100% Pass Rate** = All passes required retries (LLM non-determinism)
  - **High retry count** = System is flaky, investigate specific iterations
  - **Throttle events** = Hitting AWS limits, reduce rate
- [ ] Use filters in soak report:
  - "Warnings Only" — See which iterations had retries
  - "Has Retries" — Focus on non-deterministic runs
  - Sort by Duration to find slow runs
- [ ] Export for CI: Check `soak-result.json` for programmatic access

---

## Quick Reference

### Commands (all execute LIVE by default)
```bash
itk run --case <yaml> --out <dir>       # Single test run
itk suite --cases-dir <dir> --out <dir> # Run test suite  
itk audit --case <yaml> --out <dir>     # Analyze logging gaps
itk derive --since <duration> --out <dir>  # Generate cases from logs
itk soak --case <yaml> --out <dir> --iterations N  # Soak test with N iterations
itk soak --case <yaml> --out <dir> --duration 1h   # Soak test for 1 hour
itk scan --repo . --out <dir>           # Codebase coverage scan
itk view --since <duration> --out <dir>  # View historical executions
itk discover --out .env.discovered      # Discover AWS resources
```

### Never do this
```bash
# WRONG - don't use dev-fixtures for real tests
itk run --mode dev-fixtures --case ...  

# WRONG - don't mock AWS
ITK_MOCK_AWS=true itk run ...
```

---

## Report Status Reference

When reviewing `index.html` suite reports, understand the status indicators:

| Status | Icon | Meaning |
|--------|------|---------|
| **Passed** | ✅ | All invariants passed, no errors, no retries |
| **Warning** | ⚠️ | Passed but with retries or error spans detected |
| **Failed** | ❌ | One or more invariants failed |
| **Error** | 💥 | Test execution error (exception during run) |
| **Skipped** | ⏭️ | Test was skipped |

**Warning status** indicates "success but not happy path" — the test completed but:
- Retries occurred (`attempt > 1`)
- Error spans were logged (even if overall successful)

These are good candidates for investigation — they may indicate flaky tests or degraded behavior.

---

## Trace Viewer Quick Reference

The sequence diagram shows:
- **Entry arrow** (`▶ operation`) — Test start, pointing INTO first lifeline
- **Exit arrow** (`◀ latency ✅/❌`) — Test end, pointing OUT from first lifeline
- **Retry badge** (`🔄 retry N`) — On left margin, only for retried calls
- **Status on return arrows** — ✅ success / ❌ error
