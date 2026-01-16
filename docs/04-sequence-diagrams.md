# Sequence diagrams

Output is Mermaid so it can live as a normal `.mmd` file and render on GitHub.

The diagram must show:
- participants (agents/lambdas/models/tools)
- each request/response hop
- retries as `loop` blocks
- notes that link to full JSON payload artifacts

Example:

```mermaid
sequenceDiagram
  participant E as Entrypoint
  participant G as GatekeeperAgent
  participant S as SupervisorAgent
  participant A as ActionGroupLambda
  participant M as Model

  E->>G: invoke (payloads/entry.request.json)
  loop retry attempt 1..N
    G->>S: invoke_agent
    S->>A: invoke lambda
    A->>M: invoke_model
    M-->>A: response
  end
  G-->>E: final response
```
