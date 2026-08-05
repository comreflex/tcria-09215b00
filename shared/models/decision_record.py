"""Shared decision record model."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class DecisionRecord:
    """Immutable decision record produced at each pipeline stage."""

    decision_id: str
    product: str
    status: str
    confidence: float
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    input_sha256: str | None = None
    output_sha256: str | None = None
    human_review_required: bool = False
    notes: list[str] = field(default_factory=list)
