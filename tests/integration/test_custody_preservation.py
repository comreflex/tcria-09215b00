"""Integration tests: custody chain preservation across products."""
from __future__ import annotations

from precision_gate.custody.audit_trail import AuditTrail
from precision_gate.custody.models import CustodyStatus
from precision_gate.custody.state_machine import CustodyStateMachine
from precision_gate.composition.pipeline import PrecisionGatePipeline


BLOCKED_BUNDLE = {
    "audit_id": "custody-test-001",
    "total_files_scanned": 1,
    "files": [{"artifact_id": "doc-001", "sha256": "aaa", "source_path": "/tmp/a.txt"}],
    "decisions": [{"decision_id": "dec-001", "promoted": False}],
    "metadata": {"open_points": []},
    "logs": [],
    "artifacts": [],
    "gate_results": [],
    "prescriptive_gate_status": "blocked",
}

CLEAN_BUNDLE = {
    "audit_id": "custody-test-002",
    "total_files_scanned": 1,
    "files": [{"artifact_id": "doc-002", "sha256": "bbb", "source_path": "/tmp/b.txt"}],
    "decisions": [{"decision_id": "dec-001", "promoted": False}],
    "metadata": {"open_points": []},
    "logs": [],
    "artifacts": [],
    "gate_results": [],
}


def test_blocked_bundle_forces_human_review() -> None:
    pipeline = PrecisionGatePipeline.default()
    record, trail = pipeline.run(BLOCKED_BUNDLE, case_id="custody-blocked")

    assert record.human_review_required is True
    assert len(record.non_abandonment_flags) > 0


def test_custody_status_never_downgrades_blocked() -> None:
    """A TCRIA block cannot be overridden by a quinta-ordem approval."""
    sm = CustodyStateMachine()
    # Simulate quinta-ordem returning approved but TCRIA block is present
    qo_state = {
        "status": "approved",
        "confidence": 0.99,
        "human_review_required": False,
        "confidence_breakdown": {},
        "remaining_uncertainties": [],
        "custody_trail": {"decision_sha256": "def456"},
    }
    record = sm.build_record(
        case_id="test-block",
        execution_id="exec-001",
        tcria_bundle_sha256="abc123",
        quinta_ordem_custody_state=qo_state,
        tcria_non_abandonment_flags=["TCRIA prescriptive gate is BLOCKED — human review required."],
    )
    # Must NOT be approved despite quinta-ordem saying approved
    assert record.status != CustodyStatus.APPROVED
    assert record.human_review_required is True


def test_audit_trail_serialization_roundtrip(tmp_path) -> None:
    pipeline = PrecisionGatePipeline.default()
    _, trail = pipeline.run(CLEAN_BUNDLE, case_id="custody-serial")

    save_path = tmp_path / "trail.json"
    trail.save(save_path)

    loaded = AuditTrail.load(save_path)
    assert len(loaded.entries) == len(trail.entries)
    assert loaded.entries[0]["event_type"] == trail.entries[0]["event_type"]


def test_custody_hashes_preserved_in_report() -> None:
    from precision_gate.reporting.report_builder import ReportBuilder
    pipeline = PrecisionGatePipeline.default()
    record, trail = pipeline.run(CLEAN_BUNDLE, case_id="custody-hashes")

    builder = ReportBuilder()
    report = builder.build(record, trail)

    # TCRIA bundle hash must be present
    assert report["custody_hashes"]["tcria_bundle_sha256"] is not None
    assert len(report["custody_hashes"]["tcria_bundle_sha256"]) == 64  # SHA-256 hex
