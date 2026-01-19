# ROADMAP (Tier 2 — Development Agent)

> **Context**: Tier-2 develops OFFLINE against fixtures/mocks. We cannot access AWS resources.
> Our job is to build a generic, well-tested kit that Tier-3 can wire to live resources.

---

## Phase 0 — Skeleton + contracts ✅
- Directory structure
- JSON Schemas for cases/spans/config
- CLI command layout
- Mermaid diagram output format

## Phase 1 — Dev-fixtures engine ✅
- Fixture ingestion (JSONL logs)
- Span model normalization
- Correlation graph stitching (multi-key)
- Mermaid sequence renderer
- Log-gap auditor

## Phase 2 — AWS adapters (code complete, untestable offline) ✅
- CloudWatch Logs Insights fetcher (stubbed)
- Lambda invoke adapter (stubbed)
- SQS publish adapter (stubbed)
- Bedrock InvokeAgent adapter with enableTrace (stubbed)

## Phase 3 — Compare + coverage ✅
- Path signature grouping
- Compare-mode reporting (baseline vs current)
- Latency delta detection

## Phase 4 — Work repo integration (partial) 🔄
- Drop-in instructions
- Copilot merge artifacts
- Minimal required logging contract guidance
- GitHub Actions / CI templates
- VS Code integration (tasks.json, settings)

## Phase 5 — Codebase coverage scanner ✅
- Static analysis of work repo to find components
- Detect handlers/functions not represented in test cases
- Identify logic branches (if/else, error paths) not exercised
- Find logging gaps: missing boundary logs in code
- Generate skeleton cases for uncovered paths

## Phase 6 — Environment + resolver contract 🆕
- `.env.example` files for dev-fixtures (Tier-2) and live (Tier-3)
- Resolver hook: pre-run command to refresh targets
- `itk.targets.schema.json` for dynamic target resolution
- CLI `--mode dev-fixtures|live` flag
- dotenv consumption with proper precedence

## Phase 7 — Strong interactive trace viewer 🆕
- Vendor JS libs (no CDN): svg-pan-zoom, vis-timeline, fuse.js, jsoneditor
- `trace-viewer.html` per run: sequence view + timeline view + payload inspector
- Search, filter, keyboard navigation
- Retry visualization, error highlighting
- `mini.svg` for report thumbnails
- Keep Mermaid `.mmd` as secondary output

## Phase 8 — Suite + soak reporting 🆕
- Top-level `index.html` listing all runs in suite/soak
- Per-row: status, duration, span count, mini diagram preview
- Click to open full trace viewer
- `index.json` summary for tooling

## Phase 9 — Soak mode + rate limiter 🆕
- `itk soak` command for continuous test execution
- Dynamic rate controller (AIMD-based)
- Throttle detection from logs/traces
- Max inflight, interval/jitter controls

## Phase 10 — Tier 3 agent preparation 🔄
- Step-by-step guide for weak models
- Structured task handoff schema
- Example prompts for common operations
- Pre-flight checklists
- Rollback/recovery procedures

---

## Phase 11 — Personal live environment (Tier 2 validation) 🆕
> **Goal**: Validate ITK's live mode works end-to-end using a personal AWS account.
> This removes dependency on work environments and derpy Tier 3 agents.

### Human Actions Required:
- [ ] Recover AWS account access (account recovery flow)
- [ ] Pay outstanding AWS bills (if any)
- [ ] Set up billing alerts ($10, $25, $50 thresholds)
- [ ] Create IAM user with limited permissions for ITK testing

### AWS Resource Setup:
- [ ] Create minimal Lambda function (echo handler)
- [ ] Create SQS queue (itk-test-queue)
- [ ] Configure CloudWatch log groups with proper retention (7 days)
- [ ] (Optional) Set up Bedrock agent with simple prompt

### ITK Live Mode Validation:
- [ ] Test `itk run --mode live` against personal Lambda
- [ ] Test `itk derive` from real CloudWatch logs
- [ ] Test `itk soak` with real rate limiting behavior
- [ ] Document any gaps between fixture mode and live mode

## Phase 12 — Zero-config bootstrap 🆕
> **Goal**: Make ITK impossible to mis-install. One command, zero decisions.

### Single-command installer:
- [ ] Create `scripts/bootstrap.sh` (Mac/Linux) and `scripts/bootstrap.ps1` (Windows)
- [ ] Script creates venv, installs deps, validates, runs smoke test
- [ ] No user decisions during install (pick sensible defaults)
- [ ] Print clear "SUCCESS" or "FAILED" with next steps

### Auto-detection:
- [ ] Auto-detect Python version (fail early if <3.10)
- [ ] Auto-detect if already in venv (don't nest)
- [ ] Auto-detect if ITK already installed (offer upgrade)
- [ ] Auto-create .env from .env.example if missing

### Environment auto-discovery (for work repos):
- [ ] `itk discover` command to probe AWS and fill .env
- [ ] Detect log groups matching common patterns
- [ ] Detect SQS queues in account
- [ ] Detect Bedrock agents (list-agents API)
- [ ] Output: populated .env.discovered, human reviews and renames

## Phase 13 — Derp-proof downstream usage 🆕
> **Goal**: Tier 3 (or any downstream user) runs ITK, doesn't modify it.

### Lock down modification points:
- [ ] Move all config to .env (no code changes needed)
- [ ] Remove any "edit this file" instructions from docs
- [ ] All CLI args have sensible defaults (can run with minimal flags)
- [ ] `itk doctor` command to diagnose issues without code changes

### Single-action workflows:
- [ ] `itk quickstart` — runs bootstrap + discover + first test
- [ ] `itk validate-env` — checks .env is valid before any AWS calls
- [ ] `itk status` — shows current config, last run, any issues

### Improved error messages:
- [ ] Every error includes "Next step: run <command>"
- [ ] No stack traces by default (--verbose for debug)
- [ ] Common errors get named codes (ITK-E001, ITK-E002) with docs

## Phase 14 — Log schema documentation 🆕
> **Goal**: Document expected log structure so agents/humans understand the contract.

### Reference artifacts:
- [ ] Create `docs/log-schema-example.json` — annotated example span
- [ ] Create `docs/log-field-glossary.md` — every field explained
- [ ] Add inline comments to `itk.span.schema.json`

### Auto-generation:
- [ ] `itk explain-schema` — pretty-prints schema with examples
- [ ] `itk validate-log --file <log.jsonl>` — validates log file against schema

---

## Phase 15 — Reference infrastructure library 🆕
> **Goal**: Build a library of pre-canned AWS infrastructure patterns that produce
> significantly different log structures, enabling comprehensive log processing coverage.

### Motivation:
- Current testing uses a single Bedrock agent pattern
- Real-world systems have diverse architectures: Step Functions, API Gateway, EventBridge, etc.
- Need reference implementations that produce varied log formats for parser testing
- Infrastructure should be spin-up-able, maskable (no secrets), and safe for CI

### AWS Example Sources to Evaluate:
- [ ] AWS Samples GitHub repos (aws-samples/*)
- [ ] AWS Solutions Constructs (CDK patterns)
- [ ] Serverless Application Repository examples
- [ ] AWS Well-Architected Labs

### Target Architecture Patterns:
- [ ] **Pattern A: API Gateway → Lambda → DynamoDB** (REST API pattern)
  - Logs: API GW access logs, Lambda structured logs, DynamoDB streams
- [ ] **Pattern B: SQS → Lambda → SNS** (async messaging pattern)
  - Logs: SQS delivery logs, Lambda processing, SNS notifications
- [ ] **Pattern C: Step Functions orchestration** (workflow pattern)
  - Logs: State machine execution history, task logs, CloudWatch events
- [ ] **Pattern D: EventBridge → Multiple targets** (event-driven pattern)
  - Logs: Event patterns, rule matches, target invocations
- [ ] **Pattern E: Kinesis → Lambda → S3** (streaming pattern)
  - Logs: Shard iterator logs, batch processing, S3 put events

### Infrastructure as Code:
- [ ] Create `infra/` directory with CDK/SAM templates
- [ ] Each pattern has: template, deploy script, teardown script
- [ ] Cost estimates per pattern (target: <$1/day when idle)
- [ ] Auto-shutdown after N hours (prevent bill shock)

### Log Fixture Generation:
- [ ] Scripts to invoke each pattern and capture logs
- [ ] Masking/redaction pipeline to sanitize captured logs
- [ ] Save as fixtures for offline testing
- [ ] Document expected span structure per pattern

### Failure Injection:
- [ ] Each pattern includes failure modes (timeouts, throttles, errors)
- [ ] Chaos testing hooks (Lambda failures, DLQ routing)
- [ ] Retry behavior testing (exponential backoff visibility)

---

## Phase 16 — Enhanced Agent Discovery + Targeting 🆕
> **Goal**: Streamline agent version management and default to "latest prepared" version.

### Version/Alias Discovery (ITK-0042):
- [ ] Enhance `itk discover` to show version → alias mapping
- [ ] Display: agent versions with status (PREPARED/DRAFT/FAILED)
- [ ] Display: which alias points to which version
- [ ] Display: inference profile per alias
- [ ] Table format in terminal, YAML in .env.discovered

### Default Latest Version (ITK-0043):
- [ ] Support `agent_version: "latest"` in case YAML target
- [ ] Resolve to most recent PREPARED version at runtime
- [ ] Skip DRAFT versions by default (safety)
- [ ] Add `agent_version: "draft"` for explicit draft testing
- [ ] Cache resolution per run to avoid API churn

### Version Pinning for CI:
- [ ] `itk pin-version --agent AGENTID --out .env.pinned`
- [ ] Writes exact version ID for reproducible CI runs
- [ ] Prevents "works on my machine" version drift

---

## Phase 17 — Historical Execution Viewer 🆕
> **Goal**: Browse past executions with the same UI as test runs.

### `itk view` Command (ITK-0044):
- [ ] Fetch logs from CloudWatch for time window
- [ ] Group by trace/session ID into discrete executions
- [ ] Generate full artifact set per execution:
  - index.html (summary report)
  - trace-viewer.html (sequence diagram)
  - timeline.html (temporal view)
  - spans.jsonl (raw data)
- [ ] Generate gallery page listing all executions
- [ ] Click any row → opens that execution's report

### Filtering + Search:
- [ ] `--filter errors` — only failed executions
- [ ] `--filter slow` — latency > threshold
- [ ] `--search "keyword"` — text search in payloads
- [ ] `--limit N` — cap number of executions

### Offline Mode:
- [ ] `--logs-file <path>` — view from local JSONL file
- [ ] Enables Tier-2 development/testing

---

## Development Principles (Tier-2)

1. **Offline-only execution**: We test against fixtures/mocks, never real AWS
2. **Live-ready code**: AWS adapters are implemented but stubbed; Tier-3 wires them
3. **Static output**: All artifacts must work via `file://` with no server
4. **No secrets**: Repo stays public-safe
5. **Tier-3 friendly**: Code is simple enough for a weaker model to wire/extend
