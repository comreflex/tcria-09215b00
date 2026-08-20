"""Final Report Markdown Generator.

Renders a FinalConsolidationResult as a comprehensive Markdown report
for human review and downstream consumption by any AI reading all three outputs.

Sections:
- Executive Summary (overall status + confidence)
- Confirmed Findings (full cross-stage agreement)
- Contradictions (divergence between stages — potential anomalies/lies)
- Anomalies (evidence missing from one or more stages)
- Confidence Matrix (per-evidence score table)
- Open Points (requires human adjudication)
- Traceability Chain (provenance from each stage)
- Governance Footer

Governance rules applied:
- RULE_4.1: contradictions are flagged for human decision, never auto-resolved
- RULE_2.1: traceability links preserved in every section
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tcria.consolidation.final_consolidator import FinalConsolidationResult


class FinalReportMarkdownReporter:
    """Renders a FinalConsolidationResult as Markdown."""

    def generate(self, result: FinalConsolidationResult) -> str:
        parts = [
            self._render_header(result),
            self._render_executive_summary(result),
            self._render_confirmed(result),
            self._render_contradictions(result),
            self._render_anomalies(result),
            self._render_confidence_matrix(result),
            self._render_open_points(result),
            self._render_traceability(result),
            self._render_footer(result),
        ]
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    @staticmethod
    def _render_header(result: FinalConsolidationResult) -> str:
        now = datetime.now(timezone.utc).isoformat()
        return (
            f"# TCRIA — Final Consolidated Report\n\n"
            f"**Execution ID:** `{result.execution_id}`  \n"
            f"**Report generated:** {now}  \n"
            f"**Pipeline:** TCRIA → Quinta Ordem → Precision Gate  \n"
            f"**Human accountability:** `{result.human_accountability}`"
        )

    @staticmethod
    def _render_executive_summary(result: FinalConsolidationResult) -> str:
        status_icons = {
            "APPROVED": "✅",
            "CONDITIONAL": "⚠️",
            "BLOCKED": "🚫",
            "PENDING": "🔄",
        }
        icon = status_icons.get(result.overall_status, "❓")
        bar_filled = round(result.overall_confidence / 10)
        confidence_bar = "█" * bar_filled + "░" * (10 - bar_filled)

        total = (
            len(result.confirmed)
            + len(result.contradicted)
            + len(result.anomalies)
        )

        lines = [
            "## Executive Summary",
            "",
            f"| Field | Value |",
            f"|---|---|",
            f"| Overall status | {icon} **{result.overall_status}** |",
            f"| Overall confidence | `{result.overall_confidence}%` {confidence_bar} |",
            f"| Total evidence items | {total} |",
            f"| Confirmed (full agreement) | {len(result.confirmed)} |",
            f"| Contradicted (divergence) | {len(result.contradicted)} |",
            f"| Anomalies (incomplete chain) | {len(result.anomalies)} |",
            f"| Open points requiring human review | {len(result.open_points)} |",
        ]

        if result.overall_status == "BLOCKED":
            lines += [
                "",
                "> 🚫 **BLOCKED:** Contradictions were detected across pipeline stages. "
                "These items **cannot be auto-resolved** and require explicit human "
                "adjudication before any legal or operational conclusion can be drawn (RULE_4.1).",
            ]
        elif result.overall_status == "CONDITIONAL":
            lines += [
                "",
                "> ⚠️ **CONDITIONAL:** Some evidence items are missing stage data or "
                "contain unresolved accusatory signals. Human review is required before "
                "promoting any conclusion.",
            ]
        else:
            lines += [
                "",
                "> ✅ **APPROVED:** All three pipeline stages reached consistent conclusions "
                "for all evidence items. Human accountability metadata is attached to every "
                "decision per RULE_4.1.",
            ]

        return "\n".join(lines)

    @staticmethod
    def _render_confirmed(result: FinalConsolidationResult) -> str:
        lines = ["## Confirmed Findings"]

        if not result.confirmed:
            lines += ["", "_No items with full cross-stage agreement._"]
            return "\n".join(lines)

        lines += [
            "",
            "All three pipeline stages agreed on these items.",
            "",
            "| Evidence | Classification | Confidence | Stage 1 TCRIA | Stage 2 Quinta Ordem | Stage 3 Precision |",
            "|---|---|---|---|---|---|",
        ]
        for ea in result.confirmed:
            conf = f"`{ea.confidence_score}%`"
            lines.append(
                f"| {ea.file_name} "
                f"| {ea.stage1_classification or '—'} "
                f"| {conf} "
                f"| {ea.stage1_outcome or ea.stage1_classification or '—'} "
                f"| {ea.stage2_classification or '—'} "
                f"| {ea.stage3_outcome or ea.stage3_status or '—'} |"
            )
        return "\n".join(lines)

    @staticmethod
    def _render_contradictions(result: FinalConsolidationResult) -> str:
        lines = ["## Contradictions"]

        if not result.contradicted:
            lines += ["", "_No contradictions detected across pipeline stages._"]
            return "\n".join(lines)

        lines += [
            "",
            "> ⚠️ **These items have diverging classifications across stages.**  ",
            "> This may indicate **inconsistent evidence**, **processing errors**, "
            "or **deliberate manipulation**. Human adjudication is mandatory (RULE_4.1).",
            "",
            "| Evidence | Stage 1 TCRIA | Stage 2 Quinta Ordem | Stage 3 Precision | Contradiction Detail | Confidence |",
            "|---|---|---|---|---|---|",
        ]
        for ea in result.contradicted:
            detail = (ea.contradiction_detail or "").replace("|", "\\|")
            lines.append(
                f"| **{ea.file_name}** "
                f"| {ea.stage1_classification or '—'} "
                f"| {ea.stage2_classification or '—'} "
                f"| {ea.stage3_outcome or ea.stage3_status or '—'} "
                f"| {detail} "
                f"| `{ea.confidence_score}%` |"
            )
        return "\n".join(lines)

    @staticmethod
    def _render_anomalies(result: FinalConsolidationResult) -> str:
        lines = ["## Anomalies"]

        if not result.anomalies:
            lines += ["", "_No anomalies detected._"]
            return "\n".join(lines)

        lines += [
            "",
            "> These items were **not consistently tracked** across all three stages. "
            "Missing data in a stage may indicate a gap in the chain of custody.",
            "",
            "| Evidence | Agreement Level | Stage 1 | Stage 2 | Stage 3 | Confidence |",
            "|---|---|---|---|---|---|",
        ]
        for ea in result.anomalies:
            level_icon = "⚠️" if ea.agreement_level == "PARTIAL" else "🔴"
            lines.append(
                f"| {ea.file_name} "
                f"| {level_icon} {ea.agreement_level} "
                f"| {ea.stage1_classification or '—'} "
                f"| {ea.stage2_classification or '—'} "
                f"| {ea.stage3_outcome or ea.stage3_status or '—'} "
                f"| `{ea.confidence_score}%` |"
            )
        return "\n".join(lines)

    @staticmethod
    def _render_confidence_matrix(result: FinalConsolidationResult) -> str:
        lines = [
            "## Confidence Matrix",
            "",
            "Per-evidence cross-stage confidence scores. "
            "Higher scores indicate stronger agreement across all three pipeline stages.",
            "",
            "| Evidence | TCRIA (S1) | Quinta Ordem (S2) | Precision (S3) | Agreement | Score |",
            "|---|---|---|---|---|---|",
        ]

        agreement_icons = {
            "FULL": "✅ FULL",
            "PARTIAL": "⚠️ PARTIAL",
            "CONTRADICTION": "🚫 CONTRADICTION",
            "MISSING": "🔴 MISSING",
            "UNKNOWN": "❓ UNKNOWN",
        }

        for row in result.confidence_matrix:
            agreement = agreement_icons.get(row["agreement"], row["agreement"])
            score = row["confidence_score"]
            bar = "█" * round(score / 20) + "░" * (5 - round(score / 20))
            lines.append(
                f"| {row['file_name']} "
                f"| {row['stage1_tcria']} "
                f"| {row['stage2_quinta_ordem']} "
                f"| {row['stage3_precision']} "
                f"| {agreement} "
                f"| `{score}%` {bar} |"
            )
        if not result.confidence_matrix:
            lines.append("| — | — | — | — | — | — |")
        return "\n".join(lines)

    @staticmethod
    def _render_open_points(result: FinalConsolidationResult) -> str:
        lines = ["## Open Points — Human Review Required"]

        if not result.open_points:
            lines += ["", "_No open points. All items resolved across pipeline stages._"]
            return "\n".join(lines)

        lines += [
            "",
            f"**{len(result.open_points)} item(s) require explicit human adjudication** before "
            "any legal or operational conclusion can be drawn (RULE_4.1).",
            "",
        ]
        for i, point in enumerate(result.open_points, 1):
            lines.append(f"{i}. {point}")
        return "\n".join(lines)

    @staticmethod
    def _render_traceability(result: FinalConsolidationResult) -> str:
        lines = [
            "## Traceability Chain",
            "",
            "| Stage | Source | Role |",
            "|---|---|---|",
            f"| Stage 1 — TCRIA | `{result.source_stage1}` | Evidence ingestion, classification, gate evaluation |",
            f"| Stage 2 — Quinta Ordem | `{result.source_stage2}` | ExecutionContext validation, decision mapping |",
            f"| Stage 3 — Precision Gate | `{result.source_stage3}` | Custody validation, final gate verification |",
            "",
            "**Rules applied:**",
            "",
            "- `RULE_4.1` — Human responsibility required for all accusatory decisions and contradictions",
            "- `RULE_2.1` — Original evidence was never modified; all operations are read-only mappings",
            "- Chain-of-custody integrity: each stage output traced back to TCRIA source bundle",
        ]
        return "\n".join(lines)

    @staticmethod
    def _render_footer(result: FinalConsolidationResult) -> str:
        status = result.overall_status
        confidence = result.overall_confidence
        return (
            "---\n\n"
            "> **Governance Notice:** This final consolidated report was produced by the TCRIA "
            "pipeline consolidator reading all three stage outputs: TCRIA, Quinta Ordem, and "
            "Precision Gate. "
            f"**Overall status: {status} — Overall confidence: {confidence}%.** "
            "No legal or operational conclusion may be drawn from this report without "
            f"explicit human accountability as required by RULE_4.1. "
            f"Execution ID: `{result.execution_id}`."
        )
