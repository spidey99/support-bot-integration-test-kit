# TODO (Tier 3 — Work Repo Agent)

> **REMEMBER**: All test execution is LIVE. Never use mocks. Never use dev-fixtures mode for real tests.

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
  - `trace.html` — opens in browser, shows sequence
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

## ITK-W-0008 — Soak testing (optional)
- [ ] Configure soak parameters in `.env`:
  - `ITK_SOAK_DURATION` or `ITK_SOAK_ITERATIONS`
  - `ITK_SOAK_INTERVAL`
  - `ITK_SOAK_MAX_INFLIGHT`
- [ ] Run: `itk soak --suite suites/smoke.yaml --out artifacts/soak/`
- [ ] Monitor for throttling, adjust rate limiter as needed

---

## Quick Reference

### Commands (all execute LIVE by default)
```bash
itk run --case <yaml> --out <dir>       # Single test run
itk suite --suite <yaml> --out <dir>    # Run test suite  
itk audit --case <yaml> --out <dir>     # Analyze logging gaps
itk derive --since <duration> --out <dir>  # Generate cases from logs
itk soak --suite <yaml> --out <dir>     # Continuous execution
itk scan --repo . --out <dir>           # Codebase coverage scan
```

### Never do this
```bash
# WRONG - don't use dev-fixtures for real tests
itk run --mode dev-fixtures --case ...  

# WRONG - don't mock AWS
ITK_MOCK_AWS=true itk run ...
```
