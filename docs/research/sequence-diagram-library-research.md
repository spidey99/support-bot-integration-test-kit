# Research Prompt: Interactive Sequence Diagram Library Evaluation

## Context

I am building an **Integration Test Kit (ITK)** for testing AWS-based distributed systems. The ITK ingests structured log spans from various AWS services (Lambda, Bedrock Agents, SQS, etc.) and produces visual sequence diagrams showing the flow of requests through the system.

### Project Goals
- **Offline-first**: All rendering happens locally without network dependencies
- **Developer-focused**: Diagrams are used for debugging, understanding execution flow, and documenting test cases
- **CI-friendly**: Output must be static files that can be committed to repos or viewed in CI artifacts
- **Interactive**: Developers need to explore payloads, zoom, filter, and understand timing

### Current Tech Stack
- **Python 3.10+** (CLI tool, data processing)
- **Output formats needed**: Static HTML (primary), Mermaid `.mmd` files (secondary for GitHub rendering)
- **No server requirement**: Must work as static files opened in browser via `file://` protocol
- **No build step**: Prefer solutions that don't require Node.js/npm/webpack to generate output

---

## Current Implementation

We currently generate two outputs:
1. **Mermaid `.mmd` files** - Works but limited interactivity, depends on external renderers
2. **Custom HTML/CSS/JS** - Hand-rolled sequence diagram with basic features

### Current HTML Implementation Features
- CSS Grid-based layout for participant lanes
- Color-coded participant icons by component type
- Arrows between participants showing operation flow
- Collapsible `<details>` sections for request/response payloads
- Dark mode toggle via CSS variables
- Zoom controls via CSS transform
- Stats footer (span count, participant count, error count)

### Current Limitations
- No true pan/drag interaction
- Limited scalability (100+ spans becomes unwieldy)
- No search/filter capability
- No timeline view showing actual timing
- Arrows don't scale well with many participants
- No span selection/highlighting for tracing a single request
- Mobile/responsive issues

---

## Data Model

### Span (Single Event)
```python
@dataclass
class Span:
    span_id: str                          # Unique identifier
    parent_span_id: Optional[str]         # Parent span (forms tree)
    component: str                        # e.g., "lambda:handler", "agent:supervisor", "model:claude-3-sonnet"
    operation: str                        # e.g., "InvokeAgent", "InvokeModel", "InvokeLambda"
    ts_start: Optional[str]               # ISO 8601 timestamp
    ts_end: Optional[str]                 # ISO 8601 timestamp
    attempt: Optional[int]                # Retry attempt number (1, 2, 3...)
    request: Optional[dict]               # Request payload (JSON-serializable)
    response: Optional[dict]              # Response payload (JSON-serializable)
    error: Optional[dict]                 # Error details if failed
    
    # Correlation IDs (for linking across services)
    itk_trace_id: Optional[str]
    lambda_request_id: Optional[str]
    xray_trace_id: Optional[str]
    sqs_message_id: Optional[str]
    bedrock_session_id: Optional[str]
```

### Trace (Collection of Spans)
```python
@dataclass
class Trace:
    spans: list[Span]                     # Ordered list of spans
    # Spans form a tree via parent_span_id relationships
    # Root spans have parent_span_id = None
```

### Typical Data Characteristics
- **Span count**: 5-50 spans typical, up to 200+ for complex flows
- **Participant count**: 3-15 unique components
- **Tree depth**: 3-8 levels of nesting
- **Payload sizes**: Request/response JSON can be 1KB-100KB each
- **Timing**: Sub-second to multi-minute traces

---

## Required Display Features

### Must Have
1. **Participant lanes** - Vertical lanes for each unique component
2. **Arrows/messages** - Show calls between components with operation names
3. **Parent-child relationships** - Visual indication of which spans are children of others
4. **Error highlighting** - Red/distinct styling for failed spans
5. **Retry indication** - Badge or visual for retry attempts
6. **Latency display** - Show duration for each span
7. **Payload inspection** - Click/expand to see request/response JSON
8. **Zoom** - Scale diagram up/down for large traces

### Should Have
1. **Timeline view** - Show spans on a time axis (waterfall/Gantt style)
2. **Search/filter** - Find spans by component, operation, or payload content
3. **Span selection** - Click a span to highlight its ancestors/descendants
4. **Correlation ID display** - Show linking IDs between spans
5. **Dark mode** - Theme toggle
6. **Collapsible subtrees** - Collapse children of a span to simplify view

### Nice to Have
1. **Pan/drag** - Click and drag to navigate large diagrams
2. **Minimap** - Overview panel for large diagrams
3. **Export** - SVG/PNG export
4. **Diff view** - Side-by-side comparison of two traces
5. **Keyboard navigation** - Arrow keys to move between spans
6. **URL deep-linking** - Link to specific spans

---

## Interaction Requirements

### Click Interactions
- Click span → Show payload modal/panel with full JSON
- Click participant → Highlight all spans involving that participant
- Click arrow → Show span details inline

### Hover Interactions
- Hover span → Show tooltip with timing, correlation IDs
- Hover participant → Dim unrelated spans

### Keyboard
- Arrow keys → Navigate between spans
- Enter → Expand selected span details
- Escape → Close modals/panels
- `/` → Focus search

---

## Constraints

### Technical Constraints
1. **No server**: Output must be a single `.html` file (or `.html` + bundled `.js/.css`) that works via `file://`
2. **No build step**: Python generates the HTML directly, no Node.js in the pipeline
3. **Offline**: No CDN dependencies in production (can inline libraries)
4. **File size**: Reasonable size for large traces (< 5MB HTML for 200 spans)
5. **Browser support**: Modern browsers (Chrome, Firefox, Safari, Edge - last 2 versions)

### UX Constraints
1. **Fast initial render**: Should display within 1-2 seconds
2. **Responsive**: Work on 1080p and 4K displays
3. **Accessible**: Basic keyboard navigation, screen reader friendly labels
4. **Print-friendly**: Reasonable output when printed/PDF'd

---

## Research Questions

1. **What JavaScript libraries exist for interactive sequence diagrams?**
   - Looking for: D3.js-based, React-based, vanilla JS, or other approaches
   - Examples: js-sequence-diagrams, mermaid.js (already using), GoJS, JointJS, vis.js, etc.

2. **What libraries handle timeline/waterfall visualizations well?**
   - Similar to Chrome DevTools Network panel or distributed tracing UIs
   - Examples: vis-timeline, Gantt libraries, flame graph libraries

3. **Are there tracing-specific visualization libraries?**
   - Libraries designed for OpenTelemetry, Jaeger, Zipkin trace visualization
   - May have the exact features we need

4. **What's the best approach for large diagrams (100+ spans)?**
   - Virtual scrolling, canvas-based rendering, WebGL?
   - How do existing tools handle scale?

5. **Can we get interactive features without a build step?**
   - UMD/IIFE bundles we can inline?
   - Web Components that work standalone?

6. **What's the maintenance/licensing situation?**
   - MIT/Apache preferred
   - Active maintenance important
   - Bundle size considerations

---

## Evaluation Criteria

Please evaluate libraries against these criteria (1-5 scale):

| Criteria | Weight | Description |
|----------|--------|-------------|
| Feature fit | 5 | Does it support sequence diagrams or timeline views? |
| Interactivity | 5 | Click, hover, zoom, pan, search capabilities |
| No-build usage | 4 | Can we use it without Node.js/webpack? |
| Bundle size | 3 | Reasonable size for inlining (< 500KB ideal) |
| Documentation | 3 | Good docs and examples |
| Maintenance | 3 | Active development, recent releases |
| License | 2 | MIT/Apache/BSD preferred |
| Accessibility | 2 | Keyboard nav, ARIA support |

---

## Desired Output Format

Please provide:

1. **Top 3-5 library recommendations** with:
   - Name and URL
   - Brief description
   - Pros/cons for our use case
   - Example of how we'd use it (code snippet if possible)
   - Scores on evaluation criteria

2. **Alternative approaches** we might not have considered:
   - Different visualization paradigms
   - Hybrid approaches (e.g., Mermaid for static + separate interactive view)

3. **Implementation recommendation**:
   - Which library/approach to pursue
   - Estimated effort to integrate
   - Any gotchas or concerns

4. **If rolling our own is best**:
   - What specific improvements to make to current implementation
   - Which sub-libraries to use (e.g., for zoom/pan specifically)

---

## Reference Links

- **Mermaid.js**: https://mermaid.js.org/ (current secondary output)
- **OpenTelemetry**: https://opentelemetry.io/ (standard we loosely follow)
- **Jaeger UI**: https://www.jaegertracing.io/ (example of tracing UI)
- **Chrome DevTools Network**: (inspiration for timeline view)

---

## Current Code Reference

Our Python renderer signature:
```python
def render_html_sequence(
    trace: Trace,
    title: str = "Sequence Diagram",
    include_payloads: bool = True,
) -> str:
    """Render trace as an interactive HTML sequence diagram.
    
    Returns complete HTML document as string.
    """
```

We need to either:
1. Replace this with a library-based renderer
2. Enhance it with better JS libraries for interactivity
3. Generate data JSON and use a client-side library to render

Any of these approaches are acceptable as long as the output remains a static file.
