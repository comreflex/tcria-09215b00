from __future__ import annotations

from collections.abc import Mapping

from quinta_ordem.models import ExecutionContext, Finding, Severity
from quinta_ordem.verifiers.base import Verifier
from quinta_ordem.verifiers.utils import evidence_ref_from_raw

_CLASSIFICATIONS = {"fact", "hypothesis", "allegation", "signal", "recommendation"}
_SUPPORT_LEVELS = {"direct", "corroborated", "partial", "unsupported", "none", "unknown"}


class EvidenceSupportVerifier(Verifier):
    name = "evidence_support"

    def verify(self, context: ExecutionContext) -> list[Finding]:
        findings: list[Finding] = []
        evidence_by_id = {
            item.get("artifact_id"): item
            for item in context.evidence
            if isinstance(item, Mapping) and isinstance(item.get("artifact_id"), str)
        }
        evidence_ids = set(evidence_by_id)

        for index, decision in enumerate(context.decisions):
            if not isinstance(decision, Mapping):
                continue
            point_id = str(decision.get("decision_id") or f"decision-{index}")
            raw_classification = decision.get("classification")
            raw_support = decision.get("support_level")
            classification = (
                raw_classification.strip().lower() if isinstance(raw_classification, str) else None
            )
            support = raw_support.strip().lower() if isinstance(raw_support, str) else None
            refs = [
                ref
                for raw_ref in decision.get("evidence_refs", [])
                if (ref := evidence_ref_from_raw(raw_ref)) is not None
            ]
            known_ref_ids = {ref.artifact_id for ref in refs if ref.artifact_id in evidence_ids}
            known_hashes = {
                evidence_by_id[artifact_id].get("sha256")
                for artifact_id in known_ref_ids
                if isinstance(evidence_by_id[artifact_id].get("sha256"), str)
            }

            if classification not in _CLASSIFICATIONS:
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="UNKNOWN_CLASSIFICATION",
                        severity=Severity.HIGH,
                        message="A decisão não possui classificação informacional reconhecida.",
                        point_id=point_id,
                        evidence_refs=refs,
                        return_to="analysis",
                        required_action=(
                            "Classificar como fact, hypothesis, allegation, signal ou recommendation."
                        ),
                    )
                )
                continue

            if support not in _SUPPORT_LEVELS:
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="UNKNOWN_SUPPORT_LEVEL",
                        severity=Severity.HIGH,
                        message="A decisão não possui nível de suporte reconhecido.",
                        point_id=point_id,
                        evidence_refs=refs,
                        return_to="analysis",
                        required_action="Declarar nível de suporte verificável.",
                    )
                )

            if classification == "fact" and support not in {"direct", "corroborated"}:
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="FACT_WITH_INSUFFICIENT_SUPPORT",
                        severity=Severity.CRITICAL,
                        message="Item promovido como fato sem suporte direto ou corroborado.",
                        point_id=point_id,
                        evidence_refs=refs,
                        return_to="analysis",
                        required_action="Reclassificar como alegação/hipótese ou anexar suporte.",
                    )
                )
            elif support in {"unsupported", "none", "unknown"}:
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="UNSUPPORTED_ITEM_REQUIRES_REVIEW",
                        severity=Severity.WARNING,
                        message="Item sem suporte suficiente permanece sujeito à revisão humana.",
                        point_id=point_id,
                        evidence_refs=refs,
                        return_to="human_review",
                        required_action="Obter suporte, manter como sinal ou encerrar sem promoção.",
                    )
                )
            elif classification == "fact" and support == "direct" and not known_ref_ids:
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="DIRECT_SUPPORT_NOT_LINKED",
                        severity=Severity.CRITICAL,
                        message="Fato com suporte direto sem evidência conhecida vinculada.",
                        point_id=point_id,
                        evidence_refs=refs,
                        return_to="evidence_linking",
                        required_action="Vincular ao menos uma evidência original existente.",
                    )
                )
            elif (
                classification == "fact"
                and support == "corroborated"
                and (len(known_ref_ids) < 2 or len(known_hashes) < 2)
            ):
                findings.append(
                    Finding(
                        verifier=self.name,
                        code="CORROBORATION_NOT_DEMONSTRATED",
                        severity=Severity.CRITICAL,
                        message="Suporte corroborado exige ao menos duas evidências distintas.",
                        point_id=point_id,
                        evidence_refs=refs,
                        return_to="evidence_linking",
                        required_action="Vincular duas ou mais evidências independentes.",
                    )
                )

        return findings
