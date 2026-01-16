# ITK: Add minimal span logging guidance

Goal: update `docs/03-log-span-contract.md` with copy/paste log snippets.

Constraints:
- Logs may only be WARN+ in QA.
- Keep logging changes minimal.
- Focus on boundary wrappers: invoke_agent_with_retries, invoke_model wrapper, action group handler.
