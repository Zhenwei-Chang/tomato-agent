from typing import Any, Literal
from pydantic import Field
from .agent import Intent
from .common import Contract


class AgentEvalCase(Contract):
    case_id: str
    query: str
    expected_intent: Intent
    expected_tools: list[str]
    expected_arguments: dict[str, Any] = Field(default_factory=dict)
    expected_behavior: Literal['success', 'data_not_found', 'no_reliable_cases', 'unsupported', 'evidence_insufficient']
    forbidden_behaviors: list[str] = Field(default_factory=list)
    expected_evidence_ids: list[str] | None = None
    expected_evidence_sufficiency: str | None = None
    difficulty: Literal['easy', 'medium', 'hard']
    golden: bool = False
    notes: str = ''


class CaseResult(Contract):
    case_id: str
    intent: str
    difficulty: str
    checks: dict[str, bool]
    metrics: dict[str, float | int | bool | None]
    failures: list[str] = Field(default_factory=list)
    actual: dict[str, Any] = Field(default_factory=dict)
    passed: bool


class WorkflowEvalCase(Contract):
    case_id: str
    query: str
    expected_workflow: str
    expected_required_evidence: list[str]
    expected_available_evidence: list[str]
    expected_tools: list[str]
    expected_answerability: Literal['FULL', 'PARTIAL', 'ABSTAIN']
    expected_conflict: Literal['AGREE', 'PARTIAL', 'DISAGREE', 'NOT_AVAILABLE'] = 'NOT_AVAILABLE'
    expected_unsupported: bool = False
    difficulty: Literal['easy', 'medium', 'hard']
    golden: bool = False
    notes: str = ''


class WorkflowCaseResult(Contract):
    case_id: str
    workflow: str
    difficulty: str
    checks: dict[str, bool]
    scores: dict[str, float]
    metrics: dict[str, float | int | bool | None]
    failures: list[str] = Field(default_factory=list)
    actual: dict[str, Any] = Field(default_factory=dict)
    passed: bool


class OnlineEvalCase(Contract):
    case_id: str
    mode: Literal['atomic', 'workflow']
    query: str
    expected_intent: Intent | None = None
    expected_workflow: str | None = None
    expected_tools: list[str]
    expected_arguments: dict[str, dict[str, Any]] = Field(default_factory=dict)
    expected_answerability: Literal['FULL', 'PARTIAL', 'ABSTAIN'] | None = None
    expected_behavior: Literal['success', 'partial', 'unsupported', 'data_not_found']
    expected_scope: str | None = None
    forbidden_behaviors: list[str] = Field(default_factory=list)
    category: str
    difficulty: Literal['easy', 'medium', 'hard']
    human_review_required: bool = False
    frozen: bool = True
    notes: str = ''


class OnlineCaseResult(Contract):
    case_id: str
    mode: str
    category: str
    difficulty: str
    checks: dict[str, bool]
    scores: dict[str, float]
    metrics: dict[str, float | int | bool | None]
    failures: list[str] = Field(default_factory=list)
    actual: dict[str, Any] = Field(default_factory=dict)
    passed: bool
