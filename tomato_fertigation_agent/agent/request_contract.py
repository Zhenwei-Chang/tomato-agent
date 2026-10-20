from __future__ import annotations

import re
from uuid import uuid5, NAMESPACE_URL

from ..schemas.agent import (Intent, RequestContract, RequestSubtask,
                             RequestSubtaskSource, RouterDecision)
from .reliability_policy import ReliabilityRequirementMatrix


class RequestContractBuilder:
    """Build the trusted request boundary from query + validated application policy.

    Provider-generated unsupported notes are never promoted to required user work
    unless the original query independently contains an affirmative request.
    """

    VERSION = 'v1.4.5-request-contract-1'
    _PRIMARY = {
        Intent.TREATMENT_QUERY: ('treatment_recipe', '查询处理配方', ['get_treatment_recipe']),
        Intent.SENSOR_QUERY: ('sensor_history', '查询环境历史', ['get_sensor_history']),
        Intent.DATA_QUERY: ('growth_context', '查询当前生长数据', ['get_growth_context']),
        Intent.GROWTH_PREDICTION: ('height_prediction', '预测七天后株高', ['predict_height_t7']),
        Intent.RGB_ANALYSIS: ('rgb_analysis', '分析 View 级 RGB 长势', ['analyze_rgb']),
        Intent.KNOWLEDGE_QA: ('knowledge_evidence', '检索水肥知识证据', ['retrieve_water_fertilizer_knowledge']),
        Intent.SIMILAR_CASE_QUERY: ('historical_cases', '检索历史相似案例', ['find_similar_cases']),
        Intent.COMPREHENSIVE_ANALYSIS: ('comprehensive_analysis', '执行综合分析', []),
        Intent.UNSUPPORTED_REQUEST: ('unsupported_request', '判断并说明不支持的请求', []),
    }
    _IRRIGATION = re.compile(
        r'(?:灌水|浇水|浇|灌溉|施肥|肥液).{0,14}(?:多少|几|用量|剂量|毫升|ml|升|l/株)|'
        r'(?:多少|几).{0,8}(?:毫升|ml|升|l/株|水|肥)|'
        r'精确.{0,10}(?:灌水|浇水|灌溉|施肥|水肥)(?:量|用量|剂量)?', re.I)
    _NEGATION = re.compile(r'(?:不需要|无需|不要|不必|不用|别).{0,12}(?:灌水|浇水|灌溉|施肥|水肥|建议|用量|剂量)', re.I)
    _VIEW_TO_PLANT = re.compile(
        r'(?:view|视图|图片|图像|照片|画面).{0,30}(?:精确.{0,8}(?:单株|植株|这株)|(?:单株|植株|这株).{0,8}精确)',
        re.I)

    def __init__(self, reliability_matrix=None):
        self.reliability_matrix = reliability_matrix or ReliabilityRequirementMatrix()

    @staticmethod
    def _id(query: str, label: str) -> str:
        return str(uuid5(NAMESPACE_URL, f'{query}|{label}'))

    def build(self, query: str, route: RouterDecision) -> RequestContract:
        result_type, description, tools = self._PRIMARY[route.intent]
        scope = route.requested_scope
        subtasks = [RequestSubtask(subtask_id=self._id(query, result_type),
            description=description, source=RequestSubtaskSource.EXPLICIT_USER,
            required=True, requested_scope=scope, expected_result_type=result_type,
            required_tools=tools)]

        reliability = self.reliability_matrix.for_intent(route.intent)
        if reliability.required:
            subtasks.append(RequestSubtask(subtask_id=self._id(query, 'reliability_assessment'),
                description=reliability.reason,
                source=RequestSubtaskSource.REQUIRED_BY_TASK_POLICY, required=True,
                requested_scope=reliability.model_scope,
                expected_result_type='reliability_assessment',
                required_tools=['assess_prediction_reliability']))

        # An explicit affirmative dosage request is a separate user subtask. A
        # negated request ("不需要水肥建议") creates no obligation.
        if self._IRRIGATION.search(query) and not self._NEGATION.search(query):
            already_primary = route.intent == Intent.UNSUPPORTED_REQUEST
            if not already_primary:
                subtasks.append(RequestSubtask(subtask_id=self._id(query, 'exact_irrigation_amount'),
                    description='Exact irrigation/fertilizer amount: no validated decision or dosage model',
                    source=RequestSubtaskSource.EXPLICIT_USER, required=True,
                    requested_scope=scope, expected_result_type='exact_irrigation_amount'))
        if self._VIEW_TO_PLANT.search(query) and route.intent != Intent.UNSUPPORTED_REQUEST:
            subtasks.append(RequestSubtask(subtask_id=self._id(query, 'view_to_plant_scope'),
                description='Plant-specific inference from View-level RGB evidence: incompatible scope',
                source=RequestSubtaskSource.EXPLICIT_USER, required=True,
                requested_scope=scope, expected_result_type='unsupported_request'))

        # Router/synthesis capability notes remain visible for audit but cannot
        # become user obligations without independent confirmation above.
        explicit_descriptions={row.description for row in subtasks
            if row.source == RequestSubtaskSource.EXPLICIT_USER}
        for note in route.unsupported_requests:
            if note and note not in explicit_descriptions:
                subtasks.append(RequestSubtask(subtask_id=self._id(query, f'optional:{note}'),
                    description=note, source=RequestSubtaskSource.OPTIONAL_ASSISTANT,
                    required=False, requested_scope=scope,
                    expected_result_type='capability_note'))
        return RequestContract(version=self.VERSION, original_query=query,
            intent=route.intent, entities=route.entities, subtasks=subtasks)

    @staticmethod
    def explicit_unsupported(contract: RequestContract) -> list[str]:
        unsupported_types={'unsupported_request','exact_irrigation_amount'}
        return [row.description for row in contract.required_user_subtasks
                if row.expected_result_type in unsupported_types]
