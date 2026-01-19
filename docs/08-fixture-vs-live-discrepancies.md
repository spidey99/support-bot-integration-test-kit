# Fixture vs Live Mode Discrepancies

This document describes the differences observed between running ITK in `dev-fixtures` mode (offline, deterministic) versus `live` mode (real AWS calls).

---

## Summary Table

| Aspect | Fixture Mode | Live Mode |
|--------|--------------|-----------|
| Data source | JSONL files in `fixtures/logs/` | CloudWatch + Bedrock traces |
| Span count | Predefined in fixture | Varies by agent behavior |
| Timestamps | Static, evenly spaced | Real wall-clock times |
| `parent_span_id` | Explicit hierarchy | Often null (no parent known) |
| `attempt` field | Usually set | Often null |
| Request/response | Compact JSON | Verbose Bedrock format |
| Latency | Artificial (2s total) | Real (4-8s per iteration) |
| CloudWatch logs | 0 (uses fixtures) | 0 or more (depends on Lambda invocation) |

---

## Detailed Discrepancies

### 1. Span ID Format

**Fixture mode:**
```json
{"span_id": "span-001", "span_id": "span-002", ...}
```
Sequential, human-readable IDs like `span-001`, `span-002`.

**Live mode:**
```json
{"span_id": "bedrock-model-001", "span_id": "bedrock-action-002", ...}
```
IDs include component hints like `bedrock-model-XXX` or `bedrock-action-XXX`.

**Impact:** None. Both are valid span IDs. The `no_duplicate_span_ids` invariant works with either format.

---

### 2. Parent-Child Relationships

**Fixture mode:**
```json
{"span_id": "span-003", "parent_span_id": "span-002", ...}
```
Explicit parent-child hierarchy defined in fixtures.

**Live mode:**
```json
{"span_id": "bedrock-action-002", "parent_span_id": null, ...}
```
Bedrock traces do not include parent span IDs. All spans appear as root-level.

**Impact:** 
- Sequence diagrams show flat structure in live mode
- Correlation relies on `bedrock_session_id` instead of `parent_span_id`
- Future work: Infer hierarchy from timing + session ID

---

### 3. Timestamp Precision

**Fixture mode:**
```json
{"ts_start": "2026-01-15T12:00:00.000Z", "ts_end": "2026-01-15T12:00:02.000Z"}
```
Clean timestamps with 1-second or 500ms granularity.

**Live mode:**
```json
{"ts_start": "2026-01-18T21:18:18.887631+00:00", "ts_end": "2026-01-18T21:18:18.887631+00:00"}
```
Microsecond precision. Note: `ts_start` equals `ts_end` for Bedrock trace spans (timing not exposed).

**Impact:**
- Timeline diagrams are less informative in live mode (0-duration spans)
- Duration calculations may be 0ms for Bedrock spans
- Future work: Extract timing from `traceStartTime` in Bedrock traces

---

### 4. Request/Response Payload Size

**Fixture mode:**
```json
{"request": {"inputText": "hello", "enableTrace": true}}
```
Compact, minimal payloads designed for testing.

**Live mode:**
```json
{"request": {"text": "{\"system\":\" You are an assistant that uses Claude Haiku...500+ chars...", ...}}
```
Full system prompts, message history, and tool results embedded in payloads.

**Impact:**
- Live `spans.jsonl` files are 3-5x larger
- Trace viewer details panel shows full payloads (scrollable)
- Consider payload truncation option for reports

---

### 5. Component Naming

**Fixture mode:**
```json
{"component": "entrypoint:sqs_event", "component": "agent:gatekeeper", "component": "lambda:actionGroupFoo"}
```
Descriptive component names matching the fixture design.

**Live mode:**
```json
{"component": "agent:bedrock-model", "component": "lambda:invoke-haiku"}
```
Components inferred from Bedrock trace types and Lambda function names.

**Impact:**
- Sequence diagrams show different lifeline labels
- Component detection is accurate but less descriptive
- Consider mapping Lambda ARNs to friendly names via config

---

### 6. CloudWatch Log Availability

**Fixture mode:**
- Reads from `fixtures/logs/sample_run_001.jsonl`
- Guaranteed consistent data

**Live mode:**
- Fetches from `/aws/lambda/...` log groups
- May return 0 events if:
  - Lambda was not invoked (agent answered directly)
  - CloudWatch propagation delay exceeded wait time
  - Log retention expired
  - Log group name mismatch

**Observation:** In test runs, agent responded without invoking Lambda action group, resulting in 0 CloudWatch log events but 7 Bedrock traces (3 spans).

**Impact:**
- Span count depends on agent's decision path
- `has_spans` invariant may pass on Bedrock traces alone
- Recommend: Configure log groups only for expected paths

---

### 7. Bedrock Session ID Correlation

**Fixture mode:**
```json
{"bedrock_session_id": "sess-111"}
```
Optional, may be null.

**Live mode:**
```json
{"bedrock_session_id": "017467e2-025e-4121-ad29-7d4e46771da4"}
```
Always populated for Bedrock agent invocations. UUID format.

**Impact:**
- Reliable correlation ID for grouping spans from same conversation
- Derive command uses session ID to group cases
- Works well for multi-turn conversations

---

### 8. Rate and Throttling

**Fixture mode:**
- Instant execution, no throttling possible
- Rate controller has no effect

**Live mode:**
- Real API calls subject to AWS quotas
- Soak test at 1.0 req/s completed 20 iterations with 0 throttle events
- Rate controller successfully maintained stable rate

**Observation:** Bedrock Agents API has generous quotas. Throttling detection works but was not triggered in testing.

---

## Recommendations for Test Authors

### Checklist: Writing Cases That Work in Both Modes

- [ ] Use `bedrock_session_id` for correlation, not `parent_span_id`
- [ ] Set `has_spans` invariant (works with 0+ CloudWatch logs)
- [ ] Avoid `expected_span_count` unless fixture-only test
- [ ] Use `has_entrypoint` instead of checking specific span IDs
- [ ] Accept that live latency varies significantly
- [ ] Use env var placeholders (`${ITK_...}`) for live mode IDs

### Checklist: Interpreting Live Results

- [ ] 0 CloudWatch logs is normal if agent doesn't invoke action groups
- [ ] Check Bedrock trace count matches expected orchestration pattern
- [ ] Verify `bedrock_session_id` is consistent across spans
- [ ] Timeline may show 0-duration bars (Bedrock timing limitation)
- [ ] Large payloads are expected (system prompts included)

---

## Known Limitations

1. **Bedrock traces lack timing:** Cannot calculate model inference latency from traces
2. **No parent span IDs:** Hierarchy must be inferred or ignored
3. **Large payloads:** System prompts inflate spans.jsonl significantly
4. **Log propagation delay:** 3-second wait may be insufficient under load
5. **Agent decision path varies:** May or may not invoke action groups

---

## Version History

| Date | Change |
|------|--------|
| 2026-01-18 | Initial documentation based on ITK-0031 live testing |
