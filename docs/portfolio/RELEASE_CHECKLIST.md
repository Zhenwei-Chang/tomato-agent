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
| GitHub Pages payload | DONE | workflow uploads `demo/` only; remote deployment NOT_RUN |
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
| Git staged-index secret/asset scan | CONDITIONAL | scanner passes working candidate; rerun after final staging |
| Git history scan | NOT_APPLICABLE | repository has no commit/history yet |

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
| DeepSeek online regression for V1.4.5 | NOT_RUN | requires authorization |
| 48-case independent holdout | NOT_RUN | sealed |

## Before public GitHub publication

1. Review the final staged explicit allowlist and the candidate audit.
2. Configure the verified GitHub account identity locally before creating the first commit.
3. Confirm no full `data/cases`, `outputs/traces`, original images, PDFs, holdout or model weights are tracked.
4. Re-run `python scripts/portfolio_release_check.py` and `python -m pytest -q`.
5. Run a history-aware secret scan before any public visibility change.
6. Keep the repository unlicensed unless the owner makes a separate explicit licensing decision.

## Readiness decision

- **Interview-ready:** YES.
- **Offline Demo-ready:** YES.
- **Live DeepSeek Demo-ready:** CONDITIONAL — code path exists; credentials/consent and a V1.4.5 online smoke are still required.
- **GitHub Public-ready:** YES — technical checks pass and public-display authority was explicitly confirmed on 2026-10-20; no open-source license is granted.
- **Research Production-ready:** NO — no live greenhouse validation or control labels.
