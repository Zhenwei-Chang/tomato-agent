import numpy as np
from .base_retriever import BaseCaseRetriever
from .similarity import cosine_similarity, standardized_similarity


class ViewCaseRetriever(BaseCaseRetriever):
    scope='view'

    def components(self,query,candidates):
        vectors=self.repository.view_embeddings()
        q=vectors[str(query['case_id'])]
        x=np.stack([vectors[case_id] for case_id in candidates['case_id'].astype(str)])
        normalizers=self.repository.normalizers()
        return {'image':cosine_similarity(q,x),
                'sensor':standardized_similarity(query,candidates,normalizers['view_sensor']),
                'state':standardized_similarity(query,candidates,normalizers['view_state'])}

    def ood_groups(self):
        n=self.repository.normalizers(); return {'state':n['view_state'],'sensor':n['view_sensor']}

    def _context(self,row):
        return {'view_id':str(row['view_id']),'view_mean_height_t0_cm':float(row['view_mean_height_t0']),
                'treatment_id':None if str(row.get('treatment_id'))=='nan' else str(row.get('treatment_id')),
                'variety':None if str(row.get('variety'))=='nan' else str(row.get('variety')),
                'n_plants':int(row['n_plants']),'target_coverage':float(row['target_coverage']),
                'sensor_scope':'greenhouse_global','substrate_scope':'greenhouse_global_proxy'}
