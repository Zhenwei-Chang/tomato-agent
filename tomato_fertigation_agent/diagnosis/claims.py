from __future__ import annotations

import re
from uuid import uuid4

from ..evidence.schemas import ConflictRecord, ConflictStatus, EvidenceType
from ..evidence.store import EvidenceStore
from ..schemas.common import Confidence
from .schemas import Claim, ClaimType, ManagementConsideration, ManagementLevel


class ClaimBuilder:
    def build(self, store: EvidenceStore, conflicts: list[ConflictRecord], reliability: Confidence):
        claims: list[Claim] = []
        considerations: list[ManagementConsideration] = []
        for record in store.all():
            if record.evidence_type == EvidenceType.OBSERVATION:
                phenotype = record.value.get("phenotype", {})
                height = phenotype.get("plant_height_cm") or phenotype.get("height_cm")
                if height is not None:
                    claims.append(self._claim(ClaimType.OBSERVATION,
                        f"当前观测株高为 {float(height):.2f} cm。", [record.evidence_id], record.reliability))
            elif record.evidence_type == EvidenceType.VISUAL_OBSERVATION:
                height = record.value.get("current_view_mean_height_cm")
                if height is not None:
                    claims.append(self._claim(ClaimType.PREDICTION,
                        f"RGB 模型估计当前 View 平均株高为 {float(height):.2f} cm；这不是单株实测。",
                        [record.evidence_id], record.reliability))
            elif record.evidence_type == EvidenceType.PREDICTION:
                height = record.value.get("height_t7_cm")
                if height is not None:
                    noun = "View 平均株高" if record.scope.value == "view" else "株高"
                    claims.append(self._claim(ClaimType.PREDICTION,
                        f"模型估计 7 天后{noun}为 {float(height):.2f} cm。", [record.evidence_id], record.reliability))
            elif record.evidence_type == EvidenceType.HISTORICAL_CASE:
                height = record.value.get("case_weighted_height_t7_cm")
                if height is not None:
                    claims.append(self._claim(ClaimType.HISTORICAL_INTERPRETATION,
                        f"历史相似案例的加权 t+7 株高为 {float(height):.2f} cm；这是历史关联，不是因果证明。",
                        [record.evidence_id], record.reliability))
            elif record.evidence_type == EvidenceType.KNOWLEDGE:
                text = str(record.value.get("summary") or "").strip()
                if text:
                    claims.append(self._claim(ClaimType.KNOWLEDGE, text, [record.evidence_id], record.reliability))
        for conflict in conflicts:
            if conflict.status == ConflictStatus.DISAGREE:
                claims.append(self._claim(ClaimType.LIMITATION,
                    f"模型预测与历史案例相差 {conflict.absolute_difference:.2f} cm，属于 DISAGREE，不能合并成单一结论。",
                    conflict.evidence_ids, Confidence.LOW))
            elif conflict.status == ConflictStatus.PARTIAL:
                claims.append(self._claim(ClaimType.LIMITATION,
                    f"模型预测与历史案例相差 {conflict.absolute_difference:.2f} cm，仅部分一致。",
                    conflict.evidence_ids, Confidence.MEDIUM))
        sensor = store.by_type(EvidenceType.SENSOR)
        knowledge = store.by_type(EvidenceType.KNOWLEDGE)
        if sensor and knowledge:
            support = [sensor[0].evidence_id, knowledge[0].evidence_id]
            text = "建议继续监测温湿度、光照与根区代理变量，并结合知识证据复核风险趋势；当前不支持直接下发控制量。"
            considerations.append(ManagementConsideration(level=ManagementLevel.MONITOR, text=text,
                support_evidence_ids=support))
            claims.append(self._claim(ClaimType.RECOMMENDATION, text, support, reliability))
        return claims, considerations

    @staticmethod
    def _claim(kind, text, evidence_ids, confidence):
        return Claim(claim_id=f"CLAIM-{uuid4().hex[:10]}", claim_type=kind, text=text,
            support_evidence_ids=evidence_ids, confidence=confidence)


class ClaimSafetyValidator:
    NUMBER = re.compile(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?")

    def validate(self, claims: list[Claim], store: EvidenceStore, conflicts: list[ConflictRecord]):
        violations: list[str] = []
        allowed = {
            ClaimType.OBSERVATION: {"observation", "sensor"},
            ClaimType.PREDICTION: {"prediction", "visual_observation"},
            ClaimType.HISTORICAL_INTERPRETATION: {"historical_case"},
            ClaimType.KNOWLEDGE: {"knowledge"},
            ClaimType.RECOMMENDATION: {"knowledge", "sensor"},
        }
        for claim in claims:
            if any(not store.get(eid) for eid in claim.support_evidence_ids):
                violations.append("UNGROUNDED_CLAIM")
            if claim.claim_type in {ClaimType.PREDICTION, ClaimType.HISTORICAL_INTERPRETATION,
                                   ClaimType.KNOWLEDGE, ClaimType.RECOMMENDATION} and not claim.support_evidence_ids:
                violations.append("UNSUPPORTED_CLAIM")
            if claim.support_evidence_ids and not self._numbers_supported(claim, store):
                violations.append("UNSUPPORTED_NUMERICAL_CLAIM")
            expected=allowed.get(claim.claim_type)
            if expected and any(store.get(eid) and store.get(eid).evidence_type.value not in expected
                                for eid in claim.support_evidence_ids):
                violations.append("IRRELEVANT_EVIDENCE")
        if any(c.status == ConflictStatus.DISAGREE for c in conflicts):
            forbidden = ("一致表明", "共同证明", "一致证明")
            if any(any(phrase in claim.text for phrase in forbidden) for claim in claims):
                violations.append("CONFLICT_HIDDEN")
        low_claims = [claim for claim in claims if claim.confidence == Confidence.LOW]
        if any(any(word in claim.text for word in ("确定", "明确证明", "一定会")) for claim in low_claims):
            violations.append("RELIABILITY_OVERSTATED")
        return list(dict.fromkeys(violations))

    def _numbers_supported(self, claim, store):
        claimed = [float(value) for value in self.NUMBER.findall(claim.text)]
        if not claimed:
            return True
        supported = []
        for evidence_id in claim.support_evidence_ids:
            record = store.get(evidence_id)
            if record:
                supported.extend(float(value) for value in self.NUMBER.findall(str(record.value)))
        derived = supported + [abs(left-right) for left in supported for right in supported]
        return all(any(abs(number-value) <= max(0.02, abs(value)*0.001) for value in derived)
                   for number in claimed)
