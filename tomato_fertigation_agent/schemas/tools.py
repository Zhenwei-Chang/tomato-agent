from datetime import date as Date
from typing import Literal
from pydantic import Field, model_validator
from .common import Contract, Scope


class ContextInput(Contract):
    date: Date
    year: int = Field(ge=2000, le=2100)
    plant_id: str | None = Field(default=None, min_length=1)
    view_id: str | None = Field(default=None, min_length=1)
    treatment_id: str | None = Field(default=None, min_length=1)
    matching_strategy: Literal["exact"] = "exact"

    @model_validator(mode="after")
    def check(self):
        if self.date.year != self.year:
            raise ValueError("year must equal date.year")
        if self.plant_id and self.view_id:
            raise ValueError("Choose plant_id or view_id, not both")
        return self


class SensorInput(Contract):
    end_date: Date
    window_days: int = Field(default=7, ge=1, le=90)
    view_id: str | None = Field(default=None, min_length=1)
    plant_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def check(self):
        if self.plant_id and self.view_id:
            raise ValueError("Choose plant_id or view_id, not both")
        return self


class TreatmentInput(Contract):
    treatment_id: str = Field(min_length=1, max_length=30)


class PredictionInput(Contract):
    year: int = Field(ge=2000, le=2100)
    date: Date
    plant_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def check(self):
        if self.year != self.date.year:
            raise ValueError("year must equal date.year")
        return self


class ImageInput(Contract):
    image_path: str | None = Field(default=None, min_length=1)
    view_id: str | None = Field(default=None, min_length=1)
    date: Date | None = None
    requested_scope: Scope = Scope.view

    @model_validator(mode="after")
    def check(self):
        by_path = self.image_path is not None
        by_view = self.view_id is not None and self.date is not None
        if by_path == by_view or (by_path and (self.view_id or self.date)) or (not by_path and not by_view):
            raise ValueError("Provide image_path OR view_id + date")
        return self


class RGBInput(ImageInput):
    include_embedding: bool = False


class KnowledgeInput(Contract):
    query: str = Field(min_length=1, max_length=4000)
    growth_stage: str | None = Field(default=None, max_length=100)
    topic: str | None = Field(default=None, max_length=100)
    top_k: int = Field(default=6, ge=1, le=20)

    @model_validator(mode="after")
    def check(self):
        if not self.query.strip():
            raise ValueError("query cannot be blank")
        return self


class ReliabilityInput(Contract):
    model_name: Literal["height_v03_b0", "rgb_v05", "unknown"]
    year: int | None = Field(default=None, ge=2000, le=2100)
    requested_scope: Scope
    model_scope: Scope
    critical_features_complete: bool | None = None
    sensor_available: bool | None = None
    image_available: bool | None = None
    scenario_id: str | None = None
    case_retrieval_confidence: Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"] | None = None
    case_model_agreement: Literal["AGREE", "PARTIAL", "DISAGREE", "NOT_AVAILABLE"] | None = None


class SimilarCasesInput(Contract):
    scope: Literal["plant", "view"]
    date: Date
    plant_id: str | None = Field(default=None, min_length=1)
    view_id: str | None = Field(default=None, min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)
    historical_only: bool = True
    retrieval_mode: Literal["historical", "retrospective"] = "historical"
    retrieval_policy: Literal["unrestricted", "cross_entity", "cross_year"] = "cross_entity"
    exclude_same_entity: bool = True
    year_filter: int | None = Field(default=None, ge=2000, le=2100)
    treatment_filter: str | None = Field(default=None, min_length=1, max_length=30)
    minimum_similarity: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def check(self):
        if self.scope == "plant" and (not self.plant_id or self.view_id):
            raise ValueError("Plant scope requires plant_id and forbids view_id")
        if self.scope == "view" and (not self.view_id or self.plant_id):
            raise ValueError("View scope requires view_id and forbids plant_id")
        if self.historical_only != (self.retrieval_mode == "historical"):
            raise ValueError("historical_only must agree with retrieval_mode")
        return self
