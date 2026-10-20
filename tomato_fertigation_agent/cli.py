"""CLI for atomic tools, the controlled Agent, and V1.3 evidence workflows."""
import argparse
import json
import os
import sys
from pathlib import Path
from .registry import ToolRegistry


def main():
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='Tomato fertigation research tools and evidence workflows')
    sub = parser.add_subparsers(dest='command',required=True)
    listing = sub.add_parser('tools'); listing.add_argument('action',choices=['list','schema'])
    call = sub.add_parser('tool'); call.add_argument('name')
    call_args = call.add_mutually_exclusive_group(required=True)
    call_args.add_argument('--args',help='JSON arguments')
    call_args.add_argument('--args-file',type=Path,help='UTF-8 JSON file; fixture with arguments field also accepted')
    call.add_argument('--trace-id')
    agent_parser=sub.add_parser('agent'); agent_parser.add_argument('action',choices=['ask'])
    agent_parser.add_argument('--query',required=True); agent_parser.add_argument('--profile',choices=['baseline','improved'],default='improved')
    agent_parser.add_argument('--provider',choices=['mock','openai','deepseek']); agent_parser.add_argument('--debug',action='store_true')
    agent_parser.add_argument('--allow-local-tool-data',action='store_true',
        help='Explicitly allow local ToolResult payloads to be sent to the selected external provider')
    agent_parser.add_argument('--workflow',action='store_true',help='Use the V1.3 evidence-driven workflow engine')
    evaluation=sub.add_parser('eval'); evaluation.add_argument('action',choices=['v11','v12','v13','case','online'])
    evaluation.add_argument('--profile',choices=['baseline','improved','compare'],default='improved')
    evaluation.add_argument('--golden-only',action='store_true')
    evaluation.add_argument('--enable-online',action='store_true')
    evaluation.add_argument('--max-cases',type=int)
    evaluation.add_argument('--max-api-calls',type=int)
    evaluation.add_argument('--run-label',default='baseline')
    evaluation.add_argument('--online-provider',choices=['openai','deepseek'])
    evaluation.add_argument('--suite',choices=['smoke','holdout'],default='smoke')
    evaluation.add_argument('--allow-local-tool-data',action='store_true')
    options = parser.parse_args(); registry = ToolRegistry()
    if options.command == 'tools':
        result = registry.function_schemas() if options.action == 'schema' else [{k:d[k] for k in ('name','description','scope','version')} for d in registry.discover()]
        print(json.dumps(result,ensure_ascii=False,indent=2)); return
    if options.command == 'agent':
        try:
            if options.allow_local_tool_data:
                os.environ['TOMATO_ALLOW_EXTERNAL_TOOL_DATA']='1'
            if options.workflow:
                from .workflow import build_workflow_agent
                run=build_workflow_agent(provider=options.provider or 'mock').ask(options.query,debug=options.debug)
            else:
                from .agent import build_agent
                run=build_agent(profile=options.profile,provider=options.provider).ask(options.query,debug=options.debug)
        except Exception as exc:
            from .providers import ProviderError
            if isinstance(exc,ProviderError):
                print(json.dumps({'status':'error','error':exc.as_dict()},ensure_ascii=False,indent=2)); raise SystemExit(2)
            if options.provider in {'openai','deepseek'} and isinstance(exc,ValueError):
                print(json.dumps({'status':'error','error':{'code':'PROVIDER_UNAVAILABLE',
                    'message':str(exc),'details':{}}},ensure_ascii=False,indent=2)); raise SystemExit(2)
            raise
        print(run.model_dump_json(indent=2) if options.debug else run.rendered); return
    if options.command == 'eval':
        from .evaluation.runner import run_comparison,run_evaluation,run_v12_evaluation
        if options.action=='online':
            from .evaluation.online_eval import run_online_evaluation
            result=run_online_evaluation(enabled=options.enable_online,max_cases=options.max_cases,
                max_api_calls=options.max_api_calls,profile=options.run_label,
                provider_name=options.online_provider,suite=options.suite,
                allow_credential_file=options.enable_online,
                allow_local_tool_data=options.allow_local_tool_data)
        elif options.action=='case':
            from .evaluation.case_retrieval import CaseRetrievalEvaluator
            result=CaseRetrievalEvaluator().run(write=True)
        elif options.action=='v13':
            from .evaluation.workflow_eval import run_v13_comparison,run_v13_evaluation
            if options.profile=='compare':
                baseline,improved,comparison=run_v13_comparison(); result={'baseline':baseline['metrics'],'improved':improved['metrics'],'comparison':comparison}
            else: result=run_v13_evaluation(golden_only=options.golden_only)['metrics']
        elif options.action=='v12': result=run_v12_evaluation(options.golden_only)['metrics']
        elif options.profile=='compare':
            baseline,improved,comparison=run_comparison(); result={'baseline':baseline['metrics'],'improved':improved['metrics'],'comparison':comparison}
        else: result=run_evaluation(options.profile,options.golden_only)['metrics']
        print(json.dumps(result,ensure_ascii=False,indent=2)); return
    try:
        raw = options.args_file.read_text(encoding='utf-8-sig') if options.args_file else options.args
        value = json.loads(raw)
        if isinstance(value,dict) and 'arguments' in value:
            value = value['arguments']
    except (ValueError,OSError):
        value = None  # Through registry for the same INVALID_ARGUMENT and trace contract.
    result = registry.call(options.name,value,trace_id=options.trace_id)
    print(result.model_dump_json(indent=2))
    if result.status == 'error':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
