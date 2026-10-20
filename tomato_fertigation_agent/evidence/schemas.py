from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from ..schemas.common import Confidence, Contract, Scope


class WorkflowName(str, Enum):
    GROWTH_STATUS = "growth_status"
    GROWTH_FORECAST = "growth_forecast"
    KNOWLEDGE_QA = "knowledge_qa"
    COMPREHENSIVE_DIAGNOSIS = "comprehensive_diagnosis"


class EvidenceType(str, Enum):
    OBSERVATION = "observation"
    SENSOR = "sensor"
    VISUAL_OBSERVATION = "visual_observation"
    PREDICTION = "prediction"
    HISTORICAL_CASE = "historical_case"
    KNOWLEDGE = "knowledge"
    RELIABILITY = "reliability"


class CompletenessStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


class ConflictStatus(str, Enum):
    AGREE = "AGREE"
    PARTIAL = "PARTIAL"
    DISAGREE = "DISAGREE"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class EvidenceRequirement(Contract):
    evidence_type: EvidenceType
    required: bool
    reason: str
    scope: Scope | None = None


class EvidencePlan(Contract):
    workflow: WorkflowName
    requirements: list[EvidenceRequirement]
    requested_scope: Scope | None = None
    entities: dict[str, Any] = Field(default_factory=dict)
    unsupported_subtasks: list[str] = Field(default_factory=list)
    planner_source: str = "provider"
    fallback_used: bool = False


class EvidenceRecord(Contract):
    evidence_id: str
    evidence_type: EvidenceType
    source_tool: str
    scope: Scope
    entity_id: str | None = None
    timestamp: str | None = None
    value: dict[str, Any] = Field(default_factory=dict)
    reliability: Confidence = Confidence.UNKNOWN
    limitations: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class EvidenceCompleteness(Contract):
    status: CompletenessStatus
    available: list[EvidenceType] = Field(default_factory=list)
    missing_required: list[EvidenceType] = Field(default_factory=list)
    missing_optional: list[EvidenceType] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class ConflictRecord(Contract):
    conflict_id: str
    conflict_type: str
    status: ConflictStatus
    evidence_ids: list[str] = Field(default_factory=list)
    scope: Scope | None = None
    model_value: float | None = None
    case_value: float | None = None
    absolute_difference: float | None = None
    impact: str = "NONE"
    explanation: str


class ReliabilityFactor(Contract):
    name: str
    level: Confidence
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)


class WorkflowReliability(Contract):
    level: Confidence
    factors: list[ReliabilityFactor] = Field(default_factory=list)
    statistically_calibrated: bool = False
    policy_version: str = "v1.3-rule-based"


class ProvenanceEdge(Contract):
    from_id: str
    to_id: str
    relation: str


class ProvenanceGraph(Contract):
    edges: list[ProvenanceEdge] = Field(default_factory=list)
    complete: bool = True
    missing_links: list[str] = Field(default_factory=list)
    evidence_collected_count: int = 0
    evidence_referenced_count: int = 0
    missing_evidence_reference_count: int = 0
    invalid_reference_count: int = 0
    semantic_mismatch_count: int = 0
