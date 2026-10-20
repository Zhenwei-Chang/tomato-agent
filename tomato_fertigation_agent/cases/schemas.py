from enum import Enum
from typing import Any, Literal
from pydantic import Field
from ..schemas.common import Confidence, Contract, Scope


class RetrievalMode(str, Enum):
    historical = 'historical'
    retrospective = 'retrospective'


class RetrievalPolicy(str, Enum):
    unrestricted = 'unrestricted'
    cross_entity = 'cross_entity'
    cross_year = 'cross_year'


class CaseMatch(Contract):
    case_id: str
    scope: Scope
    entity_id: str
    case_date: str
    outcome_date: str
    year: int
    similarity: float = Field(ge=0, le=1)
    similarity_breakdown: dict[str, float]
    case_context: dict[str, Any]
    historical_outcome: dict[str, float]
    same_year: bool
    same_treatment: bool | None = None
    same_variety: bool | None = None
    domain_warning: bool = False
    warnings: list[str] = Field(default_factory=list)

class RetrievalSummary(Contract):
    requested_top_k: int
    returned_cases: int
    candidate_count: int
    similarity_min: float | None = None
    similarity_max: float | None = None
    similarity_mean: float | None = None
    outcome_mean: float | None = None
    outcome_median: float | None = None
    outcome_std: float | None = None
    outcome_range: list[float] | None = None
    similarity_weighted_height_t7_cm: float | None = None
    similarity_weighted_delta_height_cm: float | None = None
    same_year_rate: float | None = None
    same_treatment_rate: float | None = None
    same_variety_rate: float | None = None
    narrative: str


class CaseRetrievalResult(Contract):
    query_case: dict[str, Any]
    matches: list[CaseMatch]
    summary: RetrievalSummary
    retrieval_confidence: Confidence
    ood: bool
    ood_reasons: list[str] = Field(default_factory=list)
    retrieval_mode: RetrievalMode
    retrieval_policy: RetrievalPolicy
    historical_availability_rule: Literal['outcome_date <= query_date', 'retrospective_offline_only']
    minimum_similarity: float | None = None
    warnings: list[str] = Field(default_factory=list)
