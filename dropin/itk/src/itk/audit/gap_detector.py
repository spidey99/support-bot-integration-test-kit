"""Detect logging gaps in trace data."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from itk.cases.loader import CaseConfig
from itk.trace.span_model import Span
from itk.trace.trace_model import Trace


@dataclass(frozen=True)
class LoggingGap:
    """A detected gap in logging coverage."""

    severity: str  # "critical" | "warning" | "info"
    component: str
    span_id: Optional[str]
    issue: str
    recommendation: str


# Components that are critical for sequence diagrams
CRITICAL_BOUNDARY_PREFIXES = (
    "entrypoint:",
    "agent:",
    "lambda:",
    "model:",
)


def _check_span_completeness(span: Span) -> list[LoggingGap]:
    """Check a single span for missing required fields."""
    gaps: list[LoggingGap] = []

    # Missing timestamps
    if span.ts_start is None:
        gaps.append(
            LoggingGap(
                severity="warning",
                component=span.component,
                span_id=span.span_id,
                issue="Missing ts_start timestamp",
                recommendation="Add ISO8601 timestamp at span start",
            )
        )

    # Missing request payload for entry/agent boundaries
    if span.component.startswith(CRITICAL_BOUNDARY_PREFIXES):
        if span.request is None:
            gaps.append(
                LoggingGap(
                    severity="critical",
                    component=span.component,
                    span_id=span.span_id,
                    issue="Missing request payload",
                    recommendation=(
                        f"Log request payload at {span.component} boundary. "
                        "Use WARN level with JSON format."
                    ),
                )
            )

        if span.response is None and span.error is None:
            gaps.append(
                LoggingGap(
                    severity="warning",
                    component=span.component,
                    span_id=span.span_id,
                    issue="Missing response or error payload",
                    recommendation=(
                        f"Log response/error at {span.component} boundary. "
                        "This enables completion detection."
                    ),
                )
            )

    # Missing correlation IDs
    has_any_correlation_id = any(
        [
            span.itk_trace_id,
            span.lambda_request_id,
            span.xray_trace_id,
            span.sqs_message_id,
            span.bedrock_session_id,
        ]
    )
    if not has_any_correlation_id:
        gaps.append(
            LoggingGap(
                severity="warning",
                component=span.component,
                span_id=span.span_id,
                issue="No correlation IDs present",
                recommendation=(
                    "Add at least one correlation ID (lambda_request_id, sqs_message_id, "
                    "bedrock_session_id, xray_trace_id, or itk_trace_id)"
                ),
            )
        )

    return gaps


def _check_trace_structure(trace: Trace) -> list[LoggingGap]:
    """Check the overall trace structure for issues."""
    gaps: list[LoggingGap] = []

    if len(trace.spans) == 0:
        gaps.append(
            LoggingGap(
                severity="critical",
                component="trace",
                span_id=None,
                issue="No spans found in trace",
                recommendation="Ensure log sources contain boundary events",
            )
        )
        return gaps

    # Check for orphaned spans (parent_span_id that doesn't exist)
    span_ids = {s.span_id for s in trace.spans}
    for span in trace.spans:
        if span.parent_span_id and span.parent_span_id not in span_ids:
            gaps.append(
                LoggingGap(
                    severity="info",
                    component=span.component,
                    span_id=span.span_id,
                    issue=f"Orphaned span: parent {span.parent_span_id} not found",
                    recommendation="Ensure parent span is logged or update parent_span_id",
                )
            )

    # Check for missing entrypoint
    has_entrypoint = any(s.component.startswith("entrypoint:") for s in trace.spans)
    if not has_entrypoint:
        gaps.append(
            LoggingGap(
                severity="warning",
                component="trace",
                span_id=None,
                issue="No entrypoint span found",
                recommendation=(
                    "Add a span with component='entrypoint:*' to mark the request entry"
                ),
            )
        )

    return gaps


def _check_expected_components(trace: Trace, case: CaseConfig) -> list[LoggingGap]:
    """Check if expected components from case config are present."""
    gaps: list[LoggingGap] = []

    # Extract expected entrypoint type
    entrypoint_type = case.entrypoint.type
    expected_component_prefix = f"entrypoint:{entrypoint_type}"

    components = {s.component for s in trace.spans}
    has_expected_entry = any(
        c.startswith(expected_component_prefix) or c.startswith("entrypoint:")
        for c in components
    )

    if not has_expected_entry:
        gaps.append(
            LoggingGap(
                severity="warning",
                component="case",
                span_id=None,
                issue=f"Expected entrypoint type '{entrypoint_type}' not found in trace",
                recommendation=(
                    f"Ensure logs contain a span with component starting with 'entrypoint:'"
                ),
            )
        )

    return gaps


def detect_gaps(trace: Trace, case: CaseConfig) -> list[LoggingGap]:
    """Detect all logging gaps in a trace for a given case.

    Returns a list of LoggingGap objects sorted by severity.
    """
    gaps: list[LoggingGap] = []

    # Check individual spans
    for span in trace.spans:
        gaps.extend(_check_span_completeness(span))

    # Check trace structure
    gaps.extend(_check_trace_structure(trace))

    # Check against case expectations
    gaps.extend(_check_expected_components(trace, case))

    # Sort by severity (critical first)
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    gaps.sort(key=lambda g: (severity_order.get(g.severity, 99), g.component))

    return gaps
