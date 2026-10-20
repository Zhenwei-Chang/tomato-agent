from .base import Outcome, SENSOR_LIMITS


def get_sensor_history(data, args):
    result, warnings = data.sensor(args)
    return Outcome(result, 'greenhouse', warnings=warnings,
                   evidence=[data.evidence('data/processed/environment_daily_canonical.csv', f'{result["start_date"]}..{result["end_date"]}')],
                   confidence='LOW' if warnings else 'MEDIUM', reasons=['Exact daily records; missing dates explicitly retained'],
                   limitations=SENSOR_LIMITS, status='partial' if warnings else 'success')
