from __future__ import annotations

from collections.abc import Mapping

from quinta_ordem.models import ExecutionContext, Finding, Severity
from quinta_ordem.verifiers.base import Verifier
from quinta_ordem.verifiers.utils import evidence_ref_from_raw


class TraceabilityVerifier(Verifier):
    name = "traceability"

    def verify(self, context: ExecutionContext) -> list[Finding]:
        findings: list[Finding] = []
        known_items = _index_items([*context.evidence, *context.artifacts])

        for index, decision in enumerate(context.decisions):
            if not isinstance(decision, Mapping):
                continue
            point_id = str(decision.get("decision_id") or f"decision-{index}")
            raw_refs = decision.get("evidence_refs")

            if not isinstance(raw_refs, list) or not raw_refs:
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="DECISION_WITHOUT_EVIDENCE",
                        severity=Severity.HIGH,
                        message="Decisão sem referência rastreável a evidências.",
                        point_id=point_id,
                        return_to="evidence_linking",
                        required_action="Adicionar referências ou reclassificar como hipótese.",
                    )
                )
                continue

            seen_refs: set[str] = set()
            for ref_index, raw_ref in enumerate(raw_refs):
                ref = evidence_ref_from_raw(raw_ref)
                if ref is None:
                    findings.append(
                        Finding(
                            verifier=self.name,
                            code="INVALID_EVIDENCE_REFERENCE",
                            severity=Severity.HIGH,
                            message="A decisão contém referência de evidência inválida.",
                            point_id=point_id,
                            return_to="evidence_linking",
                            required_action="Usar artifact_id válido em cada referência.",
                            details={"reference_index": ref_index},
                        )
                    )
                    continue

                if ref.artifact_id in seen_refs:
                    findings.append(
                        Finding(
                            verifier=self.name,
                            code="DUPLICATE_EVIDENCE_REFERENCE",
                            severity=Severity.WARNING,
                            message="A decisão repete a mesma referência de evidência.",
                            point_id=point_id,
                            evidence_refs=[ref],
                            return_to="evidence_linking",
                            required_action="Remover referências duplicadas.",
                        )
                    )
                seen_refs.add(ref.artifact_id)

                known = known_items.get(ref.artifact_id)
                if known is None:
                    findings.append(
                        Finding(
                            verifier=self.name,
                            code="UNKNOWN_EVIDENCE_REFERENCE",
                            severity=Severity.HIGH,
                            message="A decisão referencia artefato ausente do contexto.",
                            point_id=point_id,
                            evidence_refs=[ref],
                            return_to="evidence_linking",
                            required_action="Incluir o artefato referenciado ou remover a referência.",
                        )
                    )
                    continue

                known_hash = known.get("sha256")
                if (
                    ref.sha256 is not None
                    and isinstance(known_hash, str)
                    and ref.sha256.lower() != known_hash.lower()
                ):
                    findings.append(
                        Finding(
                            verifier=self.name,
                            code="REFERENCE_HASH_MISMATCH",
                            severity=Severity.CRITICAL,
                            message="A referência usa hash divergente do artefato registrado.",
                            point_id=point_id,
                            evidence_refs=[ref],
                            return_to="chain_of_custody",
                            required_action="Bloquear e reconciliar os hashes antes de continuar.",
                        )
                    )

        return findings


def _index_items(items: list[dict[str, object]]) -> dict[str, Mapping[str, object]]:
    indexed: dict[str, Mapping[str, object]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        artifact_id = item.get("artifact_id")
        if isinstance(artifact_id, str) and artifact_id not in indexed:
            indexed[artifact_id] = item
    return indexed
