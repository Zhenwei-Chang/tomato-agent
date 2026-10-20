from .base import Outcome


def retrieve_water_fertilizer_knowledge(rag, args):
    result, evidence = rag.retrieve(args)
    return Outcome(result,'knowledge',evidence=evidence,confidence='UNKNOWN',
                   warnings=['Retrieved evidence may not answer this query; relevance and answer sufficiency require review'],
                   reasons=['Existing repository scores are uncalibrated'],
                   limitations=['Retrieval only; no final answer or quantitative recommendation generated','Preserve each source applicability boundary and numeric_policy'],
                   status='success' if evidence else 'partial')
