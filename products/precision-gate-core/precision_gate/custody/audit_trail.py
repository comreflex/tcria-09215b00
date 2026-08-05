"""Audit trail: append-only, human-readable and machine-auditable custody log."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AuditTrail:
    """Append-only in-memory audit trail with optional JSON persistence.

    Each entry is a timestamped dict. The trail is never mutated after append.
    """

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def append(self, event_type: str, data: dict[str, Any]) -> None:
        """Append an immutable event to the trail."""
        entry = {
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        self._entries.append(entry)
        logger.debug("AuditTrail: %s", event_type)

    @property
    def entries(self) -> list[dict[str, Any]]:
        return list(self._entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "entry_count": len(self._entries),
            "entries": self.entries,
        }

    def save(self, path: str | Path) -> None:
        """Persist the audit trail as a JSON file."""
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info("AuditTrail: saved %d entries to %s", len(self._entries), dest)

    @classmethod
    def load(cls, path: str | Path) -> "AuditTrail":
        """Load a persisted audit trail (read-only verification)."""
        trail = cls()
        with Path(path).open(encoding="utf-8") as f:
            data = json.load(f)
        for entry in data.get("entries", []):
            trail._entries.append(entry)
        return trail
