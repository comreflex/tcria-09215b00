"""Composition pipeline: orchestrates TCRIA → Quinta Ordem → Precision Gate."""
from __future__ import annotations

import hashlib
import json
import logging
import sys
from collections.abc import Mapping
from typing import Any

from precision_gate.adapters.tcria_adapter import TCRIAAdapter
from precision_gate.adapters.quinta_ordem_adapter import QuintaOrdemAdapter
from precision_gate.custody.audit_trail import AuditTrail
from precision_gate.custody.models import CustodyRecord
from precision_gate.custody.state_machine import CustodyStateMachine

logger = logging.getLogger(__name__)


class PrecisionGatePipeline:
    """Orchestrates the full TCRIA → Quinta Ordem → Precision Gate pipeline.

    Usage::

        pipeline = PrecisionGatePipeline.default()
        record, trail = pipeline.run(
            tcria_bundle=bundle,
            case_id="case-001",
        )

    Chain-of-custody guarantees:
    - TCRIA bundle is never mutated.
    - Quinta Ordem evaluates an independent deep copy of the context.
    - Non-abandonment flags always override gate approvals.
    - Every step is logged in an append-only AuditTrail.
    """

    def __init__(
        self,
        *,
        tcria_adapter: TCRIAAdapter,
        quinta_ordem_adapter: QuintaOrdemAdapter,
        custody_state_machine: CustodyStateMachine,
    ) -> None:
        self._tcria_adapter = tcria_adapter
        self._qo_adapter = quinta_ordem_adapter
        self._custody_sm = custody_state_machine

    @classmethod
    def default(cls) -> "PrecisionGatePipeline":
        return cls(
            tcria_adapter=TCRIAAdapter(version="1.0"),
            quinta_ordem_adapter=QuintaOrdemAdapter(version="1.0"),
            custody_state_machine=CustodyStateMachine(),
        )

    def run(
        self,
        tcria_bundle: Mapping[str, Any],
        *,
        case_id: str,
        execution_id: str | None = None,
    ) -> tuple[CustodyRecord, AuditTrail]:
        """Run the full pipeline.

        Args:
            tcria_bundle: Output of ``TCRIAEngine.run_audit`` (the ``bundle`` key).
            case_id: Human-readable case identifier for the audit trail.
            execution_id: Override execution_id; otherwise derived from the bundle.

        Returns:
            A tuple of (CustodyRecord, AuditTrail).
        """
        trail = AuditTrail()
        bundle_sha = _sha256_dict(dict(tcria_bundle))

        trail.append("pipeline_started", {"case_id": case_id, "bundle_sha256": bundle_sha})

        # Step 1: Convert TCRIA bundle → Quinta Ordem payload
        payload = self._tcria_adapter.to_execution_context_payload(
            tcria_bundle, execution_id=execution_id
        )
        meta = payload.get("_precision_gate_meta", {})
        trail.append(
            "tcria_adapted",
            {
                "input_sha256": meta.get("input_sha256"),
                "output_sha256": meta.get("output_sha256"),
                "non_abandonment_checks": meta.get("non_abandonment_checks", []),
                "adapter_version": meta.get("adapter_version"),
            },
        )

        non_abandonment_flags: list[str] = list(
            meta.get("non_abandonment_checks") or []
        )

        # Step 2: Convert payload → ExecutionContext and evaluate with Quinta Ordem Gate
        try:
            quinta_ordem = _import_quinta_ordem()
        except ImportError:
            logger.warning(
                "quinta_ordem not importable — using stub gate decision (blocked)."
            )
            quinta_ordem = None

        if quinta_ordem is not None:
            qo_adapter_cls = quinta_ordem["TCRIAExecutionContextAdapter"]
            gate_cls = quinta_ordem["QuintaOrdemGate"]

            context_adapter = qo_adapter_cls()
            context = context_adapter.adapt(payload, execution_id=payload.get("execution_id"))

            gate = gate_cls.default()
            decision = gate.evaluate(context)

            trail.append(
                "quinta_ordem_evaluated",
                {
                    "execution_id": decision.execution_id,
                    "status": str(decision.status),
                    "confidence": decision.confidence,
                    "human_review_required": decision.human_review_required,
                    "evaluated_verifiers": decision.evaluated_verifiers,
                    "execution_context_sha256": decision.execution_context_sha256,
                },
            )

            custody_state = self._qo_adapter.to_custody_state(
                decision=decision,
                execution_context=context,
                tcria_findings=non_abandonment_flags,
            )
        else:
            custody_state = _stub_blocked_state(payload.get("execution_id", "unknown"))
            trail.append(
                "quinta_ordem_stubbed",
                {"reason": "quinta_ordem package not available", "status": "blocked"},
            )

        # Step 3: Build CustodyRecord
        record = self._custody_sm.build_record(
            case_id=case_id,
            execution_id=payload.get("execution_id", "unknown"),
            tcria_bundle_sha256=bundle_sha,
            quinta_ordem_custody_state=custody_state,
            tcria_non_abandonment_flags=non_abandonment_flags,
        )

        trail.append(
            "custody_record_built",
            {
                "case_id": record.case_id,
                "execution_id": record.execution_id,
                "status": record.status.value,
                "human_review_required": record.human_review_required,
                "confidence": record.confidence,
            },
        )

        return record, trail


def _import_quinta_ordem() -> dict[str, Any]:
    import importlib
    qo = importlib.import_module("quinta_ordem")
    qo_adapters = importlib.import_module("quinta_ordem.adapters")
    return {
        "QuintaOrdemGate": qo.QuintaOrdemGate,
        "TCRIAExecutionContextAdapter": qo_adapters.TCRIAExecutionContextAdapter,
    }


def _stub_blocked_state(execution_id: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "confidence": 0.0,
        "human_review_required": True,
        "confidence_breakdown": {},
        "remaining_uncertainties": ["quinta_ordem unavailable"],
        "custody_trail": {
            "execution_context_sha256": None,
            "decision_sha256": None,
        },
    }


def _sha256_dict(d: dict[str, Any]) -> str:
    serialized = json.dumps(d, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
