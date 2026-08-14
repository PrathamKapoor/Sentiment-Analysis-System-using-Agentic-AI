from dataclasses import dataclass, field

from ..models import Intent


@dataclass
class ProvenanceTrace:
    intent: Intent
    direct_collection_possible: bool
    fallback_reason: str
    candidates_considered: list[str] = field(default_factory=list)
    attempts: list[dict] = field(default_factory=list)

    def attempt(self, source_id: str, outcome: str, records: int = 0) -> None:
        self.attempts.append({"sourceId": source_id, "outcome": outcome, "records": records})

    def to_dict(self, status: str, records: int) -> dict:
        return {
            "requestedSource": self.intent.requested_source,
            "requestedEntity": self.intent.entity,
            "directCollection": self.direct_collection_possible,
            "fallbackUsed": True,
            "fallbackReason": self.fallback_reason,
            "candidateSourcesConsidered": self.candidates_considered,
            "sourcesAttempted": self.attempts,
            "actualSources": [{"sourceId": item["sourceId"], "records": item["records"]} for item in self.attempts if item["records"]],
            "recordsCollected": records,
            "status": status,
        }
