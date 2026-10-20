from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd
import yaml


PLANT_SOURCE = {
    'air_temperature_mean_7d': 'env_air_temperature_mean_7d',
    'air_temperature_std_7d': 'env_air_temperature_std_7d',
    'relative_humidity_mean_7d': 'env_relative_humidity_mean_7d',
    'relative_humidity_std_7d': 'env_relative_humidity_std_7d',
    'light_mean_7d': 'env_light_mean_7d',
    'co2_mean_7d': 'env_co2_mean_7d',
    'substrate_temperature_mean_7d': 'env_substrate_temperature_mean_7d',
    'substrate_moisture_mean_7d': 'env_substrate_moisture_mean_7d',
    'vpd_mean_7d': 'env_vpd_kpa_mean_7d',
}
VIEW_SOURCE = {name: 'sensor_' + source for name, source in PLANT_SOURCE.items()}
SENSOR_FEATURES = list(PLANT_SOURCE)
PLANT_STATE_FEATURES = ['height_t0', 'lai_t0']
VIEW_STATE_FEATURES = ['view_mean_height_t0']


def _digest(path: Path):
    h = sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _fit_stats(frame: pd.DataFrame, columns: list[str]):
    values = frame[columns].astype(float)
    mean = values.mean().to_numpy(float)
    scale = values.std(ddof=0).replace(0, 1).fillna(1).to_numpy(float)
    return {
        'features': columns,
        'mean': mean,
        'scale': scale,
        'min': values.min().to_numpy(float),
        'max': values.max().to_numpy(float),
        'q01': values.quantile(.01).to_numpy(float),
        'q99': values.quantile(.99).to_numpy(float),
        'fit_year': 2023,
        'fit_rule': '2023 outcome-available cases only',
    }


class CaseMemoryBuilder:
    VERSION = 'v1.2.0'

    def __init__(self, project_root: Path, research_root: Path, config_path: Path | None = None):
        self.project = Path(project_root)
        self.research = Path(research_root)
        self.config_path = config_path or self.project / 'configs/case_retrieval.yaml'
        self.config = yaml.safe_load(self.config_path.read_text(encoding='utf-8'))
        self.output = self.project / 'data/cases'

    def _read(self, relative):
        return pd.read_csv(self.research / relative, low_memory=False)

    def build_plant_cases(self):
        source = self._read('data/processed/plant_daily_sample_index.csv')
        keep = source['height_t0'].notna() & source['lai_t0'].notna() & source['env_window_complete'].fillna(False)
        source = source.loc[keep].copy()
        frame = pd.DataFrame({
            'case_id': 'plant__' + source['year'].astype(str) + '__' + source['plant_id'].astype(str) + '__' + source['target_date'].astype(str),
            'scope': 'plant', 'entity_id': source['plant_id'], 'plant_id': source['plant_id'],
            'case_date': source['target_date'], 'outcome_date': source['height_t7_exact_date'],
            'year': source['year'].astype(int), 'variety': source['variety'], 'treatment_id': source['treatment_id'],
            'view_id': source['view_id'], 'height_t0': source['height_t0'], 'lai_t0': source['lai_t0'],
            'height_t7': source['height_t7_exact'],
            'outcome_available': source['height_t7_exact_is_observed'].fillna(False) & source['height_t7_exact'].notna(),
            'environment_scope': 'greenhouse_global',
            'substrate_moisture_scope': 'greenhouse_global_proxy',
            'substrate_temperature_scope': 'greenhouse_global_proxy',
            'source_sample_key': source['sample_key'], 'case_memory_version': self.VERSION,
        })
        for target, original in PLANT_SOURCE.items():
            frame[target] = source[original].to_numpy()
        frame['delta_height'] = frame['height_t7'] - frame['height_t0']
        frame.loc[~frame['outcome_available'], ['height_t7', 'delta_height', 'outcome_date']] = np.nan
        if not frame['case_id'].is_unique:
            raise ValueError('Plant case_id is not unique')
        return frame.sort_values(['case_date', 'plant_id']).reset_index(drop=True)

    def build_view_cases(self):
        views = self._read('data/indexes/view_date_dataset.csv')
        embeddings = self._read('data/processed/image_embeddings.csv')
        samples = self._read('data/processed/plant_daily_sample_index.csv')
        env_sources = list(PLANT_SOURCE.values())
        env = samples[['year', 'target_date', 'env_window_complete', *env_sources]].copy()
        conflict = env.groupby(['year', 'target_date'], dropna=False)[env_sources].nunique(dropna=False).max(axis=1)
        if (conflict > 1).any():
            raise ValueError('Environment features are not unique within year/date')
        env = env.drop_duplicates(['year', 'target_date']).rename(columns={'target_date': 'image_date', **{v: VIEW_SOURCE[k] for k, v in PLANT_SOURCE.items()}})
        embedding_cols = [f'embedding_{i}' for i in range(512)]
        selected_embedding = embeddings[['image_path', *embedding_cols]].copy()
        merged = views.merge(selected_embedding, on='image_path', how='inner', validate='one_to_one').merge(
            env, on=['year', 'image_date'], how='left', validate='many_to_one')
        keep = merged['height_t0_mean'].notna() & merged['env_window_complete'].eq(True)
        merged = merged.loc[keep].copy()
        outcome = merged['future_target_available'].fillna(False) & merged['height_t7_mean'].notna() & merged['delta_height_mean'].notna()
        frame = pd.DataFrame({
            'case_id': 'view__' + merged['year'].astype(str) + '__' + merged['view_id'].astype(str) + '__' + merged['image_date'].astype(str),
            'scope': 'view', 'entity_id': merged['view_id'], 'view_id': merged['view_id'],
            'physical_view_id': merged['physical_view_id'], 'physical_view_id_status': merged['physical_view_id_status'],
            'case_date': merged['image_date'], 'image_date': merged['image_date'],
            'outcome_date': merged['future_date_exact'], 'year': merged['year'].astype(int),
            'treatment_id': merged['treatment_id_primary'], 'variety': merged['variety_primary'],
            'image_path': merged['image_path'], 'view_mean_height_t0': merged['height_t0_mean'],
            'view_mean_height_t0_paired': merged['height_t0_paired_mean'],
            'height_t7': merged['height_t7_mean'], 'delta_height': merged['delta_height_mean'],
            'n_plants': np.where(outcome, merged['n_paired_plants'], merged['n_current_valid_plants']),
            'target_coverage': np.where(outcome, merged['coverage_ratio_paired'], merged['coverage_ratio_current']),
            'outcome_available': outcome,
            'paired_cohort_rule': merged['paired_cohort_rule'],
            'environment_scope': 'greenhouse_global',
            'substrate_moisture_scope': 'greenhouse_global_proxy',
            'substrate_temperature_scope': 'greenhouse_global_proxy',
            'case_memory_version': self.VERSION,
        })
        for target in SENSOR_FEATURES:
            frame[target] = merged['sensor_' + PLANT_SOURCE[target]].to_numpy()
        frame.loc[~frame['outcome_available'], ['height_t7', 'delta_height', 'outcome_date']] = np.nan
        if not frame['case_id'].is_unique:
            raise ValueError('View case_id is not unique')
        order = np.lexsort((frame['view_id'].astype(str), frame['case_date'].astype(str)))
        frame = frame.iloc[order].reset_index(drop=True)
        vectors = merged.iloc[order][embedding_cols].to_numpy(np.float32)
        return frame, vectors

    def build(self):
        self.output.mkdir(parents=True, exist_ok=True)
        plant = self.build_plant_cases()
        view, vectors = self.build_view_cases()
        plant_path = self.project / self.config['storage']['plant_cases']
        view_path = self.project / self.config['storage']['view_cases']
        embedding_path = self.project / self.config['storage']['view_embeddings']
        normalizer_path = self.project / self.config['storage']['normalizers']
        manifest_path = self.project / self.config['storage']['manifest']
        plant.to_csv(plant_path, index=False)
        view.to_csv(view_path, index=False)
        np.savez_compressed(embedding_path, case_ids=view['case_id'].to_numpy(str), embeddings=vectors)
        plant_train = plant[(plant.year == 2023) & plant.outcome_available]
        view_train = view[(view.year == 2023) & view.outcome_available]
        normalizers = {
            'plant_state': _fit_stats(plant_train, PLANT_STATE_FEATURES),
            'plant_sensor': _fit_stats(plant_train, SENSOR_FEATURES),
            'view_state': _fit_stats(view_train, VIEW_STATE_FEATURES),
            'view_sensor': _fit_stats(view_train, SENSOR_FEATURES),
        }
        joblib.dump(normalizers, normalizer_path)
        sources = [
            self.research / 'data/processed/plant_daily_sample_index.csv',
            self.research / 'data/indexes/view_date_dataset.csv',
            self.research / 'data/processed/image_embeddings.csv',
        ]
        manifest = {
            'case_memory_version': self.VERSION,
            'built_at': datetime.now(timezone.utc).isoformat(),
            'source_dataset': 'tomato_multimodal_public canonical V0.2/V0.5 assets',
            'source_files': [{'path': str(path), 'sha256': _digest(path)} for path in sources],
            'feature_schema': {'plant_state': PLANT_STATE_FEATURES, 'view_state': VIEW_STATE_FEATURES, 'sensor': SENSOR_FEATURES, 'image_dimension': 512},
            'target_definition': 'exact +7 day observed height; View targets preserve V0.5 same-plant paired cohort',
            'plant_cases': {'rows': len(plant), 'outcome_available': int(plant.outcome_available.sum())},
            'view_cases': {'rows': len(view), 'outcome_available': int(view.outcome_available.sum())},
            'normalizer_fit_rule': '2023 outcome-available cases only',
            'storage_note': 'CSV metadata plus compressed NPZ embeddings; pyarrow was unavailable.',
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        return manifest
