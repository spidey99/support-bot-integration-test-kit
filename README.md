# Support Bot Integration Test Kit (Wrapper Repo)

This public repo is a **safe, generic wrapper** you can work on at home.

It contains a **drop-in kit** you will later copy into a private/work codebase that has:
- AWS access
- deployed QA resources
- real CloudWatch logs
- Bedrock Agent Runtime + direct model invocations

## Three-tier workflow (important)

### Tier 1 (this chat)
Defines architecture, artifacts, schemas, and the drop-in structure.

### Tier 2 (home machine / Claude Opus 4.5)
Implements as much as possible **offline**:
- schemas
- CLI
- log parsing
- correlation/stitching logic
- sequence diagram rendering
- fixture-driven tests

Tier 2 has **no access** to work code or AWS.

### Tier 3 (work environment / free-tier model)
Uses the **drop-in kit** inside the work repo to:
- pull CloudWatch logs with work creds
- call deployed Lambdas/Agents
- generate artifacts (diagrams + payloads + reports)

## What’s inside

- `/planning/*` — planning artifacts for **Tier 2** work (wrapper repo)
- `/docs/*` — design docs, “explain like I’m 5” level
- `/.github/*` — Copilot instructions + prompt files for Tier 2
- `/dropin/itk/*` — the **drop-in kit** to copy into the work repo
  - `/dropin/itk/planning/*` — separate planning artifacts for **Tier 3**
  - `/dropin/itk/_merge_to_repo_root/.github/*` — Copilot guidance to merge into work repo root

## Quickstart (Tier 2 / offline)

1) Open this repo in VS Code.
2) Create a virtualenv.
3) Install the drop-in kit in editable mode:

```bash
cd dropin/itk
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

4) Run the CLI in offline fixture mode:

```bash
itk render-fixture --fixture fixtures/logs/sample_run_001.jsonl --out artifacts/sample_run_001
```

This produces a Mermaid sequence diagram and payload artifacts without needing AWS.

## Next step

Use the planning artifacts in `/planning` to drive Tier 2 implementation work.
Then copy `dropin/itk/` into your work repo and follow `dropin/itk/README_WORK_REPO.md`.
