# Copilot instructions (Tier 2 / wrapper repo)

You are implementing the **Integration Test Kit (ITK)**.

## Tier Context

**You are Tier-2**: You develop OFFLINE against fixtures/mocks.
- You do NOT have access to AWS resources
- You test against `dev-fixtures` mode only
- Your job: build a generic kit that Tier-3 can wire to live resources

**Tier-3 (work repo agent)**: Executes LIVE against real AWS QA.
- Tier-3 NEVER uses mocks or dev-fixtures for real tests
- Only the OUTPUT artifacts are static (viewable via file://)

## Non-negotiables

- Do NOT invent request formats. Use fixtures + schemas.
- Keep everything generic. No work identifiers, no secrets.
- Every CLI command must produce artifacts under the `--out` directory.
- Prefer deterministic tests with fixtures.
- All output must work via `file://` (no server/CDN required).

## Definition of done for a feature

- Code implemented
- At least one fixture example
- Output artifact example
- Docs updated
- Tests pass (`pytest`)

## Where things live

- CLI: `dropin/itk/src/itk/cli.py`
- Mermaid renderer: `dropin/itk/src/itk/diagrams/mermaid_seq.py`
- HTML renderer: `dropin/itk/src/itk/diagrams/html_renderer.py`
- Correlation graph: `dropin/itk/src/itk/correlation/stitch_graph.py`
- Scanner: `dropin/itk/src/itk/scanner/`
- Schemas: `dropin/itk/schemas/`
- Fixtures: `dropin/itk/fixtures/`
- Cases: `dropin/itk/cases/`
- Planning (Tier-2): `planning/`
- Planning (Tier-3): `dropin/itk/planning/`
