"""Redaction logic for PII and sensitive data.

Provides pattern-based redaction with allowlists for safe artifact output.
By default, redacts:
- Email addresses
- Phone numbers
- API keys / tokens
- AWS account IDs
- Credit card numbers
- SSN-like patterns
- IP addresses (optional)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Pattern, Union


@dataclass
class RedactionPattern:
    """A pattern to match and redact."""

    name: str
    pattern: Pattern[str]
    replacement: str = "[REDACTED]"
    enabled: bool = True


# Default patterns for common PII
DEFAULT_PATTERNS: list[RedactionPattern] = [
    RedactionPattern(
        name="email",
        pattern=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        replacement="[EMAIL_REDACTED]",
    ),
    RedactionPattern(
        name="phone_us",
        pattern=re.compile(r"\b(?:\+1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b"),
        replacement="[PHONE_REDACTED]",
    ),
    RedactionPattern(
        name="ssn",
        pattern=re.compile(r"\b[0-9]{3}[-.\s]?[0-9]{2}[-.\s]?[0-9]{4}\b"),
        replacement="[SSN_REDACTED]",
    ),
    RedactionPattern(
        name="credit_card",
        pattern=re.compile(r"\b(?:[0-9]{4}[-.\s]?){3}[0-9]{4}\b"),
        replacement="[CC_REDACTED]",
    ),
    RedactionPattern(
        name="aws_account_id",
        pattern=re.compile(r"\b[0-9]{12}\b"),
        replacement="[AWS_ACCOUNT_REDACTED]",
    ),
    RedactionPattern(
        name="api_key",
        # Match common API key patterns: sk-, pk-, api_, key_, token_, etc.
        pattern=re.compile(
            r"\b(?:sk|pk|api|key|token|secret|password|bearer)[-_]?[A-Za-z0-9_-]{16,}\b",
            re.IGNORECASE,
        ),
        replacement="[API_KEY_REDACTED]",
    ),
    RedactionPattern(
        name="aws_access_key",
        pattern=re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        replacement="[AWS_KEY_REDACTED]",
    ),
    RedactionPattern(
        name="aws_secret_key",
        pattern=re.compile(r"\b[A-Za-z0-9/+=]{40}\b"),
        replacement="[AWS_SECRET_REDACTED]",
        enabled=False,  # Disabled by default - too many false positives
    ),
    RedactionPattern(
        name="ipv4",
        pattern=re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"),
        replacement="[IP_REDACTED]",
        enabled=False,  # Disabled by default - often not PII
    ),
]


def _copy_default_patterns() -> list[RedactionPattern]:
    """Create a fresh copy of default patterns."""
    return [
        RedactionPattern(
            name=p.name,
            pattern=p.pattern,
            replacement=p.replacement,
            enabled=p.enabled,
        )
        for p in DEFAULT_PATTERNS
    ]


@dataclass
class RedactionConfig:
    """Configuration for redaction behavior."""

    # Enable/disable redaction entirely
    enabled: bool = True

    # Patterns to apply (default: copy of DEFAULT_PATTERNS)
    patterns: list[RedactionPattern] = field(default_factory=_copy_default_patterns)

    # Keys to always redact (case-insensitive)
    sensitive_keys: set[str] = field(
        default_factory=lambda: {
            "password",
            "secret",
            "token",
            "api_key",
            "apikey",
            "api-key",
            "authorization",
            "auth",
            "credential",
            "private_key",
            "privatekey",
            "access_token",
            "refresh_token",
            "ssn",
            "social_security",
            "credit_card",
            "card_number",
        }
    )

    # Keys to never redact (allowlist - case-insensitive)
    allowed_keys: set[str] = field(
        default_factory=lambda: {
            "span_id",
            "parent_span_id",
            "trace_id",
            "request_id",
            "message_id",
            "session_id",
            "correlation_id",
            "component",
            "operation",
            "ts_start",
            "ts_end",
            "timestamp",
            "attempt",
            "error_type",
            "status_code",
        }
    )

    def enable_pattern(self, name: str) -> None:
        """Enable a pattern by name."""
        for p in self.patterns:
            if p.name == name:
                p.enabled = True
                return

    def disable_pattern(self, name: str) -> None:
        """Disable a pattern by name."""
        for p in self.patterns:
            if p.name == name:
                p.enabled = False
                return


class Redactor:
    """Redactor instance with configuration."""

    def __init__(self, config: Optional[RedactionConfig] = None) -> None:
        self.config = config or RedactionConfig()

    def redact_string(self, value: str) -> str:
        """Apply pattern-based redaction to a string."""
        if not self.config.enabled:
            return value

        result = value
        for pattern in self.config.patterns:
            if pattern.enabled:
                result = pattern.pattern.sub(pattern.replacement, result)
        return result

    def should_redact_key(self, key: str) -> bool:
        """Check if a key should be fully redacted."""
        if not self.config.enabled:
            return False

        key_lower = key.lower()

        # Allowed keys are never redacted
        if key_lower in {k.lower() for k in self.config.allowed_keys}:
            return False

        # Sensitive keys are always redacted
        if key_lower in {k.lower() for k in self.config.sensitive_keys}:
            return True

        return False

    def redact_value(self, value: Any, key: Optional[str] = None) -> Any:
        """Redact a single value, optionally considering its key."""
        if not self.config.enabled:
            return value

        # If key indicates sensitive data, redact entirely
        if key and self.should_redact_key(key):
            return "[REDACTED]"

        # Apply pattern-based redaction to strings
        if isinstance(value, str):
            return self.redact_string(value)

        # Recurse into collections
        if isinstance(value, dict):
            return self.redact_dict(value)

        if isinstance(value, list):
            return [self.redact_value(item) for item in value]

        # Leave other types unchanged
        return value

    def redact_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively redact a dictionary."""
        if not self.config.enabled:
            return data

        result: dict[str, Any] = {}
        for k, v in data.items():
            result[k] = self.redact_value(v, key=k)
        return result


# Default redactor instance
_default_redactor: Optional[Redactor] = None


def default_redactor() -> Redactor:
    """Get or create the default redactor."""
    global _default_redactor
    if _default_redactor is None:
        _default_redactor = Redactor()
    return _default_redactor


def redact_value(value: Any, key: Optional[str] = None) -> Any:
    """Convenience function to redact a value using the default redactor."""
    return default_redactor().redact_value(value, key=key)


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Convenience function to redact a dict using the default redactor."""
    return default_redactor().redact_dict(data)
