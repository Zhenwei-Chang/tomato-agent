from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from ..evidence.schemas import (ConflictRecord, EvidenceCompleteness, EvidencePlan,
                                EvidenceRecord, ProvenanceGraph,
                                WorkflowReliability)
from ..schemas.common import Confidence, Contract


class Answerability(str, Enum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    ABSTAIN = "ABSTAIN"


class ClaimType(str, Enum):
    OBSERVATION = "observation"
    PREDICTION = "prediction"
    HISTORICAL_INTERPRETATION = "historical_interpretation"
    KNOWLEDGE = "knowledge"
    RECOMMENDATION = "recommendation"
    LIMITATION = "limitation"


class ManagementLevel(str, Enum):
    MONITOR = "MONITOR"
    CONSIDER = "CONSIDER"
    NOT_SUPPORTED = "NOT_SUPPORTED"


class UnsupportedSubtask(Contract):
    request: str
    reason: str


class Claim(Contract):
    claim_id: str
    claim_type: ClaimType
    text: str
    support_evidence_ids: list[str] = Field(default_factory=list)
    confidence: Confidence

    @model_validator(mode="after")
    def require_support(self):
        if self.claim_type in {ClaimType.PREDICTION, ClaimType.HISTORICAL_INTERPRETATION,
                              ClaimType.KNOWLEDGE, ClaimType.RECOMMENDATION} and not self.support_evidence_ids:
            raise ValueError(f"{self.claim_type.value} claims require evidence")
        return self


class ManagementConsideration(Contract):
    level: ManagementLevel
    text: str
    support_evidence_ids: list[str] = Field(default_factory=list)


class DiagnosisResult(Contract):
    answerability: Answerability
    workflow: str
    summary: str
    current_state: dict[str, Any] = Field(default_factory=dict)
    sensor_context: dict[str, Any] = Field(default_factory=dict)
    forecast: dict[str, Any] = Field(default_factory=dict)
    historical_context: dict[str, Any] = Field(default_factory=dict)
    knowledge_context: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[ConflictRecord] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    management_considerations: list[ManagementConsideration] = Field(default_factory=list)
    unsupported_subtasks: list[UnsupportedSubtask] = Field(default_factory=list)
    overall_reliability: WorkflowReliability
    evidence_completeness: EvidenceCompleteness
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    provenance: ProvenanceGraph
    limitations: list[str] = Field(default_factory=list)


class WorkflowRun(Contract):
    diagnosis: DiagnosisResult
    rendered: str
    state: dict[str, Any]
    provider: dict[str, Any]
    debug: dict[str, Any] | None = None
