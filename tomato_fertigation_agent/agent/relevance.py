from ..schemas.agent import EvidenceSufficiency, RelevanceJudgment, RelevanceLabel
from ..tracing.trace import AgentTraceEvent
from ..providers.errors import ProviderError


class RAGRelevanceGate:
    def __init__(self, provider, prompt, trace_writer, minimum_score=3.0):
        self.provider,self.prompt,self.trace,self.minimum_score=provider,prompt,trace_writer,minimum_score

    def apply(self, query, results, state, parent_event_id=None, max_provider_calls=None):
        candidates=[e for r in results if r.metadata.tool_name=='retrieve_water_fertilizer_knowledge' for e in r.evidence]
        if not candidates: return [],EvidenceSufficiency.NOT_APPLICABLE,{'candidates':0,'accepted':0,'rejected_score':0,'rejected_relevance':0}
        accepted=[]; report={'candidates':len(candidates),'accepted':0,'rejected_score':0,'rejected_relevance':0,'labels':{}}
        for evidence in candidates:
            if evidence.score is None or evidence.score < self.minimum_score:
                report['rejected_score']+=1; continue
            if max_provider_calls is not None and max_provider_calls <= 0:
                report.setdefault('not_judged_budget', 0); report['not_judged_budget'] += 1
                continue
            try:
                response=self.provider.structured_completion(purpose='relevance',system_prompt=self.prompt,
                    payload={'query':query,'evidence':evidence.model_dump(mode='json'),'minimum_score':self.minimum_score},
                    response_model=RelevanceJudgment)
            except ProviderError as exc:
                state.provider_errors.append(exc.as_dict())
                state.warnings.append(f'RAG relevance provider error: {exc.code.value}')
                report.setdefault('provider_errors', 0); report['provider_errors'] += 1
                continue
            if max_provider_calls is not None:
                max_provider_calls -= response.provider_calls
            state.llm_calls+=1; state.input_tokens+=response.usage.input_tokens; state.output_tokens+=response.usage.output_tokens
            state.provider_events.append({'purpose':'relevance','response_id':response.response_id,
                'model':response.response_model,'status':response.status,
                'input_tokens':response.usage.input_tokens,'output_tokens':response.usage.output_tokens,
                'cached_input_tokens':response.usage.cached_input_tokens,
                'reasoning_tokens':response.usage.reasoning_tokens,
                'latency_ms':response.latency_ms})
            judgment=RelevanceJudgment.model_validate(response.value); report['labels'][evidence.evidence_id]=judgment.label.value
            self.trace.append(AgentTraceEvent(trace_id=state.trace_id,parent_event_id=parent_event_id,event_type='rag_relevance',
                component='RAGRelevanceGate',input_summary={'evidence_id':evidence.evidence_id,'score':evidence.score},
                output_summary={'label':judgment.label.value,'reason':judgment.reason},
                latency_ms=response.latency_ms,input_tokens=response.usage.input_tokens,output_tokens=response.usage.output_tokens))
            if judgment.label != RelevanceLabel.IRRELEVANT:
                attrs={**evidence.attributes,'relevance_label':judgment.label.value,'relevance_reason':judgment.reason}
                accepted.append(evidence.model_copy(update={'attributes':attrs}))
            else: report['rejected_relevance']+=1
        report['accepted']=len(accepted)
        quantitative=bool(state.entities.get('requests_precise_quantity'))
        if not accepted: suff=EvidenceSufficiency.INSUFFICIENT
        elif quantitative and not any(str(e.attributes.get('numeric_policy','')).lower() in ('allowed','context_only') for e in accepted):
            suff=EvidenceSufficiency.INSUFFICIENT
        elif sum(e.attributes.get('relevance_label')=='RELEVANT' for e in accepted)>=2:
            suff=EvidenceSufficiency.SUFFICIENT
        else: suff=EvidenceSufficiency.PARTIAL
        if suff==EvidenceSufficiency.INSUFFICIENT:
            state.warnings.append('RAG evidence is insufficient for the requested conclusion')
            if quantitative: state.unsupported_requests.append('No retrieved evidence supports a quantitative irrigation/fertilizer adjustment')
        return accepted,suff,report
