from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any
import json
import math
import os

import yaml

from ..agent.orchestrator import ToolCallingAgent
from ..agent_config import AgentConfig, OnlineProviderConfig, build_online_provider
from ..config import PROJECT
from ..providers import ProviderError
from ..registry import ToolRegistry
from ..schemas.eval import OnlineCaseResult, OnlineEvalCase
from ..workflow.engine import WorkflowAgent
from .answer_quality import AnswerQualityEvaluator
from .required_tools import IndependentRequiredToolEvaluator


ERROR_TYPES = {
    'intent': 'WRONG_INTENT', 'workflow': 'WRONG_WORKFLOW',
    'tool_selection': 'WRONG_TOOL', 'arguments': 'WRONG_ARGUMENT',
    'sequence': 'TOOL_SEQUENCE_ERROR', 'grounding': 'UNSUPPORTED_CLAIM',
    'provenance': 'PROVENANCE_BROKEN', 'scope': 'SCOPE_VIOLATION',
    'answerability': 'ABSTENTION_FAILURE', 'provider': 'PROVIDER_ERROR',
    'answer_relevance': 'ANSWER_IRRELEVANT', 'answer_completeness': 'ANSWER_INCOMPLETE',
    'canonical_tool_names': 'NON_CANONICAL_TOOL_NAME',
    'required_tool_completion': 'REQUIRED_TOOL_MISSING',
    'request_status': 'REQUEST_STATUS_INCONSISTENT',
}


class OnlineEvalConfig:
    def __init__(self, path=None):
        raw = yaml.safe_load(Path(path or PROJECT / 'configs/online_evaluation.yaml').read_text(encoding='utf-8'))
        evaluation, cost = raw['evaluation'], raw['cost']
        self.enabled = bool(evaluation.get('online_enabled', False))
        self.max_cases = int(evaluation['max_cases'])
        self.max_api_calls = int(evaluation['max_api_calls'])
        self.holdout_path = PROJECT / evaluation['holdout_path']
        self.smoke_path = PROJECT / evaluation.get('smoke_path', evaluation['holdout_path'])
        self.output_dir = PROJECT / evaluation['output_dir']
        self.provider = str(evaluation.get('provider', 'openai'))
        self.input_price = cost.get('input_usd_per_million')
        self.output_price = cost.get('output_usd_per_million')
        self.deepseek_prices = cost.get('deepseek_flash', {})
        self.selected_provider = self.provider
        self.selected_model = None


def load_online_cases(path=None) -> list[OnlineEvalCase]:
    path = Path(path or PROJECT / 'evals/v14_online_holdout.jsonl')
    return [OnlineEvalCase.model_validate_json(line) for line in
            path.read_text(encoding='utf-8').splitlines() if line.strip()]


def _set_scores(expected, actual):
    expected, actual = set(expected), set(actual)
    precision = len(expected & actual) / len(actual) if actual else (1.0 if not expected else 0.0)
    recall = len(expected & actual) / len(expected) if expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def _subset(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    return all(key in actual and actual[key] == value for key, value in expected.items())


def _argument_accuracy(case, calls):
    if not case.expected_arguments:
        return 1.0
    correct = 0
    for tool, expected in case.expected_arguments.items():
        candidates = [row for row in calls if row['tool_name'] == tool and row.get('final_arguments')]
        if any(_subset(expected, row['final_arguments']) for row in candidates):
            correct += 1
    return correct / len(case.expected_arguments)


def _behavior(run, mode):
    if mode == 'workflow':
        value = run.diagnosis.answerability.value
        return {'FULL':'success','PARTIAL':'partial','ABSTAIN':'unsupported'}[value]
    if run.answer.status == 'error':
        errors = [row.error_code for row in run.state.tool_calls]
        return 'data_not_found' if 'DATA_NOT_FOUND' in errors else 'unsupported'
    return run.answer.status


def evaluate_online_case(case: OnlineEvalCase, run, canonical_tool_names=None) -> OnlineCaseResult:
    state = run.state if isinstance(run.state, dict) else run.state.model_dump(mode='json')
    calls = state.get('tool_calls', [])
    model_calls = [row for row in calls if row.get('dispatch_source') == 'MODEL_GENERATED_TOOL_CALL']
    if not model_calls and not getattr(run,'provider',{}).get('online',False):
        model_calls=calls
    actual_tools = [row['tool_name'] for row in model_calls]
    canonical=set(canonical_tool_names or state.get('canonical_tool_names') or actual_tools)
    canonical_valid=all(name in canonical for name in actual_tools)
    precision, recall, f1 = _set_scores(case.expected_tools, actual_tools)
    argument_accuracy = _argument_accuracy(case, model_calls)
    sequence_ok = actual_tools == case.expected_tools
    provider_ok = not state.get('provider_errors')
    safety = state.get('safety_violations', [])
    if case.mode == 'workflow':
        diagnosis = run.diagnosis
        intent_ok = True
        workflow_ok = diagnosis.workflow == case.expected_workflow
        answerability_ok = (case.expected_answerability is None or
                            diagnosis.answerability.value == case.expected_answerability)
        evidence_ids = {row.evidence_id for row in diagnosis.evidence}
        substantive = [claim for claim in diagnosis.claims if claim.claim_type.value in
            {'prediction','historical_interpretation','knowledge','recommendation'}]
        grounding = (sum(bool(claim.support_evidence_ids) and
            set(claim.support_evidence_ids) <= evidence_ids for claim in substantive) /
            len(substantive)) if substantive else 1.0
        provenance = diagnosis.provenance.complete
        actual_intent = None; actual_workflow = diagnosis.workflow
    else:
        answer = run.answer
        intent = state.get('intent')
        intent_ok = case.expected_intent is None or intent == case.expected_intent.value
        workflow_ok = True; answerability_ok = True
        all_evidence = {item.evidence_id for item in answer.evidence}
        structured = answer.facts + answer.predictions
        statements = answer.agronomic_interpretation + answer.recommendations
        referenced = [set(row.evidence_ids) for row in structured + statements]
        referenced += [{row.evidence_id} for row in answer.historical_cases]
        grounding = (sum(bool(ids) and ids <= all_evidence for ids in referenced) /
                     len(referenced)) if referenced else 1.0
        provenance = (grounding == 1.0 and
            all(item.source and item.attributes.get('source_tool') and
                item.attributes.get('tool_call_id') for item in answer.evidence))
        actual_intent = intent; actual_workflow = None
    actual_behavior=_behavior(run,case.mode)
    behavior_ok = actual_behavior == case.expected_behavior
    request_status_ok=behavior_ok
    # For evidence-only workflows, a typed ABSTAIN is request-consistent when
    # the fixture expected PARTIAL but completeness is genuinely insufficient.
    # Strict behavior accuracy remains separately visible and unchanged.
    if (case.mode=='workflow' and case.expected_behavior=='partial' and
            actual_behavior=='unsupported' and
            run.diagnosis.evidence_completeness.status.value=='INSUFFICIENT'):
        request_status_ok=True
    quality=AnswerQualityEvaluator().evaluate(case,run.diagnosis if case.mode=='workflow' else run.answer)
    checks = {'intent':intent_ok,'workflow':workflow_ok,
        'tool_selection':f1 == 1.0,'arguments':argument_accuracy == 1.0,
        'sequence':sequence_ok,'grounding':grounding == 1.0,
        'provenance':provenance,'scope':not any('SCOPE' in item for item in safety),
        'answerability':answerability_ok,'behavior':behavior_ok,'provider':provider_ok,
        'canonical_tool_names':canonical_valid,'answer_relevance':quality.relevant,
        'answer_completeness':quality.complete,'request_status':request_status_ok}
    repair_attempted = any((row.get('repair_count') or 0) > 0 or
                           not row.get('argument_valid_first_try', True) for row in calls)
    repair_success = (not repair_attempted or any(row.get('final_argument_valid') for row in calls
                      if not row.get('argument_valid_first_try', True)))
    events = state.get('provider_events', [])
    cached_tokens = sum(int(row.get('cached_input_tokens', 0) or 0) for row in events)
    reasoning_tokens = sum(int(row.get('reasoning_tokens', 0) or 0) for row in events)
    actual_executions=sum(bool(row.get('actual_execution',True)) for row in calls)
    duplicate_attempts=sum(bool(row.get('duplicate_blocked')) for row in calls)
    reused_results=sum(bool(row.get('reused_result')) for row in calls)
    independent=IndependentRequiredToolEvaluator()
    required_tools=independent.required_from_case(case)
    contract=state.get('request_contract')
    contract_tools=independent.required_from_contract(contract)
    if contract_tools:
        required_tools=list(dict.fromkeys(required_tools+contract_tools))
    audit=independent.evaluate(calls=calls,required_tools=required_tools,
        planned_tools=state.get('planned_tools',[]),warnings=state.get('warnings',[]))
    checks['required_tool_completion']=audit.complete
    failures = [ERROR_TYPES[key] for key, value in checks.items()
                if not value and key in ERROR_TYPES]
    if not behavior_ok:
        failures.append('FORMAT_ERROR' if _behavior(run,case.mode) not in
                        {'success','partial','unsupported','data_not_found'} else 'TASK_BEHAVIOR_ERROR')
    if case.mode=='workflow':
        status_consistent=not ((run.diagnosis.answerability.value=='FULL' and not run.diagnosis.claims)
            or (run.diagnosis.answerability.value=='ABSTAIN' and any(c.claim_type.value not in {'limitation'}
                for c in run.diagnosis.claims)))
        valid_refs=run.diagnosis.provenance.evidence_referenced_count
        missing_refs=run.diagnosis.provenance.missing_evidence_reference_count
        evidence_registration=(valid_refs/(valid_refs+missing_refs)
            if valid_refs+missing_refs else 1.0)
        evidence_utilization=valid_refs/max(1,run.diagnosis.provenance.evidence_collected_count)
    else:
        has_content=bool(run.answer.facts or run.answer.predictions or run.answer.historical_cases or
                         run.answer.agronomic_interpretation or run.answer.recommendations or run.answer.evidence)
        status_consistent=not ((run.answer.status=='success' and not has_content) or
                               (run.answer.status=='unsupported' and has_content))
        valid_refs=state.get('evidence_referenced_count',0)
        missing_refs=state.get('missing_evidence_references',0)
        evidence_registration=(valid_refs/(valid_refs+missing_refs)
            if valid_refs+missing_refs else 1.0)
        evidence_utilization=valid_refs/max(1,state.get('evidence_collected_count',0))
    metrics = {'provider_calls':state.get('llm_calls',0),'tool_calls':len(calls),
        'model_generated_tool_calls':len(model_calls),
        'workflow_dispatched_tool_calls':sum(row.get('dispatch_source') == 'WORKFLOW_DISPATCHED_TOOL' for row in calls),
        'deterministic_fallback_tool_calls':sum(row.get('dispatch_source') == 'DETERMINISTIC_FALLBACK' for row in calls),
        'input_tokens':state.get('input_tokens',0),'output_tokens':state.get('output_tokens',0),
        'cached_input_tokens':cached_tokens,'reasoning_tokens':reasoning_tokens,
        'latency_ms':state.get('elapsed_ms',0.0),'argument_repair_attempted':repair_attempted,
        'argument_repair_success':repair_success,'multi_tool':len(case.expected_tools)>1,
        'canonical_tool_name_validity':canonical_valid,
        'tool_plan_validity_before_repair':state.get('tool_plan_valid_before_repair',canonical_valid),
        'tool_plan_repair_attempted':state.get('tool_plan_repair_attempted',False),
        'tool_plan_repair_success':state.get('tool_plan_repair_success',False),
        'argument_accuracy_conditional_on_valid_tool':argument_accuracy if canonical_valid else None,
        'actual_tool_execution_rate':min(1.0,(sum(row.get('actual_execution',True) and
            row.get('result_status') in {'success','partial'} for row in calls)
            / len(case.expected_tools))) if case.expected_tools else 1.0,
        'actual_tool_execution_count':actual_executions,
        'duplicate_tool_attempt_count':duplicate_attempts,
        'reused_result_count':reused_results,
        'required_tool_completion':audit.complete,
        'required_tool_planned_count':len(audit.planned),
        'required_tool_proposed_count':len(audit.proposed),
        'required_tool_actually_executed_count':len(audit.actually_executed),
        'required_tool_successfully_completed_count':len(audit.successfully_completed),
        'required_tool_result_reused_count':len(audit.reused),
        'required_tool_unavailable_count':len(audit.unavailable),
        'required_tool_missing_count':len(audit.missing),
        'evidence_registration_coverage':evidence_registration,
        'evidence_reference_utilization':evidence_utilization,
        'status_body_consistency':status_consistent,
        'request_relative_status_consistency':request_status_ok,
        'missing_evidence_references':state.get('missing_evidence_references',0),
        'semantic_evidence_mismatches':state.get('semantic_evidence_mismatches',0)}
    required = ['intent','workflow','tool_selection','arguments','grounding','provenance',
                'scope','answerability','behavior','provider','canonical_tool_names',
                'answer_relevance','answer_completeness','required_tool_completion',
                'request_status']
    return OnlineCaseResult(case_id=case.case_id,mode=case.mode,category=case.category,
        difficulty=case.difficulty,checks=checks,
        scores={'tool_precision':precision,'tool_recall':recall,'tool_f1':f1,
                'argument_accuracy':argument_accuracy,'claim_grounding':grounding,
                'answer_relevance':float(quality.relevant),'answer_completeness':float(quality.complete)},
        metrics=metrics,failures=list(dict.fromkeys(failures)),
        actual={'intent':actual_intent,'workflow':actual_workflow,'tools':actual_tools,
            'behavior':_behavior(run,case.mode),'provider_errors':state.get('provider_errors',[]),
            'answer_quality_reasons':quality.reasons,
            'required_tool_audit':audit.to_dict(),
            'required_tool_evaluator_version':independent.VERSION,
            'trace_id':state.get('trace_id')},passed=all(checks[key] for key in required))


def _percentile(values, p):
    values=sorted(values)
    if not values: return None
    index=(len(values)-1)*p; lo=math.floor(index); hi=math.ceil(index)
    return values[lo] if lo==hi else values[lo]+(values[hi]-values[lo])*(index-lo)


def aggregate_online_metrics(results, config):
    rows=list(results); n=len(rows)
    total_input=sum(row.metrics['input_tokens'] for row in rows)
    total_output=sum(row.metrics['output_tokens'] for row in rows)
    estimated=None
    cost_basis='UNKNOWN'
    if config.input_price is not None and config.output_price is not None:
        estimated=(total_input*float(config.input_price)+total_output*float(config.output_price))/1_000_000
        cost_basis='configured_flat_rate'
    cached_total=sum(r.metrics.get('cached_input_tokens',0) for r in rows)
    if (config.selected_provider=='deepseek' and config.selected_model=='deepseek-flash'
            and config.deepseek_prices):
        now=datetime.now(timezone.utc)
        peak=(now.weekday()<5 and (1 <= now.hour < 4 or 6 <= now.hour < 10))
        tier='peak' if peak else 'off_peak'
        prices=config.deepseek_prices[tier]
        uncached=max(0,total_input-cached_total)
        estimated=(uncached*float(prices['cache_miss_input_usd_per_million'])+
            cached_total*float(prices['cache_hit_input_usd_per_million'])+
            total_output*float(prices['output_usd_per_million']))/1_000_000
        cost_basis=f'deepseek_flash_{tier}_official_config'
    def avg_score(name): return mean(row.scores.get(name,0.0) for row in rows) if rows else 0.0
    def rate(check): return mean(float(row.checks.get(check,False)) for row in rows) if rows else 0.0
    multi=[row for row in rows if row.metrics['multi_tool']]
    repairs=[row for row in rows if row.metrics['argument_repair_attempted']]
    plan_repairs=[row for row in rows if row.metrics.get('tool_plan_repair_attempted')]
    conditional=[row.metrics.get('argument_accuracy_conditional_on_valid_tool') for row in rows]
    conditional=[value for value in conditional if value is not None]
    return {'n_cases':n,'passed':sum(row.passed for row in rows),
        'intent_accuracy':rate('intent'),'tool_selection_precision':avg_score('tool_precision'),
        'tool_selection_recall':avg_score('tool_recall'),'tool_selection_f1':avg_score('tool_f1'),
        'argument_accuracy':avg_score('argument_accuracy'),'task_success':mean(float(r.passed) for r in rows) if rows else 0.0,
        'canonical_tool_name_validity':mean(float(r.metrics.get('canonical_tool_name_validity',False)) for r in rows) if rows else 0.0,
        'tool_plan_validity_before_repair':mean(float(r.metrics.get('tool_plan_validity_before_repair',False)) for r in rows) if rows else 0.0,
        'tool_plan_repair_success':mean(float(r.metrics.get('tool_plan_repair_success',False)) for r in plan_repairs) if plan_repairs else None,
        'argument_accuracy_conditional_on_valid_tool':mean(conditional) if conditional else None,
        'actual_tool_execution_rate':mean(float(r.metrics.get('actual_tool_execution_rate',0.0)) for r in rows) if rows else 0.0,
        'multi_tool_success':mean(float(r.passed) for r in multi) if multi else None,
        'argument_repair_success':mean(float(r.metrics['argument_repair_success']) for r in repairs) if repairs else None,
        'evidence_grounding':avg_score('claim_grounding'),'claim_provenance_completeness':rate('provenance'),
        'answer_relevance':rate('answer_relevance'),'answer_completeness':rate('answer_completeness'),
        'evidence_registration_coverage':mean(float(r.metrics.get('evidence_registration_coverage',0.0)) for r in rows) if rows else 0.0,
        'evidence_reference_utilization':mean(float(r.metrics.get('evidence_reference_utilization',0.0)) for r in rows) if rows else 0.0,
        'status_body_consistency':mean(float(r.metrics.get('status_body_consistency',False)) for r in rows) if rows else 0.0,
        'request_relative_status_consistency':mean(float(
            r.metrics.get('request_relative_status_consistency',False)) for r in rows) if rows else 0.0,
        'required_tool_completion':mean(float(r.metrics.get('required_tool_completion',False)) for r in rows) if rows else 0.0,
        'duplicate_tool_attempt_rate':mean(float(r.metrics.get('duplicate_tool_attempt_count',0)>0) for r in rows) if rows else 0.0,
        'average_actual_tool_executions':mean(float(r.metrics.get('actual_tool_execution_count',0)) for r in rows) if rows else 0.0,
        'average_reused_results':mean(float(r.metrics.get('reused_result_count',0)) for r in rows) if rows else 0.0,
        'scope_violation_rate':1-rate('scope'),'unsupported_numerical_claim_rate':mean(
            float(any('UNSUPPORTED_NUMERICAL' in failure for failure in r.failures)) for r in rows) if rows else 0.0,
        'abstention_partial_accuracy':rate('answerability'),
        'average_provider_calls':mean(r.metrics['provider_calls'] for r in rows) if rows else 0.0,
        'average_tool_calls':mean(r.metrics['tool_calls'] for r in rows) if rows else 0.0,
        'input_tokens':total_input,'output_tokens':total_output,
        'cached_input_tokens':cached_total,
        'reasoning_tokens':sum(r.metrics.get('reasoning_tokens',0) for r in rows),
        'latency_ms_p50':_percentile([r.metrics['latency_ms'] for r in rows],.5),
        'latency_ms_p95':_percentile([r.metrics['latency_ms'] for r in rows],.95),
        'estimated_api_cost_usd':estimated,'estimated_cost_basis':cost_basis,
        'human_reviewed_answer_quality':'NOT_REVIEWED',
        'failure_counts':dict(Counter(failure for row in rows for failure in row.failures))}


def _not_run(reason, config, write=True):
    payload={'benchmark':'Real LLM Online Holdout','status':'NOT_RUN','reason':reason,
        'timestamp':datetime.now(timezone.utc).isoformat(),'metrics':'NOT_RUN',
        'offline_mock_results_substituted':False}
    if write:
        config.output_dir.mkdir(parents=True,exist_ok=True)
        (config.output_dir/'online_not_run.json').write_text(
            json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    return payload


def _freeze_metadata(suite, cases):
    """Describe fixture immutability without labeling a smoke suite as holdout."""
    frozen = bool(cases) and all(case.frozen for case in cases)
    return {
        'suite_frozen_at_run': frozen,
        'frozen_holdout': suite == 'holdout' and frozen,
    }


def run_online_evaluation(*, enabled=False, max_cases=None, max_api_calls=None,
                          profile='baseline', write=True, registry=None,
                          provider_name=None, suite='smoke',
                          allow_credential_file=False,
                          allow_local_tool_data=False):
    config=OnlineEvalConfig()
    if not enabled:
        return _not_run('Online evaluation requires the explicit --enable-online flag',config,write)
    if not allow_local_tool_data:
        return _not_run('Real Agent evaluation requires explicit consent to send local ToolResult data',
                        config,write)
    selected_provider=provider_name or os.getenv('TOMATO_ONLINE_PROVIDER') or config.provider
    if (selected_provider == 'deepseek' and not os.getenv('DEEPSEEK_API_KEY') and
            not allow_credential_file):
        return _not_run('Controlled DeepSeek credential-file reuse requires an explicit CLI online run',
                        config,write)
    try:
        online=OnlineProviderConfig.load(selected_provider)
    except (ValueError, ProviderError) as exc:
        return _not_run(str(exc),config,write)
    if not online.api_key:
        return _not_run(f'{online.api_key_env} is not configured',config,write)
    config.selected_provider=selected_provider; config.selected_model=online.model
    case_path=config.smoke_path if suite=='smoke' else config.holdout_path
    cases=load_online_cases(case_path)
    limit=min(int(max_cases or config.max_cases),len(cases))
    call_budget=int(max_api_calls or config.max_api_calls)
    provider=build_online_provider(selected_provider,max_total_calls=call_budget,
        allow_external_tool_data=allow_local_tool_data)
    registry=registry or ToolRegistry(); results=[]; raw=[]
    for case in cases[:limit]:
        try:
            if case.mode=='workflow':
                run=WorkflowAgent(registry=registry,provider=provider).ask(case.query,debug=True,
                    trace_id=f'v14-{profile}-{case.case_id}')
            else:
                cfg=AgentConfig.load(profile='improved',provider=selected_provider)
                run=ToolCallingAgent(config=cfg,registry=registry,provider=provider).ask(
                    case.query,debug=True,trace_id=f'v14-{profile}-{case.case_id}')
            result=evaluate_online_case(case,run,registry.canonical_names); results.append(result)
            state_payload=run.state if isinstance(run.state,dict) else run.state.model_dump(mode='json')
            raw.append({'case':case.model_dump(mode='json'),'result':result.model_dump(mode='json'),
                'provider':run.provider,'provider_responses':state_payload.get('provider_events',[]),
                'tool_calls':state_payload.get('tool_calls',[]),
                'final_answer':run.diagnosis.model_dump(mode='json') if case.mode=='workflow'
                    else run.answer.model_dump(mode='json'),'trace_id':result.actual.get('trace_id')})
        except ProviderError as exc:
            result=OnlineCaseResult(case_id=case.case_id,mode=case.mode,category=case.category,
                difficulty=case.difficulty,checks={'provider':False},scores={'tool_precision':0,
                'tool_recall':0,'tool_f1':0,'argument_accuracy':0,'claim_grounding':0},
                metrics={'provider_calls':0,'tool_calls':0,'model_generated_tool_calls':0,
                    'workflow_dispatched_tool_calls':0,'deterministic_fallback_tool_calls':0,
                    'input_tokens':0,'output_tokens':0,'cached_input_tokens':0,'reasoning_tokens':0,
                    'latency_ms':0,'argument_repair_attempted':False,
                    'argument_repair_success':False,'multi_tool':len(case.expected_tools)>1},
                failures=['PROVIDER_ERROR'],actual={'provider_error':exc.as_dict()},passed=False)
            results.append(result); raw.append({'case':case.model_dump(mode='json'),
                'provider_error':exc.as_dict()})
            if exc.code.value=='PROVIDER_BUDGET_EXCEEDED': break
    freeze_metadata=_freeze_metadata(suite,cases[:limit])
    payload={'benchmark':'Real LLM Online Holdout','status':'COMPLETED','profile':profile,
        'provider':selected_provider,'model':online.model,'api':'responses','suite':suite,
        'credential_source':online.credential_source,'legacy_model_normalized_from':online.legacy_model,
        'timestamp':datetime.now(timezone.utc).isoformat(),
        **freeze_metadata,'api_call_budget':call_budget,'actual_api_calls':provider.total_api_calls,
        'metrics':aggregate_online_metrics(results,config),
        'results':[row.model_dump(mode='json') for row in results],
        'records':raw,'offline_mock_results_substituted':False}
    if write:
        config.output_dir.mkdir(parents=True,exist_ok=True)
        name=f'online_{profile}_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json'
        (config.output_dir/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    return payload
