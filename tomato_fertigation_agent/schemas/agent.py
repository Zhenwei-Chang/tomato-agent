from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4
from pydantic import Field
from .common import Confidence, Contract, EvidenceItem, Scope


class Intent(str, Enum):
    DATA_QUERY = 'DATA_QUERY'
    SENSOR_QUERY = 'SENSOR_QUERY'
    TREATMENT_QUERY = 'TREATMENT_QUERY'
    GROWTH_PREDICTION = 'GROWTH_PREDICTION'
    RGB_ANALYSIS = 'RGB_ANALYSIS'
    KNOWLEDGE_QA = 'KNOWLEDGE_QA'
    SIMILAR_CASE_QUERY = 'SIMILAR_CASE_QUERY'
    COMPREHENSIVE_ANALYSIS = 'COMPREHENSIVE_ANALYSIS'
    UNSUPPORTED_REQUEST = 'UNSUPPORTED_REQUEST'


class EvidenceSufficiency(str, Enum):
    SUFFICIENT = 'SUFFICIENT'
    PARTIAL = 'PARTIAL'
    INSUFFICIENT = 'INSUFFICIENT'
    NOT_APPLICABLE = 'NOT_APPLICABLE'


class RelevanceLabel(str, Enum):
    RELEVANT = 'RELEVANT'
    PARTIALLY_RELEVANT = 'PARTIALLY_RELEVANT'
    IRRELEVANT = 'IRRELEVANT'


class RequestSubtaskSource(str, Enum):
    EXPLICIT_USER = 'EXPLICIT_USER'
    REQUIRED_BY_TASK_POLICY = 'REQUIRED_BY_TASK_POLICY'
    OPTIONAL_ASSISTANT = 'OPTIONAL_ASSISTANT'


class RequestSubtask(Contract):
    subtask_id: str
    description: str
    source: RequestSubtaskSource
    required: bool
    requested_scope: Scope | None = None
    expected_result_type: str
    required_tools: list[str] = Field(default_factory=list)


class RequestContract(Contract):
    version: str = 'v1.4.5'
    original_query: str
    intent: Intent
    entities: dict[str, Any] = Field(default_factory=dict)
    subtasks: list[RequestSubtask] = Field(default_factory=list)

    @property
    def required_user_subtasks(self) -> list[RequestSubtask]:
        return [row for row in self.subtasks
                if row.required and row.source == RequestSubtaskSource.EXPLICIT_USER]

    @property
    def required_policy_subtasks(self) -> list[RequestSubtask]:
        return [row for row in self.subtasks
                if row.required and row.source == RequestSubtaskSource.REQUIRED_BY_TASK_POLICY]


class RouterDecision(Contract):
    intent: Intent
    requested_scope: Scope | None = None
    entities: dict[str, Any] = Field(default_factory=dict)
    required_tools: list[str] = Field(default_factory=list)
    unsupported_requests: list[str] = Field(default_factory=list)
    reasoning_code: str = 'ROUTED'


class PlannedToolCall(Contract):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolPlan(Contract):
    calls: list[PlannedToolCall] = Field(default_factory=list)


class ToolPlanRepair(Contract):
    required_tools: list[str] = Field(default_factory=list)
    reasoning_code: str = 'TOOL_PLAN_REPAIRED'


class RelevanceJudgment(Contract):
    label: RelevanceLabel
    reason: str


class FactItem(Contract):
    name: str
    value: Any
    unit: str | None = None
    scope: Scope
    source_tool: str
    evidence_ids: list[str] = Field(default_factory=list)
    observed: bool = True


class PredictionItem(Contract):
    name: str
    value: float
    unit: str
    scope: Scope
    horizon_days: int | None = None
    source_tool: str
    model_version: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class GroundedStatement(Contract):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    category: Literal['interpretation', 'general_management_consideration']


class HistoricalCaseEvidence(Contract):
    case_id: str
    scope: Scope
    similarity: float = Field(ge=0, le=1)
    case_date: str
    outcome_date: str
    historical_outcome: dict[str, float]
    domain_warning: bool = False
    evidence_id: str
    query_timestamp: str | None = None
    retrieval_mode: str | None = None
    retrieval_confidence: Confidence = Confidence.UNKNOWN
    source_tool_call_id: str | None = None


class ToolCallRecord(Contract):
    call_index: int
    tool_name: str
    initial_arguments: dict[str, Any]
    final_arguments: dict[str, Any] | None = None
    argument_valid_first_try: bool = False
    repair_count: int = 0
    final_argument_valid: bool = False
    duplicate_blocked: bool = False
    reused_result: bool = False
    actual_execution: bool = True
    cached_from_tool_call_id: str | None = None
    result_status: str | None = None
    error_code: str | None = None
    tool_call_id: str | None = None
    provider_call_id: str | None = None
    dispatch_source: Literal['MODEL_GENERATED_TOOL_CALL',
                             'WORKFLOW_DISPATCHED_TOOL',
                             'DETERMINISTIC_FALLBACK'] = 'WORKFLOW_DISPATCHED_TOOL'
    result_summary: dict[str, Any] = Field(default_factory=dict)


class AggregatedEvidence(Contract):
    facts: list[FactItem] = Field(default_factory=list)
    predictions: list[PredictionItem] = Field(default_factory=list)
    knowledge_evidence: list[EvidenceItem] = Field(default_factory=list)
    historical_case_evidence: list[EvidenceItem] = Field(default_factory=list)
    evidence_registry: list[EvidenceItem] = Field(default_factory=list)
    reliability_evidence_ids: list[str] = Field(default_factory=list)
    historical_cases: list[HistoricalCaseEvidence] = Field(default_factory=list)
    case_prediction_height_t7_cm: float | None = None
    case_model_agreement: Literal['AGREE','PARTIAL','DISAGREE','NOT_AVAILABLE'] = 'NOT_AVAILABLE'
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    unsupported_requests: list[str] = Field(default_factory=list)
    evidence_sufficiency: EvidenceSufficiency = EvidenceSufficiency.NOT_APPLICABLE
    confidence: Confidence = Confidence.UNKNOWN


class AgentAnswer(Contract):
    answer_type: str
    status: Literal['success', 'partial', 'unsupported', 'error']
    summary: str
    current_state: dict[str, Any] | None = None
    facts: list[FactItem] = Field(default_factory=list)
    predictions: list[PredictionItem] = Field(default_factory=list)
    agronomic_interpretation: list[GroundedStatement] = Field(default_factory=list)
    recommendations: list[GroundedStatement] = Field(default_factory=list)
    confidence: Confidence = Confidence.UNKNOWN
    evidence_sufficiency: EvidenceSufficiency = EvidenceSufficiency.NOT_APPLICABLE
    evidence: list[EvidenceItem] = Field(default_factory=list)
    historical_cases: list[HistoricalCaseEvidence] = Field(default_factory=list)
    case_prediction_height_t7_cm: float | None = None
    case_model_agreement: Literal['AGREE','PARTIAL','DISAGREE','NOT_AVAILABLE'] = 'NOT_AVAILABLE'
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    unsupported_requests: list[str] = Field(default_factory=list)


class AgentState(Contract):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_query: str
    intent: Intent | None = None
    entities: dict[str, Any] = Field(default_factory=dict)
    requested_scope: Scope | None = None
    request_contract: RequestContract | None = None
    planned_tools: list[str] = Field(default_factory=list)
    canonical_tool_names: list[str] = Field(default_factory=list)
    tool_plan_valid_before_repair: bool = True
    tool_plan_repair_attempted: bool = False
    tool_plan_repair_success: bool = False
    tool_plan_repair_count: int = 0
    invalid_tool_names: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    facts: list[FactItem] = Field(default_factory=list)
    predictions: list[PredictionItem] = Field(default_factory=list)
    knowledge_evidence_ids: list[str] = Field(default_factory=list)
    historical_case_ids: list[str] = Field(default_factory=list)
    case_model_agreement: Literal['AGREE','PARTIAL','DISAGREE','NOT_AVAILABLE'] = 'NOT_AVAILABLE'
    evidence_sufficiency: EvidenceSufficiency = EvidenceSufficiency.NOT_APPLICABLE
    reliability: Confidence | None = None
    warnings: list[str] = Field(default_factory=list)
    unsupported_requests: list[str] = Field(default_factory=list)
    final_structured_answer: AgentAnswer | None = None
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_ms: float = 0.0
    safety_violations: list[str] = Field(default_factory=list)
    evidence_collected_count: int = 0
    evidence_referenced_count: int = 0
    missing_evidence_references: int = 0
    invalid_evidence_references: int = 0
    semantic_evidence_mismatches: int = 0
    duplicate_tool_attempts: int = 0
    reused_tool_results: int = 0
    actual_tool_executions: int = 0
    required_tool_completion: bool = True
    provider_events: list[dict[str, Any]] = Field(default_factory=list)
    provider_errors: list[dict[str, Any]] = Field(default_factory=list)


class AgentRun(Contract):
    state: AgentState
    answer: AgentAnswer
    rendered: str
    provider: dict[str, Any]
    debug: dict[str, Any] | None = None
