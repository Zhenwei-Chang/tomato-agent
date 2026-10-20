from pathlib import Path
from time import perf_counter
import json
from ..schemas.agent import AgentState, Intent, RouterDecision, ToolPlanRepair
from ..tracing.trace import AgentTraceEvent


class StructuredRouter:
    def __init__(self, provider, prompt_path: Path, trace_writer, registry,
                 repair_prompt_path: Path, max_tool_plan_repairs=1):
        self.provider, self.prompt_path, self.trace = provider, prompt_path, trace_writer
        self.registry = registry
        self.repair_prompt_path = repair_prompt_path
        self.max_tool_plan_repairs = max(0, int(max_tool_plan_repairs))

    def route(self, state: AgentState, parent_event_id=None):
        started=perf_counter(); catalog=self.registry.router_catalog()
        prompt=self.prompt_path.read_text(encoding='utf-8') + (
            '\n\nExecutable tool registry (single source of truth):\n' +
            json.dumps(catalog,ensure_ascii=False))
        response=self.provider.structured_completion(purpose='router',system_prompt=prompt,
            payload={'user_query':state.user_query,'registry_contract_version':self.registry.CONTRACT_VERSION,
                     'registry_catalog':catalog},response_model=RouterDecision)
        state.llm_calls += 1; state.input_tokens += response.usage.input_tokens; state.output_tokens += response.usage.output_tokens
        state.provider_events.append({'purpose':'router','response_id':response.response_id,
            'model':response.response_model,'status':response.status,
            'input_tokens':response.usage.input_tokens,'output_tokens':response.usage.output_tokens,
            'cached_input_tokens':response.usage.cached_input_tokens,
            'reasoning_tokens':response.usage.reasoning_tokens,
            'latency_ms':response.latency_ms})
        decision=RouterDecision.model_validate(response.value)
        state.canonical_tool_names=list(self.registry.canonical_names)
        require_nonempty=decision.intent != Intent.UNSUPPORTED_REQUEST
        validation=self.registry.validate_tool_names(decision.required_tools,
            require_nonempty=require_nonempty)
        state.tool_plan_valid_before_repair=validation['valid']
        state.invalid_tool_names=list(validation['unknown'])
        repair_event=None
        if not validation['valid'] and self.max_tool_plan_repairs:
            state.tool_plan_repair_attempted=True
            state.tool_plan_repair_count=1
            repair_prompt=self.repair_prompt_path.read_text(encoding='utf-8')
            repaired=self.provider.structured_completion(purpose='tool_plan_repair',
                system_prompt=repair_prompt,payload={'user_query':state.user_query,
                    'intent':decision.intent.value,'entities':decision.entities,
                    'requested_scope':decision.requested_scope.value if decision.requested_scope else None,
                    'invalid_required_tools':decision.required_tools,
                    'validation_errors':{k:validation[k] for k in ('unknown','duplicates','empty')},
                    'registry_contract_version':self.registry.CONTRACT_VERSION,
                    'registry_catalog':catalog},response_model=ToolPlanRepair)
            state.llm_calls += 1; state.input_tokens += repaired.usage.input_tokens
            state.output_tokens += repaired.usage.output_tokens
            state.provider_events.append({'purpose':'tool_plan_repair','response_id':repaired.response_id,
                'model':repaired.response_model,'status':repaired.status,
                'input_tokens':repaired.usage.input_tokens,'output_tokens':repaired.usage.output_tokens,
                'cached_input_tokens':repaired.usage.cached_input_tokens,
                'reasoning_tokens':repaired.usage.reasoning_tokens,'latency_ms':repaired.latency_ms})
            repair=ToolPlanRepair.model_validate(repaired.value)
            repaired_validation=self.registry.validate_tool_names(repair.required_tools,
                require_nonempty=require_nonempty)
            state.tool_plan_repair_success=repaired_validation['valid']
            safe_tools=repair.required_tools if repaired_validation['valid'] else []
            decision=decision.model_copy(update={'required_tools':safe_tools,
                'reasoning_code':repair.reasoning_code if repaired_validation['valid'] else 'TOOL_PLAN_REPAIR_FAILED'})
            repair_event=self.trace.append(AgentTraceEvent(trace_id=state.trace_id,
                parent_event_id=parent_event_id,event_type='tool_plan_repair',component='StructuredRouter',
                input_summary={'invalid_tools':validation['unknown'],'intent':decision.intent.value},
                output_summary={'success':state.tool_plan_repair_success,'tools':safe_tools,
                    'repair_count':state.tool_plan_repair_count},latency_ms=repaired.latency_ms,
                input_tokens=repaired.usage.input_tokens,output_tokens=repaired.usage.output_tokens,
                status='success' if state.tool_plan_repair_success else 'error',
                error_code=None if state.tool_plan_repair_success else 'INVALID_TOOL_PLAN'))
            if not state.tool_plan_repair_success:
                state.warnings.append('Tool plan repair failed registry validation; no tool executed')
        state.intent=decision.intent; state.entities=decision.entities; state.requested_scope=decision.requested_scope
        state.planned_tools=list(decision.required_tools); state.unsupported_requests.extend(decision.unsupported_requests)
        event=AgentTraceEvent(trace_id=state.trace_id,parent_event_id=repair_event or parent_event_id,event_type='router',component='StructuredRouter',
            input_summary={'query_length':len(state.user_query),'registry_contract_version':self.registry.CONTRACT_VERSION},
            output_summary={'intent':decision.intent.value,'tools':decision.required_tools,
            'valid_before_repair':state.tool_plan_valid_before_repair,
            'repair_attempted':state.tool_plan_repair_attempted,'repair_success':state.tool_plan_repair_success,
            'requested_scope':decision.requested_scope.value if decision.requested_scope else None},
            latency_ms=(perf_counter()-started)*1000,input_tokens=response.usage.input_tokens,output_tokens=response.usage.output_tokens)
        return decision,self.trace.append(event)
