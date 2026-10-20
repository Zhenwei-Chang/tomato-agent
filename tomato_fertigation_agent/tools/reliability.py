from .base import Outcome


def assess_prediction_reliability(args):
    reasons = []
    known_scope = {'height_v03_b0':'plant','rgb_v05':'view'}.get(args.model_name)
    if args.requested_scope != args.model_scope or (known_scope and args.model_scope.value != known_scope):
        reasons.append('Requested scope does not match the supported model scope')
    if args.critical_features_complete is False:
        reasons.append('Critical input missing')
    if args.model_name == 'height_v03_b0' and args.sensor_available is False:
        reasons.append('Required sensor window missing')
    if args.model_name == 'rgb_v05' and args.image_available is False:
        reasons.append('Required image missing')
    if args.year is not None and args.year not in (2023,2024,2025):
        reasons.append('Unseen year/domain')
    elif args.year in (2024,2025):
        reasons.append('Known cross-season domain shift; observed holdout is not an untouched test')
    if args.model_name == 'rgb_v05':
        reasons.append('RGB background/View shortcut risk remains unresolved')
    if args.case_retrieval_confidence == 'LOW':
        reasons.append('Historical Case retrieval confidence is LOW')
    if args.case_model_agreement == 'DISAGREE':
        reasons.append('ML prediction and historical Case evidence disagree')
    if reasons:
        level = 'LOW'
    elif args.model_name == 'unknown' or args.year is None or args.critical_features_complete is None or (args.model_name == 'height_v03_b0' and args.sensor_available is None):
        level = 'UNKNOWN'; reasons.append('Insufficient metadata or unknown model')
    else:
        level = 'MEDIUM'; reasons.append('Known domain, complete inputs, matching scope; numerical accuracy not guaranteed')
    return Outcome({'confidence':level,'confidence_reason':reasons,'assessment_type':'rule_based',
                    'statistically_calibrated':False,'scenario_id':args.scenario_id,
                    'input_metadata_verified':False,'high_enabled':False,
                    'case_retrieval_confidence':args.case_retrieval_confidence,
                    'case_model_agreement':args.case_model_agreement}, args.model_scope.value,
                   confidence=level, reasons=reasons, limitations=['Rules are not probability calibration; standalone caller assertions are not independently verified'])
