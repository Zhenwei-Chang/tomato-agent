# Security Policy

## Supported surface

This candidate supports the dependency-light Offline Replay path. Full local data/model adapters and online providers are optional and require explicit configuration.

## Reporting

Do not open a public issue containing API keys, local paths, source data, private traces or provider payloads. Use a private maintainer channel once the repository owner configures one.

## Credential handling

- Store provider keys in process environment variables or a credential file outside the repository.
- Never expose provider keys to browser JavaScript.
- Online execution is disabled unless the caller explicitly selects a provider and permits outbound local ToolResult data.
- Recorded Replay performs no provider call and sends no data.

## Data handling

Only the sanitized files under `demo/fixtures/` are intended for distribution. Do not attach original RGB, canonical tables, full Case Memory, RAG documents, private Holdout or raw traces to issues or releases.
