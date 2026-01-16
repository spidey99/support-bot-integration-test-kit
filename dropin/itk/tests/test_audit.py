"""Tests for audit gap detection."""
from __future__ import annotations

from itk.audit.gap_detector import LoggingGap, detect_gaps
from itk.cases.loader import CaseConfig, EntrypointConfig, InvariantSpec
from itk.trace.span_model import Span
from itk.trace.trace_model import Trace


def _make_case() -> CaseConfig:
    """Create a minimal case config for testing."""
    return CaseConfig(
        id="test-case",
        name="Test Case",
        entrypoint=EntrypointConfig(
            type="sqs_event",
            target={"mode": "invoke_lambda"},
            payload={},
        ),
        invariants=[],
        notes={},
    )


class TestGapDetector:
    """Tests for logging gap detection."""

    def test_detect_missing_timestamp(self) -> None:
        """Detect missing ts_start as a warning."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="entrypoint:sqs",
                    operation="Op",
                    ts_start=None,  # Missing
                    request={"data": "test"},
                    lambda_request_id="req-123",
                )
            ]
        )

        gaps = detect_gaps(trace, _make_case())

        ts_gaps = [g for g in gaps if "ts_start" in g.issue]
        assert len(ts_gaps) == 1
        assert ts_gaps[0].severity == "warning"

    def test_detect_missing_request_critical(self) -> None:
        """Detect missing request payload as critical for boundary components."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="entrypoint:sqs",
                    operation="Op",
                    ts_start="2026-01-15T12:00:00Z",
                    request=None,  # Missing for critical boundary
                    lambda_request_id="req-123",
                )
            ]
        )

        gaps = detect_gaps(trace, _make_case())

        req_gaps = [g for g in gaps if "request payload" in g.issue]
        assert len(req_gaps) == 1
        assert req_gaps[0].severity == "critical"

    def test_detect_missing_correlation_ids(self) -> None:
        """Detect spans with no correlation IDs."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="lambda:handler",
                    operation="Op",
                    # No correlation IDs
                )
            ]
        )

        gaps = detect_gaps(trace, _make_case())

        id_gaps = [g for g in gaps if "correlation ID" in g.issue]
        assert len(id_gaps) >= 1

    def test_detect_orphaned_span(self) -> None:
        """Detect spans with parent_span_id that doesn't exist."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id="nonexistent",
                    component="lambda:handler",
                    operation="Op",
                    lambda_request_id="req-123",
                )
            ]
        )

        gaps = detect_gaps(trace, _make_case())

        orphan_gaps = [g for g in gaps if "Orphaned" in g.issue]
        assert len(orphan_gaps) == 1
        assert orphan_gaps[0].severity == "info"

    def test_detect_missing_entrypoint(self) -> None:
        """Detect trace with no entrypoint component."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="lambda:handler",  # Not an entrypoint
                    operation="Op",
                    lambda_request_id="req-123",
                )
            ]
        )

        gaps = detect_gaps(trace, _make_case())

        entry_gaps = [g for g in gaps if "entrypoint" in g.issue.lower()]
        assert len(entry_gaps) >= 1

    def test_no_gaps_for_complete_span(self) -> None:
        """No gaps detected for a complete span."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="entrypoint:sqs",
                    operation="Op",
                    ts_start="2026-01-15T12:00:00Z",
                    request={"data": "test"},
                    response={"result": "ok"},
                    lambda_request_id="req-123",
                )
            ]
        )

        gaps = detect_gaps(trace, _make_case())

        # Should only have info about missing response/error for non-critical
        # or structural checks, not critical/warning for the span itself
        critical_gaps = [g for g in gaps if g.severity == "critical" and g.span_id == "s1"]
        assert len(critical_gaps) == 0

    def test_gaps_sorted_by_severity(self) -> None:
        """Gaps are returned sorted by severity (critical first)."""
        trace = Trace(
            spans=[
                Span(
                    span_id="s1",
                    parent_span_id=None,
                    component="entrypoint:sqs",
                    operation="Op",
                    request=None,  # Critical
                ),
                Span(
                    span_id="s2",
                    parent_span_id="nonexistent",  # Info (orphan)
                    component="lambda:handler",
                    operation="Op2",
                    lambda_request_id="req-123",
                ),
            ]
        )

        gaps = detect_gaps(trace, _make_case())

        # First gap should be critical
        if gaps:
            severities = [g.severity for g in gaps]
            # All critical should come before warning, which comes before info
            critical_indices = [i for i, s in enumerate(severities) if s == "critical"]
            warning_indices = [i for i, s in enumerate(severities) if s == "warning"]
            info_indices = [i for i, s in enumerate(severities) if s == "info"]

            if critical_indices and warning_indices:
                assert max(critical_indices) < min(warning_indices)
            if warning_indices and info_indices:
                assert max(warning_indices) < min(info_indices)
