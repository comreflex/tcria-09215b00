from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from generate_case_preparation_summary import compute_case_readiness
from generate_case_timeline import build_timeline_entries
from tcria.engine import TCRIAEngine


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = REPO_ROOT / "benchmarks" / "stf_inq_4436"
BENCHMARK_PATH = BENCHMARK_DIR / "benchmark.json"


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().upper()


@pytest.fixture(scope="module")
def benchmark_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict, dict, dict]:
    manifest = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    source_path = BENCHMARK_DIR / manifest["source"]["path"]
    out_dir = tmp_path_factory.mktemp("stf-inq-4436-benchmark")

    engine = TCRIAEngine(repo_root=REPO_ROOT)
    result = engine.run_audit(
        input_path=str(source_path),
        strict=True,
        out_dir=out_dir,
        output_stem="stf_inq_4436_benchmark",
        include_pdf=False,
    )
    return manifest, result["bundle"], result["artifacts"]


def test_stf_inq_4436_preserves_and_governs_complex_decision(benchmark_run: tuple[dict, dict, dict]) -> None:
    manifest, bundle, artifacts = benchmark_run
    expected = manifest["tcria_contract"]
    source_path = BENCHMARK_DIR / manifest["source"]["path"]

    assert source_path.stat().st_size == manifest["source"]["size_bytes"]
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == manifest["source"]["sha256"]
    assert bundle["total_files_scanned"] == expected["total_files_scanned"]
    assert bundle["accusation_set_count"] == expected["accusation_set_count"]
    assert bundle["accusation_set"] == []
    assert len(bundle["non_accusation_set"]) == 1
    assert Path(artifacts["json"]).exists()
    assert Path(artifacts["markdown"]).exists()

    record = bundle["non_accusation_set"][0]
    intent = record["interpretation"]["document_intent"]
    route = record["interpretation"]["route_selection"]
    role = record["interpretation"]["document_role"]
    gates = record["gates"]
    signals = record["key_signals"]

    assert record["sha256"] == manifest["source"]["sha256"]
    assert record["extraction_status"] == expected["extraction_status"]
    assert record["extraction_method"] == expected["extraction_method"]
    assert record["text_quality"] == expected["text_quality"]
    assert record["text_chars"] >= expected["minimum_text_chars"]
    assert record["classification"] == expected["classification"]
    assert record["artifact_type"] == expected["artifact_type"]
    assert record["raises_accusation"] is expected["raises_accusation"]
    assert record["overall_outcome"] == expected["overall_outcome"]
    assert role["value"] == expected["document_role"]
    assert route["selected_route"] == expected["selected_route"]
    assert intent["document_kind"] == expected["document_kind"]
    assert intent["promotion_reason_code"] == expected["promotion_reason_code"]
    assert gates["prescriptiveGate"]["status"] == expected["prescriptive_gate_status"]
    assert gates["complianceGate"]["status"] == expected["compliance_gate_status"]
    assert gates["traceabilityCheck"]["status"] == expected["traceability_status"]
    assert signals["dates_found"] >= expected["minimum_dates_found"]
    assert signals["currency_values_found"] >= expected["minimum_currency_values_found"]

    source_text = _normalized_text(record["document"]["text"])
    for marker in expected["required_text_markers"]:
        assert _normalized_text(marker) in source_text


def test_stf_inq_4436_empty_accusatory_portal_is_not_information_loss(
    benchmark_run: tuple[dict, dict, dict],
) -> None:
    manifest, bundle, _ = benchmark_run
    record = bundle["non_accusation_set"][0]

    assert record["key_signals"]["dates_found"] >= manifest["tcria_contract"]["minimum_dates_found"]
    assert record["key_signals"]["currency_values_found"] >= manifest["tcria_contract"]["minimum_currency_values_found"]
    assert record["gates"]["traceabilityCheck"]["status"] == "PASS"

    # Complementary portals intentionally project accusation_set only. The
    # decision remains fully preserved in non_accusation_set.
    assert build_timeline_entries(bundle, top_k=30) == []
    assert compute_case_readiness(bundle["accusation_set"], {"blocked_artifacts_review": []}) == "low"
    assert len(record["document"]["text"]) >= manifest["tcria_contract"]["minimum_text_chars"]
