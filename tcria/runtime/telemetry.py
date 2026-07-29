from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from tcria.runtime.events import GovernanceEvent


_ARTIFACT_KEYS = ("artifact_path", "audit_json", "review_json", "review_md")


@dataclass
class RuntimeTelemetrySnapshot:
    event_count: int
    artifact_count: int
    blocked_event_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GovernanceTelemetry:
    def __init__(self) -> None:
        self._event_count = 0
        self._artifact_count = 0
        self._blocked_event_count = 0

    def register_event(self, event: GovernanceEvent) -> None:
        self._event_count += 1
        payload = event.payload or {}
        for key in _ARTIFACT_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                self._artifact_count += 1
        if self._is_blocked_signal(event.event_type.value, payload):
            self._blocked_event_count += 1

    @staticmethod
    def _is_blocked_signal(event_type: str, payload: dict[str, Any]) -> bool:
        if "BLOCKED" in event_type:
            return True
        if payload.get("allow_promotion") is False:
            return True
        blocked_records = payload.get("blocked_records")
        if isinstance(blocked_records, int) and blocked_records > 0:
            return True
        return False

    def snapshot(self) -> RuntimeTelemetrySnapshot:
        return RuntimeTelemetrySnapshot(
            event_count=self._event_count,
            artifact_count=self._artifact_count,
            blocked_event_count=self._blocked_event_count,
        )
