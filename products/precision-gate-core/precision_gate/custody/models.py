"""Custody state models."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CustodyStatus(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    CONDITIONAL = "conditional"
    RETURNED = "returned_for_correction"
    BLOCKED = "blocked"
    HUMAN_REVIEW = "human_review_required"


@dataclass(frozen=True)
class CustodyRecord:
    """Immutable custody record capturing a complete pipeline evaluation."""

    case_id: str
    execution_id: str
    status: CustodyStatus
    tcria_bundle_sha256: str | None
    quinta_ordem_decision_sha256: str | None
    confidence: float
    human_review_required: bool
    non_abandonment_flags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamps: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "execution_id": self.execution_id,
            "status": self.status.value,
            "tcria_bundle_sha256": self.tcria_bundle_sha256,
            "quinta_ordem_decision_sha256": self.quinta_ordem_decision_sha256,
            "confidence": self.confidence,
            "human_review_required": self.human_review_required,
            "non_abandonment_flags": list(self.non_abandonment_flags),
            "metadata": dict(self.metadata),
            "timestamps": dict(self.timestamps),
        }
