"""Custody state machine: transitions and non-abandonment enforcement."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .models import CustodyRecord, CustodyStatus

logger = logging.getLogger(__name__)


class CustodyStateMachine:
    """Manages custody state transitions with non-abandonment enforcement.

    Rules:
    - A BLOCKED status can never be overridden by a later gate approval.
    - TCRIA non-abandonment flags always require human review.
    - Human review is required for any non-APPROVED quinta-ordem status.
    """

    def build_record(
        self,
        *,
        case_id: str,
        execution_id: str,
        tcria_bundle_sha256: str | None,
        quinta_ordem_custody_state: dict[str, Any],
        tcria_non_abandonment_flags: list[str],
    ) -> CustodyRecord:
        """Build an immutable CustodyRecord from pipeline outputs.

        This is the single place where TCRIA and Quinta Ordem results are merged.
        Non-abandonment checks are enforced here.
        """
        qo_status_raw = quinta_ordem_custody_state.get("status", "blocked")
        qo_status_str = (
            qo_status_raw.value
            if hasattr(qo_status_raw, "value")
            else str(qo_status_raw)
        )

        # Non-abandonment: if TCRIA blocked, custody must reflect that
        if tcria_non_abandonment_flags:
            logger.warning(
                "CustodyStateMachine: non-abandonment flags present — forcing human_review "
                "regardless of quinta-ordem decision. flags=%s",
                tcria_non_abandonment_flags,
            )

        human_review = quinta_ordem_custody_state.get("human_review_required", True)
        if tcria_non_abandonment_flags:
            human_review = True

        # Map quinta_ordem status to CustodyStatus
        status = _map_status(qo_status_str, tcria_non_abandonment_flags)

        timestamps = {"built_at": datetime.now(timezone.utc).isoformat()}

        qo_sha = quinta_ordem_custody_state.get("custody_trail", {}).get("decision_sha256")

        record = CustodyRecord(
            case_id=case_id,
            execution_id=execution_id,
            status=status,
            tcria_bundle_sha256=tcria_bundle_sha256,
            quinta_ordem_decision_sha256=qo_sha,
            confidence=quinta_ordem_custody_state.get("confidence", 0.0),
            human_review_required=human_review,
            non_abandonment_flags=list(tcria_non_abandonment_flags),
            metadata={
                "quinta_ordem_breakdown": quinta_ordem_custody_state.get(
                    "confidence_breakdown", {}
                ),
                "remaining_uncertainties": quinta_ordem_custody_state.get(
                    "remaining_uncertainties", []
                ),
            },
            timestamps=timestamps,
        )

        logger.info(
            "CustodyStateMachine: record built case_id=%s execution_id=%s status=%s "
            "human_review=%s",
            case_id,
            execution_id,
            status.value,
            human_review,
        )

        return record


def _map_status(
    qo_status: str, non_abandonment_flags: list[str]
) -> CustodyStatus:
    mapping = {
        "approved": CustodyStatus.APPROVED,
        "conditional": CustodyStatus.CONDITIONAL,
        "returned_for_correction": CustodyStatus.RETURNED,
        "returned": CustodyStatus.RETURNED,
        "blocked": CustodyStatus.BLOCKED,
    }
    base = mapping.get(qo_status.lower(), CustodyStatus.BLOCKED)

    # Non-abandonment: a TCRIA block overrides an otherwise approved outcome
    if non_abandonment_flags and base == CustodyStatus.APPROVED:
        return CustodyStatus.HUMAN_REVIEW

    return base
