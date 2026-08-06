"""Tests for FinalConsolidator and FinalReportMarkdownReporter.

Covers:
- Contradiction detection between stages
- Anomaly detection (missing stage data)
- Confidence score computation
- Overall status derivation
- Final Markdown report generation
- Chain-of-custody integrity (original data not mutated)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tcria.consolidation.final_consolidator import FinalConsolidator, FinalConsolidationResult
from tcria.reporting.final_report_markdown import FinalReportMarkdownReporter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64

EXAMPLE_BUNDLE_PATH = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "audit-artifacts"
    / "tcr_gateway_accusation_bundle_audit.json"
)


def _stage1_bundle(
    accusation_set=None,
    non_accusation_set=None,
) -> dict:
    return {
        "generated_at": "2026-01-01T00:00:00",
        "audit_basis": "test",
        "compliance_gate_mode": "default-heuristic",
        "total_files_scanned": 2,
        "accusation_set_count": 1,
        "classification_counts": {"ACCUSATORY_CANDIDATE": 1, "SUPPORTING_EVIDENCE": 1},
        "accusation_set": accusation_set or [
            {
                "file_name": "doc_a.pdf",
                "file_path": "/tmp/doc_a.pdf",
                "suffix": ".pdf",
                "size_bytes": 1024,
                "sha256": SHA_A,
                "extraction_status": "ok",
                "extraction_method": "pdfminer",
                "text_chars": 500,
                "text_quality": "medium",
                "sensitive_handling": "normal",
                "classification": "ACCUSATORY_CANDIDATE",
                "raises_accusation": True,
                "classification_reasons": ["fraud keywords"],
                "artifact_type": "legal_document",
                "artifact_type_reason": "legal",
                "key_signals": {"dates_found": 2, "currency_values_found": 1, "accusation_keyword_hits": {"fraude": 3}},
                "gates": {},
                "overall_outcome": None,
            }
        ],
        "non_accusation_set": non_accusation_set or [
            {
                "file_name": "doc_b.pdf",
                "file_path": "/tmp/doc_b.pdf",
                "suffix": ".pdf",
                "size_bytes": 512,
                "sha256": SHA_B,
                "extraction_status": "ok",
                "extraction_method": "pdfminer",
                "text_chars": 200,
                "text_quality": "low",
                "sensitive_handling": "normal",
                "classification": "SUPPORTING_EVIDENCE",
                "raises_accusation": False,
                "classification_reasons": ["no accusations"],
                "artifact_type": "invoice",
                "artifact_type_reason": "invoice",
                "key_signals": {"dates_found": 1, "currency_values_found": 0, "accusation_keyword_hits": {}},
                "gates": {},
                "overall_outcome": "APPROVED",
            }
        ],
    }


def _stage2_context_agreeing() -> dict:
    """Quinta Ordem decisions agreeing with TCRIA."""
    return {
        "execution_id": "tcria-exec-test",
        "decisions": [
            {
                "decision_id": "dec-a",
                "classification": "ACCUSATORY",
                "support_level": "MEDIUM",
                "evidence_refs": [SHA_A[:16]],
                "file_name": "doc_a.pdf",
                "overall_outcome": None,
                "human_responsibility": "RULE_4.1:required",
            },
            {
                "decision_id": "dec-b",
                "classification": "NON_ACCUSATORY",
                "support_level": "LOW",
                "evidence_refs": [SHA_B[:16]],
                "file_name": "doc_b.pdf",
                "overall_outcome": "APPROVED",
                "human_responsibility": "RULE_4.1:required",
            },
        ],
        "evidence": [],
        "artifacts": [],
        "gate_results": [],
        "logs": [],
        "metadata": {"open_points": [], "traceability": {}, "governance": {}},
    }


def _stage2_context_contradicting() -> dict:
    """Quinta Ordem disagrees on doc_a: says NON_ACCUSATORY while TCRIA says ACCUSATORY."""
    ctx = _stage2_context_agreeing()
    ctx["decisions"][0]["classification"] = "NON_ACCUSATORY"
    return ctx


def _stage3_precision_agreeing() -> dict:
    """Precision Gate output agreeing with both previous stages."""
    return {
        "decisions": [
            {
                "evidence_refs": [SHA_A[:16]],
                "file_name": "doc_a.pdf",
                "classification": "ACCUSATORY",
                "overall_outcome": None,
            },
            {
                "evidence_refs": [SHA_B[:16]],
                "file_name": "doc_b.pdf",
                "classification": "NON_ACCUSATORY",
                "overall_outcome": "APPROVED",
            },
        ],
        "gate_results": [],
    }


def _stage3_precision_contradicting() -> dict:
    """Precision Gate disagrees on doc_b: says ACCUSATORY while TCRIA says NON_ACCUSATORY."""
    return {
        "decisions": [
            {
                "evidence_refs": [SHA_A[:16]],
                "file_name": "doc_a.pdf",
                "classification": "ACCUSATORY",
                "overall_outcome": None,
            },
            {
                "evidence_refs": [SHA_B[:16]],
                "file_name": "doc_b.pdf",
                "classification": "ACCUSATORY",   # contradiction
                "overall_outcome": "BLOCKED",
            },
        ],
        "gate_results": [],
    }


# ---------------------------------------------------------------------------
# FinalConsolidator tests
# ---------------------------------------------------------------------------

class TestFullAgreement:
    def setup_method(self):
        self.consolidator = FinalConsolidator()
        self.result = self.consolidator.consolidate(
            stage1=_stage1_bundle(),
            stage2=_stage2_context_agreeing(),
            stage3=_stage3_precision_agreeing(),
        )

    def test_returns_result(self):
        assert isinstance(self.result, FinalConsolidationResult)

    def test_no_contradictions(self):
        assert len(self.result.contradicted) == 0

    def test_confirmed_items(self):
        assert len(self.result.confirmed) >= 1

    def test_no_open_contradiction_points(self):
        contradiction_points = [p for p in self.result.open_points if "CONTRADICTION" in p]
        assert len(contradiction_points) == 0

    def test_overall_status_not_blocked(self):
        assert self.result.overall_status != "BLOCKED"

    def test_confidence_above_zero(self):
        assert self.result.overall_confidence > 0

    def test_confidence_matrix_populated(self):
        assert len(self.result.confidence_matrix) >= 2

    def test_final_decisions_populated(self):
        assert len(self.result.final_decisions) >= 2

    def test_execution_id_from_stage2(self):
        assert self.result.execution_id == "tcria-exec-test"

    def test_human_accountability_metadata(self):
        assert "RULE_4.1" in self.result.human_accountability


class TestContradictionDetection:
    def setup_method(self):
        self.consolidator = FinalConsolidator()
        self.result = self.consolidator.consolidate(
            stage1=_stage1_bundle(),
            stage2=_stage2_context_contradicting(),
            stage3={},
        )

    def test_contradiction_detected(self):
        assert len(self.result.contradicted) >= 1

    def test_overall_status_blocked(self):
        assert self.result.overall_status == "BLOCKED"

    def test_open_points_contain_contradiction(self):
        contradiction_points = [p for p in self.result.open_points if "CONTRADICTION" in p]
        assert len(contradiction_points) >= 1

    def test_contradiction_confidence_low(self):
        for ea in self.result.contradicted:
            assert ea.confidence_score <= 20

    def test_contradiction_detail_recorded(self):
        for ea in self.result.contradicted:
            assert ea.contradiction_detail is not None
            assert "Stage1=" in ea.contradiction_detail

    def test_contradicted_decision_requires_human(self):
        dec = next(
            d for d in self.result.final_decisions
            if d["status"] == "REQUIRES_HUMAN_ADJUDICATION"
        )
        assert "RULE_4.1" in dec["human_responsibility"]
        assert "auto-resolved" in dec["human_responsibility"]


class TestThreeStageContradiction:
    def setup_method(self):
        self.consolidator = FinalConsolidator()
        # Stage2 agrees, Stage3 contradicts on doc_b
        self.result = self.consolidator.consolidate(
            stage1=_stage1_bundle(),
            stage2=_stage2_context_agreeing(),
            stage3=_stage3_precision_contradicting(),
        )

    def test_contradiction_from_stage3_detected(self):
        assert len(self.result.contradicted) >= 1

    def test_overall_status_blocked(self):
        assert self.result.overall_status == "BLOCKED"


class TestMissingStageData:
    def setup_method(self):
        self.consolidator = FinalConsolidator()
        # No stage3 data
        self.result = self.consolidator.consolidate(
            stage1=_stage1_bundle(),
            stage2=_stage2_context_agreeing(),
            stage3={},
        )

    def test_no_full_three_stage_agreement(self):
        # With stage3 empty, no item can have FULL 3-stage agreement
        for ea in self.result.confirmed:
            assert ea.stage3_status is None
            assert ea.stage3_outcome is None

    def test_anomalies_or_confirmed_present(self):
        total = len(self.result.confirmed) + len(self.result.anomalies)
        assert total >= 2


class TestChainOfCustodyIntegrity:
    def test_stage1_bundle_not_mutated(self):
        bundle = _stage1_bundle()
        original_sha = bundle["accusation_set"][0]["sha256"]
        consolidator = FinalConsolidator()
        consolidator.consolidate(
            stage1=bundle,
            stage2=_stage2_context_agreeing(),
            stage3={},
        )
        assert bundle["accusation_set"][0]["sha256"] == original_sha

    def test_stage2_not_mutated(self):
        ctx = _stage2_context_agreeing()
        original_id = ctx["execution_id"]
        consolidator = FinalConsolidator()
        consolidator.consolidate(
            stage1=_stage1_bundle(),
            stage2=ctx,
            stage3={},
        )
        assert ctx["execution_id"] == original_id

    def test_traceability_sources_recorded(self):
        consolidator = FinalConsolidator()
        result = consolidator.consolidate(
            stage1=_stage1_bundle(),
            stage2=_stage2_context_agreeing(),
            stage3={},
        )
        assert result.source_stage1 == "<dict>"
        assert result.source_stage2 == "<dict>"


class TestConfidenceScoring:
    def test_full_agreement_high_confidence(self):
        consolidator = FinalConsolidator()
        result = consolidator.consolidate(
            stage1=_stage1_bundle(),
            stage2=_stage2_context_agreeing(),
            stage3=_stage3_precision_agreeing(),
        )
        for ea in result.confirmed:
            assert ea.confidence_score >= 60

    def test_contradiction_very_low_confidence(self):
        consolidator = FinalConsolidator()
        result = consolidator.consolidate(
            stage1=_stage1_bundle(),
            stage2=_stage2_context_contradicting(),
            stage3={},
        )
        for ea in result.contradicted:
            assert ea.confidence_score <= 20

    def test_overall_confidence_range(self):
        consolidator = FinalConsolidator()
        result = consolidator.consolidate(
            stage1=_stage1_bundle(),
            stage2=_stage2_context_agreeing(),
            stage3={},
        )
        assert 0 <= result.overall_confidence <= 100


class TestToJson:
    def test_serializable(self):
        consolidator = FinalConsolidator()
        result = consolidator.consolidate(
            stage1=_stage1_bundle(),
            stage2=_stage2_context_agreeing(),
            stage3={},
        )
        raw = result.to_json()
        parsed = json.loads(raw)
        assert "execution_id" in parsed
        assert "final_decisions" in parsed
        assert "confidence_matrix" in parsed
        assert "overall_status" in parsed


class TestRealBundleSmoke:
    def test_from_real_bundle(self):
        if not EXAMPLE_BUNDLE_PATH.exists():
            pytest.skip("Example bundle not available")

        # Build a minimal stage2 from the real bundle
        from tcria.adapters.quinta_ordem_adapter import QuintaOrdemAdapter
        ctx = QuintaOrdemAdapter().from_bundle_json(EXAMPLE_BUNDLE_PATH)

        import json as _json
        with open(EXAMPLE_BUNDLE_PATH, encoding="utf-8") as f:
            s1 = _json.load(f)

        consolidator = FinalConsolidator()
        result = consolidator.consolidate(
            stage1=s1,
            stage2=ctx.to_dict(),
            stage3={},
        )
        assert result.overall_confidence >= 0
        assert result.overall_status in ("APPROVED", "CONDITIONAL", "BLOCKED", "PENDING")
        assert len(result.confidence_matrix) > 0


# ---------------------------------------------------------------------------
# FinalReportMarkdownReporter tests
# ---------------------------------------------------------------------------

class TestFinalReportMarkdown:
    def setup_method(self):
        consolidator = FinalConsolidator()
        self.result_agree = consolidator.consolidate(
            stage1=_stage1_bundle(),
            stage2=_stage2_context_agreeing(),
            stage3=_stage3_precision_agreeing(),
        )
        self.result_contra = consolidator.consolidate(
            stage1=_stage1_bundle(),
            stage2=_stage2_context_contradicting(),
            stage3={},
        )
        self.reporter = FinalReportMarkdownReporter()

    def test_output_is_string(self):
        md = self.reporter.generate(self.result_agree)
        assert isinstance(md, str)

    def test_contains_header(self):
        md = self.reporter.generate(self.result_agree)
        assert "# TCRIA — Final Consolidated Report" in md

    def test_contains_executive_summary(self):
        md = self.reporter.generate(self.result_agree)
        assert "## Executive Summary" in md

    def test_contains_confirmed_section(self):
        md = self.reporter.generate(self.result_agree)
        assert "## Confirmed Findings" in md

    def test_contains_contradictions_section(self):
        md = self.reporter.generate(self.result_agree)
        assert "## Contradictions" in md

    def test_contains_anomalies_section(self):
        md = self.reporter.generate(self.result_agree)
        assert "## Anomalies" in md

    def test_contains_confidence_matrix(self):
        md = self.reporter.generate(self.result_agree)
        assert "## Confidence Matrix" in md

    def test_contains_open_points(self):
        md = self.reporter.generate(self.result_agree)
        assert "## Open Points" in md

    def test_contains_traceability(self):
        md = self.reporter.generate(self.result_agree)
        assert "## Traceability Chain" in md

    def test_contains_rule_4_1(self):
        md = self.reporter.generate(self.result_agree)
        assert "RULE_4.1" in md

    def test_contains_rule_2_1(self):
        md = self.reporter.generate(self.result_agree)
        assert "RULE_2.1" in md

    def test_blocked_status_shown_in_summary(self):
        md = self.reporter.generate(self.result_contra)
        assert "BLOCKED" in md

    def test_contradiction_section_shows_files(self):
        md = self.reporter.generate(self.result_contra)
        assert "doc_a.pdf" in md

    def test_approved_status_shown_when_agreed(self):
        md = self.reporter.generate(self.result_agree)
        assert "APPROVED" in md or "CONDITIONAL" in md

    def test_contains_execution_id(self):
        md = self.reporter.generate(self.result_agree)
        assert self.result_agree.execution_id in md

    def test_governance_footer_present(self):
        md = self.reporter.generate(self.result_agree)
        assert "Governance Notice" in md

    def test_contains_confidence_percentage(self):
        md = self.reporter.generate(self.result_agree)
        assert "%" in md
