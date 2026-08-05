from __future__ import annotations

from collections.abc import Mapping

from quinta_ordem.models import DecisionStatus, ExecutionContext, Finding, Severity
from quinta_ordem.verifiers.base import Verifier

_RETURNED = {"returned", "return", DecisionStatus.RETURNED.value}
_KNOWN_STATUSES = {
    DecisionStatus.APPROVED.value,
    DecisionStatus.CONDITIONAL.value,
    DecisionStatus.BLOCKED.value,
    *_RETURNED,
}


class ConsistencyVerifier(Verifier):
    name = "logical_consistency"

    def verify(self, context: ExecutionContext) -> list[Finding]:
        findings: list[Finding] = []
        statuses_by_gate: dict[str, list[str]] = {}

        for index, item in enumerate(context.gate_results):
            if not isinstance(item, Mapping):
                continue
            raw_gate = item.get("gate")
            raw_status = item.get("status")
            if not isinstance(raw_gate, str) or not isinstance(raw_status, str):
                continue
            gate_name = raw_gate.strip()
            status = raw_status.strip().lower()
            point_id = f"previous-gate:{gate_name or index}"
            statuses_by_gate.setdefault(gate_name, []).append(status)

            if status == DecisionStatus.BLOCKED.value:
                continue
            elif status in _RETURNED:
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="PREVIOUS_GATE_RETURNED",
                        severity=Severity.HIGH,
                        message=f"O gate anterior {gate_name!r} devolveu o fluxo para correção.",
                        point_id=point_id,
                        return_to=gate_name or "orchestration",
                        required_action="Concluir a correção antes de promover o resultado.",
                    )
                )
            elif status == DecisionStatus.CONDITIONAL.value:
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="PREVIOUS_GATE_CONDITIONAL",
                        severity=Severity.WARNING,
                        message=f"O gate anterior {gate_name!r} permanece condicional.",
                        point_id=point_id,
                        return_to=gate_name or "human_review",
                        required_action="Registrar a revisão ou condição pendente.",
                    )
                )
            elif status not in _KNOWN_STATUSES:
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="UNKNOWN_PREVIOUS_GATE_STATUS",
                        severity=Severity.HIGH,
                        message=f"O gate anterior {gate_name!r} possui status desconhecido.",
                        point_id=point_id,
                        return_to="orchestration",
                        required_action="Mapear explicitamente o status antes da promoção.",
                        details={"status": raw_status},
                    )
                )

        for gate_name, statuses in statuses_by_gate.items():
            if len(set(statuses)) > 1:
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="CONFLICTING_GATE_RESULTS",
                        severity=Severity.CRITICAL,
                        message=f"O gate anterior {gate_name!r} possui resultados conflitantes.",
                        point_id=f"previous-gate:{gate_name}",
                        return_to="orchestration",
                        required_action="Preservar o resultado mais restritivo e reconciliar o histórico.",
                        details={"statuses": statuses},
                    )
                )

        promoted = [
            item
            for item in context.decisions
            if isinstance(item, Mapping) and item.get("promoted") is True
        ]
        for index, decision in enumerate(promoted):
            classification = decision.get("classification")
            support = decision.get("support_level")
            if classification != "fact" or support not in {"direct", "corroborated"}:
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="UNSUPPORTED_PROMOTION",
                        severity=Severity.CRITICAL,
                        message="Resultado foi promovido sem classificação e suporte suficientes.",
                        point_id=str(decision.get("decision_id") or f"promoted-{index}"),
                        return_to="analysis",
                        required_action="Cancelar a promoção ou demonstrar suporte probatório.",
                    )
                )

        return findings
