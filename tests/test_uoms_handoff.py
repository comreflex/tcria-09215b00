from __future__ import annotations

import json
import os
import zipfile
from hashlib import sha256
from pathlib import Path

import pytest

from tcria.engine import TCRIAEngine
from tcria.handoff import HandoffError, run_tcria_handoff

ATTESTATION_KEY = "tcria-test-attestation-key-000000000000"


def _decision_record(path: Path) -> None:
    path.write_text(
        "[TCR-IA DECISION RECORD]\n"
        "responsibleHuman: Test Owner\n"
        "declaredPurpose: Controlled handoff verification\n"
        "approved: YES\n"
        "[/TCR-IA DECISION RECORD]\n\n"
        "Registro administrativo com data 05/03/2026 e evidência anexada.",
        encoding="utf-8",
    )


def test_tcria_handoff_closes_only_after_native_artifacts_are_hashed(tmp_path: Path) -> None:
    source = tmp_path / "evidence" / "record.txt"
    source.parent.mkdir()
    _decision_record(source)
    custody = tmp_path / "custody"

    result = run_tcria_handoff(
        input_paths=[str(source)],
        custody_root=custody,
        run_id="run-001",
        include_pdf=False,
        producer_commit="a" * 40,
        attestation_key=ATTESTATION_KEY,
        engine=TCRIAEngine(repo_root=Path(__file__).resolve().parents[1]),
    )

    manifest_path = Path(result["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["state"] == "closed"
    assert manifest["stage"] == "tcria"
    assert manifest["predecessor"] is None
    assert manifest["next_stage"] == "quinta_ordem"
    assert manifest["originals"][0]["sha256"] == sha256(source.read_bytes()).hexdigest()
    assert manifest["primary_artifact"]["role"] == "tcria.native.audit_json"
    assert manifest["attestation"]["key_id"] == "tcria-handoff-v1"
    lifecycle = Path(manifest["lifecycle"]["path"]).read_text(encoding="utf-8")
    assert [json.loads(line)["event"] for line in lifecycle.splitlines()] == [
        "OPEN",
        "RUNNING",
        "OUTPUT",
        "CLOSE",
    ]


def test_tcria_handoff_never_overwrites_an_existing_stage(tmp_path: Path) -> None:
    source = tmp_path / "evidence" / "record.txt"
    source.parent.mkdir()
    _decision_record(source)
    custody = tmp_path / "custody"
    kwargs = {
        "input_paths": [str(source)],
        "custody_root": custody,
        "run_id": "same-run",
        "include_pdf": False,
        "producer_commit": "a" * 40,
        "attestation_key": ATTESTATION_KEY,
        "engine": TCRIAEngine(repo_root=Path(__file__).resolve().parents[1]),
    }
    run_tcria_handoff(**kwargs)

    with pytest.raises(HandoffError, match="will not be overwritten"):
        run_tcria_handoff(**kwargs)


def test_tcria_handoff_rejects_output_inside_original_root(tmp_path: Path) -> None:
    source_root = tmp_path / "evidence"
    source_root.mkdir()
    source = source_root / "record.txt"
    _decision_record(source)

    with pytest.raises(HandoffError, match="outside the original input root"):
        run_tcria_handoff(
            input_paths=[str(source_root)],
            custody_root=source_root / "custody",
            run_id="unsafe",
            include_pdf=False,
            producer_commit="a" * 40,
            attestation_key=ATTESTATION_KEY,
        )


def test_tcria_handoff_rejects_a_path_like_output_stem_before_open(tmp_path: Path) -> None:
    source = tmp_path / "record.txt"
    _decision_record(source)
    custody = tmp_path / "custody"

    with pytest.raises(HandoffError, match="output_stem"):
        run_tcria_handoff(
            input_paths=[str(source)],
            custody_root=custody,
            run_id="unsafe-stem",
            output_stem="../escaped",
            include_pdf=False,
            producer_commit="a" * 40,
            attestation_key=ATTESTATION_KEY,
        )

    assert not (custody / "unsafe-stem" / "tcria").exists()


def test_tcria_handoff_rejects_archives_before_open(tmp_path: Path) -> None:
    source = tmp_path / "evidence" / "archive.zip"
    source.parent.mkdir()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("record.txt", "bounded fixture")
    custody = tmp_path / "custody"

    with pytest.raises(HandoffError, match="ZIP archives"):
        run_tcria_handoff(
            input_paths=[str(source)],
            custody_root=custody,
            run_id="archive",
            include_pdf=False,
            producer_commit="a" * 40,
            attestation_key=ATTESTATION_KEY,
        )

    assert not (custody / "archive" / "tcria").exists()


def test_tcria_handoff_consumes_the_bytes_verified_before_open(tmp_path: Path) -> None:
    source_root = tmp_path / "evidence"
    source_root.mkdir()
    source = source_root / "record.txt"
    _decision_record(source)

    class MutatingEngine(TCRIAEngine):
        def run_audit(self, *args: object, **kwargs: object) -> dict[str, object]:
            with zipfile.ZipFile(source_root / "late.zip", "w") as archive:
                archive.writestr("late.txt", "must not enter the verified snapshot")
            return super().run_audit(*args, **kwargs)

    result = run_tcria_handoff(
        input_paths=[str(source_root)],
        custody_root=tmp_path / "custody",
        run_id="snapshot",
        include_pdf=False,
        producer_commit="a" * 40,
        attestation_key=ATTESTATION_KEY,
        engine=MutatingEngine(repo_root=Path(__file__).resolve().parents[1]),
    )

    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert [entry["path"] for entry in manifest["originals"]] == [str(source)]


def test_tcria_handoff_rejects_a_symlinked_run_directory(tmp_path: Path) -> None:
    source = tmp_path / "evidence" / "record.txt"
    source.parent.mkdir()
    _decision_record(source)
    custody = tmp_path / "custody"
    custody.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, custody / "redirected")

    with pytest.raises(HandoffError, match="will not be overwritten"):
        run_tcria_handoff(
            input_paths=[str(source)],
            custody_root=custody,
            run_id="redirected",
            include_pdf=False,
            producer_commit="a" * 40,
            attestation_key=ATTESTATION_KEY,
        )

    assert not (outside / "tcria").exists()
