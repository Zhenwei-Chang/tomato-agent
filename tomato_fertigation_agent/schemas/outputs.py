"""Minimum required payloads; source-specific provenance fields stay extensible."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class Payload(BaseModel):
    model_config = ConfigDict(extra='allow',allow_inf_nan=False)


class GrowthPayload(Payload):
    year: int
    date: str
    phenotype: dict[str,float | None]
    environment: dict[str,Any]
    treatment_ids: list[str]
    varieties: list[Any]
    available_images: list[dict]
    data_quality: dict


class SensorPayload(Payload):
    end_date: str
    start_date: str
    window_days: int
    spatial_scope: dict[str,str]
    daily: list[dict]
    summary: dict
    data_quality: dict


class TreatmentPayload(Payload):
    treatment_id: str
    fertilizer_salts: dict
    elements: dict
    derived_fields: list[str]
    source: str
    is_irrigation_or_fertilization_event: Literal[False]


class HeightValue(Payload):
    height_t7_cm: float
    target_date: str
    horizon_days: Literal[7]


class HeightPayload(Payload):
    plant_id: str
    year: int
    date: str
    prediction: HeightValue
    current_state: dict[str,float]
    input_window: dict[str,str]
    model: dict


class EmbeddingPayload(Payload):
    image_path: str
    dimension: Literal[512]
    embedding: list[float] = Field(min_length=512,max_length=512)
    encoder: str
    embedding_source: str


class VisionValue(Payload):
    current_view_mean_height_cm: float
    future_view_mean_height_t7_cm: float
    horizon_days: Literal[7]


class VisionPayload(Payload):
    image_path: str
    dimension: Literal[512]
    prediction: VisionValue
    model_heads: list[str]


class KnowledgePayload(Payload):
    query: str
    effective_query: str
    retrieved_chunks: list[dict]
    snapshot_id: str
    retrieval_only: Literal[True]
    existing_rag_generated_answer: None
    answer_sufficiency: Literal['NOT_ASSESSED']


class ReliabilityPayload(Payload):
    confidence: Literal['HIGH','MEDIUM','LOW','UNKNOWN']
    confidence_reason: list[str]
    assessment_type: Literal['rule_based']
    statistically_calibrated: Literal[False]
    input_metadata_verified: Literal[False]


class SimilarCasesPayload(Payload):
    query_case: dict
    matches: list[dict]
    summary: dict
    retrieval_confidence: Literal['HIGH','MEDIUM','LOW','UNKNOWN']
    ood: bool
    ood_reasons: list[str]
    retrieval_mode: Literal['historical','retrospective']
    retrieval_policy: Literal['unrestricted','cross_entity','cross_year']
    historical_availability_rule: str
    minimum_similarity: float | None
    warnings: list[str]


OUTPUTS = dict(get_growth_context=GrowthPayload,get_sensor_history=SensorPayload,
               get_treatment_recipe=TreatmentPayload,predict_height_t7=HeightPayload,
               analyze_rgb=VisionPayload,get_image_embedding=EmbeddingPayload,
               retrieve_water_fertilizer_knowledge=KnowledgePayload,assess_prediction_reliability=ReliabilityPayload,
               find_similar_cases=SimilarCasesPayload)
