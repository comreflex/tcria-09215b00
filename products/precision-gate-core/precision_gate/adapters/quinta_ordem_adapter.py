"""Quinta Ordem Adapter: converts a GateDecision into a Precision Gate CustodyState."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class QuintaOrdemAdapterError(ValueError):
    """Raised when a GateDecision cannot be converted to custody state."""


class QuintaOrdemAdapter:
    """Convert a Quinta Ordem ``GateDecision`` into a Precision Gate custody state dict.

    The state dict is an immutable snapshot that includes:
    - Quinta Ordem decision and confidence breakdown
    - Custody trail from TCRIA through Quinta Ordem
    - Non-abandonment reconciliation
    - Human review requirements
    """

    schema_version: ClassVar[str] = "1.0"

    def __init__(self, version: str = "1.0") -> None:
        if version != "1.0":
            raise QuintaOrdemAdapterError(f"Unsupported version: {version!r}")
        self.version = version

    def to_custody_state(
        self,
        *,
        decision: Any,
        execution_context: Any,
        tcria_findings: list[str] | None = None,
    ) -> dict[str, Any]:
        """Convert a GateDecision to a Precision Gate custody state.

        Args:
            decision: A ``quinta_ordem.GateDecision`` instance.
            execution_context: The ``quinta_ordem.ExecutionContext`` that was evaluated.
            tcria_findings: Optional list of TCRIA non-abandonment warnings.

        Returns:
            An immutable custody state dict.
        """
        decision_dict = _decision_to_dict(decision)
        context_sha = getattr(decision, "execution_context_sha256", None)
        context_sha_str = context_sha if isinstance(context_sha, str) else None

        tcria_flags = tcria_findings or []
        human_review = getattr(decision, "human_review_required", True) or bool(tcria_flags)

        state: dict[str, Any] = {
            "schema_version": self.version,
            "custody_state_at": datetime.now(timezone.utc).isoformat(),
            "execution_id": getattr(decision, "execution_id", "unknown"),
            "status": getattr(decision, "status", "unknown"),
            "confidence": getattr(decision, "confidence", 0.0),
            "confidence_breakdown": _breakdown_to_dict(
                getattr(decision, "breakdown", None)
            ),
            "human_review_required": human_review,
            "non_abandonment_flags": tcria_flags,
            "quinta_ordem_decision": decision_dict,
            "custody_trail": {
                "execution_context_sha256": context_sha_str,
                "decision_sha256": _sha256_dict(decision_dict),
            },
            "remaining_uncertainties": getattr(decision, "remaining_uncertainties", []),
        }

        logger.info(
            "QuintaOrdemAdapter v%s: custody state created for execution_id=%s status=%s",
            self.version,
            state["execution_id"],
            state["status"],
        )

        return state


def _decision_to_dict(decision: Any) -> dict[str, Any]:
    if hasattr(decision, "__dataclass_fields__"):
        import dataclasses
        return dataclasses.asdict(decision)
    if isinstance(decision, dict):
        return dict(decision)
    return {"raw": str(decision)}


def _breakdown_to_dict(breakdown: Any) -> dict[str, float]:
    if breakdown is None:
        return {}
    if hasattr(breakdown, "as_dict"):
        return breakdown.as_dict()
    if isinstance(breakdown, dict):
        return breakdown
    return {}


def _sha256_dict(d: dict[str, Any]) -> str:
    serialized = json.dumps(d, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
