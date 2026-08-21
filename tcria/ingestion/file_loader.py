from __future__ import annotations

import hashlib
import os
import stat
import zipfile
from io import BytesIO
from pathlib import Path

from tcria.ingestion.docx_reader import extract_docx_text, extract_docx_text_from_bytes
from tcria.ingestion.html_reader import extract_html_text
from tcria.ingestion.pdf_reader import extract_pdf_text, extract_pdf_text_from_bytes
from tcria.ingestion.xlsx_reader import extract_xlsx_text, extract_xlsx_text_from_bytes
from tcria.models import Document

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt", ".md", ".csv", ".html", ".htm", ".zip", ".xlsx"}
ARCHIVE_ENTRY_SUFFIXES = {".pdf", ".docx", ".txt", ".md", ".csv", ".html", ".htm", ".zip", ".xlsx"}


def _decode_text(raw: bytes) -> tuple[str, str]:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("latin1", errors="replace"), "latin1-replace"


def _extract_text(path: Path) -> tuple[str, str, str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_text(path)
    if suffix == ".docx":
        return extract_docx_text(path)
    if suffix == ".xlsx":
        return extract_xlsx_text(path)
    if suffix in {".html", ".htm"}:
        return extract_html_text(path.read_bytes())
    if suffix in {".txt", ".md", ".csv"}:
        text, encoding = _decode_text(path.read_bytes())
        return text, "ok", encoding
    return "", "unsupported", "none"


def _extract_text_from_bytes(raw: bytes, suffix: str) -> tuple[str, str, str]:
    if suffix == ".pdf":
        return extract_pdf_text_from_bytes(raw)
    if suffix == ".docx":
        return extract_docx_text_from_bytes(raw)
    if suffix == ".xlsx":
        return extract_xlsx_text_from_bytes(raw)
    if suffix in {".html", ".htm"}:
        return extract_html_text(raw)
    if suffix in {".txt", ".md", ".csv"}:
        text, encoding = _decode_text(raw)
        return text, "ok", encoding
    return "", "unsupported", "none"


def _iter_supported_files(root: Path, max_files: int | None = None) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in SUPPORTED_SUFFIXES else []
    files: list[Path] = []
    for child in sorted(root.rglob("*")):
        if child.is_symlink():
            continue
        if child.is_file() and child.suffix.lower() in SUPPORTED_SUFFIXES:
            files.append(child)
            if max_files is not None and len(files) > max_files:
                raise ValueError(f"Input exceeds max_files={max_files}.")
    return files


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_documents_from_zip(path: Path) -> list[Document]:
    return _load_documents_from_zip_raw(path.read_bytes(), path.name, path)


def _load_documents_from_zip_raw(raw_zip: bytes, label: str, source_path: Path | None = None) -> list[Document]:
    documents: list[Document] = []
    with zipfile.ZipFile(BytesIO(raw_zip)) as zf:
        for info in sorted(zf.infolist(), key=lambda item: item.filename.lower()):
            if info.is_dir():
                continue
            suffix = Path(info.filename).suffix.lower()
            if suffix not in ARCHIVE_ENTRY_SUFFIXES:
                continue
            raw = zf.read(info)
            if suffix == ".zip":
                nested_label = f"{label}/{info.filename}"
                documents.extend(_load_documents_from_zip_raw(raw, nested_label, source_path))
                continue
            text, extraction_status, extraction_method = _extract_text_from_bytes(raw, suffix)
            base_path = source_path if source_path is not None else Path(label)
            virtual_path = Path(f"{base_path}!/{info.filename}")
            documents.append(
                Document(
                    path=virtual_path,
                    relative_path=f"{label}/{info.filename}",
                    suffix=suffix,
                    size_bytes=info.file_size,
                    sha256=_sha256_bytes(raw),
                    text=text,
                    extraction_status=extraction_status,
                    extraction_method=f"zip:{extraction_method}",
                )
            )
    return documents


def load_documents(
    input_path: str,
    *,
    max_files: int | None = None,
    max_total_bytes: int | None = None,
) -> list[Document]:
    root = Path(input_path).expanduser().resolve()
    if not root.exists():
        raise ValueError(f"Input path does not exist: {root}")
    if not root.is_file() and not root.is_dir():
        raise ValueError(f"Input path must be a file or directory: {root}")
    if max_files is not None and max_files <= 0:
        raise ValueError("max_files must be greater than zero.")
    if max_total_bytes is not None and max_total_bytes <= 0:
        raise ValueError("max_total_bytes must be greater than zero.")

    files = _iter_supported_files(root, max_files=max_files)
    documents: list[Document] = []
    total_bytes = 0
    for fp in files:
        file_documents: list[Document]
        bytes_accounted = False
        if fp.suffix.lower() == ".zip":
            file_documents = _load_documents_from_zip(fp)
        else:
            declared_size = fp.stat().st_size
            if max_total_bytes is not None and total_bytes + declared_size > max_total_bytes:
                raise ValueError(f"Input exceeds max_total_bytes={max_total_bytes}.")
            raw = fp.read_bytes()
            size_bytes = len(raw)
            total_bytes += size_bytes
            bytes_accounted = True
            if max_total_bytes is not None and total_bytes > max_total_bytes:
                raise ValueError(f"Input exceeds max_total_bytes={max_total_bytes}.")
            text, extraction_status, extraction_method = _extract_text_from_bytes(
                raw, fp.suffix.lower()
            )
            rel = str(fp.relative_to(root)) if root.is_dir() else fp.name
            file_documents = [
                Document(
                    path=fp,
                    relative_path=rel,
                    suffix=fp.suffix.lower(),
                    size_bytes=size_bytes,
                    sha256=_sha256_bytes(raw),
                    text=text,
                    extraction_status=extraction_status,
                    extraction_method=extraction_method,
                )
            ]

        for doc in file_documents:
            if not bytes_accounted:
                total_bytes += doc.size_bytes
                if max_total_bytes is not None and total_bytes > max_total_bytes:
                    raise ValueError(f"Input exceeds max_total_bytes={max_total_bytes}.")
            documents.append(doc)
            if max_files is not None and len(documents) > max_files:
                raise ValueError(f"Input exceeds max_files={max_files}.")
    return documents


def load_documents_secure(
    input_paths: list[str],
    *,
    max_files: int,
    max_total_bytes: int,
    reject_archives: bool = True,
) -> list[Document]:
    """Snapshot authorized files once through no-follow directory descriptors.

    This is the custody-boundary loader. The returned ``Document`` objects are
    built from the exact bytes that passed the aggregate limits, so a later
    filesystem mutation cannot alter what the engine evaluates.
    """

    if not input_paths:
        raise ValueError("At least one input path is required.")
    if max_files <= 0 or max_total_bytes <= 0:
        raise ValueError("Secure input limits must be greater than zero.")

    documents: list[Document] = []
    total_bytes = 0
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)

    def append_file(parent_fd: int | None, name: str, path: Path, relative: str) -> None:
        nonlocal total_bytes
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            return
        if suffix == ".zip" and reject_archives:
            raise ValueError(
                "ZIP archives are not accepted by the custody boundary; expand them in the "
                "authorized evidence area before OPEN."
            )
        if len(documents) + 1 > max_files:
            raise ValueError(f"Input exceeds max_files={max_files}.")

        flags = os.O_RDONLY | nofollow
        descriptor = os.open(name if parent_fd is not None else path, flags, dir_fd=parent_fd)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"Input is not a regular file: {path}")
            if total_bytes + metadata.st_size > max_total_bytes:
                raise ValueError(f"Input exceeds max_total_bytes={max_total_bytes}.")
            remaining = max_total_bytes - total_bytes
            chunks: list[bytes] = []
            captured = 0
            while True:
                chunk = os.read(descriptor, min(1024 * 1024, remaining - captured + 1))
                if not chunk:
                    break
                chunks.append(chunk)
                captured += len(chunk)
                if captured > remaining:
                    raise ValueError(f"Input exceeds max_total_bytes={max_total_bytes}.")
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)

        total_bytes += len(raw)
        if suffix == ".zip":
            archive_documents = _load_documents_from_zip_raw(raw, path.name, path)
            for document in archive_documents:
                if len(documents) + 1 > max_files:
                    raise ValueError(f"Input exceeds max_files={max_files}.")
                documents.append(document)
            return

        text, extraction_status, extraction_method = _extract_text_from_bytes(raw, suffix)
        documents.append(
            Document(
                path=path,
                relative_path=relative,
                suffix=suffix,
                size_bytes=len(raw),
                sha256=_sha256_bytes(raw),
                text=text,
                extraction_status=extraction_status,
                extraction_method=extraction_method,
            )
        )

    def walk(directory_fd: int, root: Path, relative_dir: Path) -> None:
        with os.scandir(directory_fd) as iterator:
            entries = sorted(iterator, key=lambda item: item.name)
        for entry in entries:
            relative = relative_dir / entry.name
            entry_path = root / relative
            metadata = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                continue
            if stat.S_ISDIR(metadata.st_mode):
                child_fd = os.open(entry.name, directory_flags | nofollow, dir_fd=directory_fd)
                try:
                    if not stat.S_ISDIR(os.fstat(child_fd).st_mode):
                        raise ValueError(f"Input changed during directory traversal: {entry_path}")
                    walk(child_fd, root, relative)
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(metadata.st_mode):
                append_file(directory_fd, entry.name, entry_path, str(relative))

    for input_path in input_paths:
        root = Path(input_path).expanduser().resolve(strict=True)
        root_fd = os.open(root, os.O_RDONLY | nofollow)
        try:
            root_metadata = os.fstat(root_fd)
            if stat.S_ISDIR(root_metadata.st_mode):
                walk(root_fd, root, Path())
            elif stat.S_ISREG(root_metadata.st_mode):
                os.close(root_fd)
                root_fd = -1
                append_file(None, "", root, root.name)
            else:
                raise ValueError(f"Input path must be a regular file or directory: {root}")
        finally:
            if root_fd >= 0:
                os.close(root_fd)

    if not documents:
        raise ValueError("No supported documents were found in the authorized input roots.")
    return documents
