"""Integration tests: TCRIA adapter → Quinta Ordem ExecutionContext."""
from __future__ import annotations

import pytest

from precision_gate.adapters.tcria_adapter import TCRIAAdapter, TCRIAAdapterError


MINIMAL_BUNDLE = {
    "audit_id": "case-integration-001",
    "total_files_scanned": 2,
    "accusation_set_count": 0,
    "files": [
        {
            "artifact_id": "doc-001",
            "sha256": "abc123",
            "source_path": "/tmp/doc.pdf",
            "type": "pdf",
        }
    ],
    "decisions": [{"decision_id": "dec-001", "promoted": False}],
    "metadata": {"open_points": []},
    "logs": [],
    "artifacts": [],
    "gate_results": [],
}


def test_tcria_adapter_produces_valid_payload() -> None:
    adapter = TCRIAAdapter(version="1.0")
    payload = adapter.to_execution_context_payload(MINIMAL_BUNDLE)

    assert payload["quinta_ordem_adapter_version"] == "1.0"
    assert payload["execution_id"] == "case-integration-001"
    assert isinstance(payload["evidence"], list)
    assert isinstance(payload["decisions"], list)
    assert "_precision_gate_meta" in payload


def test_tcria_adapter_preserves_input_bundle() -> None:
    import copy
    original = copy.deepcopy(MINIMAL_BUNDLE)
    adapter = TCRIAAdapter(version="1.0")
    adapter.to_execution_context_payload(MINIMAL_BUNDLE)

    # Bundle must not be mutated
    assert MINIMAL_BUNDLE == original


def test_tcria_adapter_detects_prescriptive_block() -> None:
    bundle = {**MINIMAL_BUNDLE, "prescriptive_gate_status": "blocked"}
    adapter = TCRIAAdapter(version="1.0")
    payload = adapter.to_execution_context_payload(bundle)

    meta = payload["_precision_gate_meta"]
    assert len(meta["non_abandonment_checks"]) > 0
    assert any("blocked" in flag.lower() for flag in meta["non_abandonment_checks"])


def test_tcria_adapter_requires_audit_id() -> None:
    bad_bundle = {k: v for k, v in MINIMAL_BUNDLE.items() if k != "audit_id"}
    adapter = TCRIAAdapter(version="1.0")
    with pytest.raises(TCRIAAdapterError, match="audit_id"):
        adapter.to_execution_context_payload(bad_bundle)


def test_tcria_adapter_unsupported_version() -> None:
    with pytest.raises(TCRIAAdapterError, match="Unsupported"):
        TCRIAAdapter(version="99.0")


def test_tcria_adapter_hashes_are_stable() -> None:
    adapter = TCRIAAdapter(version="1.0")
    p1 = adapter.to_execution_context_payload(MINIMAL_BUNDLE)
    p2 = adapter.to_execution_context_payload(MINIMAL_BUNDLE)

    # SHA of the same input should always be the same
    assert p1["_precision_gate_meta"]["input_sha256"] == p2["_precision_gate_meta"]["input_sha256"]
