"""Generate a demo trace viewer."""
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from itk.diagrams.trace_viewer import render_trace_viewer, render_mini_svg
from itk.trace.span_model import Span
from itk.trace.trace_model import Trace

# Create a realistic demo trace
spans = [
    Span(
        span_id="req-001",
        parent_span_id=None,
        component="entrypoint:api-gateway",
        operation="POST /chat",
        ts_start="2026-01-15T10:00:00.000Z",
        ts_end="2026-01-15T10:00:02.500Z",
        request={"path": "/chat", "body": {"message": "Hello"}},
    ),
    Span(
        span_id="lmb-001",
        parent_span_id="req-001",
        component="lambda:chat-handler",
        operation="invoke",
        ts_start="2026-01-15T10:00:00.050Z",
        ts_end="2026-01-15T10:00:02.450Z",
        request={"input": "Hello"},
    ),
    Span(
        span_id="agn-001",
        parent_span_id="lmb-001",
        component="agent:supervisor",
        operation="route_request",
        ts_start="2026-01-15T10:00:00.100Z",
        ts_end="2026-01-15T10:00:00.200Z",
    ),
    Span(
        span_id="mdl-001",
        parent_span_id="agn-001",
        component="model:claude-3-sonnet",
        operation="invoke_model",
        ts_start="2026-01-15T10:00:00.250Z",
        ts_end="2026-01-15T10:00:01.800Z",
        request={"prompt": "Classify intent"},
        response={"classification": "greeting"},
    ),
    Span(
        span_id="agn-002",
        parent_span_id="lmb-001",
        component="agent:gatekeeper",
        operation="validate",
        ts_start="2026-01-15T10:00:01.850Z",
        ts_end="2026-01-15T10:00:01.900Z",
    ),
    Span(
        span_id="mdl-002",
        parent_span_id="agn-002",
        component="model:claude-3-sonnet",
        operation="invoke_model",
        ts_start="2026-01-15T10:00:01.950Z",
        ts_end="2026-01-15T10:00:02.300Z",
        request={"prompt": "Generate response"},
        response={"text": "Hi there! How can I help?"},
    ),
    Span(
        span_id="err-001",
        parent_span_id="lmb-001",
        component="dynamodb:sessions",
        operation="put_item",
        ts_start="2026-01-15T10:00:02.320Z",
        ts_end="2026-01-15T10:00:02.380Z",
        attempt=2,
        error={"code": "ProvisionedThroughputExceeded", "message": "Rate exceeded"},
    ),
    Span(
        span_id="ok-001",
        parent_span_id="lmb-001",
        component="dynamodb:sessions",
        operation="put_item",
        ts_start="2026-01-15T10:00:02.400Z",
        ts_end="2026-01-15T10:00:02.420Z",
        attempt=3,
        response={"status": "ok"},
    ),
]

trace = Trace(spans=spans)

# Generate outputs
out_dir = Path(__file__).parent.parent / "artifacts" / "demo"
out_dir.mkdir(parents=True, exist_ok=True)

html = render_trace_viewer(trace, title="ITK Demo - Chat Request Flow")
(out_dir / "trace-viewer.html").write_text(html, encoding="utf-8")

svg = render_mini_svg(trace)
(out_dir / "thumbnail.svg").write_text(svg, encoding="utf-8")

print(f"Generated: {out_dir.absolute() / 'trace-viewer.html'}")
