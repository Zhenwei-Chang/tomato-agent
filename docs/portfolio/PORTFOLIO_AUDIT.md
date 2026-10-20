# Portfolio Readiness Audit

Audit date: 2026-10-19. Scope: local workspace inspection only; no DeepSeek call, holdout run, upload or repository publication.

## 1. Workspace

| Project | Role | Local size observed |
|---|---|---:|
| `tomato_fertigation_agent` | Agent orchestration, tools, evidence, evaluation | 18.73 MB before portfolio files |
| `tomato_multimodal_public` | Canonical data, ML/CV research assets | 248.84 MB |
| `tomato_agent_app` | Existing knowledge-assistant PWA | 15.74 MB |
| `agent_system` | Existing verified knowledge repository/RAG runtime | 240.69 MB |

Runtime inspected: Python 3.12.9; package requirement remains Python 3.11+.

At the original audit time, neither `tomato_fertigation_agent` nor its parent was a Git repository. The portfolio work was therefore copied through an explicit allowlist into a separate candidate, where a new local `main` repository is now initialized. It has no remote and has not been pushed.

## 2. Can it run without the 26 GB raw dataset?

**Offline Replay: yes.** `demo/app.py` and `tomato_fertigation_agent.portfolio_demo` use only sanitized JSON and the Python standard library.

**Full Local Agent: only partly.** Canonical plant/sensor tools, the height model, RAG, and case retrieval require sibling project assets. Live RGB from an image path additionally needs the original image or an allowed local input. Full local operation is therefore a workstation mode, not the minimal public demo.

## 3. Absolute-path dependencies

Core configuration now defaults the raw/image root to local `inputs/`; a real raw root must be supplied through `TOMATO_RAW_ROOT`. `TOMATO_RESEARCH_ROOT`, `TOMATO_WORKSPACE`, and `TOMATO_OUTPUT_ROOT` support relocation.

Absolute local paths remain in historical artifacts that should not be published as-is:

- `data/cases/case_memory_manifest.json` source lineage.
- `data/cases/view_cases.csv` image paths.
- old `outputs/evals/**` and `outputs/traces/**` provenance.
- older research documentation describing the original workstation.

The portfolio fixtures contain no workstation drive path. The new `.gitignore` excludes raw traces and full case assets, but ignore rules protect only untracked files; a future repository must still inspect its index before commit.

## 4. Models and large files

The Agent directory's largest files were:

| Asset | Size | Release decision |
|---|---:|---|
| `outputs/traces/agent_traces.jsonl` | 6.40 MB | Exclude; local paths/provider metadata |
| `data/cases/plant_cases.csv` | 4.43 MB | Exclude pending source-data redistribution review |
| `data/cases/view_case_embeddings.npz` | 1.76 MB | Exclude pending image-derived asset review |
| `outputs/traces/tool_calls.jsonl` | 1.42 MB | Exclude; use sanitized showcase |
| `data/cases/view_cases.csv` | 0.59 MB | Exclude; contains source image paths |

The locked sklearn checkpoints in the sibling research project are individually about 0.4 MB or less, but they are not bundled until source-data/model redistribution rights are confirmed. Frozen ResNet18 ImageNet weights are loaded from the local PyTorch cache and are not committed.

## 5. CLI and UI decision

The existing `tomato-tools` CLI is strong enough for full local development: registry discovery, direct tool calls, Agent queries, workflows, and evaluation. It is not a minimal public entry because constructing the registry loads pandas/scikit-learn adapters and expects sibling assets.

The existing PWA targets the older knowledge assistant and has a different product contract. Connecting it to the current Agent would require API and frontend changes beyond portfolio scope. The release therefore adds a zero-build, localhost-only static viewer under `demo/`, with a separate dependency-light terminal replay. It does not copy Agent logic.

## 6. Credentials and sensitive material

- No real `.env` file was found inside the Agent project; only `.env.example` exists.
- The secret-pattern candidate in `tests/unit/test_v141_deepseek_provider.py` is test fixture content, not a live credential.
- `configs/agent.yaml` previously contained a workstation-relative credential-file fallback. It has been removed; online use now requires an explicit environment variable.
- Raw traces and provider outputs are not suitable for publication without sanitization.
- No API key, original image, 512D vector, document PDF, or large table is included in the portfolio fixtures.

## 7. License and redistribution audit

No local `LICENSE`, `LICENCE`, `COPYING`, `NOTICE`, or dataset license file was found across the inspected projects. Therefore:

- **Project code:** owner must explicitly confirm authority for public display. No reuse license was invented in this release; public visibility alone would grant no reuse rights.
- **Public tomato dataset/RGB:** redistribution permission is UNKNOWN; do not repack raw files or derived bulk assets merely because the dataset is downloadable.
- **RAG documents/PDFs:** source-specific terms are not consolidated; distribute citations/locators or retrieval summaries, not full documents.
- **PyTorch/torchvision code:** upstream code is BSD-style/BSD-3-Clause, but TorchVision explicitly warns that pretrained weights may inherit terms from their training datasets. See [TorchVision model documentation](https://docs.pytorch.org/vision/master/models.html) and [TorchVision repository](https://github.com/pytorch/vision).
- **scikit-learn:** BSD-3-Clause; see its [official COPYING](https://github.com/scikit-learn/scikit-learn/blob/main/COPYING).
- **Pydantic:** MIT; see its [official project metadata](https://github.com/pydantic/pydantic/blob/main/pyproject.toml).
- **DeepSeek API:** credentials must remain secret and submitted inputs must be authorized. See the [official API docs](https://api-docs.deepseek.com/api/deepseek-api/) and [Open Platform Terms](https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html).

This is an engineering audit, not legal advice.

## 8. Release blockers

| Item | Interview demo | Public GitHub |
|---|---:|---:|
| No isolated Git repository | No | Resolved in the public candidate |
| No owner-selected code license | No | Warning: the repository must not claim an open-source license; public display still requires owner authority |
| Dataset/document redistribution unknown | No for sanitized replay | **Blocker** for bundling full assets |
| V1.4.5 not tested online | Must disclose | Not a source-publication blocker |
| 48-case holdout NOT_RUN | Must disclose | Not a source-publication blocker |
| Full local mode needs sibling assets | No | Documented limitation |

## 9. Audit answers

- **A — independent of 26 GB?** Offline Demo yes; full Local Agent no.
- **B — absolute paths?** Historical case/provenance artifacts and old docs; core raw default was removed.
- **C — oversized assets?** Full traces, case memory, embeddings, raw RGB/data and external weights should stay out of GitHub.
- **D — CLI sufficient?** Yes for developers; a lightweight replay entry was still needed for reviewers.
- **E — Web demo?** A minimal local viewer adds clear value; PWA integration was disproportionate.
- **F — sensitive files?** Credential fallbacks, `.env`, raw traces, local paths and provider payloads require exclusion/sanitization.
- **G — licenses?** Third-party software licenses are identifiable; dataset, derived assets, RAG documents and project code redistribution boundaries remain unresolved.
