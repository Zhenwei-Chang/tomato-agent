from __future__ import annotations

import re
from pathlib import Path

from .schemas import EvidencePlan, EvidenceRequirement, EvidenceType, WorkflowName
from ..providers.errors import ProviderError


def _entities(query: str) -> dict:
    entities = {}
    date_match = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", query)
    if not date_match:
        date_match = re.search(r"\b(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?", query)
    if date_match:
        year, month, day = map(int, date_match.groups())
        entities.update(date=f"{year:04d}-{month:02d}-{day:02d}", year=year)
    plant = re.search(r"\b(20\d{2}-(?!\d{2}-\d{2}\b)[A-Za-z0-9]+)\b", query)
    view = re.search(r"(?:view|视图|小区|画面)\s*(?:ID)?\s*[:：]?\s*([0-9]+,[0-9]+)", query, re.I)
    if not view and re.search(r"view|视图|小区|画面",query,re.I):
        view = re.search(r"([0-9]+,[0-9]+)",query)
    treatment = re.search(r"(?<![A-Za-z0-9])(CK|T[1-6])(?![A-Za-z0-9])", query, re.I)
    if plant:
        entities["plant_id"] = plant.group(1)
    if view:
        entities["view_id"] = view.group(1)
    if treatment:
        entities["treatment_id"] = treatment.group(1).upper()
    window = re.search(r"(\d{1,2})\s*天", query)
    if window:
        entities["window_days"] = int(window.group(1))
    top_k = re.search(r"(?:找|返回|检索)\s*(\d{1,2})\s*个", query)
    if top_k:
        entities["top_k"] = min(10, int(top_k.group(1)))
    entities["requests_precise_quantity"] = bool(re.search(
        r"精确|具体(?:浇|灌|施).{0,8}(?:多少|几)|多少\s*(?:毫升|mL|%|百分比)|\d+\s*(?:毫升|mL|L/株)", query, re.I))
    return entities


def deterministic_plan(query: str) -> EvidencePlan:
    entities = _entities(query)
    entities["raw_query"] = query
    entities["knowledge_query"] = query
    asks_forecast = bool(re.search(r"预测|未来\s*(?:7|七)\s*天|(?:7|七)\s*天后|未来株高|会长到|多高", query))
    asks_status = bool(re.search(r"当前|现在|状态|长势|环境|传感|温度|湿度|光照|CO2|基质", query, re.I))
    asks_knowledge = bool(re.search(r"影响|风险|管理|为什么|知识|文献|依据|怎么办|缺氮|缺钾|盐|水肥|施肥|灌溉", query))
    asks_rgb = bool(re.search(r"RGB|图像|图片|照片|画面", query, re.I))
    explicit_environment=bool(re.search(r"环境|传感|温度|湿度|光照|CO2|基质",query,re.I))
    asks_comprehensive = (bool(re.search(r"综合|诊断", query)) or
        sum((asks_forecast, asks_status, asks_knowledge)) >= 3 or
        (asks_forecast and asks_status and explicit_environment))
    general_knowledge_question = asks_knowledge and not asks_forecast and not any(
        entities.get(key) for key in ("date", "plant_id", "view_id"))
    if asks_comprehensive:
        workflow = WorkflowName.COMPREHENSIVE_DIAGNOSIS
    elif asks_forecast:
        workflow = WorkflowName.GROWTH_FORECAST
    elif general_knowledge_question:
        workflow = WorkflowName.KNOWLEDGE_QA
    elif asks_status:
        workflow = WorkflowName.GROWTH_STATUS
    else:
        workflow = WorkflowName.KNOWLEDGE_QA
    scope = "plant" if entities.get("plant_id") else ("view" if entities.get("view_id") else
        ("knowledge" if workflow == WorkflowName.KNOWLEDGE_QA else "dataset"))
    asks_exact_plant_from_view = bool(entities.get("view_id") and re.search(r"单株|这株|某株|植株.{0,8}精确|精确.{0,8}株", query))
    if asks_exact_plant_from_view:
        scope = "plant"
    requirements: list[EvidenceRequirement] = []
    def add(kind, required, reason, requirement_scope=None):
        requirements.append(EvidenceRequirement(evidence_type=kind, required=required,
            reason=reason, scope=requirement_scope))
    if workflow == WorkflowName.GROWTH_STATUS:
        add(EvidenceType.OBSERVATION, True, "Current status requires exact-date observations", scope)
        add(EvidenceType.SENSOR, True, "Recent environment contextualizes current status", "greenhouse")
        if asks_rgb or entities.get("view_id"):
            add(EvidenceType.VISUAL_OBSERVATION, False, "A View image can add group-level visual context", "view")
    elif workflow == WorkflowName.GROWTH_FORECAST:
        add(EvidenceType.OBSERVATION, True, "Forecasts need the observed current state", scope)
        add(EvidenceType.PREDICTION, True, "The requested t+7 outcome is model evidence", scope)
        add(EvidenceType.HISTORICAL_CASE, True, "Historical outcomes provide an independent association check", scope)
        add(EvidenceType.RELIABILITY, True, "Forecast limitations must be propagated", scope)
    elif workflow == WorkflowName.KNOWLEDGE_QA:
        add(EvidenceType.KNOWLEDGE, True, "Agronomic claims require retrieved knowledge evidence", "knowledge")
    else:
        add(EvidenceType.OBSERVATION, True, "Diagnosis starts from observed current state", scope)
        add(EvidenceType.SENSOR, True, "Diagnosis needs recent environmental context", "greenhouse")
        add(EvidenceType.PREDICTION, True, "Future state is model evidence", scope)
        add(EvidenceType.HISTORICAL_CASE, True, "Comparable historical outcomes test forecast consistency", scope)
        add(EvidenceType.KNOWLEDGE, True, "Management considerations require agronomic evidence", "knowledge")
        add(EvidenceType.RELIABILITY, True, "Diagnosis must propagate model and data limitations", scope)
        if asks_rgb and entities.get("view_id"):
            add(EvidenceType.VISUAL_OBSERVATION, False, "View-level visual evidence is optional", "view")
    unsupported = []
    if entities["requests_precise_quantity"]:
        unsupported.append("Exact irrigation/fertilizer amount: no validated decision or dosage model")
    if asks_exact_plant_from_view:
        unsupported.append("Plant-specific inference from View-level RGB/case evidence: incompatible scope")
    return EvidencePlan(workflow=workflow, requirements=requirements, requested_scope=scope,
        entities=entities, unsupported_subtasks=unsupported, planner_source="deterministic_fallback", fallback_used=True)


class EvidencePlanner:
    def __init__(self, provider, prompt_path: Path, trace_writer=None):
        self.provider = provider
        self.prompt_path = prompt_path
        self.trace = trace_writer

    def plan(self, query: str):
        prompt = self.prompt_path.read_text(encoding="utf-8")
        try:
            response = self.provider.structured_completion(purpose="evidence_plan", system_prompt=prompt,
                payload={"user_query": query}, response_model=EvidencePlan)
            plan = EvidencePlan.model_validate(response.value).model_copy(update={"planner_source": self.provider.name})
            return plan, response, None, None
        except Exception as exc:
            plan = deterministic_plan(query)
            error = exc.as_dict() if isinstance(exc, ProviderError) else {
                "code": "PROVIDER_FORMAT_ERROR", "message": str(exc),
                "details": {"exception_type": type(exc).__name__}}
            return plan, None, f"Evidence planner fallback: {error['code']}", error
