"""ITK Error Code Registry.

Provides structured error codes with helpful messages and next steps.
Each error has:
- Code: ITK-EXXX format
- Message: Human-readable description
- Next step: Actionable command or instruction
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import sys


class ErrorCode(Enum):
    """ITK error codes."""
    
    # Configuration errors (E001-E099)
    E001 = "E001"  # Missing .env file
    E002 = "E002"  # Invalid .env format
    E003 = "E003"  # AWS credentials not configured
    E004 = "E004"  # Log group not found
    E005 = "E005"  # Case file not found
    E006 = "E006"  # Schema validation failed
    E007 = "E007"  # Missing required environment variable
    E008 = "E008"  # Invalid mode specified
    E009 = "E009"  # Resolver command failed
    
    # Runtime errors (E100-E199)
    E100 = "E100"  # CloudWatch query failed
    E101 = "E101"  # SQS send failed
    E102 = "E102"  # Lambda invocation failed
    E103 = "E103"  # Bedrock agent invocation failed
    E104 = "E104"  # Throttling detected
    E105 = "E105"  # Timeout exceeded
    E106 = "E106"  # No spans found
    
    # Validation errors (E200-E299)
    E200 = "E200"  # Invariant check failed
    E201 = "E201"  # Case YAML invalid
    E202 = "E202"  # Fixture JSONL invalid
    E203 = "E203"  # Span data invalid
    
    # File/IO errors (E300-E399)
    E300 = "E300"  # Output directory not writable
    E301 = "E301"  # Fixture file not found
    E302 = "E302"  # Cannot read file
    E303 = "E303"  # Cannot write file


@dataclass
class ITKError:
    """Structured ITK error with code, message, and next step."""
    
    code: ErrorCode
    message: str
    next_step: str
    details: Optional[str] = None
    
    def __str__(self) -> str:
        lines = [
            f"ITK-{self.code.value}: {self.message}",
        ]
        if self.details:
            lines.append(f"  Details: {self.details}")
        lines.append(f"  Next step: {self.next_step}")
        return "\n".join(lines)
    
    def print(self, file=None) -> None:
        """Print the error to stderr (or specified file)."""
        print(str(self), file=file or sys.stderr)


# Pre-defined error templates
ERROR_TEMPLATES: dict[ErrorCode, tuple[str, str]] = {
    # (message_template, next_step)
    ErrorCode.E001: (
        "Missing .env file",
        "Run 'itk discover' or copy .env.example to .env"
    ),
    ErrorCode.E002: (
        "Invalid .env file format",
        "Check .env syntax - each line should be KEY=value"
    ),
    ErrorCode.E003: (
        "AWS credentials not configured or expired",
        "Run 'aws configure' or refresh MFA session"
    ),
    ErrorCode.E004: (
        "CloudWatch log group not found: {details}",
        "Check ITK_LOG_GROUPS in .env or run 'itk discover'"
    ),
    ErrorCode.E005: (
        "Case file not found: {details}",
        "Check the --case path or list cases with 'ls cases/'"
    ),
    ErrorCode.E006: (
        "Schema validation failed",
        "Run 'itk validate --case <file>' to see details"
    ),
    ErrorCode.E007: (
        "Missing required environment variable: {details}",
        "Run 'itk validate-env' to check configuration"
    ),
    ErrorCode.E008: (
        "Invalid mode: {details}",
        "Use --mode dev-fixtures or --mode live"
    ),
    ErrorCode.E009: (
        "Resolver command failed: {details}",
        "Check ITK_RESOLVER_CMD in .env"
    ),
    ErrorCode.E100: (
        "CloudWatch query failed: {details}",
        "Check AWS credentials and log group permissions"
    ),
    ErrorCode.E101: (
        "SQS send failed: {details}",
        "Check ITK_SQS_QUEUE_URL and queue permissions"
    ),
    ErrorCode.E102: (
        "Lambda invocation failed: {details}",
        "Check ITK_LAMBDA_FUNCTION_NAME and permissions"
    ),
    ErrorCode.E103: (
        "Bedrock agent invocation failed: {details}",
        "Check ITK_BEDROCK_AGENT_ID and alias configuration"
    ),
    ErrorCode.E104: (
        "Throttling detected",
        "Reduce request rate or wait before retrying"
    ),
    ErrorCode.E105: (
        "Operation timed out: {details}",
        "Increase timeout or check service health"
    ),
    ErrorCode.E106: (
        "No spans found in logs",
        "Check log group configuration or add structured logging"
    ),
    ErrorCode.E200: (
        "Invariant check failed: {details}",
        "Review the invariant definition in case YAML"
    ),
    ErrorCode.E201: (
        "Case YAML is invalid: {details}",
        "Run 'itk validate --case <file>' to see schema errors"
    ),
    ErrorCode.E202: (
        "Fixture JSONL is invalid: {details}",
        "Run 'itk validate --fixture <file>' to see errors"
    ),
    ErrorCode.E203: (
        "Span data is invalid: {details}",
        "Check span structure against itk.span.schema.json"
    ),
    ErrorCode.E300: (
        "Output directory not writable: {details}",
        "Check permissions or use a different --out path"
    ),
    ErrorCode.E301: (
        "Fixture file not found: {details}",
        "Check fixture path or use 'itk generate-fixture'"
    ),
    ErrorCode.E302: (
        "Cannot read file: {details}",
        "Check file permissions and path"
    ),
    ErrorCode.E303: (
        "Cannot write file: {details}",
        "Check directory permissions"
    ),
}


def make_error(code: ErrorCode, details: Optional[str] = None) -> ITKError:
    """Create an ITKError from a code with optional details.
    
    Args:
        code: The error code
        details: Optional details to include in the message
        
    Returns:
        ITKError instance ready to print
    """
    template = ERROR_TEMPLATES.get(code, ("Unknown error", "Run 'itk doctor'"))
    message_template, next_step = template
    
    # Format message with details if present
    if details and "{details}" in message_template:
        message = message_template.format(details=details)
    elif details:
        message = f"{message_template}: {details}"
    else:
        message = message_template.replace(": {details}", "")
    
    return ITKError(
        code=code,
        message=message,
        next_step=next_step,
        details=details if "{details}" not in message_template else None,
    )


def error_exit(code: ErrorCode, details: Optional[str] = None, exit_code: int = 1) -> None:
    """Print an error and exit with the specified code.
    
    Args:
        code: The error code
        details: Optional details
        exit_code: Exit code (default: 1)
    """
    err = make_error(code, details)
    err.print()
    sys.exit(exit_code)


# Verbose mode flag (set by CLI)
_verbose_mode: bool = False


def set_verbose(verbose: bool) -> None:
    """Set verbose mode for error output."""
    global _verbose_mode
    _verbose_mode = verbose


def is_verbose() -> bool:
    """Check if verbose mode is enabled."""
    return _verbose_mode


def handle_exception(exc: Exception, code: ErrorCode, details: Optional[str] = None) -> None:
    """Handle an exception with proper error formatting.
    
    In verbose mode, prints the full traceback.
    Otherwise, prints a formatted error message.
    
    Args:
        exc: The exception that occurred
        code: The error code to use
        details: Optional additional details
    """
    import traceback
    
    err = make_error(code, details or str(exc))
    err.print()
    
    if _verbose_mode:
        print("\n--- Full Traceback ---", file=sys.stderr)
        traceback.print_exc()
