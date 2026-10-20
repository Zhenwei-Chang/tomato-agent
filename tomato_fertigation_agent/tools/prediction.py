from .base import Outcome, DATA_LIMITS, SENSOR_LIMITS
from .reliability import assess_prediction_reliability
from ..schemas.tools import ReliabilityInput


def predict_height_t7(data, models, args):
    result = models.height(args)
    assessment = assess_prediction_reliability(ReliabilityInput(model_name='height_v03_b0', year=args.year,
        requested_scope='plant',model_scope='plant',critical_features_complete=True,sensor_available=True))
    return Outcome(result,'plant',model_version='v03_locked_B0',confidence=assessment.confidence,
                   reasons=assessment.reasons, warnings=['Experimental forecast; not an observed future height'],
                   evidence=[data.evidence('outputs/checkpoints/height_t7_exact__B0__categorical__gradient_boosting.joblib'),
                             data.evidence('data/processed/phenotype_canonical.csv',f'{args.plant_id}/{args.date}'),
                             data.evidence('data/processed/environment_daily_canonical.csv',str(args.date)),
                             data.evidence('configs/baseline.yaml')],
                   limitations=DATA_LIMITS+SENSOR_LIMITS+['Autoregressive prediction relies strongly on current height and LAI','LAI source method UNKNOWN; no calibrated prediction interval'])
