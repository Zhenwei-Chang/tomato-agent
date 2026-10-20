from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
from pydantic import BaseModel


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0

    def __add__(self, other: "ProviderUsage") -> "ProviderUsage":
        return ProviderUsage(self.input_tokens + other.input_tokens,
                             self.output_tokens + other.output_tokens,
                             self.cached_input_tokens + other.cached_input_tokens,
                             self.reasoning_tokens + other.reasoning_tokens)


@dataclass(frozen=True)
class ProviderResponse:
    value: BaseModel
    usage: ProviderUsage
    latency_ms: float
    response_id: str | None = None
    response_model: str | None = None
    status: str = "completed"
    refusal: str | None = None
    incomplete_reason: str | None = None
    provider_calls: int = 1


@dataclass(frozen=True)
class ProviderToolCall:
    call_id: str
    tool_name: str
    arguments: dict[str, Any] | None
    result: Any
    response_id: str | None = None
    executed: bool = True
    reused: bool = False


@dataclass(frozen=True)
class ToolExecutionResult:
    """Internal callback envelope; the provider still sends only ``result``."""
    result: Any
    executed: bool = True
    reused: bool = False


@dataclass(frozen=True)
class ToolLoopResponse:
    calls: list[ProviderToolCall] = field(default_factory=list)
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    latency_ms: float = 0.0
    provider_calls: int = 0
    response_ids: list[str] = field(default_factory=list)
    response_models: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    final_text: str = ""
    stop_reason: str = "completed"


class LLMProvider(Protocol):
    name: str
    model: str

    def structured_completion(self, *, purpose: str, system_prompt: str,
                              payload: dict[str, Any], response_model: type[BaseModel]) -> ProviderResponse: ...

    def tool_completion(self, *, system_prompt: str, user_query: str,
                        route: BaseModel, tools: list[dict[str, Any]],
                        response_model: type[BaseModel]) -> ProviderResponse: ...

    def execute_tool_loop(self, *, system_prompt: str, user_query: str,
                          tools: list[dict[str, Any]],
                          execute: Callable[[str, dict[str, Any] | None, str], Any],
                          max_tool_calls: int, max_provider_calls: int,
                          max_argument_repairs: int = 2) -> ToolLoopResponse: ...
