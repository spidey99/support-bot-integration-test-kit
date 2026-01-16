"""Tests for redaction module."""
from __future__ import annotations

import pytest

from itk.redaction.redactor import (
    RedactionConfig,
    RedactionPattern,
    Redactor,
    DEFAULT_PATTERNS,
)


class TestRedactionPatterns:
    """Tests for individual redaction patterns."""

    def test_email_redaction(self) -> None:
        redactor = Redactor()
        text = "Contact me at john.doe@example.com for details"
        result = redactor.redact_string(text)
        assert "john.doe@example.com" not in result
        assert "[EMAIL_REDACTED]" in result

    def test_phone_redaction(self) -> None:
        redactor = Redactor()
        text = "Call me at 555-123-4567 or (555) 987-6543"
        result = redactor.redact_string(text)
        assert "555-123-4567" not in result
        assert "(555) 987-6543" not in result
        assert "[PHONE_REDACTED]" in result

    def test_ssn_redaction(self) -> None:
        redactor = Redactor()
        text = "SSN: 123-45-6789"
        result = redactor.redact_string(text)
        assert "123-45-6789" not in result
        assert "[SSN_REDACTED]" in result

    def test_credit_card_redaction(self) -> None:
        redactor = Redactor()
        text = "Card: 4111-1111-1111-1111"
        result = redactor.redact_string(text)
        assert "4111-1111-1111-1111" not in result
        assert "[CC_REDACTED]" in result

    def test_aws_account_id_redaction(self) -> None:
        redactor = Redactor()
        text = "AWS Account: 123456789012"
        result = redactor.redact_string(text)
        assert "123456789012" not in result
        assert "[AWS_ACCOUNT_REDACTED]" in result

    def test_api_key_redaction(self) -> None:
        redactor = Redactor()
        text = "Key: sk-abc123def456ghi789jkl012mno345pqr678"
        result = redactor.redact_string(text)
        assert "sk-abc123def456ghi789jkl012mno345pqr678" not in result
        assert "[API_KEY_REDACTED]" in result

    def test_aws_access_key_redaction(self) -> None:
        redactor = Redactor()
        text = "Access Key: AKIAIOSFODNN7EXAMPLE"
        result = redactor.redact_string(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "[AWS_KEY_REDACTED]" in result

    def test_ip_address_not_redacted_by_default(self) -> None:
        redactor = Redactor()
        text = "Server IP: 192.168.1.100"
        result = redactor.redact_string(text)
        # IP redaction is disabled by default
        assert "192.168.1.100" in result

    def test_ip_address_redacted_when_enabled(self) -> None:
        config = RedactionConfig()
        config.enable_pattern("ipv4")
        redactor = Redactor(config)
        text = "Server IP: 192.168.1.100"
        result = redactor.redact_string(text)
        assert "192.168.1.100" not in result
        assert "[IP_REDACTED]" in result


class TestSensitiveKeys:
    """Tests for key-based redaction."""

    def test_password_key_redacted(self) -> None:
        redactor = Redactor()
        data = {"username": "john", "password": "secret123"}
        result = redactor.redact_dict(data)
        assert result["username"] == "john"
        assert result["password"] == "[REDACTED]"

    def test_token_key_redacted(self) -> None:
        redactor = Redactor()
        data = {"token": "abc123xyz"}
        result = redactor.redact_dict(data)
        assert result["token"] == "[REDACTED]"

    def test_api_key_key_redacted(self) -> None:
        redactor = Redactor()
        data = {"api_key": "sk_live_xxx", "api-key": "pk_test_yyy"}
        result = redactor.redact_dict(data)
        assert result["api_key"] == "[REDACTED]"
        assert result["api-key"] == "[REDACTED]"

    def test_authorization_key_redacted(self) -> None:
        redactor = Redactor()
        data = {"authorization": "Bearer xyz123"}
        result = redactor.redact_dict(data)
        assert result["authorization"] == "[REDACTED]"


class TestAllowedKeys:
    """Tests for allowlisted keys."""

    def test_span_id_not_redacted(self) -> None:
        redactor = Redactor()
        data = {"span_id": "123-456-789"}
        result = redactor.redact_dict(data)
        assert result["span_id"] == "123-456-789"

    def test_timestamp_not_redacted(self) -> None:
        redactor = Redactor()
        data = {"timestamp": "2026-01-15T12:00:00Z"}
        result = redactor.redact_dict(data)
        assert result["timestamp"] == "2026-01-15T12:00:00Z"

    def test_correlation_id_not_redacted(self) -> None:
        redactor = Redactor()
        data = {"correlation_id": "abc-123-xyz"}
        result = redactor.redact_dict(data)
        assert result["correlation_id"] == "abc-123-xyz"


class TestNestedRedaction:
    """Tests for nested data structures."""

    def test_nested_dict_redaction(self) -> None:
        redactor = Redactor()
        data = {
            "user": {
                "email": "test@example.com",
                "password": "secret",
            }
        }
        result = redactor.redact_dict(data)
        assert "[EMAIL_REDACTED]" in result["user"]["email"]
        assert result["user"]["password"] == "[REDACTED]"

    def test_list_redaction(self) -> None:
        redactor = Redactor()
        data = {"emails": ["a@test.com", "b@test.com"]}
        result = redactor.redact_dict(data)
        for email in result["emails"]:
            assert "[EMAIL_REDACTED]" in email

    def test_deeply_nested_redaction(self) -> None:
        redactor = Redactor()
        data = {
            "request": {
                "body": {
                    "user": {
                        "contact": {
                            "phone": "555-123-4567"
                        }
                    }
                }
            }
        }
        result = redactor.redact_dict(data)
        assert "[PHONE_REDACTED]" in result["request"]["body"]["user"]["contact"]["phone"]


class TestRedactionConfig:
    """Tests for configuration options."""

    def test_disabled_redaction(self) -> None:
        config = RedactionConfig(enabled=False)
        redactor = Redactor(config)
        data = {"email": "test@example.com", "password": "secret"}
        result = redactor.redact_dict(data)
        assert result["email"] == "test@example.com"
        assert result["password"] == "secret"

    def test_custom_sensitive_keys(self) -> None:
        config = RedactionConfig(sensitive_keys={"my_secret_field"})
        redactor = Redactor(config)
        data = {"my_secret_field": "value", "password": "other"}
        result = redactor.redact_dict(data)
        assert result["my_secret_field"] == "[REDACTED]"
        # password is no longer in sensitive_keys
        assert result["password"] == "other"

    def test_enable_disable_patterns(self) -> None:
        # Create a fresh config for this test
        config1 = RedactionConfig()

        # Initially email is enabled
        redactor1 = Redactor(config1)
        assert "[EMAIL_REDACTED]" in redactor1.redact_string("test@example.com")

        # Create another config and disable email pattern
        config2 = RedactionConfig()
        config2.disable_pattern("email")
        redactor2 = Redactor(config2)
        assert redactor2.redact_string("test@example.com") == "test@example.com"


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_dict(self) -> None:
        redactor = Redactor()
        result = redactor.redact_dict({})
        assert result == {}

    def test_none_values(self) -> None:
        redactor = Redactor()
        data = {"field": None}
        result = redactor.redact_dict(data)
        assert result["field"] is None

    def test_numeric_values(self) -> None:
        redactor = Redactor()
        data = {"count": 42, "price": 19.99}
        result = redactor.redact_dict(data)
        assert result["count"] == 42
        assert result["price"] == 19.99

    def test_boolean_values(self) -> None:
        redactor = Redactor()
        data = {"enabled": True, "disabled": False}
        result = redactor.redact_dict(data)
        assert result["enabled"] is True
        assert result["disabled"] is False

    def test_mixed_content_string(self) -> None:
        redactor = Redactor()
        text = "User john@test.com called 555-123-4567 with card 4111-1111-1111-1111"
        result = redactor.redact_string(text)
        assert "john@test.com" not in result
        assert "555-123-4567" not in result
        assert "4111-1111-1111-1111" not in result
