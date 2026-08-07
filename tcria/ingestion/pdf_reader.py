from __future__ import annotations

from io import BytesIO
from pathlib import Path
import unicodedata


_ALLOWED_CONTROL_CHARACTERS = {"\n", "\r", "\t"}
_MAX_NON_TEXT_RATIO = 0.10


def _non_text_ratio(text: str) -> float:
    """Return the share of extracted characters that are not usable text.

    PDF extraction can technically succeed while returning font-map/control glyphs
    instead of readable text.  The original bytes and extracted string are preserved;
    this metric only decides whether semantic processing may continue.
    """

    if not text:
        return 0.0
    non_text = sum(
        1
        for character in text
        if character not in _ALLOWED_CONTROL_CHARACTERS
        and unicodedata.category(character).startswith("C")
    )
    return non_text / len(text)


def _extracted_text_is_unusable(text: str) -> bool:
    return bool(text) and _non_text_ratio(text) > _MAX_NON_TEXT_RATIO


def _extract_pdf_text(source: str | BytesIO, method: str) -> tuple[str, str, str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return "", "error", "pypdf_missing"

    try:
        reader = PdfReader(source)
    except Exception:
        return "", "error", "pypdf_open_error"

    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")

    text = "\n".join(pages)
    if _extracted_text_is_unusable(text):
        # Fail closed for semantic analysis without rewriting or discarding what
        # pypdf extracted.  Upstream custody still hashes the untouched PDF bytes.
        return text, "unreadable", f"{method}:text-quality-gate"
    return text, "ok", method


def extract_pdf_text(path: Path) -> tuple[str, str, str]:
    return _extract_pdf_text(str(path), "pypdf")


def extract_pdf_text_from_bytes(raw: bytes) -> tuple[str, str, str]:
    return _extract_pdf_text(BytesIO(raw), "pypdf-bytes")
