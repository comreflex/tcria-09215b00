from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class GovernanceEventType(str, Enum):
    INGESTION_STARTED = "INGESTION_STARTED"
    INGESTION_COMPLETED = "INGESTION_COMPLETED"
    OFFICIAL_AUDIT_COMPLETED = "OFFICIAL_AUDIT_COMPLETED"
    OFFICIAL_AUDIT_LOADED = "OFFICIAL_AUDIT_LOADED"
    COMPLEMENTARY_REVIEW_COMPLETED = "COMPLEMENTARY_REVIEW_COMPLETED"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    PROMOTION_BLOCKED = "PROMOTION_BLOCKED"
    ARTIFACT_GENERATED = "ARTIFACT_GENERATED"
    TRACEABILITY_FAILED = "TRACEABILITY_FAILED"


@dataclass
class GovernanceEvent:
    event_type: GovernanceEventType
    message: str
    payload: dict[str, Any]
    created_at: str

    @classmethod
    def create(cls, event_type: GovernanceEventType, message: str, payload: dict[str, Any] | None = None) -> "GovernanceEvent":
        return cls(
            event_type=event_type,
            message=message,
            payload=payload or {},
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["event_type"] = self.event_type.value
        return data
