"""Deterministic, task-oriented answer quality checks.

This module deliberately separates whether claims are grounded from whether the
answer addresses and covers the user's requested task.  It does not inject
agronomic facts and is not a substitute for human scientific review.
"""
from __future__ import annotations

from pydantic import Field

from ..schemas.common import Contract


class AnswerQualityResult(Contract):
    relevant: bool
    complete: bool
    reasons: list[str] = Field(default_factory=list)


class AnswerQualityEvaluator:
    INSUFFICIENT_MARKERS=("证据不足","没有可提取的结论","无法给出主要结论",
                          "insufficient","cannot support","unable to support")

    def evaluate(self, case, answer) -> AnswerQualityResult:
        payload=answer.model_dump(mode='json') if hasattr(answer,'model_dump') else dict(answer)
        if case.mode=='workflow':
            return self._workflow(case.category,payload)
        return self._atomic(case.category,payload)

    def _atomic(self, category, row):
        facts=row.get('facts') or []; predictions=row.get('predictions') or []
        fact_names={item.get('name') for item in facts}
        pred_names={item.get('name') for item in predictions}
        explicit=self._explicit_insufficiency(row)
        reasons=[]
        if category=='treatment':
            complete='treatment_recipe' in fact_names
        elif category=='sensor':
            complete='sensor_history_summary' in fact_names
        elif category=='data':
            complete=bool(fact_names & {'plant_height_cm','height_cm','lai','stem_diameter_mm','growth_state'})
        elif category=='prediction':
            complete='height_t7' in pred_names or explicit
        elif category=='rgb':
            complete=bool(pred_names & {'current_view_mean_height','future_view_mean_height_t7'}) and all(
                item.get('scope')=='view' for item in predictions)
        elif category=='case_retrieval':
            cases=row.get('historical_cases') or []
            evidence_ids={item.get('evidence_id') for item in row.get('evidence') or []}
            complete=bool(cases) and all(bool(item.get('historical_outcome')) for item in cases) and all(
                item.get('evidence_id') in evidence_ids for item in cases)
        elif category in {'scope_trap','unsupported_irrigation'}:
            complete=row.get('status')=='unsupported' and bool(row.get('unsupported_requests'))
        else:
            complete=bool(facts or predictions or explicit)
        relevant=complete or explicit
        if not relevant: reasons.append('Answer does not address the requested task contract')
        if not complete: reasons.append(f'Missing required structured content for category={category}')
        return AnswerQualityResult(relevant=relevant,complete=complete,reasons=reasons)

    def _workflow(self, category, row):
        claims=row.get('claims') or []; evidence=row.get('evidence') or []
        claim_types={item.get('claim_type') for item in claims}
        evidence_types={item.get('evidence_type') for item in evidence}
        explicit=self._explicit_insufficiency(row)
        reasons=[]
        if category=='knowledge':
            supported=any(item.get('claim_type')=='knowledge' and item.get('support_evidence_ids')
                          and str(item.get('text') or '').strip() for item in claims)
            relevant=supported or explicit
            complete=supported or (explicit and row.get('answerability') in {'PARTIAL','ABSTAIN'})
        elif category=='comprehensive':
            relevant=bool(claims) or explicit
            complete=({'observation','prediction'} <= evidence_types and
                      bool(row.get('limitations') is not None)) or explicit
        else:
            relevant=bool(claims) or explicit
            complete=relevant
        if not relevant: reasons.append('Workflow output does not answer the requested task')
        if not complete: reasons.append(f'Workflow answer is incomplete for category={category}')
        return AnswerQualityResult(relevant=relevant,complete=complete,reasons=reasons)

    def _explicit_insufficiency(self,row):
        text=' '.join([str(row.get('summary') or ''),
            *[str(item) for item in row.get('limitations') or []],
            *[str(item) for item in row.get('unsupported_requests') or []]])
        lowered=text.lower()
        return any(marker.lower() in lowered for marker in self.INSUFFICIENT_MARKERS)
