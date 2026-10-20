# Portfolio Release Checklist

Status labels: DONE, CONDITIONAL, BLOCKED, NOT_RUN.

## Product and demo

| Check | Status | Evidence |
|---|---|---|
| Offline Replay needs no API/data/model | DONE | `demo/app.py`, `portfolio_demo.py` |
| Replay visibly labelled as recorded | DONE | UI badge and fixture disclosure |
| Four required scenarios | DONE | knowledge, prediction, memory, comprehensive |
| Safety refusal scenario | DONE | `safety_refusal.json` |
| Desktop and 390 px screenshots | DONE | browser-rendered files under `docs/portfolio/screenshots/` |
| GitHub Pages payload | DONE | workflow uploads `demo/` only; deployment verified at `https://zhenwei-chang.github.io/tomato-agent/` |
| Full Local Agent CLI | CONDITIONAL | requires sibling assets and local extras |
| DeepSeek Online entry | CONDITIONAL | explicit credentials/consent; V1.4.5 online NOT_RUN |
| Portable Live Fixture Agent | NOT_RUN | intentionally not duplicated for the portfolio; recorded replay plus existing Full Local path retained |

## Documentation

| Check | Status |
|---|---|
| Chinese/English README | DONE |
| Three maintainable Mermaid diagrams | DONE |
| Benchmark separates online/offline/holdout | DONE |
| Sanitized real trace showcase | DONE |
| Engineering decisions and bad cases | DONE |
| Interview and resume material | DONE |

## Security and assets

| Check | Status | Note |
|---|---|---|
| Real API keys absent | DONE | only placeholders/test fixtures detected |
| Public config contains no legacy credential fallback | DONE | explicit env only |
| Raw trace/full case assets ignored | DONE | verify again after Git init |
| Portfolio fixtures contain no local drive path/vector | DONE | automated fixture validation |
| Raw dataset/document redistribution | DONE | these assets are excluded rather than redistributed |
| Sanitized fixture publication rights | DONE | owner confirmed ownership or authorization for public display on 2026-10-20 |
| Project source public-display authority | DONE | owner confirmed ownership or authorization for all 158 candidate files on 2026-10-20 |
| Project code license selected | NOT_APPLICABLE | no license will be added without a separate explicit decision; public visibility grants no reuse rights |
| Git staged-index secret/asset scan | DONE | scanner passed before the first commit and again before the release-status update |
| Git history scan | DONE | public history contains only audited release commits; no forbidden asset or secret finding |

## Verification

| Check | Status | Latest result |
|---|---|---|
| Offline fixture validation | DONE | all fixtures valid |
| Offline CLI smoke | DONE | list/show/check |
| Local demo HTTP smoke | DONE | localhost index + fixture served |
| Headless browser interaction smoke | DONE | 5 tabs, 6-tool trace, timeline toggle, Claim→Evidence highlight, safety refusal, no console/request errors |
| 390 px responsive layout | DONE | Playwright/Edge reported `scrollWidth == innerWidth == 390` |
| Public-candidate pytest | DONE | 10 passed in current environment and 10 passed in isolated wheel environment |
| Original V1.4.5 offline suite | HISTORICAL | frozen report: 140 passed, 2 skipped; not rerun or relabelled as public-candidate tests |
| Installed wheel CLI | DONE | `tomato-agent-demo check/list` works outside source tree |
| Portfolio release checks | DONE | 158 final staged files inspected; no release-scanner finding |
| README internal-link check | DONE | checked by release script |
| GitHub Actions portable checks | DONE | run 39387986178 succeeded |
| GitHub Pages deployment | DONE | rerun 39387986218 succeeded after Pages was enabled for workflow builds |
| Public Pages HTTP smoke | DONE | index, JS, CSS and all five fixtures returned HTTP 200 |
| DeepSeek online regression for V1.4.5 | NOT_RUN | requires authorization |
| 48-case independent holdout | NOT_RUN | sealed |

## Public release record

1. Public-display authority was confirmed on 2026-10-20; no reuse license was granted.
2. The verified GitHub identity was configured only in this repository.
3. The 158-file allowlist, tests, fixture validation and secret/asset checks passed before publication.
4. Public repository: `https://github.com/Zhenwei-Chang/tomato-agent`.
5. Recorded Replay: `https://zhenwei-chang.github.io/tomato-agent/`.
6. Full research assets and the private holdout remain excluded.

## Readiness decision

- **Interview-ready:** YES.
- **Offline Demo-ready:** YES.
- **Live DeepSeek Demo-ready:** CONDITIONAL — code path exists; credentials/consent and a V1.4.5 online smoke are still required.
- **GitHub Public-ready:** YES — technical checks pass and public-display authority was explicitly confirmed on 2026-10-20; no open-source license is granted.
- **Research Production-ready:** NO — no live greenhouse validation or control labels.
