from .schemas import (CompletenessStatus, EvidenceCompleteness, EvidencePlan,
                      EvidenceType)
from .store import EvidenceStore


PRIMARY = {
    "growth_status": {EvidenceType.OBSERVATION},
    "growth_forecast": {EvidenceType.PREDICTION},
    "knowledge_qa": {EvidenceType.KNOWLEDGE},
    "comprehensive_diagnosis": {EvidenceType.OBSERVATION, EvidenceType.PREDICTION},
}


class EvidenceCompletenessChecker:
    def check(self, plan: EvidencePlan, store: EvidenceStore) -> EvidenceCompleteness:
        available_types = {record.evidence_type for record in store.all()}
        required = {req.evidence_type for req in plan.requirements if req.required}
        optional = {req.evidence_type for req in plan.requirements if not req.required}
        missing_required = required - available_types
        missing_optional = optional - available_types
        critical_missing = PRIMARY[plan.workflow.value] & missing_required
        if critical_missing:
            status = CompletenessStatus.INSUFFICIENT
        elif missing_required:
            status = CompletenessStatus.PARTIAL
        else:
            status = CompletenessStatus.COMPLETE
        reasons = []
        if missing_required:
            reasons.append("Missing required evidence: " + ", ".join(sorted(x.value for x in missing_required)))
        if missing_optional:
            reasons.append("Optional evidence unavailable: " + ", ".join(sorted(x.value for x in missing_optional)))
        return EvidenceCompleteness(status=status, available=sorted(available_types, key=lambda x: x.value),
            missing_required=sorted(missing_required, key=lambda x: x.value),
            missing_optional=sorted(missing_optional, key=lambda x: x.value), reasons=reasons)
