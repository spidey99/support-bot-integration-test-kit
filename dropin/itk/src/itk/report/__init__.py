"""Suite reporting module for ITK.

This module provides data structures and utilities for running test suites
and generating consolidated reports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Sequence


class CaseStatus(Enum):
    """Status of a test case execution."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class CaseResult:
    """Result of a single test case execution.

    Attributes:
        case_id: Unique identifier for the case.
        case_name: Human-readable name.
        status: Execution status.
        duration_ms: Total execution time in milliseconds.
        span_count: Number of spans in the trace.
        error_count: Number of spans with errors.
        retry_count: Number of spans with retry attempts > 1.
        started_at: ISO timestamp when execution started.
        finished_at: ISO timestamp when execution finished.
        error_message: Error message if status is ERROR.
        invariant_failures: List of failed invariant names.
        artifacts_dir: Path to artifacts directory for this case.
        trace_viewer_path: Relative path to trace-viewer.html.
        timeline_path: Relative path to timeline.html.
        thumbnail_svg: Inline SVG for mini diagram.
        timeline_svg: Inline SVG for mini timeline.
    """

    case_id: str
    case_name: str
    status: CaseStatus
    duration_ms: float
    span_count: int = 0
    error_count: int = 0
    retry_count: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error_message: Optional[str] = None
    invariant_failures: list[str] = field(default_factory=list)
    artifacts_dir: Optional[str] = None
    trace_viewer_path: Optional[str] = None
    timeline_path: Optional[str] = None
    thumbnail_svg: Optional[str] = None
    timeline_svg: Optional[str] = None

    @property
    def passed(self) -> bool:
        """Check if case passed."""
        return self.status == CaseStatus.PASSED

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "case_id": self.case_id,
            "case_name": self.case_name,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "span_count": self.span_count,
            "error_count": self.error_count,
            "retry_count": self.retry_count,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error_message": self.error_message,
            "invariant_failures": self.invariant_failures,
            "artifacts_dir": self.artifacts_dir,
            "trace_viewer_path": self.trace_viewer_path,
            "timeline_path": self.timeline_path,
        }


@dataclass
class SuiteResult:
    """Result of a test suite execution.

    Attributes:
        suite_id: Unique identifier for the suite run.
        suite_name: Human-readable suite name.
        started_at: ISO timestamp when suite started.
        finished_at: ISO timestamp when suite finished.
        duration_ms: Total suite execution time.
        cases: List of case results.
        mode: Execution mode (dev-fixtures or live).
        environment: Target environment name.
    """

    suite_id: str
    suite_name: str
    started_at: str
    finished_at: Optional[str] = None
    duration_ms: float = 0.0
    cases: list[CaseResult] = field(default_factory=list)
    mode: str = "dev-fixtures"
    environment: Optional[str] = None

    @property
    def total_cases(self) -> int:
        """Total number of cases."""
        return len(self.cases)

    @property
    def passed_count(self) -> int:
        """Number of passed cases."""
        return sum(1 for c in self.cases if c.status == CaseStatus.PASSED)

    @property
    def failed_count(self) -> int:
        """Number of failed cases."""
        return sum(1 for c in self.cases if c.status == CaseStatus.FAILED)

    @property
    def error_count(self) -> int:
        """Number of cases with errors."""
        return sum(1 for c in self.cases if c.status == CaseStatus.ERROR)

    @property
    def skipped_count(self) -> int:
        """Number of skipped cases."""
        return sum(1 for c in self.cases if c.status == CaseStatus.SKIPPED)

    @property
    def all_passed(self) -> bool:
        """Check if all cases passed."""
        return all(c.passed for c in self.cases) and len(self.cases) > 0

    @property
    def pass_rate(self) -> float:
        """Calculate pass rate as percentage."""
        if not self.cases:
            return 0.0
        return (self.passed_count / len(self.cases)) * 100

    @property
    def total_spans(self) -> int:
        """Total spans across all cases."""
        return sum(c.span_count for c in self.cases)

    @property
    def total_errors(self) -> int:
        """Total error spans across all cases."""
        return sum(c.error_count for c in self.cases)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "suite_id": self.suite_id,
            "suite_name": self.suite_name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "mode": self.mode,
            "environment": self.environment,
            "summary": {
                "total": self.total_cases,
                "passed": self.passed_count,
                "failed": self.failed_count,
                "error": self.error_count,
                "skipped": self.skipped_count,
                "pass_rate": self.pass_rate,
                "total_spans": self.total_spans,
                "total_errors": self.total_errors,
            },
            "cases": [c.to_dict() for c in self.cases],
        }


def generate_suite_id() -> str:
    """Generate a unique suite ID based on timestamp."""
    return datetime.now(timezone.utc).strftime("suite-%Y%m%d-%H%M%S")
