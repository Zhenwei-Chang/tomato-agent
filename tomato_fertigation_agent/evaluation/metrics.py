from collections import Counter, defaultdict
from statistics import mean, median
import math
from .bad_cases import classify_failures
from ..schemas.eval import CaseResult


def _subset(expected, actual):
    if actual is None: return False
    return all(k in actual and actual[k]==v for k,v in expected.items())


def _argument_check(case, records, final):
    if not case.expected_arguments: return True
    by_name={record.tool_name:record for record in records}
    for tool,expected in case.expected_arguments.items():
        if tool not in by_name: return False
        actual=by_name[tool].final_arguments if final else by_name[tool].initial_arguments
        if not _subset(expected,actual): return False
    return True


def evaluate_case(case, run):
    actual_tools=[r.tool_name for r in run.state.tool_calls]
    errors=[r.error_code for r in run.state.tool_calls if r.error_code]
    intent_correct=run.state.intent and run.state.intent.value==case.expected_intent.value
    selection=actual_tools==case.expected_tools
    sequence=all(tool in actual_tools for tool in case.expected_tools) and [x for x in actual_tools if x in case.expected_tools]==case.expected_tools
    first=_argument_check(case,run.state.tool_calls,False); post=_argument_check(case,run.state.tool_calls,True)
    answer=run.answer
    if case.expected_behavior=='success':
        expected_records=[r for r in run.state.tool_calls if r.tool_name in case.expected_tools]
        task=bool(expected_records) and all(r.result_status in ('success','partial') for r in expected_records) and answer.status in ('success','partial')
    elif case.expected_behavior=='data_not_found':
        task='DATA_NOT_FOUND' in errors and not answer.predictions
    elif case.expected_behavior=='no_reliable_cases':
        task='NO_RELIABLE_CASES' in errors and not answer.historical_cases
    elif case.expected_behavior=='unsupported':
        task=answer.status=='unsupported' and bool(answer.unsupported_requests) and not answer.predictions
    else:
        task=answer.evidence_sufficiency.value=='INSUFFICIENT' and bool(answer.unsupported_requests)
    scope_safe=not any(v in ('RGB_SCOPE_ESCALATION','HEIGHT_SCOPE_ESCALATION','VIEW_RESULT_CANNOT_SATISFY_PLANT_REQUEST','CASE_SCOPE_ESCALATION') for v in run.state.safety_violations)
    no_hallucinated='UNSUPPORTED_NUMERICAL_CLAIM' not in run.state.safety_violations
    knowledge_expected='retrieve_water_fertilizer_knowledge' in case.expected_tools
    cited={eid for x in answer.agronomic_interpretation+answer.recommendations for eid in x.evidence_ids}
    available={e.evidence_id for e in answer.evidence}
    if case.expected_evidence_ids is not None:
        evidence_grounded=available==set(case.expected_evidence_ids) and cited.issubset(available)
    else:
        evidence_grounded=(not knowledge_expected) or (answer.evidence_sufficiency.value=='INSUFFICIENT') or (bool(available) and cited.issubset(available))
    if case.expected_evidence_sufficiency is not None:
        evidence_grounded=evidence_grounded and answer.evidence_sufficiency.value==case.expected_evidence_sufficiency
    no_unsupported='UNSUPPORTED_NUMERICAL_CLAIM' not in run.state.safety_violations
    checks={'intent_correct':bool(intent_correct),'tool_selection_correct':selection,'tool_sequence_correct':sequence,
            'argument_correct_first_pass':first,'argument_correct_after_repair':post,'task_success':task,
            'scope_safe':scope_safe,'no_hallucinated_value':no_hallucinated,
            'evidence_grounded':evidence_grounded,'no_unsupported_claim':no_unsupported,
            'answer_schema_valid':True}
    failures=classify_failures(case,run,checks)
    metrics={'tool_calls':len(run.state.tool_calls),'llm_calls':run.state.llm_calls,
             'repair_count':sum(r.repair_count for r in run.state.tool_calls),
             'needed_repair':any(r.repair_count>0 for r in run.state.tool_calls),
             'repair_success':any(r.repair_count>0 and r.final_argument_valid for r in run.state.tool_calls),
             'latency_ms':run.state.elapsed_ms,'input_tokens':run.state.input_tokens,'output_tokens':run.state.output_tokens}
    required_for_pass={k:v for k,v in checks.items() if k!='argument_correct_first_pass'}
    return CaseResult(case_id=case.case_id,intent=case.expected_intent.value,difficulty=case.difficulty,
        checks=checks,metrics=metrics,failures=failures,
        actual={'intent':run.state.intent.value if run.state.intent else None,'tools':actual_tools,'status':answer.status,
                'evidence_sufficiency':answer.evidence_sufficiency.value,'summary':answer.summary,
                'trace_id':run.state.trace_id},passed=all(required_for_pass.values()))


def _rate(rows,key): return mean(float(r.checks[key]) for r in rows) if rows else None


def aggregate_metrics(results):
    rows=list(results); lat=sorted(float(r.metrics['latency_ms']) for r in rows)
    def percentile(p):
        if not lat: return None
        idx=(len(lat)-1)*p; lo=math.floor(idx); hi=math.ceil(idx)
        return lat[lo] if lo==hi else lat[lo]+(lat[hi]-lat[lo])*(idx-lo)
    needed=[r for r in rows if r.metrics['needed_repair']]
    summary={'n_cases':len(rows),'passed':sum(r.passed for r in rows),
        'intent_accuracy':_rate(rows,'intent_correct'),'tool_selection_accuracy':_rate(rows,'tool_selection_correct'),
        'tool_sequence_accuracy':_rate(rows,'tool_sequence_correct'),
        'first_pass_argument_accuracy':_rate(rows,'argument_correct_first_pass'),
        'post_repair_argument_accuracy':_rate(rows,'argument_correct_after_repair'),
        'task_success':_rate(rows,'task_success'),'scope_violation_rate':1-_rate(rows,'scope_safe'),
        'hallucinated_value_rate':1-_rate(rows,'no_hallucinated_value'),
        'evidence_grounding_rate':_rate(rows,'evidence_grounded'),
        'unsupported_claim_rate':1-_rate(rows,'no_unsupported_claim'),
        'average_tool_calls':mean(r.metrics['tool_calls'] for r in rows),
        'average_llm_calls':mean(r.metrics['llm_calls'] for r in rows),
        'repair_rate':mean(float(r.metrics['needed_repair']) for r in rows),
        'repair_success_rate':mean(float(r.metrics['repair_success']) for r in needed) if needed else None,
        'average_repair_count':mean(r.metrics['repair_count'] for r in rows),
        'latency_ms_p50':percentile(.5),'latency_ms_p95':percentile(.95),
        'average_input_tokens':mean(r.metrics['input_tokens'] for r in rows),
        'average_output_tokens':mean(r.metrics['output_tokens'] for r in rows)}
    groups={}
    for field in ('intent','difficulty'):
        grouped=defaultdict(list)
        for row in rows: grouped[getattr(row,field)].append(row)
        groups['by_'+field]={key:{'n':len(group),'intent_accuracy':_rate(group,'intent_correct'),
            'tool_selection_accuracy':_rate(group,'tool_selection_correct'),'task_success':_rate(group,'task_success')} for key,group in grouped.items()}
    summary.update(groups); summary['failure_counts']=dict(Counter(f for r in rows for f in r.failures))
    return summary
