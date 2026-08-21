from __future__ import annotations

import hmac
import json
import os
import re
import stat
import subprocess
import tempfile
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from tcria.engine import TCRIAEngine
from tcria.ingestion import load_documents_secure

HANDOFF_SCHEMA_VERSION = "uoms.handoff.v1"
STAGE_NAME = "tcria"
NEXT_STAGE_NAME = "quinta_ordem"
SOURCE_REPOSITORY = "batt1984rodrigo-del/tcria-09215b00"
ATTESTATION_KEY_ID = "tcria-handoff-v1"
ATTESTATION_ENV = "UOMS_TCRIA_HANDOFF_KEY"
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_OUTPUT_STEM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")


class HandoffError(RuntimeError):
    """Raised when a TCRIA stage cannot be closed without weakening custody."""


def run_tcria_handoff(
    *,
    input_paths: list[str],
    custody_root: str | Path,
    run_id: str,
    strict: bool = True,
    include_pdf: bool = True,
    output_stem: str = "tcria_audit",
    producer_commit: str | None = None,
    attestation_key: str | bytes | None = None,
    max_files: int = 1_000,
    max_total_bytes: int = 256 * 1024 * 1024,
    engine: TCRIAEngine | None = None,
) -> dict[str, Any]:
    """Run TCRIA and publish its closed, hash-bound handoff manifest.

    Native TCRIA artifacts remain unchanged. This function only adds the
    operational OPEN/OUTPUT/CLOSE envelope needed by the next auditor.
    """

    safe_run_id = _validate_run_id(run_id)
    safe_output_stem = _validate_output_stem(output_stem)
    source_commit = _producer_commit(producer_commit)
    signing_key = _attestation_key(attestation_key)
    resolved_inputs = _resolve_inputs(input_paths)
    _validate_input_budget(max_files=max_files, max_total_bytes=max_total_bytes)
    try:
        verified_documents = load_documents_secure(
            [str(path) for path in resolved_inputs],
            max_files=max_files,
            max_total_bytes=max_total_bytes,
            reject_archives=True,
        )
    except (OSError, ValueError) as exc:
        raise HandoffError(str(exc)) from exc
    resolved_custody = _prepare_custody_root(Path(custody_root))
    stage_root = resolved_custody / safe_run_id / STAGE_NAME
    _assert_output_separate(stage_root, resolved_inputs)
    _create_stage_root(resolved_custody, safe_run_id)

    outputs_root = stage_root / "outputs"
    lifecycle_path = stage_root / "lifecycle.jsonl"
    outputs_root.mkdir(mode=0o700)
    opened_at = _timestamp()
    _append_event(lifecycle_path, "OPEN", opened_at, run_id=safe_run_id)

    audit_engine = engine or TCRIAEngine()
    try:
        _append_event(lifecycle_path, "RUNNING", _timestamp(), run_id=safe_run_id)
        result = audit_engine.run_audit(
            input_paths=[str(path) for path in resolved_inputs],
            strict=strict,
            out_dir=outputs_root,
            output_stem=safe_output_stem,
            include_pdf=include_pdf,
            max_files=max_files,
            max_total_bytes=max_total_bytes,
            preloaded_documents=verified_documents,
        )
        bundle = _require_mapping(result.get("bundle"), "bundle")
        artifact_paths = _require_mapping(result.get("artifacts"), "artifacts")

        originals = _original_entries(bundle)
        artifacts = _artifact_entries(artifact_paths, output_root=outputs_root)
        primary = next(
            (entry for entry in artifacts if entry["role"] == "tcria.native.audit_json"),
            None,
        )
        if primary is None:
            raise HandoffError("TCRIA did not publish its native audit JSON artifact.")

        _append_event(
            lifecycle_path,
            "OUTPUT",
            _timestamp(),
            run_id=safe_run_id,
            artifact_count=len(artifacts),
        )
        closed_at = _timestamp()
        _append_event(lifecycle_path, "CLOSE", closed_at, run_id=safe_run_id)
        lifecycle_entry = _file_entry(lifecycle_path, role="tcria.lifecycle")

        manifest = {
            "schema_version": HANDOFF_SCHEMA_VERSION,
            "run_id": safe_run_id,
            "stage": STAGE_NAME,
            "state": "closed",
            "opened_at": opened_at,
            "closed_at": closed_at,
            "producer": {
                "repository": SOURCE_REPOSITORY,
                "commit": source_commit,
            },
            "predecessor": None,
            "originals": originals,
            "artifacts": artifacts,
            "primary_artifact": primary,
            "lifecycle": lifecycle_entry,
            "next_stage": NEXT_STAGE_NAME,
            "next_stage_open_allowed": True,
        }
        manifest["attestation"] = _attest_manifest(
            manifest,
            signing_key,
            key_id=ATTESTATION_KEY_ID,
        )
        manifest_path = stage_root / "handoff.json"
        _atomic_write_json(manifest_path, manifest)
        return {
            "run_id": safe_run_id,
            "stage": STAGE_NAME,
            "state": "closed",
            "manifest_path": str(manifest_path),
            "manifest_sha256": _sha256_file(manifest_path),
            "artifact_count": len(artifacts),
            "original_count": len(originals),
        }
    except Exception as exc:
        _append_event(
            lifecycle_path,
            "HALT",
            _timestamp(),
            run_id=safe_run_id,
            reason=type(exc).__name__,
        )
        if isinstance(exc, HandoffError):
            raise
        raise HandoffError(f"TCRIA stage halted: {type(exc).__name__}.") from exc


def _resolve_inputs(values: list[str]) -> list[Path]:
    if not values:
        raise HandoffError("At least one input path is required.")
    if len(values) > 20:
        raise HandoffError("At most 20 input roots are allowed per UOMS run.")
    try:
        return [Path(value).expanduser().resolve(strict=True) for value in values]
    except OSError as exc:
        raise HandoffError("An input path does not exist or cannot be resolved.") from exc


def _validate_input_budget(*, max_files: int, max_total_bytes: int) -> None:
    if not 1 <= max_files <= 10_000:
        raise HandoffError("max_files must be between 1 and 10000.")
    if not 1 <= max_total_bytes <= 2 * 1024 * 1024 * 1024:
        raise HandoffError("max_total_bytes must be between 1 byte and 2 GiB.")


def _prepare_custody_root(value: Path) -> Path:
    path = value.expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
        resolved = path.resolve(strict=True)
        descriptor = os.open(
            resolved,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise HandoffError("Configured custody root is not a directory.")
        finally:
            os.close(descriptor)
        return resolved
    except OSError as exc:
        raise HandoffError("Configured custody root cannot be opened safely.") from exc


def _create_stage_root(custody_root: Path, run_id: str) -> None:
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    root_fd = os.open(custody_root, directory_flags | nofollow)
    try:
        try:
            os.mkdir(run_id, mode=0o700, dir_fd=root_fd)
        except FileExistsError as exc:
            raise HandoffError(
                f"TCRIA stage already exists and will not be overwritten: "
                f"{custody_root / run_id / STAGE_NAME}"
            ) from exc
        run_fd = os.open(run_id, directory_flags | nofollow, dir_fd=root_fd)
        try:
            run_metadata = os.fstat(run_fd)
            if run_metadata.st_uid != os.geteuid() or stat.S_IMODE(run_metadata.st_mode) != 0o700:
                raise HandoffError("New custody run directory has unsafe ownership or mode.")
            os.mkdir(STAGE_NAME, mode=0o700, dir_fd=run_fd)
            stage_fd = os.open(STAGE_NAME, directory_flags | nofollow, dir_fd=run_fd)
            try:
                stage_metadata = os.fstat(stage_fd)
                if (
                    stage_metadata.st_uid != os.geteuid()
                    or stat.S_IMODE(stage_metadata.st_mode) != 0o700
                ):
                    raise HandoffError("New TCRIA stage directory has unsafe ownership or mode.")
            finally:
                os.close(stage_fd)
        finally:
            os.close(run_fd)
    finally:
        os.close(root_fd)

    stage_root = (custody_root / run_id / STAGE_NAME).resolve(strict=True)
    if not stage_root.is_relative_to(custody_root):
        raise HandoffError("TCRIA stage escaped the configured custody root.")


def _assert_output_separate(stage_root: Path, inputs: list[Path]) -> None:
    resolved_stage = stage_root.resolve(strict=False)
    for source in inputs:
        protected = source if source.is_dir() else source.parent
        if resolved_stage == protected or resolved_stage.is_relative_to(protected):
            raise HandoffError(
                f"Custody output must be outside the original input root: {protected}"
            )


def _original_entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for collection in ("accusation_set", "non_accusation_set"):
        records = bundle.get(collection)
        if not isinstance(records, list):
            raise HandoffError(f"TCRIA bundle field {collection!r} must be a list.")
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise HandoffError(f"{collection}[{index}] must be an object.")
            document = record.get("document")
            if not isinstance(document, dict):
                raise HandoffError(f"{collection}[{index}].document must be an object.")
            raw_path = document.get("path") or record.get("file_path")
            declared_hash = document.get("sha256") or record.get("sha256")
            if not isinstance(raw_path, str) or not raw_path:
                raise HandoffError(f"{collection}[{index}] has no original path.")
            if not isinstance(declared_hash, str) or len(declared_hash) != 64:
                raise HandoffError(f"{collection}[{index}] has no valid SHA-256 identity.")
            path = Path(raw_path).expanduser().resolve(strict=True)
            if not path.is_file():
                raise HandoffError(f"Original is not a regular file: {path}")
            actual_hash = _sha256_file(path)
            if actual_hash != declared_hash.lower():
                raise HandoffError(f"Original hash changed before TCRIA CLOSE: {path}")
            key = (str(path), actual_hash)
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                {
                    "path": str(path),
                    "sha256": actual_hash,
                    "size_bytes": path.stat().st_size,
                    "role": "original.document",
                }
            )
    if not entries:
        raise HandoffError("TCRIA produced no identifiable original documents.")
    return entries


def _artifact_entries(
    artifacts: dict[str, Any],
    *,
    output_root: Path,
) -> list[dict[str, Any]]:
    roles = {
        "json": "tcria.native.audit_json",
        "markdown": "tcria.native.audit_markdown",
        "pdf": "tcria.native.audit_pdf",
        "institutional_markdown": "tcria.native.institutional_markdown",
    }
    entries: list[dict[str, Any]] = []
    for key, raw_path in sorted(artifacts.items()):
        if not isinstance(raw_path, str):
            raise HandoffError(f"TCRIA artifact path {key!r} must be a string.")
        entry = _file_entry(Path(raw_path), role=roles.get(key, f"tcria.native.{key}"))
        if not Path(entry["path"]).is_relative_to(output_root):
            raise HandoffError("TCRIA native artifact escaped its stage output root.")
        entries.append(entry)
    return entries


def _file_entry(path: Path, *, role: str) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise HandoffError(f"Artifact is not a regular file: {resolved}")
    return {
        "path": str(resolved),
        "sha256": _sha256_file(resolved),
        "size_bytes": resolved.stat().st_size,
        "role": role,
    }


def _append_event(path: Path, event: str, timestamp: str, **details: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"event": event, "timestamp": timestamp, **details}
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise HandoffError("Lifecycle destination is not a regular file.")
        os.write(
            descriptor,
            (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode(),
        )
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _attestation_key(explicit: str | bytes | None) -> bytes:
    value = explicit if explicit is not None else os.getenv(ATTESTATION_ENV, "")
    key = value.encode() if isinstance(value, str) else value
    if not isinstance(key, bytes) or len(key) < 32:
        raise HandoffError(f"{ATTESTATION_ENV} must contain at least 32 bytes.")
    return key


def _attest_manifest(payload: dict[str, Any], key: bytes, *, key_id: str) -> dict[str, str]:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "algorithm": "hmac-sha256",
        "key_id": key_id,
        "value": hmac.digest(key, canonical.encode(), "sha256").hex(),
    }


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_commit() -> str:
    configured = os.getenv("TCRIA_SOURCE_COMMIT", "").strip()
    if configured:
        return configured
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[1],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=Path(__file__).resolve().parents[1],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "UNSEALED"
    if dirty.stdout.strip():
        return "UNSEALED"
    return completed.stdout.strip() or "UNSEALED"


def _producer_commit(explicit: str | None) -> str:
    value = (explicit or _source_commit()).strip().lower()
    if not _COMMIT.fullmatch(value):
        raise HandoffError("TCRIA producer commit must be an exact hexadecimal Git commit.")
    return value


def _validate_run_id(value: str) -> str:
    if not isinstance(value, str) or not _RUN_ID.fullmatch(value):
        raise HandoffError("run_id must contain only letters, numbers, dot, underscore or dash.")
    return value


def _validate_output_stem(value: str) -> str:
    if not isinstance(value, str) or not _OUTPUT_STEM.fullmatch(value):
        raise HandoffError(
            "output_stem must contain only letters, numbers, dot, underscore or dash."
        )
    return value


def _require_mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HandoffError(f"TCRIA result field {name!r} must be an object.")
    return value


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")
