from __future__ import annotations

import hashlib
from io import BytesIO

import pypdf

from tcria.ingestion import file_loader
from tcria.ingestion.pdf_reader import (
    _extract_pdf_text,
    _extracted_text_is_unusable,
    _non_text_ratio,
)


def test_readable_text_passes_quality_gate() -> None:
    text = "Documento legível com conteúdo normal.\nSegunda linha com números 123."

    assert _non_text_ratio(text) == 0.0
    assert _extracted_text_is_unusable(text) is False


def test_control_heavy_text_fails_quality_gate() -> None:
    text = ("\x01\x02\x03\x04" * 40) + "trecho legível"

    assert _non_text_ratio(text) > 0.10
    assert _extracted_text_is_unusable(text) is True


def test_pdf_reader_preserves_extracted_text_but_marks_it_unreadable(monkeypatch) -> None:
    corrupted = ("\x01\x02\x03" * 50) + "conteúdo residual"

    class FakePage:
        def extract_text(self) -> str:
            return corrupted

    class FakeReader:
        pages = [FakePage()]

    monkeypatch.setattr(pypdf, "PdfReader", lambda source: FakeReader())

    text, status, method = _extract_pdf_text(BytesIO(b"not-used-by-fake-reader"), "pypdf-bytes")

    assert text == corrupted
    assert status == "unreadable"
    assert method == "pypdf-bytes:text-quality-gate"


def test_quality_status_does_not_change_original_file_hash(tmp_path, monkeypatch) -> None:
    raw = b"original-pdf-bytes-remain-untouched"
    source = tmp_path / "sample.pdf"
    source.write_bytes(raw)
    corrupted = ("\x01\x02\x03" * 50) + "texto"

    monkeypatch.setattr(
        file_loader,
        "_extract_text",
        lambda path: (corrupted, "unreadable", "pypdf:text-quality-gate"),
    )

    [document] = file_loader.load_documents(str(source))

    assert source.read_bytes() == raw
    assert document.sha256 == hashlib.sha256(raw).hexdigest()
    assert document.text == corrupted
    assert document.extraction_status == "unreadable"
