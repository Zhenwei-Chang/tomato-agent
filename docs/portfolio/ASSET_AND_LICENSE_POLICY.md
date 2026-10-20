# Asset & License Policy

## Included in the portfolio

- Source code written for the Agent project.
- Markdown documentation and Mermaid diagrams.
- Small sanitized JSON replay fixtures derived from authorized development runs.
- Aggregated benchmark metrics and sanitized trace summaries.
- Five screenshots rendered from the repository's own static replay Demo. They contain only the same sanitized fixture content already included in the repository.

## Excluded by default

- Original 26 GB tomato dataset and RGB images.
- Full canonical tables and historical case memory.
- 512D embedding arrays.
- RAG document PDFs or webpage snapshots.
- Raw provider payloads and unsanitized traces.
- API credentials, `.env` files and credential-file paths.
- Model/checkpoint files until their training-data and redistribution boundaries are reviewed.

## Third-party components

| Component | Upstream position | Release treatment |
|---|---|---|
| Pydantic | MIT | Dependency only; retain upstream notices when required |
| scikit-learn | BSD-3-Clause | Dependency only; do not relicense it |
| PyTorch | BSD-style with bundled third-party notices | Optional dependency; use upstream packages |
| torchvision | BSD-3-Clause code | Optional dependency; do not bundle source |
| ImageNet-pretrained ResNet18 weights | TorchVision warns of dataset-derived terms | Do not bundle by default |
| DeepSeek API | Governed by Open Platform Terms | User supplies key and authorizes outbound inputs |

Official references: [Pydantic metadata](https://github.com/pydantic/pydantic/blob/main/pyproject.toml), [scikit-learn COPYING](https://github.com/scikit-learn/scikit-learn/blob/main/COPYING), [PyTorch README](https://github.com/pytorch/pytorch/blob/main/README.md), [TorchVision models](https://docs.pytorch.org/vision/master/models.html), [DeepSeek API](https://api-docs.deepseek.com/api/deepseek-api/).

## Project license status

No project `LICENSE` is added because the owner has not yet selected one and the repository mixes adapters, research-derived artifacts and third-party data lineage. Public visibility without a license does not grant reuse rights. Before publication, the owner must confirm that they have authority to publish the tracked source and sanitized fixtures. A future code license may be added only after a separate, explicit licensing decision.
