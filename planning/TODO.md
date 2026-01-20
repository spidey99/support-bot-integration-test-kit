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

## ITK-0040 — Bedrock agent orchestration bug (shelved)
- [ ] Investigate Nova/Bedrock Agent message serialization bug (`[{text=...}]` format)
- [ ] Resolve collaborator association permissions for agent aliases
- [ ] Re-verify worker action-group invocation with Claude Haiku 4.5

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

## ITK-0029 — AWS Account Recovery (HUMAN ACTION) ✅
- [x] Log into AWS console (recover password if needed)
- [x] Check for outstanding bills, pay if necessary
- [x] Set up billing alerts: $10, $25, $50 thresholds
- [x] Verify account is in good standing
- [x] Note account ID for .env setup: **(see .env.example)**

## ITK-0030 — Minimal AWS Test Infrastructure (HUMAN ACTION) ✅
- [x] Create IAM user `itk-test-user` with scoped permissions:
  - logs:GetQueryResults, logs:StartQuery, logs:FilterLogEvents
  - sqs:SendMessage, sqs:ReceiveMessage (single queue)
  - lambda:InvokeFunction (single function)
  - bedrock:InvokeAgent, bedrock:InvokeModel
- [x] Create Lambda function `itk-haiku-invoker`:
  - Invokes Claude Haiku 4.5 via Bedrock inference profile
  - Returns response as text
- [x] Create SQS queue `itk-test-queue` (standard, not FIFO)
- [x] Create CloudWatch log group `/aws/lambda/itk-haiku-invoker`
  - Retention: 7 days (cost control)
- [x] Create Bedrock agents:
  - Worker agent (`WYEP3TYH1A`) with action group invoking Lambda
  - Supervisor agent (`OXKSJVXZSU`) standalone (collaboration shelved ITK-0040)
- [x] All resources managed via Terraform in `dropin/itk/infra/terraform/`
- [x] Env file generated: `dropin/itk/env/live.env`

## ITK-0031 — Live mode validation ✅

### ITK-0031a — Parser handles realistic log variance ✅
- [x] Enhance parser with `FIELD_MAPPINGS` for common field name variants
- [x] Auto-detect fields: `span_id`/`spanId`, `timestamp`/`ts_start`, `requestId`/`request_id`
- [x] Auto-generate `span_id` if missing (deterministic from trace_id + operation + timestamp)
- [x] Infer component from message text if not explicit
- [x] Skip non-span log entries (plain debug messages, Lambda runtime messages)
- [x] Add `load_realistic_logs_as_spans()` and `parse_cloudwatch_logs()` functions
- [x] 13 tests covering field variance, auto-generation, filtering

### ITK-0031b — Create live test case ✅
- [x] Create `cases/live-haiku-001.yaml` targeting Worker agent
- [x] Define entrypoint: `bedrock_invoke_agent` with agent/alias IDs from env
- [x] Define expected outcome: successful response containing text
- [x] Validate case against schema

### ITK-0031c — Run live mode end-to-end ✅
- [x] Ensure `itk run --mode live` command is implemented
- [x] Run: `itk run --mode live --case cases/live-haiku-001.yaml --out artifacts/live-001/`
- [x] Verify CloudWatch adapter fetches real logs (0 this run - agent replied directly)
- [x] Verify trace-viewer.html renders spans from live data
- [x] Verify spans are correlated correctly (3 Bedrock trace spans)

### ITK-0031d — Derive cases from CloudWatch ✅
- [x] Ensure `itk derive` command is implemented
- [x] Run: `itk derive --entrypoint bedrock_invoke_agent --since 1h --out artifacts/derived/`
- [x] Verify generated case YAML matches log structure
- [x] Verify case is runnable (tested in dev-fixtures mode)

### ITK-0031e — Soak test with real throttling ✅
- [x] Run: `itk soak --case cases/live-haiku-001.yaml --out artifacts/soak/ --iterations 20`
- [x] Verify rate controller detects/responds to throttling (0 throttle events at 1.0 req/s)
- [x] Verify soak-report.html shows real metrics (100% pass rate, 100% consistency)
- [x] Document any edge cases found:
  - No Lambda logs fetched (agent replied directly via Bedrock without action group)
  - Rate controller maintained 0.90-1.90 req/s successfully
  - Each iteration ~7.8-8.2 seconds (includes 3s CloudWatch wait)

### ITK-0031f — Document fixture vs live discrepancies ✅
- [x] Compare fixture mode output structure to live mode
- [x] Note any field differences, missing data, or timing issues
- [x] Created `docs/08-fixture-vs-live-discrepancies.md` with:
  - Summary table of 8 key differences
  - Detailed analysis of each discrepancy
  - Checklists for test authors
  - Known limitations section
- [ ] Update docs if needed

---

## Phase 12: Zero-Config Bootstrap

## ITK-0032 — Bootstrap scripts ✅
- [x] Create `scripts/bootstrap.sh` for Mac/Linux:
  - Python 3.10+ version check
  - Creates .venv if not exists
  - Installs with pip install -e ".[dev]"
  - Verifies itk --help works
  - Copies .env.example to .env if missing
- [x] Create `scripts/bootstrap.ps1` for Windows:
  - Same functionality with PowerShell syntax
  - Color-coded output for readability
- [x] Add to QUICKSTART: "Run `./scripts/bootstrap.sh` or `.\scripts\bootstrap.ps1`"
- [x] Tested on Windows (confirmed working)

## ITK-0033 — Auto-detection in CLI ✅
- [x] Add Python version check at CLI startup (friendly error, not traceback)
- [x] Add venv detection: warn if not in venv (but don't block)
  - Suppressible via `ITK_SUPPRESS_VENV_WARNING=1`
- [x] Auto-copy `.env.example` to `.env` if missing (with log message)
- [x] Add `itk doctor` command:
  - Check Python version
  - Check dependencies installed (boto3, PyYAML, jsonschema, python-dotenv)
  - Check .env exists and validates required fields
  - Check AWS credentials (if mode=live)
  - Print summary: "Ready to run" or "Fix these issues: ..."

## ITK-0034 — Environment discovery command ✅
- [x] Add `itk discover` command (live mode only):
  - Call `logs:DescribeLogGroups` → list log groups (filters for lambda/agent/bot/api)
  - Call `sqs:ListQueues` → list queues
  - Call `lambda:ListFunctions` → list Lambda functions
  - Call `bedrock-agent:ListAgents` → list agents with aliases
  - Output: `.env.discovered` with commented suggestions
  - User reviews, picks values, renames to `.env`
- [x] Add `--region` flag (default: from env or us-east-1)
- [x] Add `--profile` flag (for AWS CLI profiles)
- [x] Add `--out` flag (default: .env.discovered)
- [x] Handle permission errors gracefully ("Missing permission for X, skipping")

---

## Phase 13: Derp-Proof Usage

## ITK-0035 — Config-only operation ✅
- [x] Audit all docs for "edit this file" instructions → replaced with .env vars
- [x] Ensure every CLI flag has a sensible default (verified)
- [x] Create `schemas/itk.config.defaults.json` with all defaults documented
- [x] Add `itk show-config` to print effective config (merged from all sources)

## ITK-0036 — Single-action workflows ✅
- [x] Add `itk quickstart` command:
  1. Run bootstrap checks (Python version, dependencies)
  2. Handle .env file (create from .env.example if missing)
  3. Determine mode from env
  4. Run first test case (prefers example-*.yaml)
  5. Open trace-viewer in browser
- [x] Add `itk validate-env` command:
  - Parse .env
  - Check required fields present (with aliases: ITK_AWS_REGION or AWS_REGION)
  - Check AWS credentials valid (if mode=live)
  - Print "Environment valid" or specific issues
- [x] Add `itk status` command:
  - Show current mode (dev-fixtures/live)
  - Show configured log groups
  - Show last run timestamp/status
  - Show any pending issues (health check)

## ITK-0037 — Error message improvements ✅
- [x] Create error code registry (`src/itk/errors.py`):
  - ITK-E001: Missing .env file
  - ITK-E002: Invalid .env format
  - ITK-E003: AWS credentials not configured
  - ITK-E004: Log group not found
  - ITK-E005: Case file not found
  - ITK-E006: Schema validation failed
  - etc.
- [x] Each error prints: code, message, "Next step: <command>"
- [x] Add `--verbose` flag to show full traceback
- [x] Create `docs/error-codes.md` with all codes and solutions

---

## Phase 14: Log Schema Documentation

## ITK-0038 — Reference log documentation ✅
- [x] Create `docs/log-schema-example.json`:
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
- [x] Create `docs/log-field-glossary.md` with every field explained
- [x] Add field comments to `schemas/itk.span.schema.json`

## ITK-0039 — Schema explanation CLI ✅
- [x] Add `itk explain-schema` command:
  - Pretty-print itk.span.schema.json with examples
  - Show required vs optional fields
  - Show enum values with descriptions
- [x] Add `itk validate-log --file <path>`:
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

---

## New Work Items (January 2026)

## ITK-0041 — Top-level HTML report for single runs ✅
- [x] Add `render_run_report_html()` to artifacts.py
- [x] Generate `index.html` alongside trace-viewer.html for every run
- [x] Include: summary stats, invariant results, span table, viewer links
- [x] Pass `agent_response` and `mode` to write_run_artifacts
- [x] Print `Report: {path}/index.html` in CLI output
- [x] Dark mode styling consistent with other reports
- [x] All 482 tests passing

## ITK-0042 — Enhanced discovery with version mapping ✅
- [x] Show agent version → alias mapping in `itk discover` output
- [x] Call `bedrock-agent:ListAgentVersions` for each agent
- [x] Call `bedrock-agent:ListAgentAliases` to get alias→version mappings
- [x] Output: agent name, ID, versions (with status), aliases (with version pointer)
- [x] Console shows ✅ when alias points to latest PREPARED version
- [x] .env.discovered includes detailed version/alias info with comments
- [x] All 496 tests passing

## ITK-0043 — Default "latest version" mode for agent targeting ✅
- [x] Add `agent_version: "latest"` as valid target option in case YAML
- [x] At runtime, resolve "latest" to the most recent PREPARED version
- [x] Call `bedrock-agent:ListAgentVersions` sorted by createdAt desc
- [x] Skip DRAFT versions unless explicitly requested
- [x] Skip FAILED/DELETING versions
- [x] Support `agent_version: "draft"` using TSTALIASID
- [x] Cache resolved version for duration of run (via VersionResolver cache)
- [x] Created `itk/entrypoints/version_resolver.py` with:
  - VersionResolver class with list_versions, list_aliases, find_alias_for_version
  - AgentVersion, AgentAlias, ResolvedAgent dataclasses
  - resolve() method handling alias, latest, draft, explicit version
- [x] Updated BedrockAgentTarget to support agent_version field
- [x] Updated CLI _run_live_mode to use version resolver
- [x] Added 14 tests for version resolver
- [x] Created example cases: test-latest-version.yaml, test-draft-version.yaml
- [ ] Document in `docs/02-test-case-format.md` (pending)

## ITK-0044 — Historical execution viewer (`itk view`) ✅
- [x] Add `itk view` command for retrospective log viewing
- [x] Flags: `--since`, `--until`, `--log-groups`, `--out`, `--filter`
- [x] Fetch CloudWatch logs for time window
- [x] Group log events by trace_id or session_id
- [x] For each execution:
  - Build spans
  - Generate trace-viewer.html + timeline.html + spans.jsonl
  - Generate thumbnail.svg
- [x] Generate top-level gallery page (index.html) linking all executions
- [x] Show: timestamp, status, span count, duration, component badges
- [x] Support filtering: `--filter errors` (only failed), `--filter all`
- [x] Works offline with `--logs-file` for local JSONL
- [x] Created `itk/report/historical_viewer.py` with:
  - ExecutionSummary, ViewResult dataclasses
  - group_spans_by_execution, analyze_execution, filter_executions
  - render_gallery_html with dark mode, filter buttons, status colors
  - load_logs_from_file, fetch_logs_for_time_window
- [x] Added 29 tests for historical viewer
- [x] All 525 tests passing

## ITK-0050 — Zero-config bootstrap (`itk bootstrap`) ✅
- [x] Add `itk bootstrap` command for zero-config initialization
- [x] Auto-detect project root by walking up directory tree
- [x] Auto-find .env file from any subdirectory
- [x] Credential health check with clear fix instructions
- [x] Auto-discover AWS resources (log groups, agents, queues)
- [x] Generate .env with discovered values
- [x] Create example-001.yaml case from discovered agent
- [x] Create directory scaffold (cases/, fixtures/, artifacts/)
- [x] Run test and open browser on success
- [x] Flags: `--region`, `--profile`, `--offline`, `--force`, `--no-run`
- [x] Add `itk init` for lightweight scaffold-only mode
- [x] Add `itk discover --apply` to merge directly into .env
- [x] Auto-discover log groups in live mode when not configured
- [x] Created `itk/bootstrap.py` module with:
  - find_project_root, find_env_file (walk up tree)
  - check_credentials, get_default_region, get_default_profile
  - discover_resources_minimal (lightweight AWS scan)
  - generate_env_content, generate_example_case
  - ensure_directories, bootstrap (main orchestrator)
- [x] Added 28 tests for bootstrap module
- [x] All 553 tests passing

---

## Documentation & Templates (Final Polish)

## ITK-0045 — GitHub Actions workflow template
- [ ] Create `.github/workflows/itk.yml` in `_merge_to_repo_root/`
- [ ] Mirror GitLab CI structure: smoke, suite, audit jobs
- [ ] Use `actions/setup-python@v5` and AWS credentials action
- [ ] Upload artifacts with `actions/upload-artifact@v4`
- [ ] Add manual trigger (`workflow_dispatch`) and PR trigger
- [ ] Document in `ITK_SETUP.md`

## ITK-0046 — Simplify Tier-3 TODO to Integration Checklist
- [ ] Rename `dropin/itk/planning/TODO.md` to `INTEGRATION_CHECKLIST.md`
- [ ] Remove "Tier 3 agent" language - it's now human/simple steps
- [ ] Simplify to: Install → Discover → Configure → Run
- [ ] Remove resolver configuration (rarely used)
- [ ] Add links to ITK commands for each step
- [ ] Update references in other docs

## ITK-0047 — Document `agent_version` targeting
- [ ] Update `docs/02-test-case-format.md` with agent_version field
- [ ] Document options: `"latest"`, `"draft"`, explicit version number
- [ ] Add example cases showing each mode
- [ ] Explain version resolution behavior

## ITK-0048 — Update test counts and implementation notes
- [ ] Update "453 tests" → "543 tests" in TODO.md
- [ ] Update "What works now" section with new commands
- [ ] Add `itk view` to command list
- [ ] Add `itk discover` to command list
- [ ] Review ROADMAP.md phase checkboxes

## ITK-0049 — Mark Tier-2 feature-complete
- [ ] Add "Feature Complete" banner to ROADMAP.md
- [ ] Summarize all completed phases
- [ ] Document what's deferred (Phase 15 - reference infra)
- [ ] Update README.md with current capability summary

---

## High Priority: E2E Prove-It Test

## ITK-0051 — E2E prove_it test with isolated infra ✅
**STATUS: IMPLEMENTED** — Ready to run with fresh credentials

Goal: Fully automated test that proves the entire ITK flow works:
1. Accept AWS credentials as input (`export AWS_ACCESS_KEY_ID=...` format)
2. Stand up **isolated** test infra via Terraform (different from shared infra)
3. Invoke the infra to generate logs for ITK to consume
4. Fresh directory, simulate derpy agent following setup prompt
5. Run bootstrap, view, derive, test execution
6. Tear down infra after run

### Implementation:
- [x] Create `infra/terraform-e2e/` with isolated resources (unique naming via random_id)
- [x] Create `scripts/prove_it_e2e.ps1` orchestrator script
- [x] Credential injection: parse `export` format, inject to .env
- [x] Terraform apply with timeout/validation
- [x] Invoke Lambda to generate CloudWatch logs (wait for propagation)
- [x] Run ITK bootstrap in fresh temp directory
- [x] Run `itk view --since 10m` and validate spans found
- [x] Run dev-fixtures mode validation
- [x] Terraform destroy (always, even on failure)
- [x] Report pass/fail with timing

### Usage:
```powershell
# Get fresh credentials from AWS CloudShell:
aws configure export-credentials --format env

# Run E2E test:
.\scripts\prove_it_e2e.ps1 -Credentials @"
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...
"@
```

### Why isolated infra:
- Existing infra is used for other tests — dirty state
- E2E test must prove setup from scratch works
- Parallel runs must not conflict

### Blockers resolved before this:
- [x] Bootstrap works with `export` prefix credentials
- [x] Credentials preserved on `--force`
- [x] BootstrapResult.discovered attribute exists
- [x] CLI imports work correctly
- [x] Windows UTF-8 encoding handled