from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json

from ..schemas.agent import AgentAnswer, AggregatedEvidence
from ..schemas.common import EvidenceItem, ToolResult


def _identity(item: EvidenceItem, result: ToolResult) -> str:
    payload = {
        "source": item.source,
        "locator": item.locator,
        "content": item.content,
        "source_tool": result.metadata.tool_name,
        "scope": result.metadata.scope.value,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


@dataclass
class EvidenceAssembly:
    registry: list[EvidenceItem] = field(default_factory=list)
    ids_by_tool_call: dict[str, list[str]] = field(default_factory=dict)
    reliability_ids: list[str] = field(default_factory=list)


@dataclass
class EvidenceValidation:
    collected: int = 0
    referenced: int = 0
    missing_references: list[str] = field(default_factory=list)
    invalid_references: list[str] = field(default_factory=list)
    semantic_mismatches: list[str] = field(default_factory=list)


class EvidenceAssembler:
    """Deterministic Atomic evidence registry and final-answer linker.

    The LLM may select prose, but it cannot create evidence records or decide
    which ToolResult source backs a structured fact/prediction.
    """

    NON_CLAIM_TOOLS = {"get_image_embedding"}

    def assemble(self, results: list[ToolResult], accepted_knowledge=None) -> EvidenceAssembly:
        accepted = {item.evidence_id for item in accepted_knowledge or []}
        knowledge_filter = accepted_knowledge is not None
        by_id: dict[str, EvidenceItem] = {}
        identity_by_id: dict[str, str] = {}
        ids_by_call: dict[str, list[str]] = {}
        reliability_ids: list[str] = []
        for result in results:
            if result.status == "error":
                continue
            ids: list[str] = []
            for raw in result.evidence:
                if (result.metadata.tool_name == "retrieve_water_fertilizer_knowledge"
                        and knowledge_filter and raw.evidence_id not in accepted):
                    continue
                identity = _identity(raw, result)
                candidate = raw.evidence_id
                if candidate in identity_by_id and identity_by_id[candidate] != identity:
                    candidate = f"{candidate}-{sha256(identity.encode('utf-8')).hexdigest()[:10]}"
                attrs = dict(raw.attributes)
                attrs.update({
                    "source_tool": result.metadata.tool_name,
                    "tool_call_id": result.metadata.tool_call_id,
                    "trace_id": result.metadata.trace_id,
                    "scope": result.metadata.scope.value,
                    "model_version": result.metadata.model_version,
                    "claim_supporting": result.metadata.tool_name not in self.NON_CLAIM_TOOLS,
                })
                item = raw.model_copy(update={"evidence_id": candidate, "attributes": attrs})
                if candidate not in by_id:
                    by_id[candidate] = item
                    identity_by_id[candidate] = identity
                ids.append(candidate)
            # Reliability has no external file evidence; register the rule result itself.
            if result.metadata.tool_name == "assess_prediction_reliability":
                payload = json.dumps(result.data, ensure_ascii=False, sort_keys=True, default=str)
                candidate = f"reliability-{sha256(payload.encode('utf-8')).hexdigest()[:12]}"
                item = EvidenceItem(evidence_id=candidate,
                    source="rule-based reliability assessment",
                    locator=result.metadata.model_version or result.metadata.tool_version,
                    content=payload,
                    attributes={"source_tool": result.metadata.tool_name,
                        "tool_call_id": result.metadata.tool_call_id,
                        "trace_id": result.metadata.trace_id,
                        "scope": result.metadata.scope.value,
                        "statistically_calibrated": False,
                        "claim_supporting": True})
                by_id.setdefault(candidate, item)
                ids.append(candidate); reliability_ids.append(candidate)
            ids_by_call[result.metadata.tool_call_id] = list(dict.fromkeys(ids))
        return EvidenceAssembly(list(by_id.values()), ids_by_call,
                                list(dict.fromkeys(reliability_ids)))

    @staticmethod
    def _references(answer: AgentAnswer, aggregation: AggregatedEvidence) -> tuple[set[str], list[str]]:
        refs: set[str] = set()
        invalid: list[str] = []
        for item in answer.facts + answer.predictions:
            refs.update(item.evidence_ids)
            if not item.evidence_ids:
                invalid.append(f"{item.source_tool}:{item.name}:missing")
        for item in answer.agronomic_interpretation + answer.recommendations:
            refs.update(item.evidence_ids)
            if not item.evidence_ids:
                invalid.append(f"statement:{item.category}:missing")
        for case in answer.historical_cases:
            refs.add(case.evidence_id)
        # A retrieval-only response may cite the relevance-gated sources to
        # substantiate an explicit evidence-insufficiency statement.  This is
        # not a license to turn source metadata into an agronomic conclusion.
        if (not refs and aggregation.evidence_sufficiency.value == "PARTIAL"):
            refs.update(item.evidence_id for item in aggregation.knowledge_evidence)
        if answer.predictions:
            refs.update(aggregation.reliability_evidence_ids)
        return refs, invalid

    def finalize(self, answer: AgentAnswer, aggregation: AggregatedEvidence, *, restore=True):
        """Restore deterministic structured outputs, validate references, select evidence."""
        # Factual structures come from ToolResults, never from model copying.
        candidate = answer.model_copy(update={
            "facts": aggregation.facts,
            "predictions": aggregation.predictions,
            "historical_cases": aggregation.historical_cases,
            "case_prediction_height_t7_cm": aggregation.case_prediction_height_t7_cm,
            "case_model_agreement": aggregation.case_model_agreement,
            "confidence": aggregation.confidence,
            "evidence_sufficiency": aggregation.evidence_sufficiency,
            "warnings": list(dict.fromkeys(aggregation.warnings + answer.warnings)),
            "limitations": list(dict.fromkeys(aggregation.limitations + answer.limitations)),
            "unsupported_requests": list(dict.fromkeys(
                aggregation.unsupported_requests + answer.unsupported_requests)),
        }) if restore else answer
        registry = {item.evidence_id: item for item in aggregation.evidence_registry}
        allowed_statements = []
        semantic: list[str] = []
        for statement in candidate.agronomic_interpretation + candidate.recommendations:
            records = [registry.get(eid) for eid in statement.evidence_ids]
            valid = bool(records) and all(records)
            if aggregation.evidence_sufficiency.value == "INSUFFICIENT":
                valid = False
            if valid and statement.category in {"interpretation", "general_management_consideration"}:
                valid = any(row.attributes.get("source_tool") ==
                    "retrieve_water_fertilizer_knowledge" for row in records)
            if valid:
                allowed_statements.append(statement)
            else:
                semantic.append(statement.text[:120])
        interpretations = [row for row in allowed_statements if row.category == "interpretation"]
        recommendations = [row for row in allowed_statements
                           if row.category == "general_management_consideration"]
        candidate = candidate.model_copy(update={"agronomic_interpretation": interpretations,
                                                  "recommendations": recommendations})
        refs, invalid = self._references(candidate, aggregation)
        missing = sorted(refs - set(registry))
        selected = [item for item in aggregation.evidence_registry if item.evidence_id in refs]
        candidate = candidate.model_copy(update={"evidence": selected})
        validation = EvidenceValidation(collected=len(registry), referenced=len(refs & set(registry)),
            missing_references=missing, invalid_references=invalid,
            semantic_mismatches=semantic)
        return candidate, validation
