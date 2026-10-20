# Agent Portfolio Release V1.0 Report

## Scope delivered

- Zero-dependency Recorded Replay CLI and localhost UI.
- Five sanitized scenarios covering RAG, prediction, case memory, six-tool orchestration and safety refusal.
- Minimal/local/vision/online dependency separation.
- Chinese and English portfolio READMEs.
- Three Mermaid architecture documents.
- Frozen online benchmark summary and a real six-tool sanitized Trace Showcase.
- Engineering decisions, three bad-case retrospectives, interview Q&A and bilingual resume material.
- Read-only release gate covering fixture schema, local paths, secret-like values, large public candidates and internal Markdown links.

## Verification

- Public-candidate portable suite: 10 passed in the current environment and 10 passed after an isolated wheel install.
- Original V1.4.5 offline suite (historical frozen result): 140 passed, 2 skipped; it was not relabelled as a public-candidate run.
- Registry smoke: all 9 canonical tools discovered.
- Replay fixtures: valid.
- Portfolio release check: PASS across the curated candidate; final count is recorded in `GITHUB_CANDIDATE_AUDIT.md` after staging.
- Local UI: index and comprehensive fixture returned HTTP 200.
- Dependency environment: `pip check` found no broken requirements.
- Network/provider use: none.

## Honest release status

| Target | Status | Reason |
|---|---|---|
| Interview | READY | runnable replay, architecture, trace, decisions, Q&A |
| Offline Demo | READY | no data/model/API dependency |
| Local full Agent | CONDITIONAL | sibling canonical/RAG/model assets required |
| Live DeepSeek Demo | CONDITIONAL | explicit key, consent and V1.4.5 online smoke required |
| Public GitHub | PUBLISHED | `https://github.com/Zhenwei-Chang/tomato-agent`; no open-source license is granted |
| GitHub Pages | READY | `https://zhenwei-chang.github.io/tomato-agent/`; five scenarios and static assets verified with HTTP 200 |
| Research production | NOT READY | public data, domain shift, no live control labels |

The isolated candidate was published to `Zhenwei-Chang/tomato-agent` on `main`. GitHub Actions portable checks and the Recorded Replay Pages deployment passed. No DeepSeek call was made during release, and the private 48-case holdout was not copied, run or modified.
