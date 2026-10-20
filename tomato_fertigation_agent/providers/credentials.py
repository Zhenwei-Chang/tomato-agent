"""Credential discovery that never copies or logs provider secrets."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Mapping


DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_DEFAULT_MODEL = "deepseek-flash"
_LEGACY_MODELS = {
    "deepseek-v4-flash": DEEPSEEK_DEFAULT_MODEL,
    "deepseek-v4-flash-vision-exp": DEEPSEEK_DEFAULT_MODEL,
}
_ALLOWED_KEYS = {
    "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL",
}


@dataclass(frozen=True)
class ResolvedCredential:
    api_key: str = field(repr=False)
    base_url: str
    model: str
    source: str
    configured: bool
    legacy_model: str | None = None

    def safe_summary(self) -> dict[str, str | bool | None]:
        return {
            "credential": "PRESENT" if self.configured else "MISSING",
            "base_url": self.base_url,
            "model": self.model,
            "source": self.source,
            "legacy_model_normalized_from": self.legacy_model,
        }


def _read_allowed_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in _ALLOWED_KEYS:
            values[key] = value.strip().strip('"').strip("'")
    return values


def canonical_deepseek_model(model: str | None) -> tuple[str, str | None]:
    candidate = str(model or DEEPSEEK_DEFAULT_MODEL).strip() or DEEPSEEK_DEFAULT_MODEL
    canonical = _LEGACY_MODELS.get(candidate, candidate)
    return canonical, candidate if canonical != candidate else None


def resolve_deepseek_credential(*, credential_file: str | Path | None = None,
                                env: Mapping[str, str] | None = None) -> ResolvedCredential:
    """Resolve process settings first, then the explicit legacy file.

    The file is read in place. Its secret is never copied to the Agent project and
    the returned dataclass suppresses the key from its repr.
    """
    values = dict(os.environ if env is None else env)
    path_value = values.get("DEEPSEEK_ENV_FILE") or credential_file
    file_values: dict[str, str] = {}
    source = "process_environment"
    if path_value:
        path = Path(path_value).expanduser().resolve()
        file_values = _read_allowed_env_file(path)
        if file_values:
            # Record the source class, never the workstation path. The path can
            # identify a user even when the credential value is redacted.
            source = "controlled_file"
    key = values.get("DEEPSEEK_API_KEY") or file_values.get("DEEPSEEK_API_KEY", "")
    base_url = (values.get("DEEPSEEK_BASE_URL") or
                file_values.get("DEEPSEEK_BASE_URL") or DEEPSEEK_DEFAULT_BASE_URL).rstrip("/")
    raw_model = values.get("DEEPSEEK_MODEL") or file_values.get("DEEPSEEK_MODEL")
    model, legacy = canonical_deepseek_model(raw_model)
    if values.get("DEEPSEEK_API_KEY"):
        source = "process_environment"
    elif not key:
        source = "not_configured"
    return ResolvedCredential(api_key=key, base_url=base_url, model=model,
                              source=source, configured=bool(key),
                              legacy_model=legacy)


def redact_secrets(value):
    """Recursively redact common secret fields before diagnostic serialization."""
    if isinstance(value, dict):
        secret_names = {"API_KEY", "AUTHORIZATION", "PASSWORD", "SECRET",
                        "ACCESS_TOKEN", "REFRESH_TOKEN", "BEARER_TOKEN"}
        return {key: ("***REDACTED***" if (key.upper() in secret_names or
                key.upper().endswith(("_API_KEY", "_PASSWORD", "_SECRET")))
                else redact_secrets(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value
