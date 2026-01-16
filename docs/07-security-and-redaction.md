# Security and redaction

Artifacts often contain prompts, tool outputs, and user messages that may include sensitive data.

## Default behavior

**Redaction is ON by default.** All artifacts have PII patterns automatically redacted.

To disable (use with caution):
```bash
itk run --mode dev-fixtures --case cases/test.yaml --out artifacts/ --no-redact
```

## Patterns redacted by default

| Pattern | Replacement | Example |
|---------|-------------|---------|
| Email addresses | `[EMAIL_REDACTED]` | `john@example.com` → `[EMAIL_REDACTED]` |
| US phone numbers | `[PHONE_REDACTED]` | `555-123-4567` → `[PHONE_REDACTED]` |
| SSN-like numbers | `[SSN_REDACTED]` | `123-45-6789` → `[SSN_REDACTED]` |
| Credit card numbers | `[CC_REDACTED]` | `4111-1111-1111-1111` → `[CC_REDACTED]` |
| AWS account IDs | `[AWS_ACCOUNT_REDACTED]` | `123456789012` → `[AWS_ACCOUNT_REDACTED]` |
| API keys/tokens | `[API_KEY_REDACTED]` | `sk-abc123...` → `[API_KEY_REDACTED]` |
| AWS access keys | `[AWS_KEY_REDACTED]` | `AKIAIOSFODNN7EXAMPLE` → `[AWS_KEY_REDACTED]` |

## Patterns disabled by default

These patterns have high false-positive rates:

| Pattern | Replacement | How to enable |
|---------|-------------|---------------|
| IPv4 addresses | `[IP_REDACTED]` | `config.enable_pattern("ipv4")` |
| AWS secret keys | `[AWS_SECRET_REDACTED]` | `config.enable_pattern("aws_secret_key")` |

## Sensitive keys (always redacted)

Values for these keys are always replaced with `[REDACTED]`:

- [ ] `password`, `secret`, `token`
- [ ] `api_key`, `apikey`, `api-key`
- [ ] `authorization`, `auth`, `credential`
- [ ] `private_key`, `privatekey`
- [ ] `access_token`, `refresh_token`
- [ ] `ssn`, `social_security`
- [ ] `credit_card`, `card_number`

## Allowed keys (never redacted)

These keys are never redacted, even if they match patterns:

- [ ] `span_id`, `parent_span_id`, `trace_id`
- [ ] `request_id`, `message_id`, `session_id`, `correlation_id`
- [ ] `component`, `operation`
- [ ] `ts_start`, `ts_end`, `timestamp`
- [ ] `attempt`, `error_type`, `status_code`

## Example redacted output

Before redaction:
```json
{
  "user": {
    "email": "john.doe@example.com",
    "phone": "555-123-4567"
  },
  "api_key": "sk-abc123xyz456"
}
```

After redaction:
```json
{
  "user": {
    "email": "[EMAIL_REDACTED]",
    "phone": "[PHONE_REDACTED]"
  },
  "api_key": "[REDACTED]"
}
```

## Custom configuration

For programmatic use, create a custom `RedactionConfig`:

```python
from itk.redaction import RedactionConfig, Redactor

config = RedactionConfig(
    enabled=True,
    sensitive_keys={"my_custom_secret"},
    allowed_keys={"safe_field"},
)
config.enable_pattern("ipv4")  # Enable IP redaction

redactor = Redactor(config)
result = redactor.redact_dict(my_data)
```

## Best practices checklist

- [ ] Never disable redaction for production data
- [ ] Review `comparison.json` before sharing externally
- [ ] Add custom sensitive keys for domain-specific secrets
- [ ] Test with `--no-redact` only on synthetic fixtures
