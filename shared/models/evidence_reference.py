"""Shared evidence reference model."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidenceReference:
    """Cross-product evidence reference."""

    artifact_id: str
    sha256: str | None = None
    source: str | None = None
    product_origin: str | None = None
