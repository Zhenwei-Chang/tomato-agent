# Public Code Audit

Audit date: 2026-10-20. Scope: isolated candidate repository only.

## Verdict

| Area | Status | Evidence |
|---|---|---|
| Repository isolation | PASS | Candidate is independent; no sibling research project is tracked. |
| Secret and local-path scan | PASS | Expanded scanner covers provider/GitHub/cloud token shapes, private keys, generic secret assignments, drive paths and credential filenames. |
| Data and binary boundary | PASS | No dataset, source RGB, PDF, embedding, checkpoint, model binary, raw trace or private holdout is tracked. The only PNGs are five browser-rendered screenshots of sanitized Demo content. |
| Recorded Replay truthfulness | PASS | Every fixture declares `recorded_replay`; the UI continuously displays the offline replay label. |
| Benchmark integrity | PASS | V1.4.4 Known-10 online, V1.4.5 offline-only and 48-case `NOT_RUN` remain separate. |
| GitHub Pages payload | PASS | Deployment workflow uploads only `demo/`. |
| Code ownership / publication authority | PASS | On 2026-10-20, the repository owner explicitly confirmed ownership or authorization to publicly display all 158 candidate files. |
| Project license | WARNING | No open-source license is asserted. Public visibility alone grants no reuse, modification or redistribution rights. |

## Git inventory

The earlier numbers had different denominators:

- **148 staged files** meant every path in the initial Git index.
- **146 curated files inspected** came from the first release scanner, whose explicit scan roots omitted `configs/case_retrieval.yaml` and `configs/workflow.yaml`.

The scanner now evaluates the union of the Git index and the complete public allowlist, including all example configuration and newly created Pages assets. This removes the two-file coverage gap.

## Findings by severity

### P0

No P0 code, credential, asset-boundary or publication-authority issue was found.

### P1 — fixed

1. The original Demo showed static cards but did not expose the execution contract clearly.
   - Added five-scenario navigation, expandable tool calls, dispatch-source labels, recorded latency, Claim-to-Evidence highlighting, copyable sanitized trace, benchmark and architecture panels.
2. No Pages deployment workflow existed.
   - Added a least-privilege workflow that validates the release surface and uploads only `demo/`.
3. The release scanner used narrow H/I-drive and provider-key patterns and missed two tracked config files.
   - Generalized local-path and secret patterns, added forbidden asset/root checks, symlink checks, a 1 MiB ceiling and full inventory coverage.
4. Fixture contracts did not validate dispatch source, latency or Claim-to-Evidence references.
   - Added deterministic validation and tests.
5. A clean wheel installation could not locate the Replay fixtures through the `tomato-agent-demo` entry point.
   - Packaged the existing five JSON fixtures as wheel data and added source-checkout/installed-environment resolution without creating a second fixture copy.

### P2 — fixed or documented

- Controlled credential-file diagnostics previously exposed the local credential file path in `credential_source`; it now reports only `controlled_file`.
- Full Local Agent execution still requires separately authorized research assets. This is a deliberate distribution boundary, not hidden portability.
- Portable CI validates the public Demo and contract surface; it does not claim to reproduce the complete private research integration suite.

## Core Agent review

Reviewed modules include the DeepSeek/OpenAI provider adapters, bounded function-calling loop, registry-derived schemas, router and tool-name repair, argument validation/repair, duplicate-call guard, workflow engine, RequestContract, AnswerStatusResolver, EvidenceAssembler, provenance builder, reliability policy, trace writers and online evaluator.

Observed safeguards:

- timeout, retry, provider-call, tool-call and repair budgets are bounded;
- executable tool names originate from the registry and unknown names are rejected;
- Pydantic validation runs before tool execution;
- duplicate calls reuse prior results instead of re-executing;
- evidence IDs are registered deterministically and missing/semantic mismatches are checked;
- plant/view/greenhouse/knowledge scopes are preserved;
- online evaluation requires explicit enablement and explicit consent for outbound ToolResult data;
- trace summaries omit embeddings and large sensor payloads.

No new agricultural capability or model was added during this release audit.

## Truthfulness checks

- Recorded fixtures are not described as current live inference.
- Precomputed predictions remain frozen fixture results, not real-time ML execution.
- The project is described as decision-support infrastructure, not automatic fertigation control.
- Known development tests are not described as independent generalization.
- V1.4.5 deterministic results do not replace the V1.4.4 online result.
- Missing data displays as missing or `NOT_RECORDED`; the UI does not synthesize absent latency or provenance.

## Rights decision

The repository owner explicitly confirmed on 2026-10-20 that they own or are authorized to publicly display all 158 candidate files. They also authorized publication without adding an open-source license. The repository therefore remains source-available for portfolio review only: public visibility does not grant permission to copy, modify or redistribute the code. Third-party datasets, papers, model weights and other excluded assets remain outside this authorization.
