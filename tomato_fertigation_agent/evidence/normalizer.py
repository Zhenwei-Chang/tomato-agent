from __future__ import annotations

from typing import Iterable
from hashlib import sha256
import json

from ..schemas.common import Confidence, EvidenceItem, Scope, ToolResult
from .schemas import EvidenceRecord, EvidenceType


def _record_id(prefix: str, result: ToolResult, suffix: str = "") -> str:
    tail = f"-{suffix}" if suffix else ""
    return f"{prefix}-{result.metadata.tool_call_id}{tail}"


def _stable_case_id(prefix: str, *parts) -> str:
    payload=json.dumps(parts,ensure_ascii=False,sort_keys=True,default=str)
    return f"{prefix}-{sha256(payload.encode('utf-8')).hexdigest()[:16]}"


class EvidenceNormalizer:
    """Maps heterogeneous ToolResult payloads to compact, typed evidence records."""

    def normalize(self, results: Iterable[ToolResult], accepted_knowledge: list[EvidenceItem] | None = None) -> list[EvidenceRecord]:
        accepted_by_id = {item.evidence_id: item for item in accepted_knowledge or []}
        accepted_ids = set(accepted_by_id)
        knowledge_filter_supplied = accepted_knowledge is not None
        records: list[EvidenceRecord] = []
        for result in results:
            if result.status == "error":
                continue
            name, data = result.metadata.tool_name, result.data
            common = dict(source_tool=name, reliability=result.metadata.confidence,
                limitations=result.metadata.limitations,
                provenance={"tool_call_id": result.metadata.tool_call_id,
                    "trace_id": result.metadata.trace_id,
                    "data_source": result.metadata.data_source,
                    "model_version": result.metadata.model_version})
            if name == "get_growth_context":
                entity = data.get("plant_id") or data.get("view_id")
                phenotype = data.get("phenotype", {})
                if any(value is not None for value in phenotype.values()):
                    records.append(EvidenceRecord(evidence_id=_record_id("OBS", result), evidence_type=EvidenceType.OBSERVATION,
                        scope=result.metadata.scope, entity_id=entity, timestamp=data.get("date"),
                        value={"phenotype": phenotype, "treatment_ids": data.get("treatment_ids", []),
                               "varieties": data.get("varieties", []), "data_quality": data.get("data_quality", {})}, **common))
            elif name == "get_sensor_history":
                records.append(EvidenceRecord(evidence_id=_record_id("SENSOR", result), evidence_type=EvidenceType.SENSOR,
                    scope=Scope.greenhouse, entity_id=None, timestamp=data.get("end_date"),
                    value={"start_date": data.get("start_date"), "end_date": data.get("end_date"),
                           "window_days": data.get("window_days"), "summary": data.get("summary", {}),
                           "spatial_scope": data.get("spatial_scope", {}), "data_quality": data.get("data_quality", {})}, **common))
            elif name == "get_treatment_recipe":
                records.append(EvidenceRecord(evidence_id=_record_id("TREAT", result), evidence_type=EvidenceType.OBSERVATION,
                    scope=Scope.treatment, entity_id=data.get("treatment_id"),
                    value={"fertilizer_salts": data.get("fertilizer_salts", {}), "elements": data.get("elements", {}),
                           "derived_fields": data.get("derived_fields", [])}, **common))
            elif name == "predict_height_t7":
                prediction = data.get("prediction", {})
                records.append(EvidenceRecord(evidence_id=_record_id("MODEL", result), evidence_type=EvidenceType.PREDICTION,
                    scope=Scope.plant, entity_id=data.get("plant_id"), timestamp=prediction.get("target_date"),
                    value={"height_t7_cm": prediction.get("height_t7_cm"), "horizon_days": 7,
                           "current_state": data.get("current_state", {})}, **common))
            elif name == "analyze_rgb":
                prediction = data.get("prediction", {})
                records.append(EvidenceRecord(evidence_id=_record_id("VISUAL", result), evidence_type=EvidenceType.VISUAL_OBSERVATION,
                    scope=Scope.view, timestamp=None, value={"current_view_mean_height_cm": prediction.get("current_view_mean_height_cm"),
                    "image_path": data.get("image_path")}, **common))
                records.append(EvidenceRecord(evidence_id=_record_id("MODEL", result, "t7"), evidence_type=EvidenceType.PREDICTION,
                    scope=Scope.view, timestamp=None, value={"height_t7_cm": prediction.get("future_view_mean_height_t7_cm"),
                    "horizon_days": 7}, **common))
            elif name == "get_image_embedding":
                # Representation provenance is registered for retrieval/audit,
                # but the vector is not direct support for an agronomic claim.
                records.append(EvidenceRecord(evidence_id=_record_id("VISUAL-REP", result),
                    evidence_type=EvidenceType.VISUAL_OBSERVATION, scope=Scope.view,
                    timestamp=data.get("image_date"),
                    value={"image_path": data.get("image_path"),
                           "embedding_dim": len(data.get("embedding", [])),
                           "representation_only": True,
                           "claim_supporting": False}, **common))
            elif name == "find_similar_cases":
                summary = data.get("summary", {})
                query=data.get("query_case") or {}; matches=data.get("matches", [])
                query_date=query.get("date"); entity_id=query.get("entity_id")
                retrieval={"retrieval_mode":data.get("retrieval_mode"),
                    "retrieval_policy":data.get("retrieval_policy"),
                    "retrieval_confidence":data.get("retrieval_confidence"),
                    "historical_availability_rule":data.get("historical_availability_rule")}
                records.append(EvidenceRecord(evidence_id=_stable_case_id("CASE-SUMMARY",
                    result.metadata.scope.value,entity_id,query_date,[m.get('case_id') for m in matches]),
                    evidence_type=EvidenceType.HISTORICAL_CASE,scope=result.metadata.scope,
                    entity_id=entity_id,timestamp=query_date,
                    value={"case_ids": [item.get("case_id") for item in matches],
                           "similarity_min": summary.get("similarity_min"), "similarity_max": summary.get("similarity_max"),
                           "case_weighted_height_t7_cm": summary.get("similarity_weighted_height_t7_cm"),
                           "outcome_distribution": summary.get("outcome_distribution", {}),
                           "retrieval_confidence": data.get("retrieval_confidence"), "ood": data.get("ood"),
                           "ood_reasons": data.get("ood_reasons", []),
                           "domain_warnings": [m.get("case_id") for m in matches if m.get("domain_warning")],
                           **retrieval}, **common))
                for match in matches:
                    records.append(EvidenceRecord(evidence_id=_stable_case_id("CASE-ITEM",
                        result.metadata.scope.value,entity_id,query_date,match.get('case_id')),
                        evidence_type=EvidenceType.HISTORICAL_CASE,scope=result.metadata.scope,
                        entity_id=match.get('entity_id') or match.get('plant_id') or match.get('view_id'),
                        timestamp=match.get('case_date'),value={"case_id":match.get('case_id'),
                            "query_timestamp":query_date,"case_date":match.get('case_date'),
                            "outcome_date":match.get('outcome_date'),"similarity":match.get('similarity'),
                            "historical_outcome":match.get('historical_outcome',{}),
                            "domain_warning":match.get('domain_warning',False),
                            "same_year":match.get('same_year'),"ood":data.get('ood'),**retrieval},**common))
            elif name == "retrieve_water_fertilizer_knowledge":
                for item in result.evidence:
                    if knowledge_filter_supplied and item.evidence_id not in accepted_ids:
                        continue
                    item = accepted_by_id.get(item.evidence_id, item)
                    records.append(EvidenceRecord(evidence_id=item.evidence_id, evidence_type=EvidenceType.KNOWLEDGE,
                        source_tool=name, scope=Scope.knowledge, value={"source": item.source, "locator": item.locator,
                            "summary": item.content[:500], "score": item.score,
                            "relevance": item.attributes.get("relevance_label"),
                            "applicability": item.attributes.get("applicability"),
                            "allowed_use": item.attributes.get("allowed_use")},
                        reliability=Confidence.MEDIUM if item.score is not None else Confidence.UNKNOWN,
                        limitations=result.metadata.limitations,
                        provenance={"tool_call_id": result.metadata.tool_call_id, "trace_id": result.metadata.trace_id,
                            "data_source": [item.source], "locator": item.locator}))
            elif name == "assess_prediction_reliability":
                level = Confidence(data.get("confidence", "UNKNOWN"))
                records.append(EvidenceRecord(evidence_id=_record_id("RELIABILITY", result), evidence_type=EvidenceType.RELIABILITY,
                    source_tool=name, scope=result.metadata.scope, value={"confidence": level.value,
                        "confidence_reason": data.get("confidence_reason", []),
                        "statistically_calibrated": data.get("statistically_calibrated", False)},
                    reliability=level, limitations=result.metadata.limitations, provenance=common["provenance"]))
        return records
