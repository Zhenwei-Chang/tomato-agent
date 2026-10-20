"""Deterministic tool acceptance eval; not scientific model performance evaluation."""
from pathlib import Path
import json
import sys
from importlib.metadata import version, PackageNotFoundError
from .adapters.loading import file_hash
from .config import PROJECT
from .registry import ToolRegistry
from .schemas.common import ToolResult
from .schemas.outputs import OUTPUTS


def main():
    registry=ToolRegistry(); destination=registry.settings.output/'evals'; destination.mkdir(parents=True,exist_ok=True)
    cases=[json.loads(line) for line in (PROJECT/'evals/tool_eval_cases.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    rows=[]; examples=[]
    for case in cases:
        result=registry.call(case['tool'],case['arguments'],trace_id='v10-eval-'+case['id'])
        ToolResult.model_validate_json(result.model_dump_json())
        if result.status!='error': OUTPUTS[case['tool']].model_validate(result.data)
        checks={'schema_valid':True,'expected_status':result.status==case['status'],
                'correct_scope':result.metadata.scope.value==case['scope'],
                'expected_error':(result.error.code.value if result.error else None)==case.get('error_code')}
        if case.get('deterministic'):
            repeated=registry.call(case['tool'],case['arguments'])
            checks['deterministic']=repeated.data==result.data and repeated.status==result.status and repeated.evidence==result.evidence
        rows.append({'id':case['id'],'tool':case['tool'],**checks,'passed':all(checks.values())})
        example=result.model_dump(mode='json')
        if 'embedding' in example['data']:
            example['data']['embedding']='[512 values omitted in human-readable evidence export]'
        examples.append({'case_id':case['id'],'result':example})
    summary={'cases':len(rows),'passed':sum(r['passed'] for r in rows),'all_passed':all(r['passed'] for r in rows),
             'metrics':{key:sum(r.get(key,False) for r in rows if key in r)/sum(key in r for r in rows) for key in ['schema_valid','expected_status','correct_scope','expected_error','deterministic']},
             'not_evaluated':['LLM tool selection','agronomic answer adequacy','prediction recalibration'], 'results':rows}
    positive_ids={case['id'] for case in cases if case['status']!='error'}
    summary['metrics']['execution_success_valid_cases']=sum(r['expected_status'] for r in rows if r['id'] in positive_ids)/len(positive_ids)
    summary['valid_execution_cases']=len(positive_ids)
    summary['expected_error_cases']=len(cases)-len(positive_ids)
    (destination/'tool_eval_results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (destination/'tool_examples.json').write_text(json.dumps(examples,ensure_ascii=False,indent=2),encoding='utf-8')
    (destination/'tool_contracts.json').write_text(json.dumps(registry.discover(),ensure_ascii=False,indent=2),encoding='utf-8')
    packages={}
    for name in ['pydantic','pandas','numpy','scikit-learn','joblib','torch','torchvision','Pillow']:
        try: packages[name]=version(name)
        except PackageNotFoundError: packages[name]=None
    assets=['outputs/checkpoints/height_t7_exact__B0__categorical__gradient_boosting.joblib',
            'outputs/checkpoints/v05__current__frozen_resnet18_head.joblib',
            'outputs/checkpoints/v05__future__frozen_resnet18_head.joblib',
            'data/processed/image_embeddings.csv','data/processed/plants_canonical.csv',
            'data/processed/phenotype_canonical.csv','data/processed/environment_daily_canonical.csv',
            'data/processed/treatments_canonical.csv','configs/baseline.yaml']
    manifest={'python':sys.version,'python_executable':sys.executable,'packages':packages,
              'research_root':str(registry.settings.research),'rag_entry':str(registry.settings.workspace/'agent_system/knowledge.py'),
              'knowledge_snapshot':registry.rag.load().snapshot_id,
              'assets':{p:file_hash(registry.settings.research/p) for p in assets},'models_retrained':False}
    (destination/'runtime_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    # Build a real sequential trace with consistent scenario keys.
    scenario=dict(year=2023,date='2023-05-07',plant_id='2023-111'); trace='v10-chain'; chain=[]
    context=registry.call('get_growth_context',scenario,trace_id=trace); chain.append(context)
    sensor=registry.call('get_sensor_history',{'end_date':scenario['date'],'plant_id':scenario['plant_id']},trace_id=trace,parent_id=context.metadata.tool_call_id); chain.append(sensor)
    chain.append(registry.call('get_treatment_recipe',{'treatment_id':context.data['treatment_ids'][0]},trace_id=trace))
    prediction=registry.call('predict_height_t7',scenario,trace_id=trace); chain.append(prediction)
    chain.append(registry.call('assess_prediction_reliability',dict(model_name='height_v03_b0',year=scenario['year'],requested_scope='plant',model_scope='plant',critical_features_complete=prediction.status=='success',sensor_available=sensor.data['data_quality']['complete'],scenario_id='public_2023_111_0507'),trace_id=trace,parent_id=prediction.metadata.tool_call_id))
    (destination/'integration_chain.json').write_text(json.dumps([r.model_dump(mode='json') for r in chain],ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='results'},indent=2))
    if not summary['all_passed']: raise SystemExit(1)


if __name__=='__main__': main()
