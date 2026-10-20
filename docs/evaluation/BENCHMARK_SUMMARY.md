# Benchmark Summary

## What is frozen

The latest real-provider benchmark is **V1.4.4 DeepSeek Known-10 Online Regression**, completed on 2026-10-19 with `deepseek-flash`.

- Cases: 10 known development fixtures.
- API calls: 41 of the authorized maximum 50.
- Actual tool executions: 14.
- Input/output tokens: 114,823 / 12,365.
- Median / p95 latency: 8.265 s / 12.945 s.
- Estimated API cost: USD 0.03295 under the stored price basis.
- Frozen result SHA-256: `50EE79955F4E64777F5920AB1D02F4075203992D401EB419D60F9C9559EF6843`.

## Real DeepSeek results

| Metric | Numerator / denominator | Result |
|---|---:|---:|
| Tool Selection F1 | aggregate | 96.67% |
| Argument Accuracy | valid calls | 100% |
| Evidence Grounding | evaluated claims | 100% |
| Provenance Completeness | evaluated claims | 100% |
| Human PASS | 8 / 10 | 80% |
| Human PARTIAL | 2 / 10 | 20% |
| Strict Automatic PASS | 5 / 10 | 50% |
| Scope Violations | 0 | 0 |
| Unsupported Numerical Claims | 0 | 0 |

This table intentionally includes the strict automatic score. The provider selected mostly correct tools and arguments, but answer-status behavior still produced five strict failures.

## Known-10 bad cases

- Four responses were overly conservative because synthesis introduced hypothetical unsupported requests and the old resolver treated them as requested subtasks.
- One RGB case had a wrong/incomplete tool sequence.
- The high-salinity knowledge case abstained after the relevance gate rejected evidence, while the fixture expected PARTIAL.
- Fixture-required reliability was executed in only 2/3 required cases even though the earlier route-relative metric reported 100%.

These findings motivated V1.4.5 `RequestContract`, status resolution and independent required-tool evaluation.

## V1.4.5 is offline-only

| Validation | Result | Meaning |
|---|---:|---|
| Full deterministic suite at V1.4.5 completion | 140 passed, 2 skipped | Local contracts and integrations; online tests skipped |
| Known-10 offline contract regression | 10 / 10 | Known development fixtures with deterministic provider |
| Paraphrase development set | 8 / 8 | Development paraphrases, not holdout |
| V1.4.5 real DeepSeek run | NOT_RUN | No online claim may be made for the fixes |
| 48-case independent holdout | NOT_RUN | No generalization claim may be made |

The offline 10/10 result must not replace the online 5/10 strict result in external descriptions.

## Evaluation layers

1. **Unit / integration tests** validate deterministic contracts, schemas, safety and adapters.
2. **Offline known-set regression** detects code regressions cheaply but is not independent.
3. **Real-provider regression** measures model-generated tool selection, arguments and answer behavior.
4. **Human review** judges answer usefulness and whether conservative outputs are acceptable.
5. **Independent holdout** is the missing layer and remains sealed.

## Reproducibility boundary

The sanitized portfolio fixtures preserve selected tool order, statuses, numerical claims and limitations. Raw provider payloads and local paths are intentionally not included. Re-running the online benchmark requires explicit authorization, provider credentials and outbound-data consent; it is not part of the default demo.
