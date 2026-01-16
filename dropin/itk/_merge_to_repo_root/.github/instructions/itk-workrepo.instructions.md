---
applyTo: "tools/itk/**"
---

Work repo rules:
- Assume AWS creds are available.
- Never print secrets.
- Prefer CloudWatch Logs Insights for cross-log-group queries.
- If logger is WARN+, ensure essential span logs are WARN.
