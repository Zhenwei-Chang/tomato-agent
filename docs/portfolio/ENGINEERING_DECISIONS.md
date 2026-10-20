# Engineering Decisions

## 1. Why this is not a normal RAG chatbot

A RAG chatbot retrieves text and drafts an answer. Tomato Agent also needs exact-date data access, ML inference, View-level CV, historical outcome retrieval, scope enforcement and reliability. `tomato_fertigation_agent/registry/tool_registry.py` exposes these as nine typed capabilities; the final answer is assembled from heterogeneous `ToolResult` objects rather than from retrieved prose alone.

## 2. Tool Calling and fixed Workflow work together

The provider can produce parameterized function calls, but `tomato_fertigation_agent/workflow/` defines four bounded task shapes. The workflow controls required evidence and status semantics; the model handles natural-language interpretation and arguments. This avoids both a hard-coded FAQ router and an unconstrained ReAct loop.

## 3. Why Pydantic schemas are mandatory

`schemas/tools.py` defines every tool input. Validation happens before dispatch, so dates, scope combinations, top-k bounds and required identifiers fail as structured `INVALID_ARGUMENT` errors instead of becoming ambiguous pandas/model failures. The same models export provider schemas and validate direct CLI calls.

## 4. Preventing unknown tool execution

`ToolRegistry` is the single source of callable definitions. A model-produced name is looked up against that registry; an unregistered name returns `INVALID_ARGUMENT`. The executor never evaluates code or dynamically imports a name from model text.

## 5. Argument repair

`agent/executor.py` first validates the call. Invalid arguments can be sent through a bounded repair prompt with the canonical schema and validation error. Repairs are counted, traced and capped; failure becomes a structured tool error. V1.4.2 also added registry-driven tool-plan repair for invalid names.

## 6. Duplicate-call handling

The executor fingerprints canonical tool name plus normalized arguments. Repeated calls can reuse an earlier result or be blocked, preventing token/cost loops. Evaluation reports model attempts, actual executions and reused results separately.

## 7. Historical Case Memory vs Knowledge RAG

Knowledge RAG (`adapters/rag_adapter.py`) returns source-backed agronomic statements and locators. Case Memory (`cases/`) returns structured past states with observed later outcomes and similarity scores. One answers “what sources say”; the other answers “what happened in comparable records.” Neither is treated as causal proof.

## 8. Temporal leakage prevention

Historical retrieval supports `historical_only`, compares case/outcome timestamps with the query cutoff, and can exclude the same entity. The case target is an observed exact +7-day outcome; a candidate whose future outcome is unavailable by the query's historical cutoff is not evidence for that query.

## 9. Model–Case conflict

`evidence/conflict.py` compares an ML forecast with a case-derived forecast only when both exist and are reliable enough to compare. Agreement thresholds are explicit. Missing cases produce `NOT_AVAILABLE`, not false agreement. A conflict lowers reliability and is exposed in the answer.

## 10. Evidence grounding

`EvidenceNormalizer` converts tool-specific payloads into typed records; `EvidenceStore` indexes them; claim builders attach `support_evidence_ids`. A fluent sentence without accepted support is removed or causes a downgrade. This fixed the V1.4.2 bad case where a correct ToolResult did not survive into the final answer.

## 11. Claim provenance

`evidence/provenance.py` builds edges `Claim → Evidence → Tool Call → Data/Model/Knowledge Source`. Provenance validation checks missing and semantically mismatched references. Paths are retained in the private research trace but replaced by source labels in public fixtures.

## 12. FULL / PARTIAL / ABSTAIN

`AnswerStatusResolver` compares the final response against the original `RequestContract`: FULL when every requested supported subtask is satisfied, PARTIAL when useful requested evidence exists but required pieces are missing, and ABSTAIN when the main claim cannot be supported. Hypothetical limitations added by the model no longer become fake user requests.

## 13. Evaluating a real LLM

Mock tests verify determinism, not model behavior. The V1.4.4 gate sent 10 authorized public-fixture ToolResults to `deepseek-flash`, recorded generated calls, validation, executions, evidence, tokens, latency and cost, then combined strict automatic scoring with human adjudication. It exposed failures that unit tests could not: wrong tool sequence, omitted required reliability and false PARTIAL statuses.

## 14. Why automatic fertigation is not implemented

The public data has no reliable per-event irrigation/fertilizer quantity and no expert label for an optimal action. Generating exact mL or fertilizer dose would turn a language prior into an unsupported control decision. The system therefore stops at monitoring, experimental growth forecasting and evidence-grounded considerations.

## Three engineering bad cases

### Bad Case A — invalid tool name

**Symptom:** an early provider run produced a plausible but unregistered tool name. **Localization:** Router output did not share a strong enough Registry contract. **Fix:** export provider schemas directly from the registry and add bounded plan repair. **Regression check:** canonical tool-name validity and unknown-tool rejection.

### Bad Case B — evidence missing from final answer

**Symptom:** a tool returned correct evidence, but the answer omitted or could not cite it. **Localization:** tool-specific evidence shapes were not normalized consistently before synthesis. **Fix:** `EvidenceAssembler`/`EvidenceNormalizer`, stable IDs and provenance validation. **Regression check:** evidence registration coverage, reference utilization and semantic mismatch count.

### Bad Case C — false PARTIAL

**Symptom:** the provider added warnings for capabilities the user never requested; status logic interpreted them as missing work. Four V1.4.4 answers became overly PARTIAL. **Localization:** answer status depended on generated limitations rather than user intent. **Fix:** V1.4.5 `RequestContract` plus request-relative `AnswerStatusResolver`. **Evidence boundary:** offline Known-10 improved to 10/10, but no V1.4.5 online rerun has been authorized.
