from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


def _iter_records(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("accusation_set", "records", "audit_records", "documents", "items"):
        value = bundle.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _is_blocked_record(record: dict[str, Any]) -> bool:
    outcome = str(record.get("overall_outcome", "")).upper()
    if "BLOCKED" in outcome:
        return True
    gates = record.get("gates")
    if not isinstance(gates, dict):
        return False
    for gate in gates.values():
        if isinstance(gate, dict) and str(gate.get("status", "")).upper() == "BLOCKED":
            return True
    return False


@dataclass
class PolicyEvaluationResult:
    allow_promotion: bool
    blocked_records: int
    total_records: int
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_governance_policies(bundle: dict[str, Any]) -> PolicyEvaluationResult:
    records = _iter_records(bundle)
    blocked_records = sum(1 for record in records if _is_blocked_record(record))
    reasons: list[str] = []
    if blocked_records > 0:
        reasons.append(f"Promotion blocked: {blocked_records} record(s) are blocked by governance outcomes.")
    else:
        reasons.append("No blocked governance outcomes found in evaluated records.")
    return PolicyEvaluationResult(
        allow_promotion=blocked_records == 0,
        blocked_records=blocked_records,
        total_records=len(records),
        reasons=reasons,
    )
