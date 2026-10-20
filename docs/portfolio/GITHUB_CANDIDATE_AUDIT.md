# GitHub Candidate Audit

Audit date: 2026-10-20.

## Repository state

- Isolated candidate: `tomato_agent_portfolio_public`.
- Source research directory was not converted into a repository.
- Branch: `main`.
- Remote: `https://github.com/Zhenwei-Chang/tomato-agent.git`.
- Initial audited commit: `ac4d2f4cd7aac68bf2be95e062f6e0b6c2609da2`.
- Files are staged from an explicit allowlist plus the audited Pages/Demo release additions.
- The GitHub account was verified as `Zhenwei-Chang` (user ID `199451939`); repository-local author configuration uses the account-associated GitHub noreply address.

## Staged-content policy

Included: Python source, prompt templates, example configuration, sanitized Replay fixtures, portable tests, least-privilege GitHub Actions, README, curated documentation and five screenshots rendered from the sanitized Demo.

Excluded: raw/canonical data, full Case Memory, embeddings, checkpoints, pretrained weights, RGB, PDFs, RAG index/content, raw traces, provider payloads, outputs, credentials, private holdout and unrelated research projects.

## Verification

- Portable tests: 10 passed in the current environment and 10 passed after a clean wheel installation.
- Installed `tomato-agent-demo` CLI: `check` and `list` passed from outside the source tree.
- Replay fixtures: valid under Python `-S` with no site packages.
- Candidate release scanner: PASS across 158 curated files.
- Staged secret scan: no high-confidence credential match.
- Staged local-drive-path scan: no match.
- Forbidden staged file types: none.
- Files over 1 MiB: none.
- Staged inventory: 158 files, 1,440,695 bytes (approximately 1.37 MiB); about 858 KiB is five self-rendered PNG screenshots.
- Public repository visibility: `PUBLIC`; default branch: `main`.
- GitHub Actions portable checks: PASS (run `39387986178`).
- GitHub Pages deployment: PASS after workflow build mode was enabled (run `39387986218`).
- Pages HTTP smoke: index, JS, CSS and all five fixture files returned HTTP 200.

## Publication gate

The publication-authority gate passed on 2026-10-20 when the owner confirmed ownership or authorization to publicly display all 158 candidate files. Public creation may proceed after the final staged diff, tests and secret/asset scan pass. Third-party/data assets remain excluded unless they receive separate redistribution approval.

No project license is asserted. If the repository is made public after the rights confirmation, public visibility alone will not grant third parties permission to copy, modify or redistribute the code.
