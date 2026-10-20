from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import Field

from ..diagnosis.schemas import Answerability
from ..evidence.schemas import EvidencePlan, WorkflowName
from ..schemas.agent import RequestContract, ToolCallRecord
from ..schemas.common import Contract


class WorkflowState(Contract):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_query: str
    workflow: WorkflowName | None = None
    evidence_plan: EvidencePlan | None = None
    entities: dict[str, Any] = Field(default_factory=dict)
    request_contract: RequestContract | None = None
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    nodes_executed: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    unsupported_subtasks: list[str] = Field(default_factory=list)
    unsupported_requests: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    answerability: Answerability | None = None
    llm_calls: int = 0
    planner_calls: int = 0
    router_calls: int = 0
    repair_calls: int = 0
    relevance_calls: int = 0
    synthesis_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_ms: float = 0.0
    safety_violations: list[str] = Field(default_factory=list)
    duplicate_tool_attempts: int = 0
    reused_tool_results: int = 0
    actual_tool_executions: int = 0
    required_tool_completion: bool = True
    provider_events: list[dict[str, Any]] = Field(default_factory=list)
    provider_errors: list[dict[str, Any]] = Field(default_factory=list)


class BaseWorkflow:
    name: WorkflowName

    def tool_names(self, plan: EvidencePlan) -> list[str]:
        raise NotImplementedError

    @staticmethod
    def is_view(plan: EvidencePlan) -> bool:
        return bool(plan.entities.get("view_id")) and plan.requested_scope and plan.requested_scope.value == "view"
