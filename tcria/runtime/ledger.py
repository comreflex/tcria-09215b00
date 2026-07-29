from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from tcria.runtime.events import GovernanceEvent


def _stable_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass
class LedgerEntry:
    created_at: str
    previous_hash: str
    event_hash: str
    entry_hash: str

    def to_dict(self) -> dict[str, str]:
        return {
            "created_at": self.created_at,
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
            "entry_hash": self.entry_hash,
        }


class GovernanceLedger:
    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []
        self._previous_hash = "0" * 64

    def append(self, event: GovernanceEvent) -> LedgerEntry:
        event_payload = _stable_json(event.to_dict())
        event_hash = hashlib.sha256(event_payload.encode("utf-8")).hexdigest()
        entry_source = f"{self._previous_hash}:{event_hash}"
        entry_hash = hashlib.sha256(entry_source.encode("utf-8")).hexdigest()
        entry = LedgerEntry(
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            previous_hash=self._previous_hash,
            event_hash=event_hash,
            entry_hash=entry_hash,
        )
        self._entries.append(entry)
        self._previous_hash = entry_hash
        return entry

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_count": len(self._entries),
            "entries": [entry.to_dict() for entry in self._entries],
            "head_hash": self._previous_hash,
        }
