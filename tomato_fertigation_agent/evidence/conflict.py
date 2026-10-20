from __future__ import annotations

from uuid import uuid4

from .schemas import ConflictRecord, ConflictStatus, EvidenceType
from .store import EvidenceStore


class EvidenceConflictAnalyzer:
    def __init__(self, agree_cm: float = 10.0, partial_cm: float = 20.0):
        self.agree_cm = agree_cm
        self.partial_cm = partial_cm

    def analyze(self, store: EvidenceStore) -> list[ConflictRecord]:
        predictions = store.by_type(EvidenceType.PREDICTION)
        cases = store.by_type(EvidenceType.HISTORICAL_CASE)
        if not predictions or not cases:
            return []
        model = next((x for x in predictions if x.value.get("height_t7_cm") is not None), None)
        historical = next((x for x in cases if x.value.get("case_weighted_height_t7_cm") is not None), None)
        if not model or not historical:
            return []
        if model.scope != historical.scope:
            return [ConflictRecord(conflict_id=f"conflict-{uuid4()}", conflict_type="MODEL_VS_CASE",
                status=ConflictStatus.NOT_COMPARABLE, evidence_ids=[model.evidence_id, historical.evidence_id],
                explanation="Model and historical case evidence use different spatial scopes.")]
        model_value = float(model.value["height_t7_cm"])
        case_value = float(historical.value["case_weighted_height_t7_cm"])
        difference = abs(model_value - case_value)
        if difference <= self.agree_cm:
            status, impact = ConflictStatus.AGREE, "NONE"
        elif difference <= self.partial_cm:
            status, impact = ConflictStatus.PARTIAL, "CAUTION"
        else:
            status, impact = ConflictStatus.DISAGREE, "LOWER_CONFIDENCE"
        return [ConflictRecord(conflict_id=f"conflict-{uuid4()}", conflict_type="MODEL_VS_CASE",
            status=status, evidence_ids=[model.evidence_id, historical.evidence_id], scope=model.scope,
            model_value=model_value, case_value=case_value, absolute_difference=difference, impact=impact,
            explanation=f"ML and case-weighted t+7 height differ by {difference:.2f} cm.")]
