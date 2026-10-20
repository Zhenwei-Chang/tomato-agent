from .schemas import EvidenceRecord, ProvenanceEdge, ProvenanceGraph


class ProvenanceBuilder:
    def build(self, claims, evidence: list[EvidenceRecord]) -> ProvenanceGraph:
        by_id = {record.evidence_id: record for record in evidence}
        edges: list[ProvenanceEdge] = []
        missing: list[str] = []
        referenced: set[str] = set()
        semantic_mismatches = 0
        allowed = {
            "observation": {"observation", "sensor"},
            "prediction": {"prediction", "visual_observation"},
            "historical_interpretation": {"historical_case"},
            "knowledge": {"knowledge"},
            "recommendation": {"knowledge", "sensor"},
        }
        for claim in claims:
            for evidence_id in claim.support_evidence_ids:
                referenced.add(evidence_id)
                record = by_id.get(evidence_id)
                if not record:
                    missing.append(f"{claim.claim_id}->{evidence_id}")
                    continue
                expected=allowed.get(claim.claim_type.value)
                if expected and record.evidence_type.value not in expected:
                    semantic_mismatches += 1
                    missing.append(f"{claim.claim_id}->{evidence_id}:semantic_mismatch")
                    continue
                edges.append(ProvenanceEdge(from_id=claim.claim_id, to_id=evidence_id, relation="SUPPORTED_BY"))
                tool_call_id = str(record.provenance.get("tool_call_id") or "")
                if tool_call_id:
                    edges.append(ProvenanceEdge(from_id=evidence_id, to_id=tool_call_id, relation="PRODUCED_BY"))
                else:
                    missing.append(f"{evidence_id}->tool_call")
                sources = record.provenance.get("data_source", [])
                if not sources:
                    missing.append(f"{tool_call_id or evidence_id}->source")
                for source in sources:
                    edges.append(ProvenanceEdge(from_id=tool_call_id or evidence_id, to_id=str(source), relation="SOURCED_FROM"))
        return ProvenanceGraph(edges=edges, complete=not missing, missing_links=missing,
            evidence_collected_count=len(by_id),
            evidence_referenced_count=len(referenced & set(by_id)),
            missing_evidence_reference_count=len(referenced-set(by_id)),
            invalid_reference_count=len([row for row in missing if '->' in row]),
            semantic_mismatch_count=semantic_mismatches)
