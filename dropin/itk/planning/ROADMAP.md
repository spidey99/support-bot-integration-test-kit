# ROADMAP (Tier 3 — Work Repo Agent)

> **CRITICAL**: Tier-3 executes LIVE against real AWS QA resources. NO mocks in tests.
> The ONLY offline aspect is that OUTPUT artifacts are static files viewable via `file://`.

---

## Execution Model

```
┌─────────────────────────────────────────────────────────────┐
│                    TIER-3 EXECUTION                         │
├─────────────────────────────────────────────────────────────┤
│  INPUT:   Live AWS resources (SQS, Lambda, Bedrock, CW)     │
│  PROCESS: Real end-to-end test execution                    │
│  OUTPUT:  Static artifacts (HTML, JSON, MD) via file://     │
└─────────────────────────────────────────────────────────────┘

NEVER mock AWS calls in integration tests.
NEVER use dev-fixtures mode for actual test runs.
ALWAYS hit live QA resources.
```

---

## Phase 1 — Install + first live run
- [ ] Copy ITK drop-in to work repo
- [ ] Configure `.env` with real AWS targets (queue URL, log groups, etc.)
- [ ] Run resolver to populate `targets.json`
- [ ] Execute 1 case end-to-end against live QA
- [ ] Verify artifacts generated: `trace-viewer.html`, `timeline.html`, `spans.jsonl`, `report.md`

## Phase 2 — Fix logging gaps
- [ ] Run `itk audit` to identify missing boundary logs
- [ ] Add minimal JSON span logs (WARN+) at key boundaries
- [ ] Ensure `invoke_agent_with_retries` records trace/session IDs
- [ ] Re-run case, verify improved diagram completeness

## Phase 3 — Build curated suite
- [ ] Derive cases from real CloudWatch logs (`itk derive`)
- [ ] Run top 10 common path signatures
- [ ] Run rare-but-critical paths (guardrail blocks, error handling)
- [ ] Generate suite report
- [ ] Review status distribution: ✅ Passed, ⚠️ Warning, ❌ Failed, 💥 Error
- [ ] Investigate any ⚠️ warning tests (retries or error spans detected)

## Phase 4 — CI integration
- [ ] Add ITK to CI pipeline (GitHub Actions or equivalent)
- [ ] Run suite on PR/merge to main
- [ ] Optional: compare mode gate (fail on regressions)

## Phase 5 — Soak testing
- [ ] Run soak test with 50+ iterations:
  ```bash
  itk soak --case cases/<case>.yaml --out artifacts/soak/ --iterations 50 --detailed
  ```
- [ ] Review soak-report.html metrics:
  - Pass Rate: Target 100%
  - Consistency Score: Target >90% (reveals LLM non-determinism)
  - Throttle Events: Target 0
- [ ] Drill-down into warning iterations (click row → trace-viewer.html)
- [ ] If consistency < 50%, investigate retry patterns
- [ ] If throttle events > 0, reduce rate: `--initial-rate 0.5`
- [ ] Document findings in test report

---

## Key Differences from Tier-2

| Aspect | Tier-2 (Dev Agent) | Tier-3 (Work Repo Agent) |
|--------|-------------------|-------------------------|
| AWS Access | None | Full (QA environment) |
| Test Execution | Fixtures/mocks only | Live resources only |
| Output | Static artifacts | Static artifacts |
| Mode | `--mode dev-fixtures` | `--mode live` (default) |
| Purpose | Build/test the kit | Run real integration tests |

---

## Non-Negotiables

1. **Live execution**: Every test run hits real SQS → Lambda → Bedrock → CloudWatch
2. **No downstream mocks**: The system under test runs unmodified
3. **Static output**: Artifacts work via `file://` with no server
4. **Correlation via logs/traces**: Build span graph from CloudWatch + Bedrock traces
5. **Fail loudly**: If AWS calls fail, the test fails — don't silently fall back to mocks
