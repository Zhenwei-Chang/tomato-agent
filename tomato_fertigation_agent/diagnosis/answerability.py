from ..evidence.schemas import CompletenessStatus, EvidenceCompleteness, EvidencePlan
from .schemas import Answerability


class AnswerabilityPolicy:
    def decide(self, plan: EvidencePlan, completeness: EvidenceCompleteness) -> Answerability:
        if completeness.status == CompletenessStatus.INSUFFICIENT:
            return Answerability.ABSTAIN
        if completeness.status == CompletenessStatus.PARTIAL or plan.unsupported_subtasks:
            return Answerability.PARTIAL
        return Answerability.FULL
