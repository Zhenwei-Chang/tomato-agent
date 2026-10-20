from .base import Outcome, DATA_LIMITS, SENSOR_LIMITS


def get_growth_context(data, args):
    result, scope, warnings = data.context(args)
    return Outcome(result, scope, warnings=warnings,
                   evidence=[data.evidence('data/processed/phenotype_canonical.csv', f'{args.year}/{args.date}'),
                             data.evidence('data/processed/environment_daily_canonical.csv', str(args.date)),
                             data.evidence('data/indexes/view_date_dataset.csv', str(args.date))],
                   confidence='MEDIUM', reasons=['Exact-date canonical records; field provenance retained'],
                   limitations=DATA_LIMITS+SENSOR_LIMITS, status='partial' if warnings else 'success')
