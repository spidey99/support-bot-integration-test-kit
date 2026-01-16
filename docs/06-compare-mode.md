# Compare mode

Compare two test runs to detect behavioral changes without requiring identical model outputs.

## What gets compared

| Aspect | Description |
|--------|-------------|
| Path signature | Ordered sequence of (component, operation) pairs |
| Retry counts | Number of retries per path |
| Error presence | Whether paths have errors |
| Latency | Average time per path (when timestamps available) |

## CLI usage

```bash
# Compare two run artifacts
itk compare --a artifacts/baseline --b artifacts/current --out artifacts/comparison

# Example output:
# Baseline: artifacts/baseline
# Current: artifacts/current  
# New paths: 0
# Missing paths: 0
# Regressions: NO
# Comparison artifacts: artifacts/comparison
```

## Output files

| File | Purpose |
|------|---------|
| `comparison.md` | Human-readable report with tables and verdicts |
| `comparison.json` | Machine-readable delta data for CI integration |

## What constitutes a regression

The compare command returns exit code 1 (failure) if:

- [ ] Any path present in baseline is missing in current
- [ ] Any path has increased error rate

These are considered regressions that should block deployment.

## Example comparison.md output

```markdown
# ITK Comparison Report

## Summary
- **Baseline**: artifacts/run-001
- **Current**: artifacts/run-002
- **Total paths compared**: 3

### ✅ No regressions detected

## ✅ Stable Paths
3 path(s) with no significant changes.
```

## Path signatures explained

A path signature is a canonical representation of execution flow:

```
lambda:entrypoint:Invoke -> agent:supervisor:InvokeAgent -> model:claude:InvokeModel
```

Two traces have the same signature if they follow the same sequence of boundary crossings, regardless of actual payloads or response content.

### Signatures include error state

A trace that succeeds has a different signature than one that fails:

```
lambda:foo:Invoke -> model:claude:InvokeModel           # success path
lambda:foo:Invoke -> model:claude:InvokeModel [ERROR]   # error path
```

This means a switch from success to error shows as:
- 1 missing path (the success path)
- 1 new path (the error path)

## CI integration

Use the exit code to gate deployments:

```yaml
# GitHub Actions example
- name: Compare against baseline
  run: |
    itk compare --a baseline/ --b current/ --out comparison/
    # Exits 1 if regressions detected
```

## Latency change detection

Paths with >10% latency change are highlighted in the report:

```markdown
## ⏱️ Significant Latency Changes (>10%)

| Path | Baseline (ms) | Current (ms) | Delta |
|------|---------------|--------------|-------|
| `lambda:foo:Invoke -> ...` | 100.0 | 150.0 | +50.0% |
```
