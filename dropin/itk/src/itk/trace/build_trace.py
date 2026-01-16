from __future__ import annotations

from itk.trace.span_model import Span
from itk.trace.trace_model import Trace


def build_trace_from_spans(spans: list[Span]) -> Trace:
    """Offline ordering: stable sort by ts_start when present; otherwise preserve input order."""

    def key(s: Span):
        return (s.ts_start is None, s.ts_start or "")

    ordered = sorted(spans, key=key)
    return Trace(spans=ordered)
