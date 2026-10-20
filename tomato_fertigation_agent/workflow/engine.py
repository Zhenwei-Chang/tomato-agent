from __future__ import annotations

from pathlib import Path
from time import perf_counter
from uuid import uuid4

import yaml

from ..agent.relevance import RAGRelevanceGate
from ..agent.executor import ToolExecutor, ToolResultFormatter
from ..agent.reliability_policy import ReliabilityRequirementMatrix
from ..agent.request_contract import RequestContractBuilder
from ..config import PROJECT
from ..diagnosis import (AnswerabilityPolicy, ClaimBuilder, ClaimSafetyValidator,
                         render_diagnosis)
from ..diagnosis.schemas import (DiagnosisResult, UnsupportedSubtask,
                                 WorkflowRun)
from ..evidence import (EvidenceCompletenessChecker, EvidenceConflictAnalyzer,
                        EvidenceNormalizer, EvidencePlanner, EvidenceStore,
                        ProvenanceBuilder, ReliabilityPropagator)
from ..evidence.schemas import CompletenessStatus, EvidenceType
from ..providers import (MockLLMProvider, ProviderError, ProviderErrorCode,
                         ToolExecutionResult)
from ..agent_config import build_online_provider
from ..registry import ToolRegistry
from ..schemas.agent import (EvidenceSufficiency, Intent, RouterDecision,
                             ToolCallRecord)
from ..schemas.common import Confidence
from ..tracing.trace import AgentTraceEvent, AgentTraceWriter
from .base import WorkflowState
from .registry import WorkflowRegistry


class WorkflowConfig:
    def __init__(self, path=None):
        raw = yaml.safe_load(Path(path or PROJECT / "configs/workflow.yaml").read_text(encoding="utf-8"))
        self.raw = raw
        self.max_provider_calls = int(raw["provider_budget"]["max_calls_per_request"])
        self.max_tool_calls = int(raw["provider_budget"].get("max_tool_calls_per_request", 6))
        self.max_argument_repairs = int(raw["provider_budget"].get("max_argument_repairs", 2))
        self.reserve_synthesis_calls = int(raw["provider_budget"].get("reserve_synthesis_calls", 1))
        self.knowledge_top_k = int(raw["knowledge"]["top_k"])
        self.minimum_retrieval_score = float(raw["knowledge"]["minimum_retrieval_score"])
        self.agree_cm = float(raw["conflict"]["agree_cm"])
        self.partial_cm = float(raw["conflict"]["partial_cm"])


def _provider(provider_name="mock"):
    if provider_name == "mock":
        return MockLLMProvider(version="workflow", model="mock-v13-workflow")
    if provider_name in {"openai", "deepseek"}:
        return build_online_provider(provider_name)
    raise ValueError(f"Unsupported provider: {provider_name}")


class WorkflowAgent:
    def __init__(self, registry=None, provider=None, config=None):
        self.registry = registry or ToolRegistry()
        self.provider = provider or _provider("mock")
        self.config = config or WorkflowConfig()
        self.trace = AgentTraceWriter(self.registry.settings.output)
        self.workflows = WorkflowRegistry()
        self.planner = EvidencePlanner(self.provider, PROJECT / "tomato_fertigation_agent/prompts/evidence_planner_v1.txt", self.trace)
        relevance_prompt = (PROJECT / "tomato_fertigation_agent/prompts/relevance_v2.txt").read_text(encoding="utf-8")
        self.relevance = RAGRelevanceGate(self.provider, relevance_prompt, self.trace,
                                          self.config.minimum_retrieval_score)
        self.normalizer = EvidenceNormalizer()
        self.completeness = EvidenceCompletenessChecker()
        self.conflicts = EvidenceConflictAnalyzer(self.config.agree_cm, self.config.partial_cm)
        self.reliability = ReliabilityPropagator()
        self.answerability = AnswerabilityPolicy()
        self.claims = ClaimBuilder()
        self.claim_safety = ClaimSafetyValidator()
        self.provenance = ProvenanceBuilder()
        self.reliability_policy = ReliabilityRequirementMatrix()
        self.request_contract_builder = RequestContractBuilder(self.reliability_policy)

    def ask(self, query: str, *, debug=False, trace_id=None) -> WorkflowRun:
        started = perf_counter()
        state = WorkflowState(user_query=query, **({"trace_id": trace_id} if trace_id else {}))
        parent = self._event(state, "request", "WorkflowAgent", {"query_length": len(query)},
                             {"request_id": state.request_id})
        plan, response, fallback_warning, planner_error = self.planner.plan(query)
        if response:
            state.llm_calls += 1; state.planner_calls += 1
            state.input_tokens += response.usage.input_tokens; state.output_tokens += response.usage.output_tokens
            state.provider_events.append(self._provider_event("evidence_plan", response))
        if planner_error:
            state.provider_errors.append(planner_error)
        if fallback_warning:
            state.warnings.append(fallback_warning)
        plan.entities.setdefault("raw_query", query)
        plan.entities.setdefault("knowledge_query", query)
        state.workflow = plan.workflow; state.evidence_plan = plan; state.entities = plan.entities
        state.unsupported_subtasks = list(plan.unsupported_subtasks)
        parent = self._event(state, "evidence_plan", "EvidencePlanner", {"query_length": len(query)},
            {"workflow": plan.workflow.value, "required": [r.evidence_type.value for r in plan.requirements if r.required],
             "optional": [r.evidence_type.value for r in plan.requirements if not r.required],
             "fallback": plan.fallback_used}, parent)
        workflow = self.workflows.get(plan.workflow)
        tools = workflow.tool_names(plan)
        intent={
            'growth_status':Intent.DATA_QUERY,
            'growth_forecast':Intent.GROWTH_PREDICTION,
            'knowledge_qa':Intent.KNOWLEDGE_QA,
            'comprehensive_diagnosis':Intent.COMPREHENSIVE_ANALYSIS,
        }[plan.workflow.value]
        contract_route=RouterDecision(intent=intent,requested_scope=plan.requested_scope,
            entities=plan.entities,required_tools=tools,
            unsupported_requests=plan.unsupported_subtasks)
        state.request_contract=self.request_contract_builder.build(query,contract_route)
        # Provider-planned unsupported notes are advisory. Only independently
        # confirmed explicit user requests may affect answerability.
        plan=plan.model_copy(update={'unsupported_subtasks':
            self.request_contract_builder.explicit_unsupported(state.request_contract)})
        state.evidence_plan=plan
        state.unsupported_subtasks=list(plan.unsupported_subtasks)
        if self._scope_trap(plan):
            tools = []
        parent = self._event(state, "workflow_selected", "WorkflowRegistry", {},
                             {"workflow": plan.workflow.value, "tools": tools}, parent)
        if (tools and self.provider.name in {"openai", "deepseek"} and
                not getattr(self.provider, "allow_external_tool_data", True)):
            raise ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE,
                "External ToolResult transmission requires explicit consent",
                required_flag="--allow-local-tool-data")
        if self.provider.name in {"openai", "deepseek"} and tools:
            results = self._execute_online_tools(state, plan, tools, parent)
        else:
            results = self._execute_tools(state, plan, tools, parent)
        self._ensure_required_reliability(state,plan,results,parent)
        accepted, rag_sufficiency, relevance_report = self._apply_relevance(state, results, parent)
        for item in state.unsupported_requests:
            text = f"Knowledge-backed quantitative decision: {item}"
            if text not in plan.unsupported_subtasks:
                plan.unsupported_subtasks.append(text)
        # Preserve accepted qualitative evidence even when it is insufficient
        # for a requested quantitative conclusion.  Sufficiency controls
        # answerability; it must not erase otherwise relevant provenance.
        normalized_knowledge = accepted
        store = EvidenceStore(); store.extend(self.normalizer.normalize(results, normalized_knowledge))
        state.evidence_ids = sorted(store.ids())
        completeness = self.completeness.check(plan, store)
        knowledge_rows=store.by_type(EvidenceType.KNOWLEDGE)
        knowledge_content_insufficient=(plan.workflow.value=='knowledge_qa' and bool(knowledge_rows)
            and not any(str(row.value.get('summary') or '').strip() for row in knowledge_rows))
        if knowledge_content_insufficient:
            state.warnings.append('Topic-related knowledge sources were retrieved, but no extractable conclusion supports the requested effects')
            completeness=completeness.model_copy(update={'status':CompletenessStatus.PARTIAL,
                'reasons':completeness.reasons+['Knowledge sources lack extractable claim content']})
        if (rag_sufficiency == EvidenceSufficiency.PARTIAL and
                EvidenceType.KNOWLEDGE in completeness.available and
                completeness.status == CompletenessStatus.COMPLETE):
            completeness = completeness.model_copy(update={"status": CompletenessStatus.PARTIAL,
                "reasons": completeness.reasons + ["Knowledge evidence is only partially sufficient"]})
        conflicts = self.conflicts.analyze(store)
        reliability = self.reliability.propagate(store, completeness, conflicts)
        answerability = self.answerability.decide(plan, completeness)
        state.answerability = answerability
        parent = self._event(state, "conflict_analysis", "EvidenceConflictAnalyzer",
            {"evidence_count": len(store.all())}, {"conflicts": [c.status.value for c in conflicts]}, parent)
        parent = self._event(state, "reliability_decision", "ReliabilityPropagator", {},
            {"level": reliability.level.value, "factor_count": len(reliability.factors)}, parent)
        parent = self._event(state, "answerability_decision", "AnswerabilityPolicy",
            {"completeness": completeness.status.value}, {"answerability": answerability.value}, parent)
        claims, considerations = self.claims.build(store, conflicts, reliability.level)
        violations = self.claim_safety.validate(claims, store, conflicts)
        state.safety_violations = violations
        provenance = self.provenance.build(claims, store.all())
        unsupported = [self._unsupported(item) for item in plan.unsupported_subtasks]
        summary=self._summary(plan.workflow.value, answerability.value, reliability.level.value)
        if knowledge_content_insufficient:
            summary=('检索到主题相关来源，但当前返回证据没有可提取的结论来支持用户所问的具体生长影响；'
                     '因此只能报告证据不足，不能补写农业结论。')
        diagnosis = DiagnosisResult(answerability=answerability, workflow=plan.workflow.value,
            summary=summary,
            current_state=self._current(store), sensor_context=self._sensor(store),
            forecast=self._forecast(store), historical_context=self._historical(store),
            knowledge_context=self._knowledge(store), conflicts=conflicts,
            risk_factors=self._risks(store, conflicts, reliability.level),
            management_considerations=considerations, unsupported_subtasks=unsupported,
            overall_reliability=reliability, evidence_completeness=completeness,
            claims=claims, evidence=store.all(), provenance=provenance,
            limitations=self._limitations(store, state.warnings, violations))
        parent = self._event(state, "claim_generation", "ClaimBuilder", {},
            {"claims": len(claims), "grounded": sum(bool(c.support_evidence_ids) for c in claims),
             "provenance_complete": provenance.complete, "violations": violations}, parent)
        diagnosis = self._synthesize(state, diagnosis)
        state.elapsed_ms = (perf_counter() - started) * 1000
        self._event(state, "final_synthesis", "WorkflowDiagnosis", {},
            {"answerability": diagnosis.answerability.value, "reliability": diagnosis.overall_reliability.level.value,
             "claims": len(diagnosis.claims)}, parent)
        debug_payload = None
        if debug:
            debug_payload = {"workflow": plan.workflow.value, "evidence_plan": plan.model_dump(mode="json"),
                "nodes_executed": state.nodes_executed,
                "tool_calls": [record.model_dump(mode="json") for record in state.tool_calls],
                "relevance_gate": relevance_report,
                "conflicts": [item.model_dump(mode="json") for item in conflicts],
                "answerability": answerability.value,
                "claims": [claim.model_dump(mode="json") for claim in diagnosis.claims],
                "provenance": diagnosis.provenance.model_dump(mode="json"),
                "provider_calls": self._provider_calls(state), "safety_violations": violations}
        return WorkflowRun(diagnosis=diagnosis, rendered=render_diagnosis(diagnosis, debug=False),
            state=state.model_dump(mode="json"), provider={"name": self.provider.name,
            "model": self.provider.model, "online": self.provider.name != "mock",
            "benchmark": "Deterministic Offline Workflow Benchmark" if self.provider.name == "mock" else "online"},
            debug=debug_payload)

    def _execute_tools(self, state, plan, tools, parent):
        results = []
        for index, name in enumerate(tools, start=1):
            args = self._arguments(name, plan, results)
            record = ToolCallRecord(call_index=index, tool_name=name, initial_arguments=args,
                final_arguments=args, argument_valid_first_try=True, final_argument_valid=True)
            state.nodes_executed.append(name)
            node = self._event(state, "node_start", name, {"argument_keys": sorted(args)}, {}, parent)
            result = self.registry.call(name, args, trace_id=state.trace_id, parent_id=node,
                request_id=state.request_id)
            record.result_status = result.status
            record.error_code = result.error.code.value if result.error else None
            record.tool_call_id = result.metadata.tool_call_id
            record.result_summary = {"status": result.status, "scope": result.metadata.scope.value,
                "evidence_count": len(result.evidence)}
            state.tool_calls.append(record); results.append(result)
            state.actual_tool_executions += 1
            if result.status == "error":
                state.warnings.append(f"{name}: {record.error_code}")
            self._event(state, "node_end", name, {}, {"status": result.status,
                "error_code": record.error_code, "scope": result.metadata.scope.value}, node,
                status=result.status, error_code=record.error_code)
        return results

    def _execute_online_tools(self, state, plan, tools, parent):
        results = []; memo = {}
        prompt = (PROJECT / "tomato_fertigation_agent/prompts/online_tool_loop_v1.txt").read_text(encoding="utf-8")
        schemas = self.registry.export_function_schemas("openai_responses", tools)

        def execute(name, arguments, provider_call_id):
            index = len(state.tool_calls) + 1
            args = arguments if isinstance(arguments, dict) else {}
            record = ToolCallRecord(call_index=index, tool_name=name,
                initial_arguments=args, final_arguments=args,
                provider_call_id=provider_call_id,
                dispatch_source="MODEL_GENERATED_TOOL_CALL")
            state.nodes_executed.append(name)
            node = self._event(state, "node_start", name,
                {"argument_keys": sorted(args), "provider_call_id": provider_call_id}, {}, parent)
            try:
                validated=self.registry.validate_arguments(name,args)
                record.argument_valid_first_try=True; record.final_argument_valid=True
            except Exception:
                validated=arguments
            fingerprint=ToolExecutor._hash(name,validated if isinstance(validated,dict) else args)
            if fingerprint in memo:
                cached=memo[fingerprint]
                record.duplicate_blocked=True; record.reused_result=True
                record.actual_execution=False; record.result_status=cached.status
                record.error_code='DUPLICATE_TOOL_CALL'
                record.tool_call_id=cached.metadata.tool_call_id
                record.cached_from_tool_call_id=cached.metadata.tool_call_id
                record.result_summary=ToolResultFormatter.format(cached)
                state.tool_calls.append(record); state.duplicate_tool_attempts+=1
                state.reused_tool_results+=1
                self._event(state,'duplicate_guard',name,
                    {'provider_call_id':provider_call_id},{'reused':True,
                    'cached_tool_call_id':cached.metadata.tool_call_id},parent,
                    status='success',error_code='DUPLICATE_TOOL_CALL')
                return ToolExecutionResult(cached,executed=False,reused=True)
            result = self.registry.call(name, validated, trace_id=state.trace_id,
                parent_id=node, request_id=state.request_id)
            memo[fingerprint]=result
            valid = not (result.error and result.error.code.value == "INVALID_ARGUMENT")
            record.argument_valid_first_try = valid
            record.final_argument_valid = valid
            record.result_status = result.status
            record.error_code = result.error.code.value if result.error else None
            record.tool_call_id = result.metadata.tool_call_id
            record.result_summary = {"status": result.status,
                "scope": result.metadata.scope.value, "evidence_count": len(result.evidence)}
            state.tool_calls.append(record); results.append(result)
            state.actual_tool_executions += 1
            if result.status == "error":
                state.warnings.append(f"{name}: {record.error_code}")
            self._event(state, "node_end", name, {}, {"status": result.status,
                "error_code": record.error_code, "scope": result.metadata.scope.value,
                "provider_call_id": provider_call_id}, node,
                status=result.status, error_code=record.error_code)
            return ToolExecutionResult(result,executed=True,reused=False)

        remaining = max(1, self.config.max_provider_calls - state.llm_calls - self.config.reserve_synthesis_calls)
        try:
            loop = self.provider.execute_tool_loop(system_prompt=prompt,
                user_query=state.user_query, tools=schemas, execute=execute,
                max_tool_calls=self.config.max_tool_calls,
                max_provider_calls=remaining,
                max_argument_repairs=self.config.max_argument_repairs)
            state.llm_calls += loop.provider_calls
            state.input_tokens += loop.usage.input_tokens
            state.output_tokens += loop.usage.output_tokens
            state.provider_events.append({"purpose":"tool_loop",
                "response_ids":loop.response_ids,"models":loop.response_models,
                "statuses":loop.statuses,"provider_calls":loop.provider_calls,
                "tool_calls":len(loop.calls),"input_tokens":loop.usage.input_tokens,
                "output_tokens":loop.usage.output_tokens,
                "cached_input_tokens":loop.usage.cached_input_tokens,
                "reasoning_tokens":loop.usage.reasoning_tokens,"latency_ms":loop.latency_ms,
                "stop_reason":loop.stop_reason,
                "final_text":loop.final_text[:500]})
        except ProviderError as exc:
            state.provider_errors.append(exc.as_dict())
            state.warnings.append(f"Online tool loop stopped: {exc.code.value}")
        return results

    def _ensure_required_reliability(self,state,plan,results,parent):
        requirement=self.reliability_policy.for_workflow(plan.workflow)
        if not requirement.required:
            return
        if any(r.metadata.tool_name=='assess_prediction_reliability' and
               r.status in {'success','partial'} for r in results):
            return
        if state.actual_tool_executions>=self.config.max_tool_calls:
            state.required_tool_completion=False
            state.warnings.append('Required reliability assessment unavailable: tool execution budget exhausted')
            return
        args=self._arguments('assess_prediction_reliability',plan,results)
        result=self.registry.call('assess_prediction_reliability',args,
            trace_id=state.trace_id,parent_id=parent,request_id=state.request_id)
        record=ToolCallRecord(call_index=len(state.tool_calls)+1,
            tool_name='assess_prediction_reliability',initial_arguments=args,
            final_arguments=args,argument_valid_first_try=True,final_argument_valid=True,
            dispatch_source='WORKFLOW_DISPATCHED_TOOL',result_status=result.status,
            error_code=result.error.code.value if result.error else None,
            tool_call_id=result.metadata.tool_call_id,
            result_summary=ToolResultFormatter.format(result))
        state.tool_calls.append(record); results.append(result)
        state.actual_tool_executions+=1
        if result.status=='error':
            state.required_tool_completion=False
            state.warnings.append('Required reliability assessment failed')

    def _arguments(self, name, plan, results):
        e = plan.entities; date = e.get("date"); year = e.get("year")
        entity = {key: e[key] for key in ("plant_id", "view_id") if e.get(key)}
        if name == "get_growth_context":
            return {"year": year, "date": date, **entity}
        if name == "get_sensor_history":
            return {"end_date": date, "window_days": e.get("window_days", 7), **entity}
        if name == "predict_height_t7":
            return {"year": year, "date": date, "plant_id": e.get("plant_id")}
        if name == "analyze_rgb":
            return {"view_id": e.get("view_id"), "date": date, "requested_scope": "view"}
        if name == "find_similar_cases":
            scope = "plant" if e.get("plant_id") else "view"
            return {"scope": scope, "date": date, "plant_id" if scope == "plant" else "view_id":
                    e.get("plant_id") if scope == "plant" else e.get("view_id"),
                    "top_k": e.get("top_k", 5), "historical_only": True,
                    "retrieval_mode": "historical", "retrieval_policy": "cross_entity",
                    "exclude_same_entity": True}
        if name == "retrieve_water_fertilizer_knowledge":
            return {"query": state_query(plan), "top_k": self.config.knowledge_top_k}
        if name == "assess_prediction_reliability":
            rgb = any(r.metadata.tool_name == "analyze_rgb" for r in results)
            prediction = next((r for r in results if r.metadata.tool_name in ("predict_height_t7", "analyze_rgb")), None)
            case = next((r for r in results if r.metadata.tool_name == "find_similar_cases" and r.status != "error"), None)
            agreement = None
            if prediction and prediction.status != "error" and case:
                model_value = (prediction.data.get("prediction", {}).get("height_t7_cm") or
                    prediction.data.get("prediction", {}).get("future_view_mean_height_t7_cm"))
                case_value = case.data.get("summary", {}).get("similarity_weighted_height_t7_cm")
                if model_value is not None and case_value is not None:
                    delta = abs(float(model_value) - float(case_value))
                    agreement = "AGREE" if delta <= self.config.agree_cm else ("PARTIAL" if delta <= self.config.partial_cm else "DISAGREE")
            return {"model_name": "rgb_v05" if rgb else "height_v03_b0", "year": year,
                "requested_scope": "view" if rgb else "plant", "model_scope": "view" if rgb else "plant",
                "critical_features_complete": bool(prediction and prediction.status != "error"),
                "image_available": bool(prediction and prediction.status != "error") if rgb else None,
                "sensor_available": bool(prediction and prediction.status != "error") if not rgb else None,
                "case_retrieval_confidence": case.data.get("retrieval_confidence") if case else None,
                "case_model_agreement": agreement}
        return {}

    def _apply_relevance(self, state, results, parent):
        if not any(r.metadata.tool_name == "retrieve_water_fertilizer_knowledge" for r in results):
            return [], EvidenceSufficiency.NOT_APPLICABLE, {"candidates": 0, "accepted": 0}
        before = state.llm_calls
        remaining = max(0, self.config.max_provider_calls - state.llm_calls - self.config.reserve_synthesis_calls)
        accepted, sufficiency, report = self.relevance.apply(state.user_query, results, state, parent,
            max_provider_calls=remaining)
        state.relevance_calls += state.llm_calls - before
        return accepted, sufficiency, report

    def _synthesize(self, state, diagnosis):
        if state.llm_calls >= self.config.max_provider_calls:
            state.warnings.append("Provider call budget reached; deterministic structured diagnosis retained")
            return diagnosis
        try:
            response = self.provider.structured_completion(purpose="workflow_synthesis",
                system_prompt="Preserve every evidence ID, conflict, unsupported subtask and scope. Do not invent facts or quantities.",
                payload={"diagnosis": diagnosis.model_dump(mode="json")}, response_model=DiagnosisResult)
            state.llm_calls += 1; state.synthesis_calls += 1
            state.input_tokens += response.usage.input_tokens; state.output_tokens += response.usage.output_tokens
            state.provider_events.append(self._provider_event("workflow_synthesis", response))
            candidate = DiagnosisResult.model_validate(response.value)
            candidate_store=EvidenceStoreProxy(diagnosis.evidence)
            candidate_violations=self.claim_safety.validate(candidate.claims,candidate_store,diagnosis.conflicts)
            rebuilt_provenance=self.provenance.build(candidate.claims,diagnosis.evidence)
            if candidate_violations or not rebuilt_provenance.complete:
                state.warnings.append("Provider synthesis failed safety validation; deterministic diagnosis retained")
                return diagnosis
            return candidate.model_copy(update={
                'answerability':diagnosis.answerability,
                'workflow':diagnosis.workflow,
                'current_state':diagnosis.current_state,
                'sensor_context':diagnosis.sensor_context,
                'forecast':diagnosis.forecast,
                'historical_context':diagnosis.historical_context,
                'knowledge_context':diagnosis.knowledge_context,
                'conflicts':diagnosis.conflicts,
                'unsupported_subtasks':diagnosis.unsupported_subtasks,
                'overall_reliability':diagnosis.overall_reliability,
                'evidence_completeness':diagnosis.evidence_completeness,
                'evidence':diagnosis.evidence,
                'provenance':rebuilt_provenance,
                'limitations':diagnosis.limitations})
        except ProviderError as exc:
            state.provider_errors.append(exc.as_dict())
            state.warnings.append(f"Synthesis fallback: {exc.code.value}")
            return diagnosis
        except Exception as exc:
            state.warnings.append(f"Synthesis fallback: {type(exc).__name__}")
            return diagnosis

    def _event(self, state, event_type, component, input_summary, output_summary,
               parent=None, status="success", error_code=None):
        return self.trace.append(AgentTraceEvent(trace_id=state.trace_id, parent_event_id=parent,
            event_type=event_type, component=component, input_summary=input_summary,
            output_summary=output_summary, status=status, error_code=error_code))

    @staticmethod
    def _provider_event(purpose, response):
        return {"purpose":purpose,"response_id":response.response_id,
            "model":response.response_model,"status":response.status,
            "input_tokens":response.usage.input_tokens,
            "output_tokens":response.usage.output_tokens,
            "cached_input_tokens":response.usage.cached_input_tokens,
            "reasoning_tokens":response.usage.reasoning_tokens,
            "latency_ms":response.latency_ms}

    @staticmethod
    def _scope_trap(plan):
        return bool(plan.requested_scope and plan.requested_scope.value == "plant" and
                    plan.entities.get("view_id") and not plan.entities.get("plant_id"))

    @staticmethod
    def _unsupported(text):
        request, _, reason = text.partition(":")
        return UnsupportedSubtask(request=request.strip(), reason=(reason.strip() or "Unsupported by current validated capabilities"))

    @staticmethod
    def _first(store, kind):
        rows = store.by_type(kind)
        return rows[0] if rows else None

    def _current(self, store):
        row = self._first(store, EvidenceType.OBSERVATION)
        return row.value.get("phenotype", {}) if row else {}

    def _sensor(self, store):
        row = self._first(store, EvidenceType.SENSOR)
        return {"summary": row.value.get("summary", {}), "spatial_scope": row.value.get("spatial_scope", {})} if row else {}

    def _forecast(self, store):
        row = self._first(store, EvidenceType.PREDICTION)
        return row.value if row else {}

    def _historical(self, store):
        row = self._first(store, EvidenceType.HISTORICAL_CASE)
        return row.value if row else {}

    def _knowledge(self, store):
        return [{"evidence_id": row.evidence_id, **row.value} for row in store.by_type(EvidenceType.KNOWLEDGE)]

    @staticmethod
    def _risks(store, conflicts, level):
        risks = []
        if level == Confidence.LOW:
            risks.append("Overall evidence reliability is LOW; conclusions require cautious interpretation.")
        if any(c.status.value == "DISAGREE" for c in conflicts):
            risks.append("Model and historical-case evidence disagree.")
        cases = store.by_type(EvidenceType.HISTORICAL_CASE)
        if any(case.value.get("ood") for case in cases):
            risks.append("Historical retrieval reports out-of-distribution input.")
        if any(case.value.get("domain_warnings") for case in cases):
            risks.append("Some retrieved cases cross a year/season domain boundary.")
        return risks

    @staticmethod
    def _limitations(store, warnings, violations):
        values = [item for row in store.all() for item in row.limitations]
        values.extend(warnings); values.extend(violations)
        return list(dict.fromkeys(str(item) for item in values if item))[:20]

    @staticmethod
    def _summary(workflow, answerability, reliability):
        label = {"FULL": "核心证据齐全", "PARTIAL": "只能回答部分请求", "ABSTAIN": "核心证据不足，无法给出主要结论"}[answerability]
        return f"{workflow} 工作流完成：{label}；规则化可信度为 {reliability}。"

    @staticmethod
    def _provider_calls(state):
        return {"planner": state.planner_calls, "router": state.router_calls,
            "repair": state.repair_calls, "relevance": state.relevance_calls,
            "synthesis": state.synthesis_calls, "total": state.llm_calls,
            "provider_errors": len(state.provider_errors)}


class EvidenceStoreProxy:
    def __init__(self, records):
        self.records = {record.evidence_id: record for record in records}

    def get(self, evidence_id):
        return self.records.get(evidence_id)


def state_query(plan):
    return str(plan.entities.get("knowledge_query") or plan.entities.get("raw_query") or "番茄水肥与生长风险")


def build_workflow_agent(provider="mock", registry=None):
    return WorkflowAgent(registry=registry, provider=_provider(provider))
