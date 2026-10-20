"""OpenAI Responses API adapter with bounded, traceable tool calling."""
from __future__ import annotations

from time import perf_counter
from typing import Any, Callable
import json
import os
import re

from pydantic import BaseModel, ValidationError

from .base import (ProviderResponse, ProviderToolCall, ProviderUsage,
                   ToolExecutionResult, ToolLoopResponse)
from .errors import ProviderError, ProviderErrorCode
from .openai_schemas import to_domain_value, transport_model
from ..schemas.agent import PlannedToolCall, ToolPlan


class OpenAIProvider:
    name = "openai"
    api = "responses"

    def __init__(self, model: str, temperature: float | None = None,
                 api_key: str | None = None, base_url: str | None = None,
                 timeout_seconds: float = 45.0, max_retries: int = 2,
                 max_output_tokens: int = 4096, store: bool = False,
                 max_total_calls: int | None = None,
                 allow_external_tool_data: bool = False, client=None):
        if not str(model or "").strip():
            raise ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE,
                                "An OpenAI model must be configured")
        self.model = str(model).strip()
        self.temperature = temperature
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = int(max_retries)
        self.max_output_tokens = int(max_output_tokens)
        self.store = bool(store)
        self.max_total_calls = max_total_calls
        self.allow_external_tool_data = bool(allow_external_tool_data)
        self.total_api_calls = 0
        if client is not None:
            self.client = client
            return
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ProviderError(ProviderErrorCode.MISSING_CREDENTIALS,
                                "OPENAI_API_KEY is required for online execution")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE,
                                "The optional openai dependency is not installed") from exc
        self.client = OpenAI(api_key=key,
            base_url=base_url or os.getenv("OPENAI_BASE_URL") or None,
            timeout=self.timeout_seconds, max_retries=self.max_retries)

    def _reserve_call(self) -> None:
        if self.max_total_calls is not None and self.total_api_calls >= self.max_total_calls:
            raise ProviderError(ProviderErrorCode.PROVIDER_BUDGET_EXCEEDED,
                                "Online API call budget exhausted",
                                max_total_calls=self.max_total_calls)
        self.total_api_calls += 1

    @staticmethod
    def _usage(response) -> ProviderUsage:
        usage = getattr(response, "usage", None)
        input_details = getattr(usage, "input_tokens_details", None)
        output_details = getattr(usage, "output_tokens_details", None)
        return ProviderUsage(
            int(getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", 0)) or 0),
            int(getattr(usage, "output_tokens", getattr(usage, "completion_tokens", 0)) or 0),
            int(getattr(input_details, "cached_tokens", 0) or 0),
            int(getattr(output_details, "reasoning_tokens", 0) or 0),
        )

    @staticmethod
    def _metadata(response) -> dict[str, Any]:
        incomplete = getattr(response, "incomplete_details", None)
        return {
            "response_id": getattr(response, "id", None),
            "response_model": getattr(response, "model", None),
            "status": str(getattr(response, "status", "completed") or "completed"),
            "incomplete_reason": getattr(incomplete, "reason", None),
        }

    @staticmethod
    def _refusal(response) -> str | None:
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                if getattr(content, "type", None) == "refusal":
                    return str(getattr(content, "refusal", "Model refused the request"))
        return None

    def _check_response(self, response) -> None:
        refusal = self._refusal(response)
        if refusal:
            raise ProviderError(ProviderErrorCode.PROVIDER_REFUSAL,
                "The provider refused the request", refusal=refusal,
                response_id=getattr(response, "id", None))
        status = str(getattr(response, "status", "completed") or "completed")
        if status != "completed":
            details = getattr(response, "incomplete_details", None)
            raise ProviderError(ProviderErrorCode.PROVIDER_INCOMPLETE,
                f"Provider response status is {status}",
                reason=getattr(details, "reason", None),
                response_id=getattr(response, "id", None))

    @staticmethod
    def _temperature_kwargs(value: float | None) -> dict[str, Any]:
        return {} if value is None else {"temperature": value}

    def _map_exception(self, exc: Exception) -> ProviderError:
        if isinstance(exc, ProviderError):
            return exc
        name = type(exc).__name__
        status = getattr(exc, "status_code", None)
        message = str(exc).lower()
        if name in {"APITimeoutError", "TimeoutException", "ReadTimeout", "ConnectTimeout"}:
            code = ProviderErrorCode.PROVIDER_TIMEOUT
        elif name == "RateLimitError":
            code = ProviderErrorCode.PROVIDER_RATE_LIMIT
        elif name in {"AuthenticationError", "PermissionDeniedError"} or status in {401, 403}:
            code = ProviderErrorCode.AUTH_FAILED
        elif status == 402 or "insufficient balance" in message or "insufficient_balance" in message:
            code = ProviderErrorCode.INSUFFICIENT_BALANCE
        elif name == "NotFoundError" or status == 404 or "model not found" in message:
            code = ProviderErrorCode.MODEL_NOT_FOUND
        elif name in {"APIConnectionError", "InternalServerError", "ServiceUnavailableError"}:
            code = ProviderErrorCode.NETWORK_ERROR
        else:
            code = ProviderErrorCode.PROVIDER_UNAVAILABLE
        body = getattr(exc, "body", None)
        reason = None
        if isinstance(body, dict):
            detail = body.get("error", body)
            if isinstance(detail, dict):
                reason = detail.get("message")
        if reason is None and status is not None:
            reason = str(exc)
        if reason:
            reason = re.sub(r"sk-[A-Za-z0-9_-]+", "***REDACTED***", str(reason))[:500]
        return ProviderError(code, f"{self.name} Responses API request failed",
                             exception_type=name, status_code=status,
                             provider_reason=reason)

    def _sanitize_request_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Provider compatibility hook; the OpenAI implementation is unchanged."""
        return kwargs

    def _parse(self, **kwargs):
        self._reserve_call()
        try:
            return self.client.responses.parse(**self._sanitize_request_kwargs(kwargs))
        except Exception as exc:
            raise self._map_exception(exc) from exc

    def _create(self, **kwargs):
        self._reserve_call()
        try:
            return self.client.responses.create(**self._sanitize_request_kwargs(kwargs))
        except Exception as exc:
            raise self._map_exception(exc) from exc

    def structured_completion(self, *, purpose, system_prompt, payload, response_model):
        started = perf_counter()
        output_model = transport_model(purpose, response_model, provider_name=self.name)
        response = self._parse(model=self.model, instructions=system_prompt,
            input=json.dumps(payload, ensure_ascii=False, default=str),
            text_format=output_model, max_output_tokens=self.max_output_tokens,
            store=self.store, timeout=self.timeout_seconds,
            **self._temperature_kwargs(self.temperature))
        self._check_response(response)
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ProviderError(ProviderErrorCode.PROVIDER_FORMAT_ERROR,
                f"Structured response for {purpose} had no parsed payload",
                response_id=getattr(response, "id", None))
        try:
            value = to_domain_value(purpose, parsed, response_model, payload,
                                    provider_name=self.name)
        except (ValidationError, ValueError) as exc:
            raise ProviderError(ProviderErrorCode.PROVIDER_FORMAT_ERROR,
                f"Structured response for {purpose} failed validation",
                issue_count=len(exc.errors()) if isinstance(exc, ValidationError) else 1) from exc
        metadata = self._metadata(response)
        return ProviderResponse(value=value, usage=self._usage(response),
            latency_ms=(perf_counter() - started) * 1000,
            refusal=self._refusal(response), provider_calls=1, **metadata)

    def tool_completion(self, *, system_prompt, user_query, route, tools, response_model):
        """Compatibility single-round function selection for the V1.1 agent."""
        started = perf_counter()
        response = self._create(model=self.model, instructions=system_prompt,
            input=user_query, tools=self._responses_tools(tools), tool_choice="auto",
            parallel_tool_calls=True, max_output_tokens=self.max_output_tokens,
            store=self.store, timeout=self.timeout_seconds,
            **self._temperature_kwargs(self.temperature))
        self._check_response(response)
        calls = []
        for item in self._function_calls(response):
            try:
                arguments = json.loads(item.arguments)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ProviderError(ProviderErrorCode.PROVIDER_FORMAT_ERROR,
                    "Function arguments were not valid JSON",
                    call_id=getattr(item, "call_id", None)) from exc
            calls.append(PlannedToolCall(tool_name=item.name, arguments=arguments))
        value = response_model.model_validate(ToolPlan(calls=calls))
        metadata = self._metadata(response)
        return ProviderResponse(value=value, usage=self._usage(response),
            latency_ms=(perf_counter() - started) * 1000, provider_calls=1,
            refusal=self._refusal(response), **metadata)

    def execute_tool_loop(self, *, system_prompt: str, user_query: str,
                          tools: list[dict[str, Any]],
                          execute: Callable[[str, dict[str, Any] | None, str], Any],
                          max_tool_calls: int, max_provider_calls: int,
                          max_argument_repairs: int = 2) -> ToolLoopResponse:
        """Run a bounded Responses function-calling loop with exact call-id pairing."""
        started = perf_counter()
        allowed = {tool["name"] for tool in tools}
        calls: list[ProviderToolCall] = []
        usage = ProviderUsage()
        response_ids: list[str] = []
        response_models: list[str] = []
        statuses: list[str] = []
        provider_calls = 0
        invalid_arguments: dict[str, int] = {}
        actual_executions = 0
        duplicate_attempts = 0
        # Stateless Responses mode: replay every output item (including
        # reasoning items) plus matching function_call_output items.
        history_input: list[Any] = [{"role": "user", "content": user_query}]
        while provider_calls < max_provider_calls:
            kwargs = dict(model=self.model, instructions=system_prompt,
                input=history_input, tools=tools, tool_choice="auto",
                parallel_tool_calls=True, max_output_tokens=self.max_output_tokens,
                store=self.store, timeout=self.timeout_seconds,
                **self._temperature_kwargs(self.temperature))
            response = self._create(**kwargs)
            provider_calls += 1
            self._check_response(response)
            usage = usage + self._usage(response)
            metadata = self._metadata(response)
            if metadata["response_id"]:
                response_ids.append(metadata["response_id"])
            if metadata["response_model"]:
                response_models.append(metadata["response_model"])
            statuses.append(metadata["status"])
            function_calls = self._function_calls(response)
            if not function_calls:
                return ToolLoopResponse(calls=calls, usage=usage,
                    latency_ms=(perf_counter() - started) * 1000,
                    provider_calls=provider_calls, response_ids=response_ids,
                    response_models=response_models, statuses=statuses,
                    final_text=str(getattr(response, "output_text", "") or ""),
                    stop_reason="completed")
            history_input.extend(getattr(response, "output", []) or [])
            outputs = []
            for item in function_calls:
                if actual_executions >= max_tool_calls:
                    raise ProviderError(ProviderErrorCode.PROVIDER_BUDGET_EXCEEDED,
                        "Actual tool-execution budget exhausted", max_tool_calls=max_tool_calls)
                name, call_id = str(item.name), str(item.call_id)
                executed, reused = False, False
                if name not in allowed:
                    arguments = None
                    result = {"status": "error", "error": {
                        "code": "INVALID_ARGUMENT", "message": "Tool is not allowed in this workflow"}}
                else:
                    try:
                        arguments = json.loads(item.arguments)
                        if not isinstance(arguments, dict):
                            raise TypeError("Function arguments must be an object")
                    except (TypeError, json.JSONDecodeError):
                        arguments = None
                    callback_result = execute(name, arguments, call_id)
                    if isinstance(callback_result, ToolExecutionResult):
                        result = callback_result.result
                        executed = callback_result.executed
                        reused = callback_result.reused
                    else:
                        result = callback_result
                        executed = True
                        reused = False
                    if executed:
                        actual_executions += 1
                    if reused:
                        duplicate_attempts += 1
                        if duplicate_attempts > max(2, max_argument_repairs + 1):
                            raise ProviderError(ProviderErrorCode.PROVIDER_FORMAT_ERROR,
                                "Duplicate tool-call retry budget exhausted",
                                duplicate_attempts=duplicate_attempts)
                error = getattr(result, 'error', None)
                code = getattr(getattr(error, 'code', None), 'value', getattr(error, 'code', None))
                if code == 'INVALID_ARGUMENT':
                    invalid_arguments[name] = invalid_arguments.get(name, 0) + 1
                    if invalid_arguments[name] > max_argument_repairs + 1:
                        raise ProviderError(ProviderErrorCode.PROVIDER_FORMAT_ERROR,
                            "Argument repair budget exhausted", tool_name=name,
                            max_argument_repairs=max_argument_repairs)
                calls.append(ProviderToolCall(call_id=call_id, tool_name=name,
                    arguments=arguments, result=result, response_id=metadata["response_id"],
                    executed=executed, reused=reused))
                rendered = result.model_dump_json() if isinstance(result, BaseModel) else json.dumps(
                    result, ensure_ascii=False, default=str)
                outputs.append({"type": "function_call_output", "call_id": call_id,
                                "output": rendered})
            history_input.extend(outputs)
        raise ProviderError(ProviderErrorCode.PROVIDER_BUDGET_EXCEEDED,
            "Provider-call budget exhausted before a final response",
            max_provider_calls=max_provider_calls)

    @staticmethod
    def _function_calls(response) -> list[Any]:
        return [item for item in (getattr(response, "output", []) or [])
                if getattr(item, "type", None) == "function_call"]

    @staticmethod
    def _responses_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted = []
        for tool in tools:
            if "function" in tool:
                function = tool["function"]
                converted.append({"type": "function", "name": function["name"],
                    "description": function.get("description", ""),
                    "parameters": function.get("parameters", {"type": "object", "properties": {}}),
                    "strict": bool(function.get("strict", True))})
            else:
                converted.append(tool)
        return converted
