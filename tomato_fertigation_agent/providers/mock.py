"""Deterministic provider for offline tests and orchestration evaluation.

It is intentionally transparent: metrics produced with this provider measure the
agent workflow and fixtures, not natural-language model quality.
"""
from __future__ import annotations
from time import perf_counter
from typing import Any
import json
import re
from pydantic import BaseModel
from .base import (ProviderResponse, ProviderToolCall, ProviderUsage,
                   ToolLoopResponse)
from ..schemas.agent import (AgentAnswer, AggregatedEvidence, EvidenceSufficiency,
    GroundedStatement, Intent, PlannedToolCall, RelevanceJudgment, RelevanceLabel,
    RouterDecision, ToolPlan)
from ..evidence.planner import deterministic_plan


class MockLLMProvider:
    name = 'mock'

    def __init__(self, version='improved', model='mock-v11-improved'):
        self.version = version
        self.model = model

    @staticmethod
    def _usage(source, output):
        return ProviderUsage(max(1, len(source) // 4), max(1, len(output) // 4))

    def _response(self, started, value, source):
        rendered = value.model_dump_json()
        return ProviderResponse(value, self._usage(source, rendered), (perf_counter()-started)*1000)

    def structured_completion(self, *, purpose, system_prompt, payload, response_model):
        started = perf_counter(); source = system_prompt + json.dumps(payload, ensure_ascii=False, default=str)
        if purpose == 'router':
            value = self._route(str(payload['user_query']))
        elif purpose == 'tool_plan_repair':
            catalog={item['name'] for item in payload.get('registry_catalog',[])}
            routed=self._route(str(payload['user_query']))
            value={'required_tools':[name for name in routed.required_tools if name in catalog],
                   'reasoning_code':'TOOL_PLAN_REPAIRED_FROM_REGISTRY'}
        elif purpose == 'argument_repair':
            value = PlannedToolCall(tool_name=payload['tool_name'], arguments=self._arguments(
                payload['tool_name'], payload['user_query'], improved=True,
                route=RouterDecision.model_validate(payload['route'])))
        elif purpose == 'relevance':
            value = self._relevance(payload)
        elif purpose == 'synthesis':
            value = self._synthesis(payload)
        elif purpose == 'evidence_plan':
            value = deterministic_plan(str(payload['user_query'])).model_copy(
                update={'planner_source':'mock','fallback_used':False})
        elif purpose == 'workflow_synthesis':
            value = response_model.model_validate(payload['diagnosis'])
        else:
            raise ValueError(f'Unsupported mock purpose: {purpose}')
        return self._response(started, response_model.model_validate(value), source)

    def tool_completion(self, *, system_prompt, user_query, route, tools, response_model):
        started = perf_counter(); improved = self.version == 'improved'
        calls = [PlannedToolCall(tool_name=name,
                 arguments=self._arguments(name, user_query, improved=improved, route=route))
                 for name in route.required_tools]
        value = response_model(calls=calls)
        return self._response(started, value, system_prompt + user_query + json.dumps(tools, ensure_ascii=False))

    def execute_tool_loop(self, *, system_prompt, user_query, tools, execute,
                          max_tool_calls, max_provider_calls,
                          max_argument_repairs=2):
        """Deterministic interface-parity helper; default workflows do not use it."""
        started=perf_counter(); route=self._route(user_query); calls=[]
        for index,tool in enumerate(tools[:max_tool_calls],1):
            name=tool.get('name') or tool.get('function',{}).get('name')
            arguments=self._arguments(name,user_query,improved=True,route=route)
            call_id=f'mock-call-{index}'
            result=execute(name,arguments,call_id)
            calls.append(ProviderToolCall(call_id=call_id,tool_name=name,
                arguments=arguments,result=result,response_id='mock-response-1'))
        source=system_prompt+user_query+json.dumps(tools,ensure_ascii=False)
        usage=self._usage(source,'mock tools complete')
        return ToolLoopResponse(calls=calls,usage=usage,
            latency_ms=(perf_counter()-started)*1000,provider_calls=1,
            response_ids=['mock-response-1'],response_models=[self.model],
            statuses=['completed'],final_text='mock tools complete')

    def _entities(self, query, improved):
        entities: dict[str, Any] = {}
        match = re.search(r'\b(20\d{2})-(\d{1,2})-(\d{1,2})\b', query)
        if not match and improved:
            match = re.search(r'\b(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?', query)
        if match:
            y,m,d = map(int, match.groups()); entities.update(date=f'{y:04d}-{m:02d}-{d:02d}', year=y)
        # A plant ID may be 2023-111 or 2024-CK11. Do not mistake the
        # YYYY-MM prefix of an ISO date for a plant ID.
        plant = re.search(r'\b(20\d{2}-(?!\d{2}-\d{2}\b)[A-Za-z0-9]+)\b', query)
        if plant: entities['plant_id'] = plant.group(1)
        view = re.search(r'(?:view|视图|小区|画面)\s*(?:ID)?\s*[:：]?\s*([0-9]+,[0-9]+)', query, re.I)
        if not view and re.search(r'view|视图|小区|画面',query,re.I):
            view = re.search(r'([0-9]+,[0-9]+)',query)
        if view: entities['view_id'] = view.group(1)
        treatment = re.search(r'(?<![A-Za-z0-9])(CK|T[1-6])(?![A-Za-z0-9])', query, re.I)
        if not treatment and improved:
            treatment = re.search(r'(?<![A-Za-z0-9])T\s*([1-6])(?![A-Za-z0-9])', query, re.I)
            if treatment: entities['treatment_id'] = 'T' + treatment.group(1)
        elif treatment:
            entities['treatment_id'] = treatment.group(1).upper()
        window = re.search(r'(\d{1,2})\s*天', query)
        if window: entities['window_days'] = int(window.group(1))
        top_k = re.search(r'(?:找|返回|检索)\s*(\d{1,2})\s*个', query)
        if top_k: entities['top_k'] = int(top_k.group(1))
        entities['requests_precise_quantity'] = bool(re.search(r'精确|多少\s*(?:毫升|mL|%|百分比)|\d+\s*(?:毫升|mL|L/株)', query, re.I))
        return entities

    def _route(self, query):
        improved = self.version == 'improved'; entities = self._entities(query, improved)
        has_rgb = bool(re.search(r'RGB|图像|图片|照片|画面', query, re.I))
        asks_plant = bool(entities.get('plant_id') or re.search(r'某株|单株|这株|植株', query))
        comprehensive = sum(bool(re.search(p, query)) for p in ('当前|状态','环境|传感','预测|未来|七天后','可靠|可信')) >= 3
        exact_action = entities['requests_precise_quantity'] and bool(re.search(r'灌|浇|施肥|肥料|EC', query, re.I))
        asks_case=bool(re.search(r'(?:相似|类似).{0,6}(?:案例|记录)|历史.{0,6}(?:案例|记录)|旧案例|Case',query,re.I))
        asks_prediction=bool(re.search(r'预测|七天后|7天后|未来株高|多高',query))
        asks_knowledge=bool(re.search(r'知识|农艺|水肥知识|文献|依据',query))
        if improved and asks_case and entities.get('view_id') and asks_plant:
            return RouterDecision(intent=Intent.UNSUPPORTED_REQUEST,requested_scope='plant',entities=entities,
                unsupported_requests=['View-level historical cases cannot provide a plant-specific phenotype'],reasoning_code='CASE_SCOPE_TRAP')
        if improved and has_rgb and asks_plant and re.search(r'精确|单株|这株|某株', query):
            return RouterDecision(intent=Intent.UNSUPPORTED_REQUEST, requested_scope='plant', entities=entities,
                unsupported_requests=['View-level RGB cannot provide an exact plant-level phenotype'], reasoning_code='SCOPE_TRAP')
        if exact_action and (improved or re.search(r'精确|\d+\s*(?:毫升|mL)', query, re.I)):
            if '高盐' in query and '多少' in query and '精确' not in query:
                return RouterDecision(intent=Intent.KNOWLEDGE_QA, requested_scope='knowledge', entities=entities,
                    required_tools=['retrieve_water_fertilizer_knowledge'], reasoning_code='QUANTITATIVE_EVIDENCE_CHECK')
            return RouterDecision(intent=Intent.UNSUPPORTED_REQUEST, requested_scope=entities.get('requested_scope'), entities=entities,
                unsupported_requests=['No evidence-backed irrigation/fertilizer dose model is available'], reasoning_code='UNSUPPORTED_NUMERIC_DECISION')
        if comprehensive or (asks_case and (asks_prediction or asks_knowledge or re.search(r'当前状态|分析',query))):
            tools=['get_growth_context']
            if asks_prediction: tools.append('predict_height_t7')
            if asks_case: tools.append('find_similar_cases')
            if asks_knowledge: tools.append('retrieve_water_fertilizer_knowledge')
            if asks_prediction: tools.append('assess_prediction_reliability')
            if not asks_case and comprehensive: tools=['get_growth_context','get_sensor_history','predict_height_t7','assess_prediction_reliability']
            return RouterDecision(intent=Intent.COMPREHENSIVE_ANALYSIS,requested_scope='plant' if asks_plant else 'dataset',entities=entities,required_tools=tools)
        if asks_case:
            return RouterDecision(intent=Intent.SIMILAR_CASE_QUERY,requested_scope='plant' if asks_plant else 'view',entities=entities,required_tools=['find_similar_cases'])
        if has_rgb:
            return RouterDecision(intent=Intent.RGB_ANALYSIS,requested_scope='plant' if asks_plant else 'view',entities=entities,
                required_tools=['analyze_rgb','assess_prediction_reliability'])
        if re.search(r'预测|七天后|7天后|未来株高|多高', query):
            return RouterDecision(intent=Intent.GROWTH_PREDICTION,requested_scope='plant',entities=entities,
                required_tools=['predict_height_t7','assess_prediction_reliability'])
        if re.search(r'传感|环境|温湿度|温度|湿度|光照|CO2|基质含水', query, re.I):
            return RouterDecision(intent=Intent.SENSOR_QUERY,requested_scope='greenhouse',entities=entities,required_tools=['get_sensor_history'])
        if re.search(r'配方|营养液|肥液|肥料盐|组成|KNO3|元素.{0,4}浓度|六种元素|处理方案', query, re.I) and entities.get('treatment_id'):
            return RouterDecision(intent=Intent.TREATMENT_QUERY,requested_scope='treatment',entities=entities,required_tools=['get_treatment_recipe'])
        if re.search(r'影响|风险|管理|为什么|知识|证据|怎么办|缺氮|缺钾|盐胁迫|高盐|水肥', query):
            return RouterDecision(intent=Intent.KNOWLEDGE_QA,requested_scope='knowledge',entities=entities,required_tools=['retrieve_water_fertilizer_knowledge'])
        if re.search(r'查询|当前|株高|LAI|表型|数据', query):
            return RouterDecision(intent=Intent.DATA_QUERY,requested_scope='plant' if asks_plant else ('view' if entities.get('view_id') else 'dataset'),entities=entities,required_tools=['get_growth_context'])
        return RouterDecision(intent=Intent.UNSUPPORTED_REQUEST,entities=entities,
            unsupported_requests=['The request is outside the current controlled intent taxonomy'],reasoning_code='NO_SUPPORTED_INTENT')

    def _arguments(self, name, query, improved, route):
        e = self._entities(query, improved)
        if name == 'get_growth_context':
            return {k:e[k] for k in ('year','date','plant_id','view_id','treatment_id') if k in e}
        if name == 'get_sensor_history':
            args = {'end_date':e['date']} if 'date' in e else {}
            args['window_days'] = e.get('window_days',7)
            for key in ('plant_id','view_id'):
                if key in e: args[key]=e[key]
            return args
        if name == 'get_treatment_recipe':
            return {'treatment_id':e['treatment_id']} if 'treatment_id' in e else {}
        if name == 'predict_height_t7':
            return {k:e[k] for k in ('year','date','plant_id') if k in e}
        if name in ('analyze_rgb','get_image_embedding'):
            args = {k:e[k] for k in ('view_id','date') if k in e}
            args['requested_scope'] = (route.requested_scope or 'view').value if hasattr(route.requested_scope,'value') else (route.requested_scope or 'view')
            return args
        if name == 'retrieve_water_fertilizer_knowledge':
            return {'query':query,'top_k':6}
        if name == 'assess_prediction_reliability':
            rgb = 'analyze_rgb' in route.required_tools
            return {'model_name':'rgb_v05' if rgb else 'height_v03_b0','year':e.get('year'),
                    'requested_scope':(route.requested_scope or ('view' if rgb else 'plant')).value if hasattr(route.requested_scope,'value') else (route.requested_scope or ('view' if rgb else 'plant')),
                    'model_scope':'view' if rgb else 'plant','critical_features_complete':True,
                    'image_available':True if rgb else None,'sensor_available':None if rgb else True}
        if name == 'find_similar_cases':
            scope='plant' if e.get('plant_id') else 'view'
            retrospective=bool(re.search(r'回顾性|retrospective|离线回看',query,re.I))
            policy='cross_year' if re.search(r'跨年|不同年份|cross.year',query,re.I) else 'cross_entity'
            args={'scope':scope,'date':e['date'],'top_k':e.get('top_k',5),'historical_only':not retrospective,
                  'retrieval_mode':'retrospective' if retrospective else 'historical','retrieval_policy':policy,'exclude_same_entity':True}
            args['plant_id' if scope=='plant' else 'view_id']=e.get('plant_id') if scope=='plant' else e.get('view_id')
            return args
        return {}

    def _relevance(self, payload):
        evidence = payload['evidence']; score = evidence.get('score') or 0
        if self.version == 'baseline':
            label = RelevanceLabel.RELEVANT if score >= payload.get('minimum_score',3) else RelevanceLabel.IRRELEVANT
            return RelevanceJudgment(label=label, reason='Baseline score-only relevance rule')
        query = payload['query'].lower()
        text = json.dumps(evidence, ensure_ascii=False).lower()
        concept_groups = [
            ('高盐','盐胁迫','盐分','咸水','水盐','ec'), ('水分','灌溉','浇水','含水率','排液'),
            ('氮','缺氮'), ('钾','缺钾'), ('钙','脐腐'), ('镁','缺镁'),
            ('温度','高温','低温'), ('湿度','相对湿度'), ('co2','二氧化碳'),
            ('光照','辐射','ppfd'), ('开花','坐果'), ('膨大','膨果'), ('苗期','育苗'), ('ph','酸碱')]
        query_concepts=[set(group) for group in concept_groups if any(term in query for term in group)]
        matched = not query_concepts or all(any(term in text for term in group) for group in query_concepts)
        if not matched:
            return RelevanceJudgment(label=RelevanceLabel.IRRELEVANT, reason='Evidence does not match the query concept')
        content = str(evidence.get('content') or '')
        attrs = evidence.get('attributes') or {}
        if not content or attrs.get('applicability') in ('low','partial'):
            return RelevanceJudgment(label=RelevanceLabel.PARTIALLY_RELEVANT, reason='Topic overlaps but content/applicability is limited')
        return RelevanceJudgment(label=RelevanceLabel.RELEVANT, reason='Query concept and evidence content align')

    def _synthesis(self, payload):
        bundle = AggregatedEvidence.model_validate(payload['aggregation'])
        intent = Intent(payload['intent']); unsupported=list(bundle.unsupported_requests)
        if intent == Intent.UNSUPPORTED_REQUEST and not unsupported:
            unsupported=['Current tools do not support this request']
        current={f.name:{'value':f.value,'unit':f.unit,'scope':f.scope.value} for f in bundle.facts if f.observed and f.name in ('plant_height_cm','height_cm','lai','stem_diameter_mm','growth_state')}
        interpretations=[]; recommendations=[]
        for item in bundle.knowledge_evidence[:3]:
            if item.content:
                interpretations.append(GroundedStatement(text=item.content,evidence_ids=[item.evidence_id],category='interpretation'))
            allowed=str(item.attributes.get('allowed_use') or '')
            if allowed:
                recommendations.append(GroundedStatement(text=allowed,evidence_ids=[item.evidence_id],category='general_management_consideration'))
        if unsupported:
            summary='当前工具或证据不足以支持所请求的精确结论。'
            status='unsupported'
        elif bundle.predictions:
            pieces=[f'{p.name}={p.value:.3f} {p.unit}（{p.scope.value}）' for p in bundle.predictions]
            summary='；'.join(pieces)+'。这些是模型预测，不是观测事实。'
            if bundle.historical_cases:
                summary += f' 同时检索到 {len(bundle.historical_cases)} 条严格历史可用案例；Case-Model agreement={bundle.case_model_agreement}。'
            status='partial' if bundle.warnings else 'success'
        elif bundle.historical_cases:
            summary=f'检索到 {len(bundle.historical_cases)} 条严格历史可用案例。相似性只表示历史关联，不表示因果。'
            status='partial' if bundle.warnings else 'success'
        elif bundle.facts:
            summary=f'已获得 {len(bundle.facts)} 项结构化数据事实；范围信息已逐项保留。'
            status='partial' if bundle.warnings else 'success'
        elif bundle.knowledge_evidence:
            summary=f'检索并通过相关性门控的证据共 {len(bundle.knowledge_evidence)} 条。'
            status='partial' if bundle.evidence_sufficiency != EvidenceSufficiency.SUFFICIENT else 'success'
        else:
            summary='未获得足以回答该问题的可用工具结果。'; status='error'
        return AgentAnswer(answer_type=intent.value.lower(),status=status,summary=summary,current_state=current or None,
            facts=bundle.facts,predictions=bundle.predictions,agronomic_interpretation=interpretations,
            recommendations=recommendations,confidence=bundle.confidence,evidence_sufficiency=bundle.evidence_sufficiency,
            evidence=bundle.knowledge_evidence+bundle.historical_case_evidence,
            historical_cases=bundle.historical_cases,
            case_prediction_height_t7_cm=bundle.case_prediction_height_t7_cm,case_model_agreement=bundle.case_model_agreement,
            warnings=bundle.warnings,limitations=bundle.limitations,
            unsupported_requests=unsupported)
