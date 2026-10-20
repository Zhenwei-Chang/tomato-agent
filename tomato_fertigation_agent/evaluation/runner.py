from pathlib import Path
import json
from ..agent import build_agent
from ..config import PROJECT
from ..schemas.eval import AgentEvalCase
from .metrics import aggregate_metrics, evaluate_case


def load_cases(path=None, golden_only=False):
    path=Path(path or PROJECT/'evals/v11_agent_cases.jsonl')
    cases=[AgentEvalCase.model_validate_json(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    return [case for case in cases if case.golden] if golden_only else cases


def run_evaluation(profile='improved',golden_only=False,write=True,path=None,output_version='v11'):
    agent=build_agent(profile=profile); cases=load_cases(path=path,golden_only=golden_only); results=[]
    for case in cases:
        run=agent.ask(case.query,debug=True,trace_id=f'{profile}-{case.case_id}')
        results.append(evaluate_case(case,run))
    summary=aggregate_metrics(results)
    payload={'profile':profile,'provider':{'name':agent.provider.name,'model':agent.provider.model,'online':False},
             'config':{'max_tool_calls':agent.config.max_tool_calls,'max_argument_repairs':agent.config.max_argument_repairs,
                       'minimum_retrieval_score':agent.config.minimum_retrieval_score,'prompt_versions':agent.config.prompt_versions},
             'metrics':summary,'results':[r.model_dump(mode='json') for r in results]}
    if write:
        output=agent.registry.settings.output/'evals'; output.mkdir(parents=True,exist_ok=True)
        suffix='golden' if golden_only else 'results'
        (output/f'{output_version}_{profile}_{suffix}.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    return payload


def run_comparison():
    baseline=run_evaluation('baseline'); improved=run_evaluation('improved')
    keys=['intent_accuracy','tool_selection_accuracy','tool_sequence_accuracy','first_pass_argument_accuracy',
          'post_repair_argument_accuracy','task_success','scope_violation_rate','hallucinated_value_rate',
          'evidence_grounding_rate','unsupported_claim_rate','average_tool_calls','average_llm_calls','repair_rate']
    comparison={key:{'baseline':baseline['metrics'][key],'improved':improved['metrics'][key],
                     'delta':improved['metrics'][key]-baseline['metrics'][key]} for key in keys}
    destination=PROJECT/'outputs/evals/v11_baseline_vs_improved.json'
    destination.write_text(json.dumps({'comparison':comparison},ensure_ascii=False,indent=2),encoding='utf-8')
    return baseline,improved,comparison


def run_v12_evaluation(golden_only=False,write=True):
    return run_evaluation('improved',golden_only=golden_only,write=write,
        path=PROJECT/'evals/v12_agent_cases.jsonl',output_version='v12')
