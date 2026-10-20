# Public Release Manifest

This repository candidate was created from an explicit allowlist. It is not a copy of the research workspace.

## Included

- `tomato_fertigation_agent/`: Python source and prompt templates only.
- `demo/`: zero-dependency UI, five sanitized Recorded Replay fixtures, scenario notes and smoke transcript.
- `docs/portfolio/screenshots/`: five browser-rendered screenshots of that same sanitized static Demo.
- `configs/`: example Agent, workflow and case-retrieval configuration with no credential path.
- `docs/architecture/`, `docs/evaluation/`, `docs/portfolio/`: curated public documentation.
- `tests/unit/test_portfolio_demo.py`: portable Replay contract tests.
- `scripts/portfolio_release_check.py`: read-only candidate scanner.
- README, package metadata, environment example and ignore rules.
- GitHub Actions workflows for offline CI and Demo-only Pages deployment.

## Explicitly excluded

- Original tomato dataset and RGB images.
- Canonical research tables and full Historical Case Memory.
- Image embeddings and model checkpoints/weights.
- RAG PDFs, webpage snapshots, indexes and document text.
- Raw Agent traces, provider responses and local evaluation outputs.
- The independent 48-case online holdout.
- `.env` files, API keys and workstation credential paths.
- Sibling research applications and their build/runtime artifacts.

## Reconstructing optional local capabilities

The full Local Agent can be connected to separately obtained, authorized assets through environment variables and sibling adapters. Those assets are not fetched automatically and are not prerequisites for Offline Replay.

## License state

No project license is asserted. Third-party package licenses do not grant a license for this project's own source or for the research data that informed it. Public release requires an explicit owner confirmation that the tracked source and sanitized fixtures may be publicly displayed. A separate reuse license is optional and must never be inferred from public visibility.
