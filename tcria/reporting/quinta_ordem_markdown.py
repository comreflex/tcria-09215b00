"""Quinta Ordem Markdown Reporter.

Generates standardized Markdown reports from TCRIA ExecutionContext objects,
following the format expected by the Precision Gate downstream pipeline.

Sections produced:
- summary
- evidence
- decisions
- gate_results
- metadata (including open_points)

Governance rules applied:
- RULE_2.1: traceability links preserved in every section
- RULE_4.1: human accountability metadata explicitly rendered
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tcria.adapters.quinta_ordem_adapter import ExecutionContext


class QuintaOrdemMarkdownReporter:
    """Renders an ExecutionContext as Markdown compatible with Precision Gate."""

    # Section headers follow the Precision Gate custody model
    _SECTION_ORDER = [
        "summary",
        "evidence",
        "decisions",
        "gate_results",
        "metadata",
    ]

    def generate(self, ctx: ExecutionContext) -> str:
        """Generate the full Markdown report string.

        Parameters
        ----------
        ctx:
            ExecutionContext produced by QuintaOrdemAdapter.

        Returns
        -------
        str
            Markdown-formatted report ready for downstream consumption.
        """
        parts: list[str] = [self._render_header(ctx)]
        parts.append(self._render_summary(ctx))
        parts.append(self._render_evidence(ctx))
        parts.append(self._render_decisions(ctx))
        parts.append(self._render_gate_results(ctx))
        parts.append(self._render_metadata(ctx))
        parts.append(self._render_footer(ctx))
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Section renderers
    # ------------------------------------------------------------------

    @staticmethod
    def _render_header(ctx: ExecutionContext) -> str:
        now = datetime.now(timezone.utc).isoformat()
        return (
            f"# Quinta Ordem Gate — Execution Report\n\n"
            f"**Execution ID:** `{ctx.execution_id}`  \n"
            f"**Report generated:** {now}  \n"
            f"**Source:** TCRIA Audit Bundle  \n"
            f"**Chain-of-custody:** tcria → quinta-ordem → precision-gate"
        )

    @staticmethod
    def _render_summary(ctx: ExecutionContext) -> str:
        meta = ctx.metadata
        counts = meta.get("classification_counts", {})
        lines = [
            "## Summary",
            "",
            f"| Field | Value |",
            f"|---|---|",
            f"| Execution ID | `{ctx.execution_id}` |",
            f"| Generated at | {meta.get('generated_at', '')} |",
            f"| Audit basis | {meta.get('audit_basis', '')} |",
            f"| Compliance gate mode | {meta.get('compliance_gate_mode', '')} |",
            f"| Total files scanned | {meta.get('total_files_scanned', 0)} |",
            f"| Accusation set count | {meta.get('accusation_set_count', 0)} |",
        ]

        if counts:
            lines.append("")
            lines.append("### Classification Counts")
            lines.append("")
            lines.append("| Classification | Count |")
            lines.append("|---|---|")
            for cls, cnt in counts.items():
                lines.append(f"| {cls} | {cnt} |")

        return "\n".join(lines)

    @staticmethod
    def _render_evidence(ctx: ExecutionContext) -> str:
        lines = [
            "## Evidence",
            "",
            "| Evidence ID | File Name | Classification | Raises Accusation | SHA-256 (prefix) | Status |",
            "|---|---|---|---|---|---|",
        ]
        for ev in ctx.evidence:
            sha_prefix = (ev.get("sha256") or "")[:16]
            accusation_flag = "⚠ YES" if ev.get("raises_accusation") else "NO"
            lines.append(
                f"| `{ev.get('evidence_id', '')}` "
                f"| {ev.get('file_name', '')} "
                f"| {ev.get('classification', '')} "
                f"| {accusation_flag} "
                f"| `{sha_prefix}` "
                f"| {ev.get('extraction_status', '')} |"
            )
        if not ctx.evidence:
            lines.append("| — | — | — | — | — | — |")
        return "\n".join(lines)

    @staticmethod
    def _render_decisions(ctx: ExecutionContext) -> str:
        accusatory = [d for d in ctx.decisions if d.get("classification") == "ACCUSATORY"]
        non_accusatory = [d for d in ctx.decisions if d.get("classification") == "NON_ACCUSATORY"]

        sections: list[str] = ["## Decisions"]

        def _table_rows(decisions: list[dict[str, Any]]) -> list[str]:
            rows = [
                "| Decision ID | File Name | Classification | Support Level | Outcome | Human Responsibility |",
                "|---|---|---|---|---|---|",
            ]
            for dec in decisions:
                rows.append(
                    f"| `{dec.get('decision_id', '')}` "
                    f"| {dec.get('file_name', '')} "
                    f"| **{dec.get('classification', '')}** "
                    f"| {dec.get('support_level', '')} "
                    f"| {dec.get('overall_outcome') or 'PENDING'} "
                    f"| `{dec.get('human_responsibility', '')}` |"
                )
            return rows

        if accusatory:
            sections.append("")
            sections.append("### Accusatory")
            sections.append("")
            sections.extend(_table_rows(accusatory))

        if non_accusatory:
            sections.append("")
            sections.append("### Non-Accusatory")
            sections.append("")
            sections.extend(_table_rows(non_accusatory))

        if not ctx.decisions:
            sections.append("")
            sections.append("_No decisions recorded._")

        return "\n".join(sections)

    @staticmethod
    def _render_gate_results(ctx: ExecutionContext) -> str:
        lines = [
            "## Gate Results",
            "",
            "| Gate | Artifact Ref | Status | Reason |",
            "|---|---|---|---|",
        ]
        status_icons = {
            "PASS": "✅ PASS",
            "WARN": "⚠ WARN",
            "BLOCKED": "🚫 BLOCKED",
            "NOT_EVALUATED": "— N/A",
            "NOT_APPLICABLE": "— N/A",
        }
        for gr in ctx.gate_results:
            raw_status = gr.get("status", "NOT_EVALUATED")
            status_label = status_icons.get(raw_status, raw_status)
            reason = (gr.get("reason") or "").replace("|", "\\|")
            lines.append(
                f"| {gr.get('gate_name', '')} "
                f"| `{gr.get('artifact_ref', '')}` "
                f"| {status_label} "
                f"| {reason} |"
            )
        if not ctx.gate_results:
            lines.append("| — | — | — | — |")
        return "\n".join(lines)

    @staticmethod
    def _render_metadata(ctx: ExecutionContext) -> str:
        meta = ctx.metadata
        open_points: list[str] = meta.get("open_points", [])
        traceability: dict[str, Any] = meta.get("traceability", {})
        governance: dict[str, Any] = meta.get("governance", {})

        lines: list[str] = ["## Metadata"]

        # Open points — maps to Precision Gate "pending" state
        lines.append("")
        lines.append("### Open Points")
        lines.append("")
        if open_points:
            for point in open_points:
                lines.append(f"- {point}")
        else:
            lines.append("_No open points._")

        # Traceability
        lines.append("")
        lines.append("### Traceability")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|---|---|")
        for k, v in traceability.items():
            if isinstance(v, list):
                v = ", ".join(str(i) for i in v)
            lines.append(f"| {k} | {v} |")

        # Governance
        lines.append("")
        lines.append("### Governance Accountability")
        lines.append("")
        lines.append("| Rule | Enforcement |")
        lines.append("|---|---|")
        for k, v in governance.items():
            lines.append(f"| {k} | {v} |")

        return "\n".join(lines)

    @staticmethod
    def _render_footer(ctx: ExecutionContext) -> str:
        return (
            "---\n\n"
            "> **Governance Notice:** This report was generated by the TCRIA Quinta Ordem "
            "integration layer. All decisions require explicit human review as mandated by "
            "RULE_4.1. Original evidence has not been modified (RULE_2.1). "
            f"Execution ID: `{ctx.execution_id}`."
        )
