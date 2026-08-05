from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from hashlib import sha256
from typing import Any

from quinta_ordem.confidence import DIMENSIONS, calculate_breakdown, calculate_total
from quinta_ordem.models import (
    DecisionStatus,
    ExecutionContext,
    Finding,
    GateDecision,
    Severity,
)
from quinta_ordem.serialization import SerializationError, dumps_json, to_jsonable
from quinta_ordem.validation import has_structural_failure, validate_execution_context
from quinta_ordem.verifiers.base import Verifier
from quinta_ordem.verifiers.consistency import ConsistencyVerifier
from quinta_ordem.verifiers.evidence import EvidenceSupportVerifier
from quinta_ordem.verifiers.integrity import IntegrityVerifier
from quinta_ordem.verifiers.registry import VerifierRegistry
from quinta_ordem.verifiers.resolution import ResolutionVerifier
from quinta_ordem.verifiers.traceability import TraceabilityVerifier

CORE_VERIFIER_TYPES: dict[str, type[Verifier]] = {
    "integrity": IntegrityVerifier,
    "traceability": TraceabilityVerifier,
    "evidence_support": EvidenceSupportVerifier,
    "logical_consistency": ConsistencyVerifier,
    "resolution": ResolutionVerifier,
}


class QuintaOrdemGate:
    def __init__(
        self,
        verifiers: Iterable[Verifier] | VerifierRegistry,
        approval_threshold: float = 0.95,
        return_threshold: float = 0.80,
        required_verifiers: Iterable[str] = DIMENSIONS,
    ) -> None:
        if not 0.0 <= return_threshold <= approval_threshold <= 1.0:
            raise ValueError(
                "Thresholds must satisfy 0 <= return_threshold <= approval_threshold <= 1."
            )
        self.registry = (
            verifiers if isinstance(verifiers, VerifierRegistry) else VerifierRegistry(verifiers)
        )
        self.approval_threshold = approval_threshold
        self.return_threshold = return_threshold
        self.required_verifiers = tuple(required_verifiers)

    @property
    def verifiers(self) -> list[Verifier]:
        """Backward-compatible, detached view of the registered verifiers."""

        return list(self.registry.values())

    @classmethod
    def default(cls) -> QuintaOrdemGate:
        return cls(
            verifiers=[
                IntegrityVerifier(),
                TraceabilityVerifier(),
                EvidenceSupportVerifier(),
                ConsistencyVerifier(),
                ResolutionVerifier(),
            ]
        )

    def register_verifier(self, verifier: Verifier, *, replace: bool = False) -> None:
        if verifier.name in CORE_VERIFIER_TYPES and replace:
            raise ValueError(f"Core verifier cannot be replaced: {verifier.name}.")
        self.registry.register(verifier, replace=replace)

    def evaluate(self, context: ExecutionContext) -> GateDecision:
        findings = validate_execution_context(context)
        findings.extend(_previous_block_findings(context))
        execution_id = _execution_id(context)
        evaluated_verifiers: list[str] = []
        working_context: ExecutionContext | None = None

        if isinstance(context, ExecutionContext) and not has_structural_failure(findings):
            try:
                working_context = deepcopy(context)
            except Exception as exc:  # noqa: BLE001  # pragma: no cover - defensive boundary
                findings.append(
                    _system_finding(
                        code="CONTEXT_SNAPSHOT_FAILED",
                        message="Não foi possível criar snapshot independente do contexto.",
                        point_id="execution-context",
                        details={"exception_type": type(exc).__name__},
                    )
                )

        context_digest = _context_digest(working_context or context)

        registered_names = set(self.registry.names())
        invalid_core_verifiers: set[str] = set()
        for core_name, expected_type in CORE_VERIFIER_TYPES.items():
            if core_name not in registered_names:
                findings.append(
                    _system_finding(
                        code="REQUIRED_VERIFIER_MISSING",
                        message=f"Verificador obrigatório ausente: {core_name}.",
                        point_id=f"verifier:{core_name}",
                    )
                )
            elif type(self.registry.get(core_name)) is not expected_type:
                invalid_core_verifiers.add(core_name)
                findings.append(
                    _system_finding(
                        code="CORE_VERIFIER_REPLACED",
                        message=f"Implementação do verificador central foi substituída: {core_name}.",
                        point_id=f"verifier:{core_name}",
                    )
                )

        for required_name in self.required_verifiers:
            if required_name not in registered_names and required_name not in CORE_VERIFIER_TYPES:
                findings.append(
                    _system_finding(
                        code="REQUIRED_VERIFIER_MISSING",
                        message=f"Verificador obrigatório ausente: {required_name}.",
                        point_id=f"verifier:{required_name}",
                    )
                )

        if working_context is not None:
            for verifier in self.registry:
                if verifier.name in invalid_core_verifiers:
                    continue
                try:
                    verifier_findings = verifier.verify(deepcopy(working_context))
                    _validate_verifier_output(verifier.name, verifier_findings)
                except Exception as exc:  # noqa: BLE001 - plugin failures must fail closed
                    findings.append(
                        _system_finding(
                            code="VERIFIER_EXECUTION_FAILED",
                            message=f"O verificador {verifier.name!r} falhou de modo controlado.",
                            point_id=f"verifier:{verifier.name}",
                            details={"exception_type": type(exc).__name__},
                        )
                    )
                    continue

                evaluated_verifiers.append(verifier.name)
                findings.extend(verifier_findings)

        breakdown = calculate_breakdown(
            findings,
            context=working_context,
            evaluated_verifiers=set(evaluated_verifiers),
        )
        confidence = calculate_total(breakdown)

        critical = [finding for finding in findings if finding.severity == Severity.CRITICAL]
        high = [finding for finding in findings if finding.severity == Severity.HIGH]
        remaining_uncertainties = [
            finding.message
            for finding in findings
            if finding.severity in {Severity.WARNING, Severity.INFO}
        ]

        if critical:
            status = DecisionStatus.BLOCKED
        elif high or confidence < self.return_threshold:
            status = DecisionStatus.RETURNED
        elif findings or confidence < self.approval_threshold:
            status = DecisionStatus.CONDITIONAL
        else:
            status = DecisionStatus.APPROVED

        return GateDecision(
            execution_id=execution_id,
            status=status,
            confidence=confidence,
            breakdown=breakdown,
            findings=findings,
            remaining_uncertainties=remaining_uncertainties,
            human_review_required=status != DecisionStatus.APPROVED,
            evaluated_verifiers=evaluated_verifiers,
            execution_context_sha256=context_digest,
        )


def _execution_id(context: object) -> str:
    value = getattr(context, "execution_id", None)
    if isinstance(value, str) and value.strip():
        return value
    return "invalid-execution-context"


def _system_finding(
    *,
    code: str,
    message: str,
    point_id: str,
    details: dict[str, Any] | None = None,
) -> Finding:
    return Finding(
        verifier="gate_runtime",
        code=code,
        severity=Severity.CRITICAL,
        message=message,
        point_id=point_id,
        return_to="integration",
        required_action="Corrigir a integração antes de nova avaliação.",
        details=details or {},
    )


def _validate_verifier_output(verifier_name: str, value: object) -> None:
    if not isinstance(value, list):
        raise TypeError("Verifier must return list[Finding].")
    for finding in value:
        if not isinstance(finding, Finding):
            raise TypeError("Verifier must return list[Finding].")
        if finding.verifier != verifier_name:
            raise ValueError("Finding verifier must match the registered verifier name.")
        if not isinstance(finding.severity, Severity):
            raise TypeError("Finding severity must be a Severity enum.")
        for field_name in ("code", "message", "point_id"):
            field_value = getattr(finding, field_name)
            if not isinstance(field_value, str) or not field_value.strip():
                raise ValueError(f"Finding {field_name} must be a non-empty string.")
        try:
            to_jsonable(finding)
        except SerializationError as exc:
            raise TypeError("Finding must be safely serializable.") from exc


def _context_digest(context: object) -> str | None:
    try:
        payload = dumps_json(context).encode("utf-8")
    except SerializationError:
        return None
    return sha256(payload).hexdigest()


def _previous_block_findings(context: object) -> list[Finding]:
    if not isinstance(context, ExecutionContext) or not isinstance(context.gate_results, list):
        return []

    blocked_gates = []
    for index, item in enumerate(context.gate_results):
        if not isinstance(item, Mapping):
            continue
        gate_name = item.get("gate")
        status = item.get("status")
        if isinstance(status, str) and status.strip().lower() == DecisionStatus.BLOCKED.value:
            name = gate_name if isinstance(gate_name, str) and gate_name else f"gate-{index}"
            blocked_gates.append(name)

    findings = [
        Finding(
            verifier="logical_consistency",
            code="PREVIOUS_GATE_BLOCKED",
            severity=Severity.CRITICAL,
            message=f"O gate anterior {gate_name!r} está bloqueado.",
            point_id=f"previous-gate:{gate_name}",
            return_to=gate_name,
            required_action="Preservar o bloqueio e submeter a nova revisão humana.",
        )
        for gate_name in blocked_gates
    ]
    promoted = (
        any(
            isinstance(item, Mapping) and item.get("promoted") is True for item in context.decisions
        )
        if isinstance(context.decisions, list)
        else False
    )
    if blocked_gates and promoted:
        findings.append(
            Finding(
                verifier="logical_consistency",
                code="PROMOTION_AFTER_BLOCK",
                severity=Severity.CRITICAL,
                message="Resultado foi promovido apesar de gate anterior bloqueado.",
                point_id="pipeline-outcome",
                return_to="orchestration",
                required_action="Cancelar promoção e preservar o bloqueio oficial.",
                details={"blocked_gates": blocked_gates},
            )
        )
    return findings
