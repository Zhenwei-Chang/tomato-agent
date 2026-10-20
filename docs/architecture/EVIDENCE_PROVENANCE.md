# Evidence & Provenance

The Agent treats a fluent answer as insufficient unless its claims can be traced to accepted evidence.

```mermaid
flowchart LR
    C1[Claim: current height 20.8 cm] -->|SUPPORTED_BY| E1[Observation Evidence]
    C2[Claim: t+7 estimate 34.66 cm] -->|SUPPORTED_BY| E2[Prediction Evidence]
    C3[Monitoring consideration] -->|SUPPORTED_BY| E3[Sensor Evidence]
    C3 -->|SUPPORTED_BY| E4[Knowledge Evidence]

    E1 -->|PRODUCED_BY| T1[get_growth_context]
    E2 -->|PRODUCED_BY| T2[predict_height_t7]
    E3 -->|PRODUCED_BY| T3[get_sensor_history]
    E4 -->|PRODUCED_BY| T4[retrieve_water_fertilizer_knowledge]

    T1 -->|SOURCED_FROM| S1[Canonical phenotype]
    T2 -->|SOURCED_FROM| S2[Locked model + feature schema]
    T3 -->|SOURCED_FROM| S3[Canonical environment]
    T4 -->|SOURCED_FROM| S4[Knowledge source + locator]
```

## Evidence lifecycle

```mermaid
flowchart TD
    TR[ToolResult] --> N[EvidenceNormalizer]
    N --> G{Relevance / validity gate}
    G -->|accepted| S[EvidenceStore]
    G -->|rejected| W[Warning / insufficiency reason]
    S --> C[Conflict Analyzer]
    S --> Q[Completeness Checker]
    C & Q --> R[Reliability Propagation]
    R --> CL[Claim Builder]
    CL --> P[Provenance Validator]
    P -->|complete| A[Answer]
    P -->|missing or mismatched| D[Downgrade / remove claim]
```

## Scope is part of evidence

`plant`, `view`, `greenhouse`, `treatment`, and `knowledge` are not cosmetic labels. A View-level RGB estimate cannot support an exact Plant-level claim. Substrate moisture marked `greenhouse_global_proxy` cannot be described as that plant's measured root-zone moisture.

## Reliability is not probability

HIGH / MEDIUM / LOW / UNKNOWN are rule-based audit levels. They summarize scope match, critical feature availability, known domain, evidence completeness, model/case agreement and known limitations. They are explicitly marked `statistically_calibrated=false`.
