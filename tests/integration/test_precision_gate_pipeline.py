"""Integration tests: Precision Gate pipeline custody preservation."""
from __future__ import annotations

import pytest

from precision_gate.adapters.tcria_adapter import TCRIAAdapter
from precision_gate.adapters.quinta_ordem_adapter import QuintaOrdemAdapter
from precision_gate.custody.audit_trail import AuditTrail
from precision_gate.custody.models import CustodyRecord, CustodyStatus
from precision_gate.custody.state_machine import CustodyStateMachine
from precision_gate.reporting.report_builder import ReportBuilder
from precision_gate.composition.pipeline import PrecisionGatePipeline


MINIMAL_BUNDLE = {
    "audit_id": "case-pipeline-001",
    "total_files_scanned": 1,
    "accusation_set_count": 0,
    "files": [{"artifact_id": "doc-001", "sha256": "abc123", "source_path": "/tmp/doc.pdf"}],
    "decisions": [{"decision_id": "dec-001", "promoted": False}],
    "metadata": {"open_points": []},
    "logs": [],
    "artifacts": [],
    "gate_results": [],
}


def test_pipeline_runs_and_returns_record_and_trail() -> None:
    pipeline = PrecisionGatePipeline.default()
    record, trail = pipeline.run(MINIMAL_BUNDLE, case_id="case-pipeline-001")

    assert isinstance(record, CustodyRecord)
    assert isinstance(trail, AuditTrail)
    assert record.case_id == "case-pipeline-001"
    assert len(trail.entries) >= 2


def test_pipeline_audit_trail_contains_required_events() -> None:
    pipeline = PrecisionGatePipeline.default()
    _, trail = pipeline.run(MINIMAL_BUNDLE, case_id="case-pipeline-001")

    event_types = {e["event_type"] for e in trail.entries}
    assert "pipeline_started" in event_types
    assert "tcria_adapted" in event_types
    assert "custody_record_built" in event_types


def test_pipeline_non_abandonment_blocked_bundle() -> None:
    blocked_bundle = {**MINIMAL_BUNDLE, "prescriptive_gate_status": "blocked"}
    pipeline = PrecisionGatePipeline.default()
    record, trail = pipeline.run(blocked_bundle, case_id="case-blocked-001")

    assert record.human_review_required is True
    assert len(record.non_abandonment_flags) > 0


def test_report_builder_generates_report() -> None:
    pipeline = PrecisionGatePipeline.default()
    record, trail = pipeline.run(MINIMAL_BUNDLE, case_id="case-report-001")

    builder = ReportBuilder()
    report = builder.build(record, trail)

    assert report["schema_version"] == "1.0"
    assert report["case_id"] == "case-report-001"
    assert "audit_trail" in report
    assert report["audit_trail"]["entry_count"] >= 2


def test_report_builder_generates_markdown() -> None:
    pipeline = PrecisionGatePipeline.default()
    record, trail = pipeline.run(MINIMAL_BUNDLE, case_id="case-md-001")

    builder = ReportBuilder()
    report = builder.build(record, trail)
    md = builder.build_markdown(report)

    assert "# Precision Gate Custody Report" in md
    assert "case-md-001" in md


def test_custody_record_is_immutable() -> None:
    pipeline = PrecisionGatePipeline.default()
    record, _ = pipeline.run(MINIMAL_BUNDLE, case_id="case-immutable-001")

    with pytest.raises((AttributeError, TypeError)):
        record.case_id = "hacked"  # type: ignore[misc]


def test_audit_trail_is_append_only() -> None:
    trail = AuditTrail()
    trail.append("event_a", {"data": 1})
    entries_snapshot = list(trail.entries)

    trail.append("event_b", {"data": 2})
    # Original snapshot is not affected
    assert len(entries_snapshot) == 1
    assert len(trail.entries) == 2
