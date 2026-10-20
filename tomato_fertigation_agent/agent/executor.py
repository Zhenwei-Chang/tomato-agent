from __future__ import annotations
from hashlib import sha256
from time import perf_counter
import json
from pydantic import ValidationError
from ..schemas.agent import AgentState, PlannedToolCall, RouterDecision, ToolCallRecord, ToolPlan
from ..tracing.trace import AgentTraceEvent


class ToolResultFormatter:
    OMIT = {'embedding','daily','retrieved_chunks'}

    @classmethod
    def format(cls, result):
        if result.metadata.tool_name=='find_similar_cases' and result.status!='error':
            data={'query_case':result.data.get('query_case'),'summary':result.data.get('summary'),
                  'matches':[{'case_id':m['case_id'],'scope':m['scope'],'similarity':m['similarity'],
                              'historical_outcome':m['historical_outcome'],'domain_warning':m['domain_warning']} for m in result.data.get('matches',[])],
                  'retrieval_confidence':result.data.get('retrieval_confidence'),'ood':result.data.get('ood')}
            return {'status':result.status,'scope':result.metadata.scope.value,'confidence':result.metadata.confidence.value,
                    'data':data,'warnings':result.warnings,'evidence_ids':[e.evidence_id for e in result.evidence],
                    'limitations':result.metadata.limitations,'error_code':None}
        data={k:v for k,v in result.data.items() if k not in cls.OMIT}
        if len(json.dumps(data,ensure_ascii=False,default=str)) > 3000:
            data={'keys':sorted(result.data),'prediction':result.data.get('prediction'),
                  'data_quality':result.data.get('data_quality')}
        return {'status':result.status,'scope':result.metadata.scope.value,'confidence':result.metadata.confidence.value,
                'data':data,'warnings':result.warnings,'evidence_ids':[e.evidence_id for e in result.evidence],
                'limitations':result.metadata.limitations,
                'error_code':result.error.code.value if result.error else None}


class ToolExecutor:
    def __init__(self, registry, provider, repair_prompt, trace_writer, max_calls=5, max_repairs=2):
        self.registry,self.provider,self.repair_prompt,self.trace=registry,provider,repair_prompt,trace_writer
        self.max_calls,self.max_repairs=max_calls,max_repairs

    @staticmethod
    def _hash(name,args):
        body=json.dumps({'tool':name,'arguments':args},sort_keys=True,ensure_ascii=False,separators=(',',':'))
        return sha256(body.encode('utf-8')).hexdigest()

    @staticmethod
    def _dynamic_reliability(args, route, results):
        args=dict(args); rgb=(route.intent.value=='RGB_ANALYSIS' or
            any(r.metadata.tool_name=='analyze_rgb' for r in results))
        predecessor=next((r for r in reversed(results) if r.metadata.tool_name in ('predict_height_t7','analyze_rgb')),None)
        args.update(model_name='rgb_v05' if rgb else 'height_v03_b0',model_scope='view' if rgb else 'plant',
                    requested_scope=(route.requested_scope.value if route.requested_scope else ('view' if rgb else 'plant')),
                    critical_features_complete=bool(predecessor and predecessor.status in ('success','partial')))
        if route.entities.get('year'): args['year']=route.entities['year']
        if rgb: args['image_available']=bool(predecessor and predecessor.status in ('success','partial')); args.pop('sensor_available',None)
        else: args['sensor_available']=bool(predecessor and predecessor.status in ('success','partial')); args.pop('image_available',None)
        case_result=next((r for r in reversed(results) if r.metadata.tool_name=='find_similar_cases' and r.status in ('success','partial')),None)
        if case_result:
            args['case_retrieval_confidence']=case_result.data.get('retrieval_confidence')
            model_result=next((r for r in reversed(results) if r.metadata.tool_name=='predict_height_t7' and r.status in ('success','partial')),None)
            if model_result:
                ml=float(model_result.data['prediction']['height_t7_cm'])
                case=case_result.data.get('summary',{}).get('similarity_weighted_height_t7_cm')
                if case is not None:
                    difference=abs(ml-float(case))
                    args['case_model_agreement']='AGREE' if difference<=10 else ('PARTIAL' if difference<=20 else 'DISAGREE')
        return {k:v for k,v in args.items() if v is not None}

    def execute(self, plan: ToolPlan, route: RouterDecision, state: AgentState, parent_event_id=None):
        results=[]; seen={}
        if len(plan.calls)>self.max_calls:
            state.warnings.append(f'Tool plan truncated at MAX_TOOL_CALLS={self.max_calls}')
        for index, planned in enumerate(plan.calls[:self.max_calls],start=1):
            started=perf_counter(); initial=dict(planned.arguments)
            if planned.tool_name=='assess_prediction_reliability':
                initial=self._dynamic_reliability(initial,route,results)
            record=ToolCallRecord(call_index=index,tool_name=planned.tool_name,initial_arguments=initial)
            arguments=initial; validation_error=None
            for attempt in range(self.max_repairs+1):
                try:
                    arguments=self.registry.validate_arguments(planned.tool_name,arguments)
                    record.final_argument_valid=True; record.argument_valid_first_try=(attempt==0); record.repair_count=attempt
                    break
                except (ValidationError,ValueError) as exc:
                    validation_error=exc
                    self.trace.append(AgentTraceEvent(trace_id=state.trace_id,parent_event_id=parent_event_id,
                        event_type='argument_validation',component='ToolExecutor',input_summary={'tool':planned.tool_name,'argument_keys':sorted(arguments)},
                        output_summary={'valid':False,'attempt':attempt},status='error',error_code='INVALID_ARGUMENT'))
                    if attempt>=self.max_repairs: break
                    repair=self.provider.structured_completion(purpose='argument_repair',system_prompt=self.repair_prompt,
                        payload={'user_query':state.user_query,'tool_name':planned.tool_name,
                                 'tool_schema':self.registry.definitions[planned.tool_name].input_model.model_json_schema(),
                                 'invalid_arguments':arguments,'validation_error':str(exc)[:1000],
                                 'route':route.model_dump(mode='json')},response_model=PlannedToolCall)
                    state.llm_calls+=1; state.input_tokens+=repair.usage.input_tokens; state.output_tokens+=repair.usage.output_tokens
                    arguments=dict(repair.value.arguments)
            record.final_arguments=arguments if record.final_argument_valid else None
            if not record.final_argument_valid:
                record.repair_count=self.max_repairs; record.error_code='ARGUMENT_REPAIR_FAILED'; record.result_status='error'
                state.warnings.append(f'{planned.tool_name}: argument repair failed after {self.max_repairs} attempts')
                state.tool_calls.append(record); continue
            fingerprint=self._hash(planned.tool_name,arguments)
            if fingerprint in seen:
                cached=seen[fingerprint]
                record.duplicate_blocked=True; record.reused_result=True
                record.actual_execution=False; record.result_status=cached.status
                record.error_code='DUPLICATE_TOOL_CALL'
                record.cached_from_tool_call_id=cached.metadata.tool_call_id
                record.tool_call_id=cached.metadata.tool_call_id
                record.result_summary=ToolResultFormatter.format(cached)
                state.duplicate_tool_attempts+=1; state.reused_tool_results+=1
                state.warnings.append(f'Duplicate tool call reused: {planned.tool_name}')
                state.tool_calls.append(record)
                self.trace.append(AgentTraceEvent(trace_id=state.trace_id,parent_event_id=parent_event_id,event_type='duplicate_guard',
                    component='ToolExecutor',input_summary={'tool':planned.tool_name},
                    output_summary={'reused':True,'cached_tool_call_id':cached.metadata.tool_call_id},
                    status='success',error_code='DUPLICATE_TOOL_CALL'))
                continue
            result=self.registry.call(planned.tool_name,arguments,trace_id=state.trace_id,parent_id=parent_event_id,request_id=state.request_id)
            seen[fingerprint]=result
            record.result_status=result.status; record.error_code=result.error.code.value if result.error else None
            record.tool_call_id=result.metadata.tool_call_id; record.result_summary=ToolResultFormatter.format(result)
            state.tool_calls.append(record); results.append(result)
            state.actual_tool_executions+=1
            self.trace.append(AgentTraceEvent(trace_id=state.trace_id,parent_event_id=parent_event_id,event_type='tool_execution',
                component=planned.tool_name,input_summary={'argument_keys':sorted(arguments)},
                output_summary={'status':result.status,'scope':result.metadata.scope.value,'error_code':record.error_code,
                                'evidence_count':len(result.evidence)},latency_ms=(perf_counter()-started)*1000,
                status=result.status,error_code=record.error_code))
        return results


class SingleToolAgent:
    def __init__(self, executor): self.executor=executor
    def execute(self, plan, route, state, parent_event_id=None):
        if len(plan.calls)>1: raise ValueError('SingleToolAgent accepts one call')
        return self.executor.execute(plan,route,state,parent_event_id)


class ControlledMultiToolAgent:
    def __init__(self, executor): self.executor=executor
    def execute(self, plan, route, state, parent_event_id=None):
        return self.executor.execute(plan,route,state,parent_event_id)
