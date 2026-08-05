"""Shared domain models used across all three products."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CustodyState:
    """Minimal shared custody state passed between product adapters."""

    execution_id: str
    status: str
    confidence: float
    human_review_required: bool
    sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
