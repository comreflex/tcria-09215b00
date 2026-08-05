from __future__ import annotations

from collections.abc import Mapping

from quinta_ordem.models import ExecutionContext, Finding, Severity
from quinta_ordem.verifiers.base import Verifier
from quinta_ordem.verifiers.utils import evidence_ref_from_raw


class ResolutionVerifier(Verifier):
    name = "resolution"

    def verify(self, context: ExecutionContext) -> list[Finding]:
        findings: list[Finding] = []
        open_points = context.metadata.get("open_points", [])
        if not isinstance(open_points, list):
            return findings

        for index, item in enumerate(open_points):
            if not isinstance(item, Mapping):
                continue
            point_id = str(item.get("id") or f"open-point-{index}")
            status = item.get("status")
            refs = [
                ref
                for raw_ref in item.get("evidence_refs", [])
                if (ref := evidence_ref_from_raw(raw_ref)) is not None
            ]

            if status == "accepted_uncertainty":
                if not item.get("accepted_by") or not item.get("reason"):
                    findings.append(
                        Finding(
                            verifier=self.name,
                            code="UNJUSTIFIED_ACCEPTED_UNCERTAINTY",
                            severity=Severity.WARNING,
                            message="Incerteza aceita sem responsável e justificativa formal.",
                            point_id=point_id,
                            evidence_refs=refs,
                            return_to=item.get("return_to") or "human_review",
                            required_action="Registrar accepted_by e reason.",
                        )
                    )
                continue

            if status == "resolved":
                continue

            severity = Severity.WARNING
            if item.get("blocking") is True:
                severity = Severity.HIGH
            if item.get("severity") == Severity.CRITICAL.value:
                severity = Severity.CRITICAL

            findings.append(
                Finding(
                    verifier=self.name,
                    code="UNRESOLVED_POINT",
                    severity=severity,
                    message="Ponto identificado permanece sem resolução ou aceitação formal.",
                    point_id=point_id,
                    evidence_refs=refs,
                    return_to=item.get("return_to") or "analysis",
                    required_action="Resolver ou registrar formalmente a incerteza.",
                    details={"declared_status": status},
                )
            )

        return findings
