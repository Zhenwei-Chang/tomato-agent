import numpy as np
from .similarity import weighted_mean


class CaseSummaryBuilder:
    def build(self, matches, requested_top_k, candidate_count):
        if not matches:
            return {'requested_top_k':requested_top_k,'returned_cases':0,'candidate_count':candidate_count,
                    'narrative':'No historical cases passed the configured availability and similarity rules.'}
        similarity=np.array([m['similarity'] for m in matches],float)
        heights=np.array([m['historical_outcome']['height_t7_cm'] for m in matches],float)
        deltas=np.array([m['historical_outcome']['delta_height_cm'] for m in matches],float)
        same_year=np.array([m['same_year'] for m in matches],float)
        treatment=[m['same_treatment'] for m in matches if m['same_treatment'] is not None]
        variety=[m['same_variety'] for m in matches if m['same_variety'] is not None]
        narrative=(f"Retrieved {len(matches)} valid historical cases; similarity {similarity.min():.3f}–{similarity.max():.3f}. "
                   f"Historical 7-day growth mean={deltas.mean():.2f} cm, median={np.median(deltas):.2f} cm, std={deltas.std(ddof=0):.2f} cm.")
        return {'requested_top_k':requested_top_k,'returned_cases':len(matches),'candidate_count':candidate_count,
                'similarity_min':float(similarity.min()),'similarity_max':float(similarity.max()),'similarity_mean':float(similarity.mean()),
                'outcome_mean':float(deltas.mean()),'outcome_median':float(np.median(deltas)),'outcome_std':float(deltas.std(ddof=0)),
                'outcome_range':[float(deltas.min()),float(deltas.max())],
                'similarity_weighted_height_t7_cm':weighted_mean(heights,similarity),
                'similarity_weighted_delta_height_cm':weighted_mean(deltas,similarity),
                'same_year_rate':float(same_year.mean()),
                'same_treatment_rate':float(np.mean(treatment)) if treatment else None,
                'same_variety_rate':float(np.mean(variety)) if variety else None,
                'narrative':narrative}
