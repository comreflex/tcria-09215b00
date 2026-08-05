"""Reporting: unified custody report builder."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from precision_gate.custody.models import CustodyRecord
from precision_gate.custody.audit_trail import AuditTrail


class ReportBuilder:
    """Build a human-readable and machine-auditable custody report."""

    def build(
        self,
        record: CustodyRecord,
        trail: AuditTrail,
        *,
        output_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Build the custody report.

        Args:
            record: The final CustodyRecord from the pipeline.
            trail: The AuditTrail accumulated during the pipeline run.
            output_path: If provided, saves the report as a JSON file.

        Returns:
            The report as a dict.
        """
        report = {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "case_id": record.case_id,
            "execution_id": record.execution_id,
            "final_status": record.status.value,
            "confidence": record.confidence,
            "human_review_required": record.human_review_required,
            "non_abandonment_flags": record.non_abandonment_flags,
            "custody_hashes": {
                "tcria_bundle_sha256": record.tcria_bundle_sha256,
                "quinta_ordem_decision_sha256": record.quinta_ordem_decision_sha256,
            },
            "confidence_breakdown": record.metadata.get("quinta_ordem_breakdown", {}),
            "remaining_uncertainties": record.metadata.get("remaining_uncertainties", []),
            "timestamps": record.timestamps,
            "audit_trail": trail.to_dict(),
        }

        if output_path is not None:
            dest = Path(output_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

        return report

    def build_markdown(self, report: dict[str, Any]) -> str:
        """Render a human-readable Markdown summary of the custody report."""
        status = report["final_status"]
        human_review = report["human_review_required"]
        flags = report.get("non_abandonment_flags", [])
        confidence = report.get("confidence", 0.0)

        lines = [
            f"# Precision Gate Custody Report",
            f"",
            f"**Case ID:** {report['case_id']}  ",
            f"**Execution ID:** {report['execution_id']}  ",
            f"**Generated:** {report['generated_at']}  ",
            f"",
            f"## Decision",
            f"",
            f"| Field | Value |",
            f"|-------|-------|",
            f"| Status | `{status}` |",
            f"| Confidence | {confidence:.4f} |",
            f"| Human Review Required | {'**YES**' if human_review else 'No'} |",
            f"",
        ]

        if flags:
            lines += [
                "## ⚠️ Non-Abandonment Flags",
                "",
                *[f"- {flag}" for flag in flags],
                "",
            ]

        breakdown = report.get("confidence_breakdown", {})
        if breakdown:
            lines += [
                "## Confidence Breakdown",
                "",
                "| Dimension | Score |",
                "|-----------|-------|",
                *[f"| {k} | {v:.4f} |" for k, v in breakdown.items()],
                "",
            ]

        uncertainties = report.get("remaining_uncertainties", [])
        if uncertainties:
            lines += [
                "## Remaining Uncertainties",
                "",
                *[f"- {u}" for u in uncertainties],
                "",
            ]

        hashes = report.get("custody_hashes", {})
        lines += [
            "## Custody Hashes",
            "",
            f"- **TCRIA bundle SHA-256:** `{hashes.get('tcria_bundle_sha256', 'N/A')}`",
            f"- **Quinta Ordem decision SHA-256:** `{hashes.get('quinta_ordem_decision_sha256', 'N/A')}`",
            "",
            f"_Audit trail contains {report['audit_trail']['entry_count']} entries._",
        ]

        return "\n".join(lines) + "\n"
