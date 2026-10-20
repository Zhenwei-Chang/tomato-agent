from __future__ import annotations
from pathlib import Path
from time import perf_counter
from ..agent_config import AgentConfig, build_online_provider
from ..config import PROJECT
from ..providers import MockLLMProvider, ProviderError, ProviderErrorCode
from ..providers import ToolExecutionResult
from ..registry import ToolRegistry
from ..schemas.agent import (AgentAnswer, AgentRun, AgentState,
                             EvidenceSufficiency, PlannedToolCall,
                             ToolCallRecord, ToolPlan)
from ..tracing.trace import AgentTraceEvent, AgentTraceWriter
from .evidence import EvidenceAggregator
from .evidence_assembler import EvidenceAssembler
from .executor import (ControlledMultiToolAgent, SingleToolAgent, ToolExecutor,
                       ToolResultFormatter)
from .relevance import RAGRelevanceGate
from .renderer import render_answer
from .reliability_policy import ReliabilityRequirementMatrix
from .request_contract import RequestContractBuilder
from .router import StructuredRouter
from .safety import AnswerSafetyPipeline
from .status import AnswerStatusResolver


def _prompt(name):
    return PROJECT / 'tomato_fertigation_agent/prompts' / name


def build_provider(config):
    if config.provider=='mock': return MockLLMProvider(config.mock_version,config.model)
    if config.provider in {'openai','deepseek'}:
        return build_online_provider(config.provider)
    raise ValueError(f'Unsupported provider: {config.provider}')


class ToolCallingAgent:
    def __init__(self, config=None, registry=None, provider=None):
        self.config=config or AgentConfig.load(); self.registry=registry or ToolRegistry()
        self.provider=provider or build_provider(self.config)
        self.trace=AgentTraceWriter(self.registry.settings.output)
        self.router=StructuredRouter(self.provider,_prompt(self.config.prompt_versions['router_prompt']),self.trace,
            self.registry,_prompt(self.config.prompt_versions['tool_plan_repair_prompt']),
            self.config.max_tool_plan_repairs)
        repair=_prompt(self.config.prompt_versions['repair_prompt']).read_text(encoding='utf-8')
        self.executor=ToolExecutor(self.registry,self.provider,repair,self.trace,self.config.max_tool_calls,self.config.max_argument_repairs)
        relevance=_prompt(self.config.prompt_versions['relevance_prompt']).read_text(encoding='utf-8')
        self.relevance=RAGRelevanceGate(self.provider,relevance,self.trace,self.config.minimum_retrieval_score)
        self.aggregator=EvidenceAggregator(); self.assembler=EvidenceAssembler()
        self.safety=AnswerSafetyPipeline(); self.status_resolver=AnswerStatusResolver()
        self.reliability_policy=ReliabilityRequirementMatrix()
        self.request_contract_builder=RequestContractBuilder(self.reliability_policy)
        self.synthesis_prompt=_prompt(self.config.prompt_versions['synthesis_prompt']).read_text(encoding='utf-8')

    def ask(self, query, *, debug=False, trace_id=None):
        started=perf_counter(); state=AgentState(user_query=query,**({'trace_id':trace_id} if trace_id else {}))
        request_event=self.trace.append(AgentTraceEvent(trace_id=state.trace_id,event_type='request',component='ToolCallingAgent',
            input_summary={'query_length':len(query)},output_summary={'request_id':state.request_id}))
        route,router_event=self.router.route(state,request_event)
        contract=self.request_contract_builder.build(query,route)
        state.request_contract=contract
        # Replace untrusted provider capability notes with explicit user tasks.
        state.unsupported_requests=self.request_contract_builder.explicit_unsupported(contract)
        plan=ToolPlan()
        if route.required_tools:
            if (self.provider.name in {'openai','deepseek'} and
                    not getattr(self.provider,'allow_external_tool_data',True)):
                raise ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE,
                    'External ToolResult transmission requires explicit consent',
                    required_flag='--allow-local-tool-data')
            if self.provider.name in {'openai','deepseek'}:
                plan,results,plan_event=self._online_tool_loop(query,route,state,router_event)
            else:
                plan_response=self.provider.tool_completion(system_prompt=(
                    'Select only the required registered functions. Generate JSON arguments from the user query. '
                    'Never invent IDs, dates, measurements, or unsupported scope.'),user_query=query,route=route,
                    tools=self.registry.export_function_schemas('openai',route.required_tools),response_model=ToolPlan)
                state.llm_calls+=1; state.input_tokens+=plan_response.usage.input_tokens; state.output_tokens+=plan_response.usage.output_tokens
                plan=ToolPlan.model_validate(plan_response.value)
                plan_event=self.trace.append(AgentTraceEvent(trace_id=state.trace_id,parent_event_id=router_event,event_type='tool_plan',
                    component='ProviderToolCalling',input_summary={'required_tools':route.required_tools},
                    output_summary={'planned_tools':[c.tool_name for c in plan.calls]},latency_ms=plan_response.latency_ms,
                    input_tokens=plan_response.usage.input_tokens,output_tokens=plan_response.usage.output_tokens))
                runner=SingleToolAgent(self.executor) if len(plan.calls)<=1 else ControlledMultiToolAgent(self.executor)
                results=runner.execute(plan,route,state,plan_event)
        else:
            results=[]; plan_event=router_event
        self._ensure_required_reliability(route,state,results,plan_event)
        remaining=(max(0,self.config.max_provider_calls-state.llm_calls-1)
                   if self.provider.name in {'openai','deepseek'} else None)
        accepted,sufficiency,relevance_report=self.relevance.apply(query,results,state,plan_event,
            max_provider_calls=remaining)
        if route.intent.value=='KNOWLEDGE_QA' and sufficiency==EvidenceSufficiency.NOT_APPLICABLE:
            sufficiency=EvidenceSufficiency.INSUFFICIENT
            state.warnings.append('Knowledge retrieval returned no usable evidence')
        assembly=self.assembler.assemble(results,accepted)
        aggregation=self.aggregator.aggregate(results,accepted,sufficiency,state,
            assembly.registry,assembly.ids_by_tool_call,assembly.reliability_ids)
        state.facts=aggregation.facts; state.predictions=aggregation.predictions
        state.knowledge_evidence_ids=[e.evidence_id for e in accepted]
        state.historical_case_ids=[c.case_id for c in aggregation.historical_cases]
        state.case_model_agreement=aggregation.case_model_agreement
        state.evidence_sufficiency=sufficiency; state.reliability=aggregation.confidence
        aggregation_event=self.trace.append(AgentTraceEvent(trace_id=state.trace_id,parent_event_id=plan_event,
            event_type='evidence_aggregation',component='EvidenceAggregator',
            input_summary={'tool_results':len(results)},output_summary={'facts':len(aggregation.facts),
            'predictions':len(aggregation.predictions),'historical_cases':len(aggregation.historical_cases),
            'case_model_agreement':aggregation.case_model_agreement,
            'registered_evidence':len(assembly.registry),'accepted_evidence':len(accepted),
            'sufficiency':sufficiency.value}))
        synthesis=self.provider.structured_completion(purpose='synthesis',system_prompt=self.synthesis_prompt,
            payload={'intent':route.intent.value,'requested_scope':route.requested_scope.value if route.requested_scope else None,
                     'aggregation':aggregation.model_dump(mode='json')},response_model=AgentAnswer)
        state.llm_calls+=1; state.input_tokens+=synthesis.usage.input_tokens; state.output_tokens+=synthesis.usage.output_tokens
        state.provider_events.append({'purpose':'synthesis','response_id':synthesis.response_id,
            'model':synthesis.response_model,'status':synthesis.status,
            'input_tokens':synthesis.usage.input_tokens,'output_tokens':synthesis.usage.output_tokens,
            'cached_input_tokens':synthesis.usage.cached_input_tokens,
            'reasoning_tokens':synthesis.usage.reasoning_tokens,
            'latency_ms':synthesis.latency_ms})
        answer=AgentAnswer.model_validate(synthesis.value)
        answer,pre_validation=self.assembler.finalize(answer,aggregation)
        answer,violations=self.safety.apply(answer,route.requested_scope,results)
        answer,validation=self.assembler.finalize(answer,aggregation,restore=False)
        answer,status_decision=self.status_resolver.resolve(
            answer,route,state.tool_calls,user_query=state.user_query,
            request_contract=state.request_contract)
        state.evidence_collected_count=validation.collected
        state.evidence_referenced_count=validation.referenced
        state.missing_evidence_references=len(validation.missing_references)
        state.invalid_evidence_references=len(validation.invalid_references)
        state.semantic_evidence_mismatches=len(validation.semantic_mismatches)
        state.required_tool_completion=not (status_decision.missing_required_tools or
            status_decision.failed_required_tools or status_decision.unsatisfied_policy_subtasks)
        if validation.missing_references or validation.invalid_references or validation.semantic_mismatches:
            violations=list(dict.fromkeys(violations+['EVIDENCE_CONTRACT_VIOLATION']))
        state.safety_violations=violations; state.final_structured_answer=answer
        state.warnings=list(dict.fromkeys(state.warnings+answer.warnings)); state.unsupported_requests=answer.unsupported_requests
        state.elapsed_ms=(perf_counter()-started)*1000
        self.trace.append(AgentTraceEvent(trace_id=state.trace_id,parent_event_id=aggregation_event,event_type='final_synthesis',
            component='StructuredAnswer',input_summary={'facts':len(aggregation.facts),'predictions':len(aggregation.predictions)},
            output_summary={'status':answer.status,'confidence':answer.confidence.value,'safety_violations':violations},
            latency_ms=synthesis.latency_ms,status='error' if violations else answer.status,
            error_code=violations[0] if violations else None,input_tokens=synthesis.usage.input_tokens,output_tokens=synthesis.usage.output_tokens))
        debug_payload=None
        if debug:
            debug_payload={'route':route.model_dump(mode='json'),'plan':plan.model_dump(mode='json'),
                'tool_calls':[r.model_dump(mode='json') for r in state.tool_calls],
                'relevance_gate':relevance_report,'safety_violations':violations,
                'evidence_validation':validation.__dict__,
                'status_decision':status_decision.__dict__,
                'provider_usage':{'llm_calls':state.llm_calls,'input_tokens':state.input_tokens,'output_tokens':state.output_tokens}}
        return AgentRun(state=state,answer=answer,rendered=render_answer(answer),
            provider={'name':self.provider.name,'model':self.provider.model,'profile':self.config.profile,
                       'online':self.provider.name!='mock'},debug=debug_payload)

    def _online_tool_loop(self, query, route, state, parent_event_id):
        results=[]; planned=[]; memo={}
        prompt=(PROJECT/'tomato_fertigation_agent/prompts/online_tool_loop_v1.txt').read_text(encoding='utf-8')

        def execute(name,arguments,provider_call_id):
            args=arguments if isinstance(arguments,dict) else {}
            if name=='assess_prediction_reliability':
                args=ToolExecutor._dynamic_reliability(args,route,results)
            record=ToolCallRecord(call_index=len(state.tool_calls)+1,tool_name=name,
                initial_arguments=args,final_arguments=args,provider_call_id=provider_call_id,
                dispatch_source='MODEL_GENERATED_TOOL_CALL')
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
                planned.append(PlannedToolCall(tool_name=name,arguments=args))
                self.trace.append(AgentTraceEvent(trace_id=state.trace_id,parent_event_id=parent_event_id,
                    event_type='duplicate_guard',component=name,
                    input_summary={'provider_call_id':provider_call_id},
                    output_summary={'reused':True,'cached_tool_call_id':cached.metadata.tool_call_id},
                    status='success',error_code='DUPLICATE_TOOL_CALL'))
                return ToolExecutionResult(cached,executed=False,reused=True)
            result=self.registry.call(name,validated,trace_id=state.trace_id,
                parent_id=parent_event_id,request_id=state.request_id)
            memo[fingerprint]=result
            record.result_status=result.status; record.error_code=result.error.code.value if result.error else None
            record.tool_call_id=result.metadata.tool_call_id; record.result_summary=ToolResultFormatter.format(result)
            state.tool_calls.append(record); results.append(result)
            state.actual_tool_executions+=1
            planned.append(PlannedToolCall(tool_name=name,arguments=args))
            self.trace.append(AgentTraceEvent(trace_id=state.trace_id,parent_event_id=parent_event_id,
                event_type='tool_execution',component=name,
                input_summary={'argument_keys':sorted(args),'provider_call_id':provider_call_id},
                output_summary={'status':result.status,'scope':result.metadata.scope.value,
                    'error_code':record.error_code,'evidence_count':len(result.evidence)},
                status=result.status,error_code=record.error_code))
            return ToolExecutionResult(result,executed=True,reused=False)

        remaining=max(1,self.config.max_provider_calls-state.llm_calls-1)
        loop=self.provider.execute_tool_loop(system_prompt=prompt,user_query=query,
            tools=self.registry.export_function_schemas('openai_responses',route.required_tools),
            execute=execute,max_tool_calls=self.config.max_tool_calls,max_provider_calls=remaining,
            max_argument_repairs=self.config.max_argument_repairs)
        state.llm_calls+=loop.provider_calls; state.input_tokens+=loop.usage.input_tokens
        state.output_tokens+=loop.usage.output_tokens
        state.provider_events.append({'purpose':'tool_loop','response_ids':loop.response_ids,
            'models':loop.response_models,'statuses':loop.statuses,'provider_calls':loop.provider_calls,
            'tool_calls':len(loop.calls),'input_tokens':loop.usage.input_tokens,
            'output_tokens':loop.usage.output_tokens,
            'cached_input_tokens':loop.usage.cached_input_tokens,
            'reasoning_tokens':loop.usage.reasoning_tokens,'latency_ms':loop.latency_ms,
            'stop_reason':loop.stop_reason,'final_text':loop.final_text[:500]})
        event=self.trace.append(AgentTraceEvent(trace_id=state.trace_id,parent_event_id=parent_event_id,
            event_type='tool_plan',component='ResponsesFunctionCalling',
            input_summary={'required_tools':route.required_tools},
            output_summary={'planned_tools':[call.tool_name for call in planned],
                'provider_calls':loop.provider_calls},latency_ms=loop.latency_ms,
            input_tokens=loop.usage.input_tokens,output_tokens=loop.usage.output_tokens))
        return ToolPlan(calls=planned),results,event

    def _ensure_required_reliability(self,route,state,results,parent_event_id):
        requirement=self.reliability_policy.for_intent(route.intent)
        if not requirement.required:
            return
        if any(r.metadata.tool_name=='assess_prediction_reliability' and
               r.status in {'success','partial'} for r in results):
            return
        if state.actual_tool_executions>=self.config.max_tool_calls:
            state.warnings.append('Required reliability assessment unavailable: tool execution budget exhausted')
            state.required_tool_completion=False
            return
        args=ToolExecutor._dynamic_reliability({},route,results)
        result=self.registry.call('assess_prediction_reliability',args,
            trace_id=state.trace_id,parent_id=parent_event_id,request_id=state.request_id)
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


def build_agent(profile=None, provider=None):
    return ToolCallingAgent(config=AgentConfig.load(profile=profile,provider=provider))
