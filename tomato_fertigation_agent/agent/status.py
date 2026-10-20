from __future__ import annotations

from dataclasses import dataclass

from ..schemas.agent import (AgentAnswer, EvidenceSufficiency, Intent,
                             RequestContract, RouterDecision)
from .request_contract import RequestContractBuilder


@dataclass(frozen=True)
class StatusDecision:
    status: str
    answerability: str
    satisfied_subtasks: int
    failed_required_tools: list[str]
    missing_required_tools: list[str]
    unsatisfied_user_subtasks: list[str]
    unsatisfied_policy_subtasks: list[str]


class AnswerStatusResolver:
    """Application-owned answer status; provider output is advisory only."""

    _DATA_FIELD_TERMS = {
        "plant_height_cm": ("株高", "plant height", "height"),
        "lai": ("lai", "叶面积指数", "leaf area index"),
        "stem_diameter_mm": ("茎粗", "茎径", "stem diameter"),
        "growth_state": ("生长状态", "长势", "growth state"),
    }

    @classmethod
    def _requested_data_fields(cls, query: str) -> set[str]:
        lowered=(query or '').casefold()
        return {field for field,terms in cls._DATA_FIELD_TERMS.items()
                if any(term.casefold() in lowered for term in terms)}

    @classmethod
    def _subtask_satisfied(cls, subtask, answer: AgentAnswer, successful: set[str],
                           query: str) -> bool:
        kind=subtask.expected_result_type
        facts={row.name for row in answer.facts if row.value is not None}
        predictions={row.name for row in answer.predictions if row.value is not None}
        if kind=='treatment_recipe': return 'treatment_recipe' in facts
        if kind=='sensor_history': return 'sensor_history_summary' in facts
        if kind=='growth_context':
            requested=cls._requested_data_fields(query)
            return bool(facts) if not requested else requested.issubset(facts)
        if kind=='height_prediction': return 'height_t7' in predictions
        if kind=='rgb_analysis':
            return bool(predictions & {'current_view_mean_height','future_view_mean_height_t7'}) and all(
                row.scope.value=='view' for row in answer.predictions)
        if kind=='historical_cases': return bool(answer.historical_cases)
        if kind=='knowledge_evidence':
            return bool(answer.agronomic_interpretation or answer.recommendations or answer.evidence)
        if kind=='comprehensive_analysis':
            return bool(answer.facts or answer.predictions or answer.historical_cases or
                        answer.agronomic_interpretation or answer.recommendations)
        if kind=='reliability_assessment':
            return 'assess_prediction_reliability' in successful
        if kind in {'unsupported_request','exact_irrigation_amount'}:
            return False
        return all(name in successful for name in subtask.required_tools)

    def resolve(self, answer: AgentAnswer, route: RouterDecision, tool_calls,
                user_query: str = "", request_contract: RequestContract | None = None
                ) -> tuple[AgentAnswer, StatusDecision]:
        contract=request_contract or RequestContractBuilder().build(user_query,route)
        successful = {row.tool_name for row in tool_calls
                      if row.result_status in {"success", "partial"}}
        required_tools={name for row in contract.subtasks if row.required
                        for name in row.required_tools}
        partial_tools={row.tool_name for row in tool_calls
                       if row.tool_name in required_tools and row.result_status=='partial'}
        non_material_partial=set()
        for subtask in contract.subtasks:
            if (subtask.expected_result_type in {'growth_context','historical_cases'} and
                    self._subtask_satisfied(subtask,answer,successful,user_query)):
                non_material_partial.update(subtask.required_tools)
        material_partial_tools=partial_tools-non_material_partial
        failed = sorted({row.tool_name for row in tool_calls
                        if row.tool_name in required_tools and row.result_status == "error"
                        and not row.reused_result})
        missing = sorted(required_tools - successful)
        unsatisfied_user=[row.description for row in contract.required_user_subtasks
            if not self._subtask_satisfied(row,answer,successful,user_query)]
        unsatisfied_policy=[row.description for row in contract.required_policy_subtasks
            if not self._subtask_satisfied(row,answer,successful,user_query)]
        satisfied=sum(self._subtask_satisfied(row,answer,successful,user_query)
                      for row in contract.subtasks if row.required)
        # Registered source metadata alone is not an answered subtask.  A
        # supported fact/prediction/case/statement is required for PARTIAL/FULL.
        has_content = bool(answer.facts or answer.predictions or answer.historical_cases or
                           answer.agronomic_interpretation or answer.recommendations)
        explicit_unsupported=RequestContractBuilder.explicit_unsupported(contract)
        if route.intent.value == "UNSUPPORTED_REQUEST":
            status, answerability = "unsupported", "ABSTAIN"
        elif not has_content and (unsatisfied_user or unsatisfied_policy or missing or failed or
                answer.evidence_sufficiency == EvidenceSufficiency.INSUFFICIENT):
            status, answerability = (("unsupported", "ABSTAIN") if explicit_unsupported
                                     else ("error", "ABSTAIN"))
        elif has_content and (unsatisfied_user or unsatisfied_policy or missing or failed or
                material_partial_tools or
                answer.evidence_sufficiency in {EvidenceSufficiency.PARTIAL,
                                                EvidenceSufficiency.INSUFFICIENT}):
            status, answerability = "partial", "PARTIAL"
        else:
            status, answerability = "success", "FULL"
        summary = answer.summary
        if status != answer.status:
            if status == "success":
                if answer.status in {'unsupported','error'}:
                    summary = "已获得请求所需的结构化结果；范围、来源与限制已保留。"
            elif status == "partial":
                summary = "已获得部分可验证结果；其余子任务或证据缺口已明确列出。"
            elif status == "unsupported":
                summary = "当前工具或证据不足以支持所请求的结论。"
            else:
                summary = "所需工具未能产生可用结果。"
        updated = answer.model_copy(update={"status": status, "summary": summary,
            # Only unmet explicit user tasks belong here. Provider-authored
            # hypothetical capability notes cannot change answerability.
            "unsupported_requests": list(dict.fromkeys(explicit_unsupported))})
        return updated, StatusDecision(status, answerability,
            satisfied, failed, missing, unsatisfied_user, unsatisfied_policy)
