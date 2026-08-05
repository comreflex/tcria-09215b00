from __future__ import annotations

import re
from collections.abc import Mapping

from quinta_ordem.models import ExecutionContext, Finding, Severity
from quinta_ordem.verifiers.base import Verifier
from quinta_ordem.verifiers.utils import evidence_ref_for_item

_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


class IntegrityVerifier(Verifier):
    name = "integrity"

    def verify(self, context: ExecutionContext) -> list[Finding]:
        findings: list[Finding] = []

        for index, item in enumerate(context.evidence):
            if not isinstance(item, Mapping):
                continue
            point_id = str(item.get("artifact_id") or f"evidence-{index}")
            evidence_ref = evidence_ref_for_item(item)
            evidence_refs = [evidence_ref] if evidence_ref else []
            sha256 = item.get("sha256")
            source_declared = any(
                isinstance(item.get(key), str) and bool(item.get(key).strip())
                for key in ("source", "source_path", "original_path", "path")
            )

            if not source_declared:
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="MISSING_EVIDENCE_SOURCE",
                        severity=Severity.HIGH,
                        message="A origem da evidência não foi declarada.",
                        point_id=point_id,
                        evidence_refs=evidence_refs,
                        return_to="ingestion",
                        required_action="Registrar URI ou caminho absoluto de origem.",
                    )
                )

            if not sha256:
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="MISSING_HASH",
                        severity=Severity.CRITICAL,
                        message="Evidência sem hash SHA-256 de integridade.",
                        point_id=point_id,
                        evidence_refs=evidence_refs,
                        return_to="ingestion",
                        required_action="Calcular e registrar SHA-256 antes da promoção.",
                    )
                )
            elif not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="INVALID_HASH",
                        severity=Severity.CRITICAL,
                        message="O hash declarado não possui formato SHA-256 válido.",
                        point_id=point_id,
                        evidence_refs=evidence_refs,
                        return_to="ingestion",
                        required_action="Registrar um digest SHA-256 hexadecimal de 64 caracteres.",
                    )
                )

            original_sha256 = item.get("original_sha256")
            if original_sha256 is not None and (
                not isinstance(original_sha256, str) or not _SHA256.fullmatch(original_sha256)
            ):
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="INVALID_ORIGINAL_HASH",
                        severity=Severity.CRITICAL,
                        message="O hash de cadeia de custódia do original é inválido.",
                        point_id=point_id,
                        evidence_refs=evidence_refs,
                        return_to="chain_of_custody",
                        required_action="Registrar original_sha256 hexadecimal de 64 caracteres.",
                    )
                )
            elif (
                isinstance(original_sha256, str)
                and isinstance(sha256, str)
                and _SHA256.fullmatch(sha256)
                and original_sha256.lower() != sha256.lower()
            ):
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="ORIGINAL_HASH_MISMATCH",
                        severity=Severity.CRITICAL,
                        message="O hash atual diverge do hash registrado para o original.",
                        point_id=point_id,
                        evidence_refs=evidence_refs,
                        return_to="chain_of_custody",
                        required_action="Bloquear o fluxo e revisar a cadeia de custódia.",
                    )
                )

            modified_original = item.get("modified_original")
            if modified_original is None:
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="ORIGINAL_STATE_UNDECLARED",
                        severity=Severity.HIGH,
                        message="O estado de preservação do artefato original não foi declarado.",
                        point_id=point_id,
                        evidence_refs=evidence_refs,
                        return_to="chain_of_custody",
                        required_action="Declarar explicitamente modified_original=false ou bloquear.",
                    )
                )
            elif not isinstance(modified_original, bool):
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="INVALID_ORIGINAL_STATE",
                        severity=Severity.CRITICAL,
                        message="modified_original deve ser um valor booleano.",
                        point_id=point_id,
                        evidence_refs=evidence_refs,
                        return_to="chain_of_custody",
                        required_action="Corrigir o registro da cadeia de custódia.",
                    )
                )
            elif modified_original:
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="ORIGINAL_MODIFIED",
                        severity=Severity.CRITICAL,
                        message="Há indicação de modificação do artefato original.",
                        point_id=point_id,
                        evidence_refs=evidence_refs,
                        return_to="chain_of_custody",
                        required_action="Bloquear o fluxo e revisar a cadeia de custódia.",
                    )
                )

        return findings
