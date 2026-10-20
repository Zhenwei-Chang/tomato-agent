import numpy as np
from .base_retriever import BaseCaseRetriever
from .builder import PLANT_STATE_FEATURES, SENSOR_FEATURES
from .similarity import standardized_similarity


class PlantCaseRetriever(BaseCaseRetriever):
    scope='plant'

    def components(self,query,candidates):
        normalizers=self.repository.normalizers()
        return {
            'state':standardized_similarity(query,candidates,normalizers['plant_state']),
            'sensor':standardized_similarity(query,candidates,normalizers['plant_sensor']),
            'treatment':(candidates['treatment_id'].astype(str).to_numpy()==str(query['treatment_id'])).astype(float),
            'variety':(candidates['variety'].astype(str).to_numpy()==str(query['variety'])).astype(float),
        }

    def ood_groups(self):
        n=self.repository.normalizers(); return {'state':n['plant_state'],'sensor':n['plant_sensor']}

    def _context(self,row):
        return {'plant_id':str(row['plant_id']),'height_t0_cm':float(row['height_t0']),'lai_t0':float(row['lai_t0']),
                'treatment_id':str(row['treatment_id']),'variety':str(row['variety']),
                'sensor_scope':'greenhouse_global','substrate_scope':'greenhouse_global_proxy'}
