"""DeepSeek Responses API compatibility adapter."""
from __future__ import annotations

from time import perf_counter
from typing import Any

from .base import ProviderUsage
from .errors import ProviderError, ProviderErrorCode
from .openai_provider import OpenAIProvider


class DeepSeekProvider(OpenAIProvider):
    """Reuse the bounded Responses loop while removing unsupported parameters."""

    name = "deepseek"
    api = "responses"

    def __init__(self, model: str, *, api_key: str | None = None,
                 base_url: str = "https://api.deepseek.com",
                 reasoning_effort: str | None = "none", **kwargs):
        if not api_key:
            raise ProviderError(ProviderErrorCode.MISSING_CREDENTIALS,
                                "DEEPSEEK_API_KEY is required for online execution")
        self.reasoning_effort = reasoning_effort
        super().__init__(model=model, api_key=api_key, base_url=base_url, **kwargs)

    def _sanitize_request_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        cleaned = dict(kwargs)
        # DeepSeek Responses is stateless. These options are unsupported or
        # ignored server-side, so omit them and enforce budgets in the app.
        cleaned.pop("store", None)
        cleaned.pop("parallel_tool_calls", None)
        cleaned.pop("previous_response_id", None)
        cleaned.pop("max_tool_calls", None)
        if self.reasoning_effort:
            cleaned["reasoning"] = {"effort": self.reasoning_effort}
        return cleaned

    def connectivity_check(self) -> dict[str, Any]:
        """One bounded, non-tool call used only by explicit online validation."""
        started = perf_counter()
        response = self._create(model=self.model,
            instructions="Return exactly the word OK.", input="Connectivity check.",
            max_output_tokens=16, timeout=self.timeout_seconds, store=False)
        self._check_response(response)
        usage: ProviderUsage = self._usage(response)
        metadata = self._metadata(response)
        return {
            "status": "SUCCESS",
            "provider": self.name,
            "api": self.api,
            "endpoint": "/responses",
            "model_requested": self.model,
            "model_returned": metadata["response_model"],
            "response_id_present": bool(metadata["response_id"]),
            "response_status": metadata["status"],
            "output_parseable": bool(str(getattr(response, "output_text", "") or "").strip()),
            "usage": {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cached_input_tokens": usage.cached_input_tokens,
                "reasoning_tokens": usage.reasoning_tokens,
            },
            "latency_ms": (perf_counter() - started) * 1000,
        }
