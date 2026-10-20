# Demo Walkthrough

## 30-second introduction

Tomato Agent is an evidence-driven LLM Agent that does not ask the language model to guess plant measurements or irrigation quantities. DeepSeek selects typed tools; data, ML, historical-memory and RAG adapters return structured evidence; deterministic policies then validate scope, reliability and Claim provenance before the answer is marked FULL, PARTIAL or ABSTAIN.

The public Demo is a sanitized Recorded Replay. It is interactive, but it is not live inference.

## 2–3 minute interview flow

1. **README — 20 seconds.** Explain the separation between LLM orchestration and specialized numerical tools. Point out the public-asset boundary.
2. **Scenario Explorer — 25 seconds.** Switch between Knowledge RAG, prediction, historical memory, comprehensive workflow and safety refusal.
3. **Comprehensive Agent — 45 seconds.** Select the six-tool scenario. Expand each call and show that all six calls were model-generated in the frozen V1.4.4 trace. Point out the failed historical retrieval and the resulting PARTIAL status.
4. **Evidence & Provenance — 30 seconds.** Select a grounded claim. The supporting Evidence IDs are highlighted. Explain Claim → Evidence → Tool → scoped source.
5. **Benchmark — 30 seconds.** Show 96.67% Tool Selection F1 and 100% grounding, but also the stricter 5/10 automatic PASS and the 10-case development-set limitation.
6. **Engineering lesson — 20 seconds.** Summarize the three most useful bad cases: invalid tool names, evidence lost before synthesis and false PARTIAL caused by provider-invented constraints.

## What to say about execution modes

| Mode | Interview description |
|---|---|
| Recorded Replay | Public, zero-key and zero-data interactive playback of frozen sanitized traces. |
| Full Local Agent | Real Tool Registry and adapters; requires separately authorized data, checkpoints, Case Memory and RAG assets. |
| DeepSeek Online | Real function calling with explicit credentials, network enablement, call budget and outbound-data consent. Not hosted by GitHub Pages. |

A separate Portable Live Fixture Agent was intentionally not added: doing so would require a second fixture-specific registry/runtime and would weaken the single-contract architecture. The portfolio proves online behavior with the frozen V1.4.4 trace and keeps the existing Full Local pathway for real execution.

## Suggested live navigation

- Start at the Hero and state that the yellow badge means offline replay.
- Open **Comprehensive Agent**.
- Expand `predict_height_t7`, `find_similar_cases` and `assess_prediction_reliability`.
- Select the prediction claim and show the highlighted model evidence.
- Copy the sanitized trace to demonstrate that the UI exports only the curated fixture.
- Scroll to the Benchmark and call out both 8/10 human PASS and 5/10 strict automatic PASS.
- Finish with the Safety Refusal scenario.

## Deeper interview material

- [Engineering decisions](ENGINEERING_DECISIONS.md)
- [Interview questions](INTERVIEW_PREPARATION.md)
- [Trace showcase](../evaluation/TRACE_SHOWCASE.md)
- [Benchmark integrity](../evaluation/BENCHMARK_SUMMARY.md)
