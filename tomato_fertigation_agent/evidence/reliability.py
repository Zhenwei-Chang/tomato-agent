from __future__ import annotations

from ..schemas.common import Confidence
from .schemas import (CompletenessStatus, ConflictRecord, ConflictStatus,
                      EvidenceCompleteness, EvidenceType, ReliabilityFactor,
                      WorkflowReliability)
from .store import EvidenceStore


RANK = {Confidence.LOW: 0, Confidence.UNKNOWN: 1, Confidence.MEDIUM: 2, Confidence.HIGH: 3}


class ReliabilityPropagator:
    """Deterministic policy; this is deliberately not probability calibration."""

    def propagate(self, store: EvidenceStore, completeness: EvidenceCompleteness,
                  conflicts: list[ConflictRecord]) -> WorkflowReliability:
        factors: list[ReliabilityFactor] = []
        for record in store.all():
            factors.append(ReliabilityFactor(name=record.evidence_type.value, level=record.reliability,
                reason=f"{record.source_tool} reported {record.reliability.value}", evidence_ids=[record.evidence_id]))
        if completeness.status == CompletenessStatus.INSUFFICIENT:
            factors.append(ReliabilityFactor(name="evidence_completeness", level=Confidence.LOW,
                reason="Primary required evidence is missing"))
        elif completeness.status == CompletenessStatus.PARTIAL:
            factors.append(ReliabilityFactor(name="evidence_completeness", level=Confidence.LOW,
                reason="One or more required evidence types are missing"))
        else:
            factors.append(ReliabilityFactor(name="evidence_completeness", level=Confidence.MEDIUM,
                reason="All required evidence types are present"))
        if any(c.status == ConflictStatus.DISAGREE for c in conflicts):
            factors.append(ReliabilityFactor(name="model_case_conflict", level=Confidence.LOW,
                reason="ML prediction and historical cases disagree",
                evidence_ids=[eid for c in conflicts if c.status == ConflictStatus.DISAGREE for eid in c.evidence_ids]))
        elif any(c.status == ConflictStatus.PARTIAL for c in conflicts):
            factors.append(ReliabilityFactor(name="model_case_conflict", level=Confidence.MEDIUM,
                reason="ML prediction and historical cases only partially agree"))
        case_records = store.by_type(EvidenceType.HISTORICAL_CASE)
        if any(record.value.get("ood") for record in case_records):
            factors.append(ReliabilityFactor(name="case_ood", level=Confidence.LOW,
                reason="Historical case query is outside the memory distribution",
                evidence_ids=[r.evidence_id for r in case_records if r.value.get("ood")]))
        levels = [factor.level for factor in factors]
        level = min(levels, key=lambda x: RANK[x]) if levels else Confidence.UNKNOWN
        return WorkflowReliability(level=level, factors=factors)
