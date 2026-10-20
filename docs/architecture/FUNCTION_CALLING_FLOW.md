# Function Calling Flow

The online loop is stateless at the transport layer: each continuation sends the required provider response items and tool outputs explicitly. Agent state, budgets and duplicate fingerprints are maintained by the application.

```mermaid
sequenceDiagram
    actor U as User
    participant A as Agent Orchestrator
    participant L as DeepSeek Provider
    participant V as Schema / Registry Validator
    participant T as Tool Executor
    participant E as Evidence Pipeline

    U->>A: Query
    A->>A: Route + RequestContract + budget
    A->>L: Instructions, query, registry schemas
    L-->>A: Function call(s)
    A->>V: Validate canonical name + Pydantic arguments
    alt unknown name or invalid arguments
        V-->>A: Rejected / bounded repair request
        A->>L: Contract-aware repair context
        L-->>A: Corrected call
    end
    V-->>T: Validated canonical call
    T->>T: Duplicate fingerprint + call budget check
    T-->>A: Structured ToolResult
    A->>L: Prior response items + ToolResult
    alt more evidence needed and budget remains
        L-->>A: Additional function call(s)
        A->>V: Validate again
    else final response
        L-->>A: Structured synthesis
    end
    A->>E: Normalize evidence + check relevance/conflict/completeness
    E-->>A: Claims, provenance, reliability, answer status
    A-->>U: FULL / PARTIAL / ABSTAIN answer
```

## Guardrails

1. Tool names are exported from the registry; an LLM string cannot create a callable.
2. Arguments are parsed by the tool's Pydantic input model before dispatch.
3. Repair is bounded by `max_argument_repairs` and `max_tool_plan_repairs`.
4. Duplicate calls are detected from canonical name plus normalized arguments.
5. Provider/tool budgets terminate runaway loops.
6. Provider errors become structured states; deterministic fallbacks never masquerade as model-generated calls.
7. Final status is resolved against the original RequestContract, not against limitations invented during synthesis.
