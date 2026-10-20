from __future__ import annotations
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd
from ..cases import CaseRepository, PlantCaseRetriever, ViewCaseRetriever
from ..cases.schemas import RetrievalMode, RetrievalPolicy
from ..config import PROJECT
from ..config import Settings


def _sample(frame, n):
    frame=frame.sort_values(['year','case_date','case_id']).reset_index(drop=True)
    if len(frame)<=n: return frame
    return frame.iloc[np.linspace(0,len(frame)-1,n,dtype=int)].drop_duplicates('case_id')


def _mae(values):
    values=np.asarray(values,float)
    return float(np.mean(np.abs(values))) if len(values) else None


def _rmse(values):
    values=np.asarray(values,float)
    return float(np.sqrt(np.mean(values**2))) if len(values) else None


class CaseRetrievalEvaluator:
    def __init__(self, project=PROJECT, seed=42):
        self.project=Path(project); self.seed=seed
        self.repository=CaseRepository(self.project)
        self.retrievers={'plant':PlantCaseRetriever(self.repository),'view':ViewCaseRetriever(self.repository)}

    def queries(self, scope, n):
        frame=self.repository.cases(scope)
        valid=frame[frame.outcome_available & (frame.year>=2024)].copy()
        return _sample(valid,n)

    def _random_prediction(self, candidates, k, query_id):
        seed=int(sha256(f'{self.seed}:{query_id}:{k}'.encode()).hexdigest()[:8],16)
        rng=np.random.default_rng(seed); count=min(k,len(candidates))
        chosen=candidates.iloc[rng.choice(len(candidates),size=count,replace=False)]
        return float(chosen.height_t7.mean())

    def evaluate(self, scope, *, k=5, mode='historical', policy='cross_entity', n_queries=120):
        retriever=self.retrievers[scope]; rows=[]
        for _,query in self.queries(scope,n_queries).iterrows():
            exclude_same=policy!='unrestricted'
            candidates=self.repository.candidates(query,RetrievalMode(mode),RetrievalPolicy(policy),exclude_same)
            if candidates.empty: continue
            try:
                result=retriever.retrieve(query,top_k=k,mode=mode,policy=policy,
                    exclude_same_entity=exclude_same,minimum_similarity=0.0)
            except Exception: continue
            truth=float(query.height_t7); similar=result.summary.similarity_weighted_height_t7_cm
            random_pred=self._random_prediction(candidates,k,query.case_id); mean_pred=float(candidates.height_t7.mean())
            rows.append({'scope':scope,'case_id':query.case_id,'year':int(query.year),'k':k,'mode':mode,'policy':policy,
                'truth':truth,'similar_prediction':similar,'random_prediction':random_pred,'mean_prediction':mean_pred,
                'similar_error':similar-truth,'random_error':random_pred-truth,'mean_error':mean_pred-truth,
                'top1_similarity':result.summary.similarity_max,'topk_mean_similarity':result.summary.similarity_mean,
                'same_year_rate':result.summary.same_year_rate,'same_treatment_rate':result.summary.same_treatment_rate,
                'candidate_count':result.summary.candidate_count,'returned_cases':result.summary.returned_cases,
                'leakage_violations':sum(pd.Timestamp(m.outcome_date)>pd.Timestamp(query.case_date) for m in result.matches)})
        frame=pd.DataFrame(rows)
        metrics={'scope':scope,'k':k,'mode':mode,'policy':policy,'queries_available':len(self.queries(scope,n_queries)),
                 'coverage':float(len(frame)/max(len(self.queries(scope,n_queries)),1)),'evaluated':len(frame)}
        if len(frame):
            metrics.update(similar_k_mae=_mae(frame.similar_error),random_k_mae=_mae(frame.random_error),
                mean_baseline_mae=_mae(frame.mean_error),similar_k_rmse=_rmse(frame.similar_error),
                top1_similarity_mean=float(frame.top1_similarity.mean()),top1_similarity_p05=float(frame.top1_similarity.quantile(.05)),
                top1_similarity_median=float(frame.top1_similarity.median()),top5_mean_similarity=float(frame.topk_mean_similarity.mean()),
                same_year_rate=float(frame.same_year_rate.mean()),same_treatment_rate=float(frame.same_treatment_rate.dropna().mean()),
                leakage_violations=int(frame.leakage_violations.sum()))
        return metrics,frame

    def view_shortcut(self,n_queries=80,k=5):
        rows=[]; retriever=self.retrievers['view']; vectors=self.repository.view_embeddings()
        for _,query in self.queries('view',n_queries).iterrows():
            experiments=[('image_only_retrospective_unrestricted','retrospective','unrestricted',False),
                         ('image_only_historical_cross_entity','historical','cross_entity',True),
                         ('hybrid_historical_cross_entity','historical','cross_entity',True)]
            for representation,mode,policy,exclude in experiments:
                candidates=self.repository.candidates(query,RetrievalMode(mode),RetrievalPolicy(policy),exclude)
                if candidates.empty: continue
                components=retriever.components(query,candidates)
                score=components['image'] if representation.startswith('image_only') else sum(
                    components[n]*retriever.config['weights'][n] for n in components)/sum(retriever.config['weights'].values())
                ranked=candidates.assign(score=score).sort_values(['score','case_id'],ascending=[False,True]).head(k)
                pred=float(np.average(ranked.height_t7,weights=ranked.score))
                rows.append({'representation':representation,'case_id':query.case_id,'mae':abs(pred-float(query.height_t7)),
                    'same_view_rate':float((ranked.entity_id.astype(str)==str(query.entity_id)).mean()),
                    'same_year_rate':float((ranked.year.astype(int)==int(query.year)).mean()),
                    'mean_similarity':float(ranked.score.mean())})
        frame=pd.DataFrame(rows)
        summary=frame.groupby('representation').agg(n=('case_id','size'),outcome_mae=('mae','mean'),
            same_view_rate=('same_view_rate','mean'),same_year_rate=('same_year_rate','mean'),
            mean_similarity=('mean_similarity','mean')).reset_index()
        return frame,summary

    def year_similarity_study(self,scope,n_queries=120,k=5):
        retriever=self.retrievers[scope]; rows=[]; queries=self.queries(scope,n_queries)
        for _,query in queries.iterrows():
            for label,kwargs in [('within_year',{'policy':'cross_entity','year_filter':int(query.year)}),
                                 ('cross_year',{'policy':'cross_year','year_filter':None})]:
                try:
                    result=retriever.retrieve(query,top_k=k,mode='historical',exclude_same_entity=True,
                        minimum_similarity=0.0,**kwargs)
                except Exception: continue
                pred=result.summary.similarity_weighted_height_t7_cm
                rows.append({'scope':scope,'domain':label,'case_id':query.case_id,
                    'top1_similarity':result.summary.similarity_max,'topk_similarity':result.summary.similarity_mean,
                    'absolute_error':abs(pred-float(query.height_t7))})
        frame=pd.DataFrame(rows)
        summary=frame.groupby(['scope','domain']).agg(n=('case_id','size'),top1_similarity=('top1_similarity','mean'),
            topk_similarity=('topk_similarity','mean'),outcome_mae=('absolute_error','mean')).reset_index()
        summary['coverage']=summary['n']/len(queries)
        return frame,summary

    def ood_study(self):
        results=[]
        for scope,retriever in self.retrievers.items():
            query=self.queries(scope,1).iloc[0].copy()
            state='height_t0' if scope=='plant' else 'view_mean_height_t0'
            query[state]=300.0
            query['co2_mean_7d']=2000.0
            if scope=='plant': query['treatment_id']='UNKNOWN'
            result=retriever.retrieve(query,top_k=5,mode='historical',policy='cross_entity',minimum_similarity=0.0)
            results.append({'scope':scope,'ood':result.ood,'confidence':result.retrieval_confidence.value,
                            'reasons':result.ood_reasons,'passed':result.ood and result.retrieval_confidence.value=='LOW'})
        return results

    def case_model_agreement_study(self,n_queries=160):
        settings=Settings()
        artifact=settings.research/'outputs/checkpoints/height_t7_exact__B0__categorical__gradient_boosting.joblib'
        model=joblib.load(artifact)
        samples=pd.read_csv(settings.research/'data/processed/plant_daily_sample_index.csv',low_memory=False).set_index('sample_key')
        rows=[]
        for _,query in self.queries('plant',n_queries).iterrows():
            try:
                result=self.retrievers['plant'].retrieve(query,top_k=5,mode='historical',policy='cross_entity',exclude_same_entity=True)
            except Exception: continue
            sample=samples.loc[query.source_sample_key]
            ml=float(model.predict(pd.DataFrame([sample[list(model.feature_names_in_)]],columns=model.feature_names_in_))[0])
            case=float(result.summary.similarity_weighted_height_t7_cm); truth=float(query.height_t7)
            difference=abs(ml-case); label='AGREE' if difference<=10 else ('PARTIAL' if difference<=20 else 'DISAGREE')
            rows.append({'case_id':query.case_id,'year':int(query.year),'ml_prediction':ml,'case_prediction':case,'truth':truth,
                         'absolute_difference':difference,'agreement':label,'ml_absolute_error':abs(ml-truth),'case_absolute_error':abs(case-truth)})
        frame=pd.DataFrame(rows)
        summary={'n':len(frame),'coverage':len(frame)/max(len(self.queries('plant',n_queries)),1),
                 'agreement_counts':frame.agreement.value_counts().to_dict(),
                 'agreement_rates':frame.agreement.value_counts(normalize=True).to_dict(),
                 'mean_absolute_difference_cm':float(frame.absolute_difference.mean()),
                 'ml_mae':float(frame.ml_absolute_error.mean()),'case_mae':float(frame.case_absolute_error.mean())}
        return frame,summary

    def run(self,write=True):
        details=[]; metrics=[]
        for scope,n in [('plant',160),('view',100)]:
            for k in (1,3,5,10):
                result,frame=self.evaluate(scope,k=k,n_queries=n); metrics.append(result); details.append(frame)
            for policy in ('unrestricted','cross_entity','cross_year'):
                result,frame=self.evaluate(scope,k=5,mode='retrospective' if policy=='unrestricted' else 'historical',
                                           policy=policy,n_queries=n)
                result['study']='policy'; metrics.append(result); details.append(frame)
        shortcut_rows,shortcut_summary=self.view_shortcut()
        year_rows=[]; year_summaries=[]
        for scope,n in [('plant',160),('view',100)]:
            rows,summary=self.year_similarity_study(scope,n); year_rows.append(rows); year_summaries.append(summary)
        year_summary=pd.concat(year_summaries,ignore_index=True)
        agreement_rows,agreement_summary=self.case_model_agreement_study()
        ood=self.ood_study()
        payload={'case_memory_version':'v1.2.0','seed':self.seed,'metrics':metrics,
                 'year_similarity':year_summary.to_dict(orient='records'),
                 'case_model_agreement':agreement_summary,
                 'view_shortcut':shortcut_summary.to_dict(orient='records'),'ood':ood}
        if write:
            output=self.project/'outputs/evals'; output.mkdir(parents=True,exist_ok=True)
            (output/'v12_case_retrieval_evaluation.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
            pd.concat(details,ignore_index=True).to_csv(output/'v12_case_retrieval_details.csv',index=False)
            shortcut_rows.to_csv(output/'v12_view_shortcut_details.csv',index=False)
            shortcut_summary.to_csv(output/'v12_view_shortcut_summary.csv',index=False)
            pd.concat(year_rows,ignore_index=True).to_csv(output/'v12_year_similarity_details.csv',index=False)
            year_summary.to_csv(output/'v12_year_similarity_summary.csv',index=False)
            agreement_rows.to_csv(output/'v12_case_model_agreement.csv',index=False)
        return payload


def build_eval_fixtures(project=PROJECT):
    repository=CaseRepository(project); rows=[]
    for scope,n in [('plant',14),('view',8)]:
        cases=_sample(repository.cases(scope).query('outcome_available and year >= 2024'),n)
        for i,(_,row) in enumerate(cases.iterrows(),1):
            rows.append({'case_id':f'v12_{scope}_{i:02d}','scope':scope,'entity_id':str(row.entity_id),
                         'date':row.case_date.date().isoformat(),'top_k':5,'historical_only':True,
                         'exclude_same_entity':True,'expected_scope':scope,'expected_no_future_leakage':True})
    rows += [
        {'case_id':'v12_ood_plant','scope':'plant','synthetic':{'height_t0':300,'co2_mean_7d':2000,'treatment_id':'UNKNOWN'},'expected_confidence':'LOW'},
        {'case_id':'v12_ood_view','scope':'view','synthetic':{'view_mean_height_t0':300,'co2_mean_7d':2000},'expected_confidence':'LOW'},
    ]
    path=Path(project)/'evals/v12_case_retrieval_cases.jsonl'
    path.write_text('\n'.join(json.dumps(row,ensure_ascii=False) for row in rows)+'\n',encoding='utf-8')
    return len(rows)
