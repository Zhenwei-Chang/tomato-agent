from pathlib import Path
from .base import DATA_LIMITS, RGB_LIMITS, SENSOR_LIMITS, Outcome


def find_similar_cases(repository, plant_retriever, view_retriever, args):
    entity_id = args.plant_id if args.scope == 'plant' else args.view_id
    query = repository.query_case(args.scope, entity_id, args.date)
    retriever = plant_retriever if args.scope == 'plant' else view_retriever
    result = retriever.retrieve(query, top_k=args.top_k, mode=args.retrieval_mode,
        policy=args.retrieval_policy, exclude_same_entity=args.exclude_same_entity,
        year_filter=args.year_filter, treatment_filter=args.treatment_filter,
        minimum_similarity=args.minimum_similarity)
    case_key = 'plant_cases' if args.scope == 'plant' else 'view_cases'
    case_path = repository.project / repository.config['storage'][case_key]
    manifest = repository.project / repository.config['storage']['manifest']
    evidence = [
        {'evidence_id': match.case_id, 'source': str(case_path),
         'locator': f"case_id={match.case_id}", 'content': 'Observed historical exact +7-day outcome',
         'score': match.similarity, 'attributes': {'scope':args.scope,'outcome_date':match.outcome_date,
          'historical_association_only':True,'same_year':match.same_year}}
        for match in result.matches
    ]
    evidence.append({'evidence_id':'case-memory-manifest','source':str(manifest),'locator':'case_memory_version=v1.2.0',
                     'content':'Versioned Case Memory build provenance'})
    limitations = list(DATA_LIMITS) + ['Similarity is predictive association, not a causal counterfactual.'] + list(SENSOR_LIMITS)
    if args.scope == 'view': limitations += RGB_LIMITS
    return Outcome(result.model_dump(mode='json'), args.scope, warnings=result.warnings, evidence=evidence,
        model_version='case_memory_v1.2.0', confidence=result.retrieval_confidence.value,
        reasons=[result.summary.narrative], limitations=list(dict.fromkeys(limitations)),
        status='partial' if result.warnings else 'success',
        trace_summary={'case_query':result.query_case.get('case_id'),'candidate_count':result.summary.candidate_count,
                       'top_k':result.summary.returned_cases,'retrieval_policy':result.retrieval_policy.value,
                       'similarity_min':result.summary.similarity_min,'similarity_max':result.summary.similarity_max})
