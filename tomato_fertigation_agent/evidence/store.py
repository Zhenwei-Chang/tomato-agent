from __future__ import annotations

from .schemas import EvidenceRecord, EvidenceType


class EvidenceStore:
    """Compact in-memory evidence index; large tool payloads stay outside the store."""

    def __init__(self):
        self._records: dict[str, EvidenceRecord] = {}

    def add(self, record: EvidenceRecord) -> None:
        self._records[record.evidence_id] = record

    def extend(self, records: list[EvidenceRecord]) -> None:
        for record in records:
            self.add(record)

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        return self._records.get(evidence_id)

    def by_type(self, evidence_type: EvidenceType) -> list[EvidenceRecord]:
        return [record for record in self._records.values() if record.evidence_type == evidence_type]

    def all(self) -> list[EvidenceRecord]:
        return list(self._records.values())

    def ids(self) -> set[str]:
        return set(self._records)
