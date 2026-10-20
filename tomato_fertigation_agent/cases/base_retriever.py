from __future__ import annotations
import math
import numpy as np
import pandas as pd
from ..schemas.common import Confidence, ErrorCode, ToolFailure
from .ood import OODDetector
from .schemas import CaseRetrievalResult, RetrievalMode, RetrievalPolicy
from .summary import CaseSummaryBuilder


class BaseCaseRetriever:
    scope = ''

    def __init__(self, repository):
        self.repository=repository
        self.config=repository.config[self.scope]
        self.ood=OODDetector(); self.summarizer=CaseSummaryBuilder()

    def components(self, query, candidates):
        raise NotImplementedError

    def ood_groups(self):
        raise NotImplementedError

    def _context(self,row):
        raise NotImplementedError

    def retrieve(self, query, *, top_k=5, mode=RetrievalMode.historical,
                 policy=RetrievalPolicy.cross_entity, exclude_same_entity=True,
                 year_filter=None, treatment_filter=None, minimum_similarity=None):
        mode=RetrievalMode(mode); policy=RetrievalPolicy(policy)
        candidates=self.repository.candidates(query,mode,policy,exclude_same_entity,year_filter,treatment_filter)
        if candidates.empty:
            raise ToolFailure(ErrorCode.NO_RELIABLE_CASES,'No outcome-available cases satisfy retrieval filters',scope=self.scope)
        components=self.components(query,candidates)
        weights=self.config['weights']
        score=sum(components[name]*float(weights[name]) for name in components)/sum(float(weights[name]) for name in components)
        candidates=candidates.copy(); candidates['_similarity']=score
        for name,value in components.items(): candidates['_'+name]=value
        threshold=self.config.get('minimum_similarity') if minimum_similarity is None else minimum_similarity
        if threshold is not None: candidates=candidates[candidates['_similarity']>=float(threshold)]
        candidates=candidates.sort_values(['_similarity','case_id'],ascending=[False,True]).head(top_k)
        if candidates.empty:
            raise ToolFailure(ErrorCode.NO_RELIABLE_CASES,'No cases meet minimum similarity',scope=self.scope,minimum_similarity=threshold)
        matches=[]
        for _,row in candidates.iterrows():
            same_treatment=None if pd.isna(query.get('treatment_id')) or pd.isna(row.get('treatment_id')) else str(query.get('treatment_id'))==str(row.get('treatment_id'))
            same_variety=None if pd.isna(query.get('variety')) or pd.isna(row.get('variety')) else str(query.get('variety'))==str(row.get('variety'))
            same_year=int(row['year'])==int(query['year'])
            warning=[]
            if not same_year: warning.append('Cross-season historical case')
            matches.append({'case_id':row['case_id'],'scope':self.scope,'entity_id':str(row['entity_id']),
                'case_date':row['case_date'].date().isoformat(),'outcome_date':row['outcome_date'].date().isoformat(),'year':int(row['year']),
                'similarity':float(row['_similarity']),'similarity_breakdown':{name:float(row['_'+name]) for name in components},
                'case_context':self._context(row),'historical_outcome':{'height_t7_cm':float(row['height_t7']),'delta_height_cm':float(row['delta_height'])},
                'same_year':same_year,'same_treatment':same_treatment,'same_variety':same_variety,
                'domain_warning':not same_year,'warnings':warning})
        summary=self.summarizer.build(matches,top_k,len(self.repository.candidates(query,mode,policy,exclude_same_entity,year_filter,treatment_filter)))
        ood,reasons=self.ood.assess(query,self.ood_groups())
        warnings=[]
        if summary.get('same_year_rate',1)<.5: warnings.append('Cross-season historical cases dominate retrieval.')
        if ood: warnings.append('Query is outside at least one 2023 reference feature range.')
        if self.scope=='view': warnings.append('Image similarity may partly reflect View/year/background identity.')
        high_cv=False
        if summary.get('outcome_std') is not None:
            denom=max(abs(summary.get('outcome_mean') or 0),1e-6)
            high_cv=summary['outcome_std']/denom > float(self.repository.config['confidence']['high_outcome_cv'])
            if high_cv: warnings.append('Top-case outcomes are inconsistent.')
        minimum_n=int(self.repository.config['confidence']['minimum_returned_cases'])
        confidence=Confidence.LOW if ood or len(matches)<minimum_n or high_cv else Confidence.MEDIUM
        query_payload={'case_id':str(query['case_id']),'scope':self.scope,'entity_id':str(query['entity_id']),
                       'case_date':pd.Timestamp(query['case_date']).date().isoformat(),'year':int(query['year']),
                       **self._context(query)}
        rule='outcome_date <= query_date' if mode==RetrievalMode.historical else 'retrospective_offline_only'
        return CaseRetrievalResult(query_case=query_payload,matches=matches,summary=summary,
            retrieval_confidence=confidence,ood=ood,ood_reasons=reasons,retrieval_mode=mode,retrieval_policy=policy,
            historical_availability_rule=rule,minimum_similarity=threshold,warnings=warnings)
