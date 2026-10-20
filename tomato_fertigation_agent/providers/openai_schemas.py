"""Strict, closed transport schemas for OpenAI Structured Outputs.

Domain contracts intentionally contain flexible dictionaries for Tool data.
Those dictionaries are not safe Structured Output targets because strict JSON
Schema closes unconstrained objects. These transport models keep LLM-authored
fields explicit, then merge them with deterministic evidence objects locally.
"""
from __future__ import annotations

from typing import Literal
from pydantic import Field

from ..diagnosis.schemas import DiagnosisResult
from ..evidence.schemas import EvidencePlan, EvidenceRequirement, WorkflowName
from ..schemas.agent import (AgentAnswer, AggregatedEvidence, GroundedStatement,
                             Intent, RouterDecision, ToolPlanRepair)
from ..schemas.common import Confidence, Contract, Scope


class OpenAIEntities(Contract):
    date: str | None = None
    year: int | None = None
    plant_id: str | None = None
    view_id: str | None = None
    treatment_id: str | None = None
    window_days: int | None = None
    top_k: int | None = None
    requests_precise_quantity: bool = False

    def compact(self):
        return self.model_dump(exclude_none=True)


class OpenAIRouterDecision(Contract):
    intent: Intent
    requested_scope: Scope | None = None
    entities: OpenAIEntities
    required_tools: list[str]
    unsupported_requests: list[str]
    reasoning_code: str


DeepSeekScope = Literal['plant','view','group','greenhouse','treatment',
                        'dataset','knowledge','none']


class DeepSeekEntities(Contract):
    """Closed transport without nullable ``anyOf`` for DeepSeek JSON Schema."""
    date: str = ''
    year: int = 0
    plant_id: str = ''
    view_id: str = ''
    treatment_id: str = ''
    window_days: int = 0
    top_k: int = 0
    requests_precise_quantity: bool = False

    def compact(self):
        values = self.model_dump()
        return {key:value for key,value in values.items()
                if key == 'requests_precise_quantity' or value not in ('', 0)}


class DeepSeekRouterDecision(Contract):
    intent: Intent
    requested_scope: DeepSeekScope
    entities: DeepSeekEntities
    required_tools: list[str]
    unsupported_requests: list[str]
    reasoning_code: str


class OpenAIToolPlanRepair(Contract):
    required_tools: list[str]
    reasoning_code: str


class OpenAIEvidencePlan(Contract):
    workflow: WorkflowName
    requirements: list[EvidenceRequirement]
    requested_scope: Scope | None = None
    entities: OpenAIEntities
    unsupported_subtasks: list[str]


class DeepSeekEvidencePlan(Contract):
    workflow: WorkflowName
    requirements: list[EvidenceRequirement]
    requested_scope: DeepSeekScope
    entities: DeepSeekEntities
    unsupported_subtasks: list[str]


class OpenAIGroundedText(Contract):
    text: str
    evidence_ids: list[str]
    category: Literal['interpretation', 'general_management_consideration']


class OpenAIAgentSynthesis(Contract):
    status: Literal['success', 'partial', 'unsupported', 'error']
    summary: str
    agronomic_interpretation: list[OpenAIGroundedText]
    recommendations: list[OpenAIGroundedText]
    warnings: list[str]
    limitations: list[str]
    unsupported_requests: list[str]


class OpenAIDiagnosisReview(Contract):
    selected_claim_ids: list[str]
    acknowledge_conflict: bool
    acknowledge_low_reliability: bool
    acknowledge_unsupported_subtasks: bool


def transport_model(purpose: str, fallback, provider_name: str = 'openai'):
    if provider_name == 'deepseek':
        return {'router':DeepSeekRouterDecision,'evidence_plan':DeepSeekEvidencePlan,
            'tool_plan_repair':OpenAIToolPlanRepair,
            'synthesis':OpenAIAgentSynthesis,
            'workflow_synthesis':OpenAIDiagnosisReview}.get(purpose,fallback)
    return {'router':OpenAIRouterDecision,'evidence_plan':OpenAIEvidencePlan,
        'tool_plan_repair':OpenAIToolPlanRepair,
        'synthesis':OpenAIAgentSynthesis,
        'workflow_synthesis':OpenAIDiagnosisReview}.get(purpose,fallback)


def to_domain_value(purpose: str, parsed, response_model, payload,
                    provider_name: str = 'openai'):
    if purpose=='router':
        row=(DeepSeekRouterDecision if provider_name=='deepseek' else
             OpenAIRouterDecision).model_validate(parsed)
        values=row.model_dump(exclude={'entities'})
        if values.get('requested_scope')=='none': values['requested_scope']=None
        return response_model.model_validate({**values,'entities':row.entities.compact()})
    if purpose=='tool_plan_repair':
        row=OpenAIToolPlanRepair.model_validate(parsed)
        return response_model.model_validate(row.model_dump())
    if purpose=='evidence_plan':
        row=(DeepSeekEvidencePlan if provider_name=='deepseek' else
             OpenAIEvidencePlan).model_validate(parsed)
        values=row.model_dump(exclude={'entities'})
        if values.get('requested_scope')=='none': values['requested_scope']=None
        return response_model.model_validate({**values,'entities':row.entities.compact(),
            'planner_source':provider_name,'fallback_used':False})
    if purpose=='synthesis':
        row=OpenAIAgentSynthesis.model_validate(parsed)
        bundle=AggregatedEvidence.model_validate(payload['aggregation'])
        current={fact.name:{'value':fact.value,'unit':fact.unit,'scope':fact.scope.value}
            for fact in bundle.facts if fact.observed}
        statements=lambda values:[GroundedStatement.model_validate(value.model_dump())
            for value in values if value.evidence_ids]
        answer=AgentAnswer(answer_type=str(payload['intent']).lower(),status=row.status,
            summary=row.summary,current_state=current or None,facts=bundle.facts,
            predictions=bundle.predictions,
            agronomic_interpretation=statements(row.agronomic_interpretation),
            recommendations=statements(row.recommendations),confidence=bundle.confidence,
            evidence_sufficiency=bundle.evidence_sufficiency,
            evidence=bundle.knowledge_evidence+bundle.historical_case_evidence,
            historical_cases=bundle.historical_cases,
            case_prediction_height_t7_cm=bundle.case_prediction_height_t7_cm,
            case_model_agreement=bundle.case_model_agreement,
            warnings=list(dict.fromkeys(bundle.warnings+row.warnings)),
            limitations=list(dict.fromkeys(bundle.limitations+row.limitations)),
            unsupported_requests=list(dict.fromkeys(bundle.unsupported_requests+row.unsupported_requests)))
        return response_model.model_validate(answer)
    if purpose=='workflow_synthesis':
        # The model may organize/acknowledge the deterministic result, but it is
        # not allowed to author new facts, numbers, claims, scopes or evidence.
        review=OpenAIDiagnosisReview.model_validate(parsed)
        diagnosis=DiagnosisResult.model_validate(payload['diagnosis'])
        known={claim.claim_id for claim in diagnosis.claims}
        if not set(review.selected_claim_ids) <= known:
            raise ValueError('Diagnosis review referenced an unknown claim ID')
        if any(item.status.value=='DISAGREE' for item in diagnosis.conflicts) and not review.acknowledge_conflict:
            raise ValueError('Diagnosis review hid an evidence conflict')
        if diagnosis.overall_reliability.level==Confidence.LOW and not review.acknowledge_low_reliability:
            raise ValueError('Diagnosis review hid LOW reliability')
        if diagnosis.unsupported_subtasks and not review.acknowledge_unsupported_subtasks:
            raise ValueError('Diagnosis review hid unsupported subtasks')
        return response_model.model_validate(diagnosis)
    return response_model.model_validate(parsed)
