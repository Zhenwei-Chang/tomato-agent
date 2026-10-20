from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import yaml
from ..schemas.common import ErrorCode, ToolFailure
from .schemas import RetrievalMode, RetrievalPolicy


class HistoricalAvailabilityPolicy:
    RULE = 'outcome_date <= query_date'

    @staticmethod
    def apply(cases: pd.DataFrame, query_date, mode: RetrievalMode):
        available = cases[cases['outcome_available'].fillna(False)].copy()
        if mode == RetrievalMode.historical:
            cutoff = pd.Timestamp(query_date)
            available = available[pd.to_datetime(available['outcome_date']) <= cutoff]
        return available

    @staticmethod
    def assert_safe(cases: pd.DataFrame, query_date):
        if not cases.empty and (pd.to_datetime(cases['outcome_date']) > pd.Timestamp(query_date)).any():
            raise AssertionError('Future outcome entered historical retrieval')


class CaseRepository:
    def __init__(self, project_root: Path, config_path: Path | None = None):
        self.project = Path(project_root)
        self.config_path = config_path or self.project / 'configs/case_retrieval.yaml'
        self.config = yaml.safe_load(self.config_path.read_text(encoding='utf-8'))

    def _path(self, key):
        return self.project / self.config['storage'][key]

    @lru_cache(maxsize=2)
    def cases(self, scope: str):
        key = 'plant_cases' if scope == 'plant' else 'view_cases'
        path = self._path(key)
        if not path.is_file():
            raise ToolFailure(ErrorCode.MODEL_NOT_AVAILABLE, 'Case Memory has not been built', asset=str(path))
        frame = pd.read_csv(path, low_memory=False)
        frame['case_date'] = pd.to_datetime(frame['case_date'])
        frame['outcome_date'] = pd.to_datetime(frame['outcome_date'])
        return frame

    @lru_cache(maxsize=1)
    def view_embeddings(self):
        path = self._path('view_embeddings')
        if not path.is_file():
            raise ToolFailure(ErrorCode.MODEL_NOT_AVAILABLE, 'View Case embeddings unavailable', asset=str(path))
        data = np.load(path, allow_pickle=False)
        return {case_id: vector for case_id, vector in zip(data['case_ids'].astype(str), data['embeddings'])}

    @lru_cache(maxsize=1)
    def normalizers(self):
        path = self._path('normalizers')
        if not path.is_file():
            raise ToolFailure(ErrorCode.MODEL_NOT_AVAILABLE, 'Case normalizers unavailable', asset=str(path))
        return joblib.load(path)

    def query_case(self, scope: str, entity_id: str, case_date):
        frame = self.cases(scope)
        selected = frame[(frame['entity_id'].astype(str) == str(entity_id)) & (frame['case_date'] == pd.Timestamp(case_date))]
        if len(selected) != 1:
            raise ToolFailure(ErrorCode.DATA_NOT_FOUND, 'Exact-date Case not found uniquely', scope=scope, entity_id=entity_id, date=str(case_date))
        return selected.iloc[0]

    def candidates(self, query, mode: RetrievalMode, policy: RetrievalPolicy,
                   exclude_same_entity=True, year_filter=None, treatment_filter=None):
        scope = str(query['scope'])
        cases = HistoricalAvailabilityPolicy.apply(self.cases(scope), query['case_date'], mode)
        cases = cases[cases['case_id'] != query['case_id']]
        if exclude_same_entity or policy == RetrievalPolicy.cross_entity:
            cases = cases[cases['entity_id'].astype(str) != str(query['entity_id'])]
        if policy == RetrievalPolicy.cross_year:
            cases = cases[cases['year'].astype(int) != int(query['year'])]
        if year_filter is not None:
            cases = cases[cases['year'].astype(int) == int(year_filter)]
        if treatment_filter is not None:
            cases = cases[cases['treatment_id'].astype(str) == str(treatment_filter)]
        if mode == RetrievalMode.historical:
            HistoricalAvailabilityPolicy.assert_safe(cases, query['case_date'])
        return cases.copy()
