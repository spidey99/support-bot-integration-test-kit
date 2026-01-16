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

## Development Principles (Tier-2)

1. **Offline-only execution**: We test against fixtures/mocks, never real AWS
2. **Live-ready code**: AWS adapters are implemented but stubbed; Tier-3 wires them
3. **Static output**: All artifacts must work via `file://` with no server
4. **No secrets**: Repo stays public-safe
5. **Tier-3 friendly**: Code is simple enough for a weaker model to wire/extend
