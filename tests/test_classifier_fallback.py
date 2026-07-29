from __future__ import annotations

from pathlib import Path

from tcria.classification.artifact_classifier import classify_artifact
from tcria.models import Document


def test_high_severity_accusation_fallback_avoids_false_negative() -> None:
    document = Document(
        path=Path("/tmp/oficio_comprovante.txt"),
        relative_path="oficio_comprovante.txt",
        suffix=".txt",
        size_bytes=128,
        sha256="dummy",
        text=(
            "Oficio administrativo com comprovante anexo. "
            "Há denúncia formal de fraude não autorizado contra a empresa."
        ),
        extraction_status="ok",
        extraction_method="text",
    )
    signals = {
        "target_entity_hits": {"empresa": 1},
        "evidence_marker_hits": {"comprovante": 1},
    }

    classification, raises_accusation, reasons, _ = classify_artifact(document, signals)

    assert classification == "ACCUSATORY_CANDIDATE"
    assert raises_accusation is True
    assert any("fallback activated" in reason.lower() for reason in reasons)
