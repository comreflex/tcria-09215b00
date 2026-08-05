from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionStatus(str, Enum):
    APPROVED = "approved"
    CONDITIONAL = "conditional"
    RETURNED = "returned_for_correction"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class EvidenceRef:
    artifact_id: str
    sha256: str | None = None
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionContext:
    execution_id: str
    evidence: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    gate_results: list[dict[str, Any]]
    logs: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Finding:
    verifier: str
    code: str
    severity: Severity
    message: str
    point_id: str
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    return_to: str | None = None
    required_action: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfidenceBreakdown:
    integrity: float
    traceability: float
    evidence_support: float
    logical_consistency: float
    resolution: float

    def as_dict(self) -> dict[str, float]:
        return {
            "integrity": self.integrity,
            "traceability": self.traceability,
            "evidence_support": self.evidence_support,
            "logical_consistency": self.logical_consistency,
            "resolution": self.resolution,
        }


@dataclass(frozen=True)
class GateDecision:
    execution_id: str
    status: DecisionStatus
    confidence: float
    breakdown: ConfidenceBreakdown
    findings: list[Finding]
    remaining_uncertainties: list[str]
    human_review_required: bool
    evaluated_verifiers: list[str] = field(default_factory=list)
    execution_context_sha256: str | None = None
    schema_version: str = "1.0"
