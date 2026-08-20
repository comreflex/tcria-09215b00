"""Integration tests for Quinta Ordem adapter and Markdown reporter.

Tests cover:
- ExecutionContext serialization
- Evidence reference preservation
- Decision classification mapping
- Markdown output generation
- Chain-of-custody integrity
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tcria.adapters.quinta_ordem_adapter import ExecutionContext, QuintaOrdemAdapter
from tcria.reporting.quinta_ordem_markdown import QuintaOrdemMarkdownReporter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EXAMPLE_BUNDLE_PATH = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "audit-artifacts"
    / "tcr_gateway_accusation_bundle_audit.json"
)


def _minimal_bundle() -> dict:
    return {
        "generated_at": "2026-01-01T00:00:00",
        "audit_basis": "test",
        "compliance_gate_mode": "default-heuristic",
        "total_files_scanned": 3,
        "accusation_set_count": 1,
        "classification_counts": {
            "ACCUSATORY_CANDIDATE": 1,
            "SUPPORTING_EVIDENCE": 2,
        },
        "accusation_set": [
            {
                "file_name": "evidence_a.pdf",
                "file_path": "/tmp/evidence_a.pdf",
                "suffix": ".pdf",
                "size_bytes": 1024,
                "sha256": "a" * 64,
                "extraction_status": "ok",
                "extraction_method": "pdfminer",
                "text_chars": 500,
                "text_quality": "medium",
                "sensitive_handling": "normal",
                "classification": "ACCUSATORY_CANDIDATE",
                "raises_accusation": True,
                "classification_reasons": ["Contains fraud keywords"],
                "artifact_type": "legal_document",
                "artifact_type_reason": "legal content detected",
                "key_signals": {
                    "dates_found": 3,
                    "currency_values_found": 2,
                    "accusation_keyword_hits": {"fraude": 5, "golpe": 3},
                },
                "gates": {
                    "prescriptiveGate": {"status": "BLOCKED", "reason": "Accusatory pattern found"},
                    "complianceGate": {"status": "PASS", "reason": "Within policy"},
                    "traceabilityCheck": {"status": "WARN", "reason": "Missing timestamp"},
                },
                "overall_outcome": None,
            }
        ],
        "non_accusation_set": [
            {
                "file_name": "evidence_b.pdf",
                "file_path": "/tmp/evidence_b.pdf",
                "suffix": ".pdf",
                "size_bytes": 512,
                "sha256": "b" * 64,
                "extraction_status": "ok",
                "extraction_method": "pdfminer",
                "text_chars": 200,
                "text_quality": "low",
                "sensitive_handling": "normal",
                "classification": "SUPPORTING_EVIDENCE",
                "raises_accusation": False,
                "classification_reasons": ["No accusatory content"],
                "artifact_type": "invoice",
                "artifact_type_reason": "invoice keywords",
                "key_signals": {"dates_found": 1, "currency_values_found": 1, "accusation_keyword_hits": {}},
                "gates": {
                    "prescriptiveGate": {"status": "PASS", "reason": "Clean"},
                    "complianceGate": {"status": "PASS", "reason": "OK"},
                },
                "overall_outcome": "APPROVED",
            },
            {
                "file_name": "evidence_c.csv",
                "file_path": "/tmp/evidence_c.csv",
                "suffix": ".csv",
                "size_bytes": 256,
                "sha256": "c" * 64,
                "extraction_status": "ok",
                "extraction_method": "pandas",
                "text_chars": 100,
                "text_quality": "low",
                "sensitive_handling": "normal",
                "classification": "SUPPORTING_EVIDENCE",
                "raises_accusation": False,
                "classification_reasons": ["Supporting data"],
                "artifact_type": "transaction_log",
                "artifact_type_reason": "transaction data",
                "key_signals": {"dates_found": 0, "currency_values_found": 0, "accusation_keyword_hits": {}},
                "gates": {},
                "overall_outcome": "APPROVED",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Adapter tests
# ---------------------------------------------------------------------------

class TestExecutionContextSerialization:
    def test_to_dict_has_required_keys(self):
        ctx = ExecutionContext(
            execution_id="test-id",
            evidence=[],
            artifacts=[],
            gate_results=[],
            logs=[],
            decisions=[],
            metadata={},
        )
        d = ctx.to_dict()
        for key in ("execution_id", "evidence", "artifacts", "gate_results", "logs", "decisions", "metadata"):
            assert key in d

    def test_to_json_is_valid_json(self):
        ctx = ExecutionContext(
            execution_id="test-id",
            evidence=[{"key": "value"}],
            artifacts=[],
            gate_results=[],
            logs=[],
            decisions=[],
            metadata={"open_points": []},
        )
        raw = ctx.to_json()
        parsed = json.loads(raw)
        assert parsed["execution_id"] == "test-id"

    def test_to_json_roundtrip(self):
        ctx = ExecutionContext(
            execution_id="roundtrip-id",
            evidence=[{"evidence_id": "abc123"}],
            artifacts=[{"artifact_id": "art1"}],
            gate_results=[{"gate_name": "test_gate", "status": "PASS"}],
            logs=[{"event": "test"}],
            decisions=[{"decision_id": "d1", "classification": "ACCUSATORY"}],
            metadata={"open_points": ["point1"]},
        )
        parsed = json.loads(ctx.to_json())
        assert parsed["decisions"][0]["classification"] == "ACCUSATORY"
        assert parsed["metadata"]["open_points"] == ["point1"]


class TestAdapterFromBundle:
    def setup_method(self):
        self.adapter = QuintaOrdemAdapter()
        self.bundle = _minimal_bundle()
        self.ctx = self.adapter.from_bundle_dict(self.bundle)

    def test_execution_id_deterministic(self):
        ctx2 = self.adapter.from_bundle_dict(self.bundle)
        assert self.ctx.execution_id == ctx2.execution_id

    def test_execution_id_prefix(self):
        assert self.ctx.execution_id.startswith("tcria-exec-")

    def test_evidence_count(self):
        # 1 accusatory + 2 non-accusatory = 3 evidence entries
        assert len(self.ctx.evidence) == 3

    def test_evidence_reference_preservation(self):
        sha_prefix = "a" * 16
        refs = [ev["evidence_id"] for ev in self.ctx.evidence]
        assert sha_prefix in refs

    def test_evidence_sha256_preserved(self):
        ev_a = next(e for e in self.ctx.evidence if e["file_name"] == "evidence_a.pdf")
        assert ev_a["sha256"] == "a" * 64

    def test_artifacts_count(self):
        assert len(self.ctx.artifacts) == 3

    def test_gate_results_extracted(self):
        gate_names = [gr["gate_name"] for gr in self.ctx.gate_results]
        assert "prescriptive_gate" in gate_names
        assert "compliance_gate" in gate_names

    def test_gate_result_status_mapping(self):
        prescriptive = next(
            gr for gr in self.ctx.gate_results if gr["gate_name"] == "prescriptive_gate"
            and gr["artifact_ref"] == "a" * 16
        )
        assert prescriptive["status"] == "BLOCKED"

    def test_decision_classification_mapping(self):
        accusatory = [d for d in self.ctx.decisions if d["classification"] == "ACCUSATORY"]
        non_accusatory = [d for d in self.ctx.decisions if d["classification"] == "NON_ACCUSATORY"]
        assert len(accusatory) == 1
        assert len(non_accusatory) == 2

    def test_accusatory_decision_has_human_responsibility(self):
        dec = next(d for d in self.ctx.decisions if d["classification"] == "ACCUSATORY")
        assert "RULE_4.1" in dec["human_responsibility"]

    def test_non_accusatory_decision_has_human_responsibility(self):
        dec = next(d for d in self.ctx.decisions if d["classification"] == "NON_ACCUSATORY")
        assert "RULE_4.1" in dec["human_responsibility"]

    def test_decision_evidence_refs_preserved(self):
        dec = next(d for d in self.ctx.decisions if d["classification"] == "ACCUSATORY")
        assert len(dec["evidence_refs"]) == 1
        assert dec["evidence_refs"][0] == "a" * 16

    def test_support_level_high_for_many_keywords(self):
        dec = next(d for d in self.ctx.decisions if d["classification"] == "ACCUSATORY")
        # fraude=5 + golpe=3 + dates + currency = 10 -> HIGH
        assert dec["support_level"] == "HIGH"

    def test_support_level_low_for_no_keywords(self):
        dec = next(
            d for d in self.ctx.decisions
            if d["classification"] == "NON_ACCUSATORY" and d["file_name"] == "evidence_c.csv"
        )
        assert dec["support_level"] == "LOW"

    def test_metadata_open_points_for_unresolved(self):
        # evidence_a.pdf has overall_outcome=None -> should appear in open_points
        assert len(self.ctx.metadata["open_points"]) >= 1

    def test_metadata_traceability_chain(self):
        chain = self.ctx.metadata["traceability"]["chain_of_custody"]
        assert "tcria" in chain
        assert "quinta-ordem" in chain

    def test_metadata_rules_applied(self):
        rules = self.ctx.metadata["traceability"]["rules_applied"]
        assert "RULE_4.1" in rules
        assert "RULE_2.1" in rules

    def test_logs_contain_audit_event(self):
        events = [log["event"] for log in self.ctx.logs]
        assert "audit_completed" in events

    def test_chain_of_custody_no_modification(self):
        # Original bundle should remain unchanged after adaptation
        assert self.bundle["accusation_set"][0]["sha256"] == "a" * 64
        assert self.bundle["accusation_set"][0]["raises_accusation"] is True


class TestAdapterFromExampleBundle:
    """Smoke test against the real example bundle if available."""

    def test_from_real_bundle_json(self):
        if not EXAMPLE_BUNDLE_PATH.exists():
            pytest.skip("Example bundle not available")
        adapter = QuintaOrdemAdapter()
        ctx = adapter.from_bundle_json(EXAMPLE_BUNDLE_PATH)
        assert ctx.execution_id.startswith("tcria-exec-")
        assert len(ctx.evidence) > 0
        assert len(ctx.decisions) > 0

    def test_real_bundle_decisions_have_evidence_refs(self):
        if not EXAMPLE_BUNDLE_PATH.exists():
            pytest.skip("Example bundle not available")
        adapter = QuintaOrdemAdapter()
        ctx = adapter.from_bundle_json(EXAMPLE_BUNDLE_PATH)
        for dec in ctx.decisions:
            assert len(dec["evidence_refs"]) >= 1


# ---------------------------------------------------------------------------
# Markdown reporter tests
# ---------------------------------------------------------------------------

class TestMarkdownReporter:
    def setup_method(self):
        adapter = QuintaOrdemAdapter()
        self.ctx = adapter.from_bundle_dict(_minimal_bundle())
        self.reporter = QuintaOrdemMarkdownReporter()
        self.md = self.reporter.generate(self.ctx)

    def test_output_is_string(self):
        assert isinstance(self.md, str)

    def test_contains_execution_id(self):
        assert self.ctx.execution_id in self.md

    def test_contains_summary_section(self):
        assert "## Summary" in self.md

    def test_contains_evidence_section(self):
        assert "## Evidence" in self.md

    def test_contains_decisions_section(self):
        assert "## Decisions" in self.md

    def test_contains_gate_results_section(self):
        assert "## Gate Results" in self.md

    def test_contains_metadata_section(self):
        assert "## Metadata" in self.md

    def test_contains_open_points(self):
        assert "Open Points" in self.md

    def test_contains_traceability(self):
        assert "Traceability" in self.md

    def test_contains_governance_accountability(self):
        assert "Governance Accountability" in self.md

    def test_contains_rule_4_1(self):
        assert "RULE_4.1" in self.md

    def test_contains_rule_2_1(self):
        assert "RULE_2.1" in self.md

    def test_accusatory_section_present(self):
        assert "### Accusatory" in self.md

    def test_non_accusatory_section_present(self):
        assert "### Non-Accusatory" in self.md

    def test_gate_status_icons(self):
        assert "🚫 BLOCKED" in self.md
        assert "✅ PASS" in self.md

    def test_footer_governance_notice(self):
        assert "Governance Notice" in self.md

    def test_file_names_in_evidence_table(self):
        assert "evidence_a.pdf" in self.md
        assert "evidence_b.pdf" in self.md

    def test_empty_context_renders_without_error(self):
        from tcria.adapters.quinta_ordem_adapter import ExecutionContext
        ctx = ExecutionContext(
            execution_id="empty-ctx",
            evidence=[],
            artifacts=[],
            gate_results=[],
            logs=[],
            decisions=[],
            metadata={"open_points": [], "traceability": {}, "governance": {}},
        )
        md = self.reporter.generate(ctx)
        assert "## Summary" in md
        assert "_No decisions recorded._" in md
        assert "_No open points._" in md
