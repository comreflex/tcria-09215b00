from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tcria.runtime.events import GovernanceEvent, GovernanceEventType
from tcria.runtime.ledger import GovernanceLedger
from tcria.runtime.policies import PolicyEvaluationResult, evaluate_governance_policies
from tcria.runtime.state import GovernanceState, GovernanceStateMachine
from tcria.runtime.telemetry import GovernanceTelemetry


class GovernanceRuntime:
    def __init__(self) -> None:
        self.state = GovernanceStateMachine()
        self.ledger = GovernanceLedger()
        self.telemetry = GovernanceTelemetry()
        self.events: list[GovernanceEvent] = []

    def emit(self, event_type: GovernanceEventType, message: str, payload: dict[str, Any] | None = None) -> GovernanceEvent:
        event = GovernanceEvent.create(event_type=event_type, message=message, payload=payload)
        self.events.append(event)
        self.ledger.append(event)
        self.telemetry.register_event(event)
        return event

    def transition(self, target: GovernanceState) -> None:
        self.state.transition(target)

    def evaluate_policies(self, bundle: dict[str, Any]) -> PolicyEvaluationResult:
        return evaluate_governance_policies(bundle)

    def dump_artifacts(self, out_dir: Path, stem: str) -> dict[str, str]:
        out_dir.mkdir(parents=True, exist_ok=True)
        events_path = out_dir / f"{stem}_runtime_events.json"
        ledger_path = out_dir / f"{stem}_runtime_ledger.json"
        telemetry_path = out_dir / f"{stem}_runtime_telemetry.json"

        events_payload = [event.to_dict() for event in self.events]
        ledger_payload = self.ledger.to_dict()
        telemetry_payload = self.telemetry.snapshot().to_dict()
        telemetry_payload["state"] = self.state.current.value

        events_path.write_text(json.dumps(events_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        ledger_path.write_text(json.dumps(ledger_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        telemetry_path.write_text(json.dumps(telemetry_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "events_json": str(events_path),
            "ledger_json": str(ledger_path),
            "telemetry_json": str(telemetry_path),
        }
