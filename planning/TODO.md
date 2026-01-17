# TODO (Tier 2)

## ITK-0001 — Schemas ✅
- [x] Define `itk.case.schema.json`
- [x] Define `itk.span.schema.json`
- [x] Define `itk.config.schema.json`

## ITK-0002 — Offline CLI + rendering ✅
- [x] CLI skeleton: `itk` entrypoint
- [x] `render-fixture` command
- [x] Emit: `sequence.mmd`, `spans.jsonl`, `payloads/*.json`, `report.md`

## ITK-0003 — Span normalization + correlation ✅
- [x] Extract IDs: lambda request id, xray trace id, sqs message id, bedrock session ids
- [x] Build correlation graph
- [x] Topological/timestamp ordering

## ITK-0004 — Log-gap auditor ✅
- [x] Detect missing request/response payloads for key boundaries
- [x] Emit `logging-gaps.md` with concrete actions

## ITK-0005 — AWS adapters (write-only offline) ✅
- [x] CloudWatch Logs Insights client
- [x] Lambda invoke adapter
- [x] SQS publish adapter
- [x] Bedrock InvokeAgent adapter (enableTrace)

## ITK-0006 — Compare mode ✅
- [x] Path signature
- [x] Retry/latency deltas
- [x] Error class deltas

## ITK-0007 — Ops sanity ✅
- [x] Add redaction rules + allowlist
- [x] Add safe defaults (no PII in artifacts)

## OUT-OF-BAND
- [ ] Re-enable personal AWS subscription (optional) — only if needed for local integration tests

---

## Additional Tier-2 Items (Offline)

## ITK-0008 — Enhanced invariants ✅
- [x] Add `no_orphan_spans` invariant (all spans have parent or are root)
- [x] Add `valid_timestamps` invariant (ts_end >= ts_start)
- [x] Add `no_duplicate_span_ids` invariant
- [x] Add `max_retry_count` invariant (configurable threshold)
- [x] Add `required_components` invariant (case can specify expected components)
- [x] Add `has_entrypoint` invariant (at least one root span)
- [x] Add `no_error_spans` invariant (for success-path tests)

## ITK-0009 — Documentation refresh ✅
- [x] Update `06-compare-mode.md` with CLI usage and output examples
- [x] Update `07-security-and-redaction.md` with pattern list and config
- [ ] Add architecture diagram to docs (deferred - needs visual tooling)
- [ ] Add example outputs to docs/examples/ (deferred - needs real fixtures)

## ITK-0010 — Fixture generation ✅
- [x] Add `itk generate-fixture` command to create sample fixtures
- [x] Support generating fixtures from span definitions in YAML
- [x] Useful for testing without real log data

## ITK-0011 — Schema validation CLI ✅
- [x] Add `itk validate --case <path>` to validate case YAML
- [x] Add `itk validate --fixture <path>` to validate fixture JSONL
- [x] Emit helpful error messages for schema violations

## ITK-0012 — Sequence diagram HTML renderer ✅
- [x] Create `itk/diagrams/html_renderer.py` with modern HTML/CSS/JS output
- [x] Add participant lanes with icons/colors per component type
- [x] Style arrows with latency annotations
- [x] Include collapsible payload previews inline
- [x] Auto-generate alongside `.mmd` in artifact output

## ITK-0013 — Interactive diagram features ✅
- [x] Add zoom/pan controls (CSS transform + JS) — via svg-pan-zoom in ITK-0020
- [x] Clickable spans → expand payload JSON in modal — via details panel in ITK-0020/ITK-0025
- [x] Highlight error spans in red — via error class styling in ITK-0020
- [x] Show retry attempts with visual grouping — via retry badges in ITK-0020
- [x] Dark mode toggle (CSS variables) — via theme toggle in ITK-0020

## ITK-0014 — Timeline visualization ✅
- [x] Add optional timeline view showing spans on time axis
- [x] Color-code by component type
- [x] Show latency bars proportional to duration
- [x] Highlight critical path
- [x] Integrate into artifacts output (timeline.html, timeline-thumbnail.svg)
- [x] Add 38 tests for timeline module

## ITK-0015 — Export and serve options ✅
- [x] Add `--format` flag to render commands (html, mermaid, json, svg, all)
- [x] Add `itk serve --port 8080` for live preview with auto-open browser
- [x] Support SVG export via standalone render function
- [x] Add --watch flag for file watching mode
- [x] Add 5 CLI tests for format/serve options

## ITK-0016 — Codebase coverage scanner (Tier 3 prep) ✅
- [x] Create `itk scan --repo <path>` to analyze work repo codebase
- [x] Detect components not represented in existing fixtures/cases
- [x] Identify logic branches (if/else, try/catch, match) not exercised by tests
- [x] Detect logging gaps: functions/handlers missing boundary logs
- [x] Output `coverage_report.md` with actionable recommendations
- [x] Generate skeleton case YAMLs for uncovered paths (--generate-skeletons)

## ITK-0017 — Tier 3 agent guidance artifacts ✅
- [x] Create `docs/tier3-agent-guide.md` — step-by-step for weak model
- [x] Create example prompts for common Tier 3 tasks
- [x] Create `schemas/itk.tier3-task.schema.json` for structured task handoff
- [x] Add pre-flight checklist the agent must complete before AWS calls
- [x] Add rollback/recovery procedures for failed runs

## ITK-0017.5 — Work repo context questionnaire (prereq for ITK-0018) ✅
- [x] Create `docs/work-repo-questionnaire.md` — multiple choice format
- [x] Cover: repo structure, CI/CD tooling, IDE setup, team conventions
- [x] Keep it low cognitive load (ADHD-friendly, end-of-day safe)

## ITK-0018 — Work repo integration templates ✅
- [x] Create `_merge_to_repo_root/` templates ready for copy
- [x] GitLab CI workflow for ITK (`.gitlab/itk.yml`)
- [x] VS Code tasks.json for common ITK commands
- [x] README template for work repo ITK setup (`ITK_SETUP.md`)
- [x] Resolver script for branch-specific targets
- [x] Work repo .env.example

---

## New Work Items (from Tier-1 directive)

## ITK-0019 — Environment + resolver contract ✅
- [x] Create `.env.example` at repo root (Tier-2 dev-fixtures mode)
- [x] Create `.env.example` in dropin (Tier-3 live mode)
- [x] Add `--mode dev-fixtures|live` CLI flag (rename from --offline)
- [x] Add `--env-file` CLI arg
- [x] Implement dotenv consumption with precedence: CLI > .env > env vars
- [x] Create resolver hook: execute `ITK_RESOLVER_CMD`, consume output
- [x] Create `schemas/itk.targets.schema.json`
- [x] Create sample `fixtures/targets/sample_targets_001.json`
- [x] Add tests for dotenv, resolver (mocked subprocess)

## ITK-0020 — Strong interactive trace viewer ✅
- [x] Create `vendor/` directory with vendored JS libs (no CDN)
- [x] Vendor: svg-pan-zoom, fuse.js (simplified implementations)
- [x] Create `trace_viewer.py` renderer with:
  - SVG sequence view with pan/zoom
  - Search box with fuzzy matching (Fuse.js)
  - Filters (errors-only, retries-only)
  - Right panel: span details with JSON viewer
  - Click span → highlight + dim others
  - Retry badges, error styling
  - Keyboard: / to search, Esc close, arrows navigate
  - Dark mode toggle
- [x] Create `render_mini_svg()` for report thumbnails
- [x] Integrated into artifacts output (trace-viewer.html, thumbnail.svg)
- [x] Keep Mermaid `.mmd` and legacy `sequence.html` as secondary outputs
- [x] Add 42 tests for trace_viewer module

## ITK-0021 — Suite + soak reporting ✅
- [x] Create `itk/report/` module with CaseResult, SuiteResult dataclasses
- [x] Create `suite_runner.py` for multi-case execution
- [x] Generate `index.html` for suite runs with stats table
- [x] Per-row: status, duration, span count, error count, mini diagram
- [x] Click opens full trace viewer
- [x] Generate `index.json` summary
- [x] Add `itk suite --cases-dir --out` command
- [x] Add 33 tests for report module

## ITK-0022 — Soak mode + rate limiter ✅
- [x] Add `itk soak` command
- [x] Flags: --case, --duration/--iterations, --initial-rate
- [x] Implement `RateController` with AIMD-based adaptation
- [x] Throttle detection: 429s, ThrottlingException, retry storms
- [x] On throttle: multiplicative decrease + backoff
- [x] On stability: additive increase
- [x] Live soak report (soak-report.html, soak-result.json)
- [x] Add 33 tests for soak module

## ITK-0023 — CLI mode rename ✅
- [x] Remove deprecated `--offline` flag from all commands
- [x] `--mode live` is already the default
- [x] Update all docs to use `--mode dev-fixtures`
- [x] Tier-3 guide already warns against dev-fixtures misuse

## ITK-0024 — Trace viewer: call/return arrow semantics ✅
- [x] Model invocation vs return as separate visual elements
- [x] Call arrow: left → right (caller to callee) at span start (solid line)
- [x] Return arrow: right → left (callee to caller) at span end (dashed line)
- [x] Support one-way flows (fire-and-forget) via is_async flag
- [x] Update SVG rendering to draw paired arrows per span
- [x] Add activation box on callee lifeline during span
- [x] Add status indicator on callee's lifeline:
  - ❌ Red X for error/failure spans
  - ✅ Green checkmark for successful spans
- [x] Add 3 new tests for call/return semantics

## ITK-0025 — Trace viewer: payload display fixes ✅
- [x] Fix details panel to show request/response/error JSON properly
- [x] Ensure payload data is passed through to JS correctly (escaping issues?)
- [x] Add "copy to clipboard" button for payloads
- [x] Show payload size/truncation indicator for large payloads
- [x] Add 2 new tests for payload display
- [ ] ~~Consider inline payload preview on hover (tooltip)~~ (deferred)

## ITK-0026 — Test status enhancements ✅
- [x] Add `PASSED_WITH_WARNINGS` status for non-happy-path success scenarios
- [x] Trigger warning when: retry_count > 0 OR error_count > 0
- [x] Update suite report filters: [✅][⚠️][❌][💥] (passed/warning/failed/error)
- [x] Differentiate error (execution failure) from failed (invariant failure): 💥 vs ❌
- [x] Add demo-failure-001.yaml and demo-warning-001.yaml test cases
- [x] Add 2 new tests for warning status

## ITK-0027 — Entry/exit arrow redesign ✅
- [x] Replace curved self-loop arrows with intuitive horizontal arrows
- [x] Entry arrow: `▶ operation_name` from left INTO first lifeline
- [x] Exit arrow: `◀ latency ✅/❌` from first lifeline TO left (mirrors entry)
- [x] Both arrows originate/terminate on LEFT side (no confusion with retries)
- [x] Retry badge repositioned: `🔄 retry N` at fixed left margin (x=30)
- [x] Update retry numbering: attempt 2 → "retry 1", attempt 3 → "retry 2"
- [x] Add 3 new tests for entry/exit arrow rendering

## ITK-0028 — Suite report button layout ✅
- [x] Two-row button layout in expanded test details:
  - Row 1: `🔍 Sequence` and `📊 Timeline` modal buttons (primary)
  - Row 2: `↗️ Sequence Tab` and `↗️ Timeline Tab` links (secondary)
- [x] Modal supports dynamic title ("Sequence Diagram" or "Timeline View")
- [x] Add timeline modal button test

---

## Phase 11: Personal Live Environment (Human + Tier 2)

## ITK-0029 — AWS Account Recovery (HUMAN ACTION) ⏳
- [ ] Log into AWS console (recover password if needed)
- [ ] Check for outstanding bills, pay if necessary
- [ ] Set up billing alerts: $10, $25, $50 thresholds
- [ ] Verify account is in good standing
- [ ] Note account ID for .env setup

## ITK-0030 — Minimal AWS Test Infrastructure (HUMAN ACTION) ⏳
- [ ] Create IAM user `itk-test-user` with scoped permissions:
  - logs:GetQueryResults, logs:StartQuery, logs:FilterLogEvents
  - sqs:SendMessage, sqs:ReceiveMessage (single queue)
  - lambda:InvokeFunction (single function)
  - (optional) bedrock:InvokeAgent
- [ ] Create Lambda function `itk-echo-lambda`:
  - Simple echo handler: receives JSON, logs it, returns it
  - Log format matches ITK span contract (span_type, operation, etc.)
- [ ] Create SQS queue `itk-test-queue` (standard, not FIFO)
- [ ] Create CloudWatch log group `/aws/lambda/itk-echo-lambda`
  - Retention: 7 days (cost control)
- [ ] (Optional) Create Bedrock agent `itk-test-agent` with simple prompt
- [ ] Document all resource ARNs/IDs in a local `.env.personal` file

## ITK-0031 — Live mode validation ⏳
- [ ] Create test case `cases/live-echo-001.yaml` targeting personal Lambda
- [ ] Run `itk run --mode live --case cases/live-echo-001.yaml --out artifacts/live-test/`
- [ ] Verify trace-viewer.html shows real spans from CloudWatch
- [ ] Run `itk derive --log-group /aws/lambda/itk-echo-lambda --out artifacts/derived/`
- [ ] Verify derived case captures real log structure
- [ ] Run `itk soak --case cases/live-echo-001.yaml --out artifacts/soak/ --iterations 20`
- [ ] Verify rate controller responds to real throttling (if any)
- [ ] Document any discrepancies between fixture mode and live mode

---

## Phase 12: Zero-Config Bootstrap

## ITK-0032 — Bootstrap scripts ⏳
- [ ] Create `scripts/bootstrap.sh` for Mac/Linux:
  ```bash
  #!/bin/bash
  set -e
  python3 --version | grep -E "3\.(1[0-9]|[2-9][0-9])" || { echo "Python 3.10+ required"; exit 1; }
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -e ".[dev]"
  itk --help > /dev/null && echo "SUCCESS: ITK installed" || echo "FAILED"
  ```
- [ ] Create `scripts/bootstrap.ps1` for Windows:
  ```powershell
  $ErrorActionPreference = "Stop"
  python --version | Select-String "3\.(1[0-9]|[2-9][0-9])" || throw "Python 3.10+ required"
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -e ".[dev]"
  itk --help | Out-Null; if ($?) { "SUCCESS: ITK installed" } else { "FAILED" }
  ```
- [ ] Add to QUICKSTART: "Run `./scripts/bootstrap.sh` or `.\scripts\bootstrap.ps1`"
- [ ] Test on fresh machine (no prior Python setup)

## ITK-0033 — Auto-detection in CLI ⏳
- [ ] Add Python version check at CLI startup (friendly error, not traceback)
- [ ] Add venv detection: warn if not in venv (but don't block)
- [ ] Auto-copy `.env.example` to `.env` if missing (with log message)
- [ ] Add `itk doctor` command:
  - Check Python version
  - Check dependencies installed
  - Check .env exists and is valid
  - Check AWS credentials (if mode=live)
  - Print summary: "Ready to run" or "Fix these issues: ..."

## ITK-0034 — Environment discovery command ⏳
- [ ] Add `itk discover` command (live mode only):
  - Call `logs:DescribeLogGroups` → list log groups
  - Call `sqs:ListQueues` → list queues
  - Call `bedrock-agent:ListAgents` → list agents (if available)
  - Output: `.env.discovered` with commented suggestions
  - User reviews, picks values, renames to `.env`
- [ ] Add `--region` flag (default: from env or us-east-1)
- [ ] Add `--profile` flag (for AWS CLI profiles)
- [ ] Handle permission errors gracefully ("Missing permission for X, skipping")

---

## Phase 13: Derp-Proof Usage

## ITK-0035 — Config-only operation ⏳
- [ ] Audit all docs for "edit this file" instructions → replace with .env vars
- [ ] Ensure every CLI flag has a sensible default
- [ ] Create `itk.config.defaults.json` with all defaults documented
- [ ] Add `itk show-config` to print effective config (merged from all sources)

## ITK-0036 — Single-action workflows ⏳
- [ ] Add `itk quickstart` command:
  1. Run bootstrap checks
  2. Run discover (if mode=live)
  3. Create sample .env if missing
  4. Run first test case
  5. Open trace-viewer in browser
- [ ] Add `itk validate-env` command:
  - Parse .env
  - Check required fields present
  - Check AWS credentials valid (if mode=live)
  - Print "Environment valid" or specific issues
- [ ] Add `itk status` command:
  - Show current mode (dev-fixtures/live)
  - Show configured log groups
  - Show last run timestamp/status
  - Show any pending issues from `itk doctor`

## ITK-0037 — Error message improvements ⏳
- [ ] Create error code registry (`src/itk/errors.py`):
  - ITK-E001: Missing .env file
  - ITK-E002: Invalid .env format
  - ITK-E003: AWS credentials not configured
  - ITK-E004: Log group not found
  - ITK-E005: Case file not found
  - ITK-E006: Schema validation failed
  - etc.
- [ ] Each error prints: code, message, "Next step: <command>"
- [ ] Add `--verbose` flag to show full traceback
- [ ] Create `docs/error-codes.md` with all codes and solutions

---

## Phase 14: Log Schema Documentation

## ITK-0038 — Reference log documentation ⏳
- [ ] Create `docs/log-schema-example.json`:
  ```json
  {
    "// comment": "This is a single span log entry",
    "span_type": "bedrock_agent",   // Component type
    "operation": "InvokeAgent",      // What was called
    "trace_id": "abc123",            // For correlation
    "request_id": "req-456",         // AWS request ID
    "ts_start": "2026-01-17T10:00:00Z",
    "ts_end": "2026-01-17T10:00:01Z",
    "request": { "/* input payload */" },
    "response": { "/* output payload */" },
    "error": null,                   // Or error object if failed
    "retry_attempt": 0               // 0 = first try, 1+ = retries
  }
  ```
- [ ] Create `docs/log-field-glossary.md` with every field explained
- [ ] Add field comments to `schemas/itk.span.schema.json`

## ITK-0039 — Schema explanation CLI ⏳
- [ ] Add `itk explain-schema` command:
  - Pretty-print itk.span.schema.json with examples
  - Show required vs optional fields
  - Show enum values with descriptions
- [ ] Add `itk validate-log --file <path>`:
  - Validate each line of JSONL against schema
  - Report: "Line 5: missing required field 'span_type'"
  - Summary: "X valid, Y invalid"

---

## Implementation Notes (Tier 2)

> **Context**: Tier-2 develops offline against fixtures/mocks.
> Our tests validate parsing/stitching/rendering. We cannot test live AWS.

### What works now:
- `itk run --mode dev-fixtures --case <path> --out <dir>` — produces sequence.mmd, spans.jsonl, report.md, payloads/, sequence.html, trace-viewer.html, thumbnail.svg
- `itk audit --mode dev-fixtures --case <path> --out <dir>` — produces logging-gaps.md
- `itk render-fixture --fixture <path> --out <dir>` — renders fixture to Mermaid
- `itk compare --a <dir> --b <dir> --out <dir>` — compares run outputs with path signatures
- `itk generate-fixture --definition <yaml> --out <jsonl>` — generates test fixtures
- `itk validate --case <path> --fixture <path>` — validates against JSON schemas
- `itk scan --repo <path> --out <dir>` — scans codebase for coverage gaps
- `itk suite --cases-dir <path> --out <dir>` — runs multiple cases, generates index.html report
- `itk soak --case <path> --out <dir>` — runs soak test with adaptive rate control
- 453 pytest tests covering all modules

### What Tier-3 must wire:
- AWS adapters to real resources (boto3 clients stubbed but ready)
- `itk derive` to create cases from CloudWatch logs
- Live mode execution against QA resources
