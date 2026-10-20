from functools import lru_cache
from datetime import timedelta
from pathlib import Path
import pandas as pd
import numpy as np
from .loading import load_source, json_clean, file_hash
from ..schemas.common import ToolFailure, ErrorCode

SENSORS = ['air_temperature', 'relative_humidity', 'light', 'co2', 'substrate_temperature', 'substrate_moisture']
PHENOTYPES = ['plant_height_cm', 'lai', 'stem_diameter_mm', 'growth_state']


class MultimodalAdapter:
    def __init__(self, settings):
        self.settings = settings
        self.root = settings.research

    @lru_cache(maxsize=12)
    def table(self, relative):
        path = self.root / relative
        if not path.is_file():
            raise ToolFailure(ErrorCode.DATA_NOT_FOUND, 'Research table unavailable', path=str(path))
        return pd.read_csv(path, low_memory=False)

    def evidence(self, relative, locator=''):
        path = self.root / relative
        return {'evidence_id': path.name, 'source': str(path), 'locator': locator,
                'attributes': {'sha256': file_hash(path)}}

    def plant(self, plant_id, year):
        plants = self.table('data/processed/plants_canonical.csv')
        selected = plants[(plants.plant_id == plant_id) & (plants.year == year)]
        if len(selected) != 1:
            raise ToolFailure(ErrorCode.DATA_NOT_FOUND, 'Plant/year not found uniquely', plant_id=plant_id, year=year)
        return selected.iloc[0]

    def check_view(self, view_id, year):
        views = self.table('data/indexes/view_date_dataset.csv')
        if views[(views.view_id == view_id) & (views.year == year)].empty:
            raise ToolFailure(ErrorCode.DATA_NOT_FOUND, 'View/year not found', view_id=view_id, year=year)

    def observed(self, plant_id, day):
        ph = self.table('data/processed/phenotype_canonical.csv')
        rows = ph[(ph.plant_id == plant_id) & (ph.observation_date == str(day))]
        if len(rows) != 1:
            raise ToolFailure(ErrorCode.DATA_NOT_FOUND, 'Exact-date phenotype not found', plant_id=plant_id, date=str(day))
        return rows.iloc[0]

    def context(self, args):
        ph = self.table('data/processed/phenotype_canonical.csv')
        rows = ph[(ph.year == args.year) & (ph.observation_date == str(args.date))].copy()
        scope = 'dataset'
        if args.plant_id:
            plant = self.plant(args.plant_id, args.year)
            rows = rows[rows.plant_id == args.plant_id]
            scope = 'plant'
        elif args.view_id:
            self.check_view(args.view_id, args.year)
            rows = rows[rows.view_id == args.view_id]
            scope = 'view'
        if args.treatment_id:
            self.recipe(args.treatment_id)
            rows = rows[rows.treatment_id == args.treatment_id]
            if scope == 'dataset':
                scope = 'treatment'
        if rows.empty:
            raise ToolFailure(ErrorCode.DATA_NOT_FOUND, 'No exact-date phenotype rows for selection')
        phenotype, counts = {}, {}
        for col in PHENOTYPES:
            valid = rows[col].copy()
            flag = col + '_is_observed'
            if flag in rows:
                valid = valid.where(rows[flag].eq(True))
            elif col == 'growth_state':
                valid[:] = None  # Source growth-state labels are not plant observations.
            valid = pd.to_numeric(valid, errors='coerce')
            counts[col] = int(valid.notna().sum())
            phenotype[col] = float(valid.mean()) if valid.notna().any() else None
        env = self.table('data/processed/environment_daily_canonical.csv')
        env = env[env.date == str(args.date)]
        views = self.table('data/indexes/view_date_dataset.csv')
        views = views[(views.year == args.year) & (views.image_date == str(args.date)) & views.view_id.isin(rows.view_id.dropna())]
        warnings = [f'{k} unavailable on exact date' for k, v in phenotype.items() if v is None]
        if env.empty:
            warnings.append('Exact-date environment unavailable')
        data = {'year': args.year, 'date': str(args.date), 'plant_id': args.plant_id,
                'view_id': args.view_id, 'phenotype': phenotype, 'phenotype_valid_counts': counts,
                'aggregation': 'single_plant' if scope == 'plant' else 'mean_of_valid_exact_date_values',
                'n_plants': int(rows.plant_id.nunique()),
                'treatment_ids': sorted(rows.treatment_id.dropna().unique().tolist()),
                'varieties': rows.variety.dropna().unique().tolist(),
                'environment': {'scope': 'greenhouse', 'values': env[SENSORS].iloc[0].to_dict() if len(env) else {c: None for c in SENSORS}, 'substrate_scope': 'greenhouse_global_proxy'},
                'available_images': views[['image_path', 'view_id', 'image_date']].assign(scope='view').to_dict('records'),
                'data_quality': {'matching_strategy': 'exact', 'missing_fields': [c for c,v in phenotype.items() if v is None],
                                 'value_sources': rows.value_source.dropna().unique().tolist(),
                                 'lineage': 'final processed non-interpolation; original manual measurement UNKNOWN'}}
        return json_clean(data), scope, warnings

    def sensor(self, args):
        if args.plant_id:
            self.plant(args.plant_id, args.end_date.year)
        if args.view_id:
            self.check_view(args.view_id, args.end_date.year)
        env = self.table('data/processed/environment_daily_canonical.csv')
        start = args.end_date - timedelta(days=args.window_days-1)
        selected = env[(env.date >= str(start)) & (env.date <= str(args.end_date))].copy()
        if selected.empty:
            raise ToolFailure(ErrorCode.DATA_NOT_FOUND, 'No sensor days in requested window')
        if selected.date.duplicated().any():
            raise ToolFailure(ErrorCode.DEPENDENCY_ERROR, 'Ambiguous global sensor dates')
        feature_module = load_source(self.root / 'src/features/environment.py')
        daily = selected.set_index('date')[SENSORS].reindex(pd.date_range(start, args.end_date).strftime('%Y-%m-%d'))
        daily.index.name = 'date'
        daily['vpd_kpa'] = feature_module.calculate_vpd_kpa(daily.air_temperature, daily.relative_humidity)
        missing_days = daily.index[daily[SENSORS].isna().all(axis=1)].tolist()
        summary = {c: {'mean': daily[c].mean(), 'min': daily[c].min(), 'max': daily[c].max(), 'std': daily[c].std(ddof=0)} for c in daily}
        data = {'end_date': str(args.end_date), 'start_date': str(start), 'window_days': args.window_days,
                'requested_plant_id': args.plant_id, 'requested_view_id': args.view_id,
                'spatial_scope': {c: 'greenhouse_global_proxy' if c.startswith('substrate') else 'greenhouse_global' for c in daily},
                'daily': daily.reset_index().to_dict('records'), 'summary': summary,
                'data_quality': {'missing_dates': missing_days, 'missing_values': int(daily.isna().sum().sum()), 'complete': not daily.isna().any().any()},
                'units': {'air_temperature':'degC','relative_humidity':'percent','light':'source labels lux; scale unverified','co2':'ppm','substrate_temperature':'degC','substrate_moisture':'percent proxy','vpd_kpa':'kPa'}}
        return json_clean(data), ['Incomplete sensor window; missing values remain null'] if daily.isna().any().any() else []

    def recipe(self, treatment):
        table = self.table('data/processed/treatments_canonical.csv')
        rows = table[table.treatment_id == treatment]
        if len(rows) != 1:
            raise ToolFailure(ErrorCode.DATA_NOT_FOUND, 'Unknown treatment ID', treatment_id=treatment)
        row = rows.iloc[0]
        salts = ['KNO3','NH4H2PO4','KH2PO4','K2SO4','MgSO4.7H2O','CaCl2','CaNO3.4H2O']
        derived = ['N_mgL','P_mgL','K_mgL','Ca_mgL','Mg_mgL','S_mgL']
        return json_clean({'treatment_id': treatment, 'fertilizer_salts': {c:{'value':row[c], 'unit':'mg/L', 'value_source':'derived_plan_fill' if treatment == 'CK' and c == 'K2SO4' else 'extracted_recipe'} for c in salts},
                           'elements': {c:{'value':row[c], 'unit':'mg/L', 'value_source':'derived_from_recipe'} for c in derived},
                           'derived_fields': derived + (['K2SO4'] if treatment == 'CK' else []), 'source': row.canonical_source,
                           'is_irrigation_or_fertilization_event': False})

    def prediction_features(self, args, expected):
        plant = self.plant(args.plant_id, args.year)
        observed = self.observed(args.plant_id, args.date)
        for col in ['plant_height_cm', 'lai']:
            if pd.isna(observed[col]) or observed[col + '_is_observed'] != True or observed.is_interpolated == True:
                raise ToolFailure(ErrorCode.DATA_NOT_FOUND, 'B0 requires non-interpolated current height and LAI', field=col)
        module = load_source(self.root / 'src/features/environment.py')
        values = module.build_environment_features(self.table('data/processed/environment_daily_canonical.csv'), pd.Timestamp(args.date), 7)
        if not values['env_window_complete']:
            raise ToolFailure(ErrorCode.DATA_NOT_FOUND, 'B0 requires complete seven-day sensor window')
        values.update(height_t0=float(observed.plant_height_cm), lai_t0=float(observed.lai), variety=plant.variety, treatment_id=plant.treatment_id)
        if any(c not in values for c in expected) or any('_t7' in c or c in {'year', 'date'} for c in expected):
            raise ToolFailure(ErrorCode.MODEL_NOT_AVAILABLE, 'Checkpoint input schema is incompatible')
        return pd.DataFrame([{c:values[c] for c in expected}]), values, observed
