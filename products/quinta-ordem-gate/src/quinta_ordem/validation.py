from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from quinta_ordem.models import ExecutionContext, Finding, Severity
from quinta_ordem.serialization import SerializationError, to_jsonable

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


def validate_execution_context(context: object) -> list[Finding]:
    """Return audit findings for structural and minimum-contract violations."""

    if not isinstance(context, ExecutionContext):
        return [
            _finding(
                code="INVALID_CONTEXT_TYPE",
                message="O gate recebeu um objeto que não é ExecutionContext.",
                point_id="execution-context",
            )
        ]

    findings: list[Finding] = []

    if not isinstance(context.execution_id, str) or not context.execution_id.strip():
        findings.append(
            _finding(
                code="INVALID_EXECUTION_ID",
                message="execution_id deve ser uma string não vazia.",
                point_id="execution-context",
            )
        )
    elif _CONTROL_CHARACTERS.search(context.execution_id):
        findings.append(
            _finding(
                code="INVALID_EXECUTION_ID",
                message="execution_id contém caractere de controle não permitido.",
                point_id="execution-context",
            )
        )

    collection_names = (
        "evidence",
        "artifacts",
        "gate_results",
        "logs",
        "decisions",
    )
    valid_collections: dict[str, list[Any]] = {}

    for name in collection_names:
        value = getattr(context, name)
        if not isinstance(value, list):
            findings.append(
                _finding(
                    code="INVALID_COLLECTION_TYPE",
                    message=f"{name} deve ser uma lista.",
                    point_id=f"execution-context:{name}",
                    details={"actual_type": type(value).__name__},
                )
            )
            continue

        valid_collections[name] = value
        for index, item in enumerate(value):
            if not isinstance(item, Mapping):
                findings.append(
                    _finding(
                        code="INVALID_COLLECTION_ITEM",
                        message=f"Cada item de {name} deve ser um mapeamento.",
                        point_id=f"{name}:{index}",
                        details={"actual_type": type(item).__name__},
                    )
                )

    if not isinstance(context.metadata, Mapping):
        findings.append(
            _finding(
                code="INVALID_METADATA_TYPE",
                message="metadata deve ser um mapeamento.",
                point_id="execution-context:metadata",
                details={"actual_type": type(context.metadata).__name__},
            )
        )
    else:
        evidence_roots = context.metadata.get("evidence_roots")
        if evidence_roots is not None:
            if not isinstance(evidence_roots, list):
                findings.append(
                    _finding(
                        code="INVALID_EVIDENCE_ROOTS_TYPE",
                        message="metadata.evidence_roots deve ser uma lista.",
                        point_id="execution-context:evidence-roots",
                        details={"actual_type": type(evidence_roots).__name__},
                    )
                )
            else:
                for index, value in enumerate(evidence_roots):
                    if not _is_absolute_local_path(value):
                        findings.append(
                            _finding(
                                code="INVALID_EVIDENCE_ROOT",
                                message="Cada evidence_root deve ser um caminho local absoluto.",
                                point_id=f"evidence-root:{index}",
                            )
                        )

        open_points = context.metadata.get("open_points")
        if open_points is None:
            findings.append(
                Finding(
                    verifier="resolution",
                    code="OPEN_POINTS_UNDECLARED",
                    severity=Severity.WARNING,
                    message=(
                        "O contexto não declara open_points; ausência de pendências não foi "
                        "verificada explicitamente."
                    ),
                    point_id="execution-context:open-points",
                    return_to="analysis",
                    required_action="Declarar open_points, ainda que como lista vazia.",
                )
            )
        elif not isinstance(open_points, list):
            findings.append(
                _finding(
                    code="INVALID_OPEN_POINTS_TYPE",
                    message="metadata.open_points deve ser uma lista.",
                    point_id="execution-context:open-points",
                    details={"actual_type": type(open_points).__name__},
                )
            )
        else:
            seen_open_point_ids: set[str] = set()
            for index, item in enumerate(open_points):
                if not isinstance(item, Mapping):
                    findings.append(
                        _finding(
                            code="INVALID_OPEN_POINT",
                            message="Cada open_point deve ser um mapeamento.",
                            point_id=f"open-point:{index}",
                            details={"actual_type": type(item).__name__},
                        )
                    )
                    continue
                point_id = item.get("id")
                if isinstance(point_id, str) and point_id:
                    if point_id in seen_open_point_ids:
                        findings.append(
                            _finding(
                                code="DUPLICATE_OPEN_POINT_ID",
                                message="open_point possui identificador duplicado.",
                                point_id=point_id,
                            )
                        )
                    seen_open_point_ids.add(point_id)
                refs = item.get("evidence_refs")
                if refs is not None and not isinstance(refs, list):
                    findings.append(
                        _finding(
                            code="INVALID_OPEN_POINT_REFS_TYPE",
                            message="open_point.evidence_refs deve ser uma lista.",
                            point_id=str(point_id or f"open-point:{index}"),
                            details={"actual_type": type(refs).__name__},
                        )
                    )

    evidence = valid_collections.get("evidence")
    if evidence is not None:
        if not evidence:
            findings.append(
                Finding(
                    verifier="integrity",
                    code="NO_EVIDENCE",
                    severity=Severity.HIGH,
                    message="Nenhuma evidência foi declarada para verificação.",
                    point_id="execution-context:evidence",
                    return_to="ingestion",
                    required_action="Declarar as evidências ou encerrar sem promoção.",
                )
            )
        findings.extend(_validate_unique_ids(evidence, "artifact_id", "evidence"))
        for index, item in enumerate(evidence):
            if not isinstance(item, Mapping):
                continue
            for key in ("source_path", "original_path", "path"):
                if key in item and not _is_absolute_local_path(item.get(key)):
                    findings.append(
                        _finding(
                            code="INVALID_EVIDENCE_PATH",
                            message=f"evidence.{key} deve ser um caminho local absoluto.",
                            point_id=str(item.get("artifact_id") or f"evidence:{index}"),
                        )
                    )
            if "source" in item and not _is_valid_source(item.get("source")):
                findings.append(
                    _finding(
                        code="INVALID_EVIDENCE_SOURCE",
                        message="evidence.source deve ser URI ou caminho local absoluto.",
                        point_id=str(item.get("artifact_id") or f"evidence:{index}"),
                    )
                )

    artifacts = valid_collections.get("artifacts")
    if artifacts is not None:
        findings.extend(_validate_unique_ids(artifacts, "artifact_id", "artifact"))
        evidence_ids = _declared_ids(evidence or [], "artifact_id")
        artifact_ids = _declared_ids(artifacts, "artifact_id")
        for duplicate_id in sorted(evidence_ids & artifact_ids):
            findings.append(
                _finding(
                    code="COLLIDING_ARTIFACT_ID",
                    message="O mesmo artifact_id identifica evidência original e artefato derivado.",
                    point_id=duplicate_id,
                )
            )

    decisions = valid_collections.get("decisions")
    if decisions is not None:
        if not decisions:
            findings.append(
                Finding(
                    verifier="traceability",
                    code="NO_DECISIONS",
                    severity=Severity.HIGH,
                    message="Nenhuma decisão ou sinal foi declarado para avaliação.",
                    point_id="execution-context:decisions",
                    return_to="analysis",
                    required_action="Declarar o resultado analisável ou encerrar a execução.",
                )
            )
        findings.extend(_validate_unique_ids(decisions, "decision_id", "decision"))
        for index, decision in enumerate(decisions):
            if not isinstance(decision, Mapping):
                continue
            point_id = str(decision.get("decision_id") or f"decision-{index}")
            refs = decision.get("evidence_refs")
            if refs is not None and not isinstance(refs, list):
                findings.append(
                    _finding(
                        code="INVALID_EVIDENCE_REFS_TYPE",
                        message="decision.evidence_refs deve ser uma lista.",
                        point_id=point_id,
                        details={"actual_type": type(refs).__name__},
                    )
                )
            promoted = decision.get("promoted")
            if promoted is None:
                findings.append(
                    Finding(
                        verifier="logical_consistency",
                        code="PROMOTION_STATE_UNDECLARED",
                        severity=Severity.HIGH,
                        message="A decisão não declara explicitamente seu estado de promoção.",
                        point_id=point_id,
                        return_to="analysis",
                        required_action="Declarar promoted=true ou promoted=false.",
                    )
                )
            elif not isinstance(promoted, bool):
                findings.append(
                    _finding(
                        code="INVALID_PROMOTION_STATE",
                        message="decision.promoted deve ser booleano.",
                        point_id=point_id,
                        details={"actual_type": type(promoted).__name__},
                    )
                )

    gate_results = valid_collections.get("gate_results")
    if gate_results is not None:
        for index, result in enumerate(gate_results):
            if not isinstance(result, Mapping):
                continue
            gate_name = result.get("gate")
            status = result.get("status")
            if not isinstance(gate_name, str) or not gate_name.strip():
                findings.append(
                    _finding(
                        code="INVALID_GATE_NAME",
                        message="Resultado de gate anterior sem identificador válido.",
                        point_id=f"gate-result:{index}",
                    )
                )
            if not isinstance(status, str) or not status.strip():
                findings.append(
                    _finding(
                        code="INVALID_GATE_STATUS",
                        message="Resultado de gate anterior sem status válido.",
                        point_id=f"gate-result:{index}",
                    )
                )

    try:
        to_jsonable(context)
    except SerializationError as exc:
        findings.append(
            _finding(
                code="UNSERIALIZABLE_CONTEXT",
                message="O contexto contém valor que não pode ser serializado com segurança.",
                point_id="execution-context",
                details={"reason": str(exc)},
            )
        )

    return findings


def has_structural_failure(findings: list[Finding]) -> bool:
    return any(
        finding.verifier == "context_validation" and finding.severity == Severity.CRITICAL
        for finding in findings
    )


def _validate_unique_ids(
    items: list[Any],
    id_field: str,
    item_kind: str,
) -> list[Finding]:
    findings: list[Finding] = []
    seen: dict[str, int] = {}

    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            continue
        raw_id = item.get(id_field)
        if not isinstance(raw_id, str) or not raw_id.strip():
            findings.append(
                _finding(
                    code=f"INVALID_{item_kind.upper()}_ID",
                    message=f"{item_kind} sem {id_field} válido.",
                    point_id=f"{item_kind}:{index}",
                )
            )
            continue
        if raw_id in seen:
            findings.append(
                _finding(
                    code=f"DUPLICATE_{item_kind.upper()}_ID",
                    message=f"{item_kind} possui identificador duplicado.",
                    point_id=raw_id,
                    details={"first_index": seen[raw_id], "duplicate_index": index},
                )
            )
        else:
            seen[raw_id] = index

    return findings


def _declared_ids(items: list[Any], id_field: str) -> set[str]:
    return {
        value
        for item in items
        if isinstance(item, Mapping)
        and isinstance((value := item.get(id_field)), str)
        and value.strip()
    }


def _is_absolute_local_path(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value)
    if parsed.scheme.lower() == "file":
        return bool(parsed.path and Path(unquote(parsed.path)).is_absolute())
    return Path(value).is_absolute()


def _is_valid_source(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    if _is_absolute_local_path(value):
        return True
    parsed = urlparse(value)
    return bool(parsed.scheme and parsed.scheme.lower() != "file")


def _finding(
    *,
    code: str,
    message: str,
    point_id: str,
    details: dict[str, Any] | None = None,
) -> Finding:
    return Finding(
        verifier="context_validation",
        code=code,
        severity=Severity.CRITICAL,
        message=message,
        point_id=point_id,
        return_to="integration",
        required_action="Corrigir o contrato do ExecutionContext antes de nova avaliação.",
        details=details or {},
    )
