# Why this exists

Your project has:
- Wide prompt/guardrail changes with huge blast radius
- Weak tests + noisy intermittent failures
- Multiple non-deterministic layers (LLMs + retries + external calls)

So “unit tests” won’t prove much.

This kit proves behavior by:
1) Replaying **real world requests** (derived from logs)
2) Pulling the **full execution path** from logs/trace
3) Rendering a **sequence diagram** showing every hop + retry + payload

Humans can quickly answer:
- Did the same path execute?
- Did retries explode?
- Did failures move earlier/later?
- Did latency change?
