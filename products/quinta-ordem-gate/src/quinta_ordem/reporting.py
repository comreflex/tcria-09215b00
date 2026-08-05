from __future__ import annotations

import html
import os
import re
import shutil
import tempfile
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from urllib.parse import unquote, urlparse

from quinta_ordem.models import ExecutionContext, Finding, GateDecision
from quinta_ordem.serialization import dumps_json, to_jsonable

NOTICE = (
    "Artefato analítico derivado. Este relatório não modifica, substitui "
    "ou integra a evidência original."
)


class UnsafeOutputPathError(ValueError):
    """Raised when a report destination overlaps an original-evidence root."""


@dataclass(frozen=True)
class ReportBundle:
    root: Path
    json_report: Path
    markdown_report: Path
    point_reports: tuple[Path, ...]
    manifest: Path


def write_json_report(
    decision: GateDecision,
    output_dir: Path,
    *,
    context: ExecutionContext,
) -> Path:
    _validate_decision_context_identity(decision, context)
    output_dir = _prepare_output_dir(output_dir, context)
    path = output_dir / f"{_safe_component(decision.execution_id)}_quinta_ordem.json"
    payload = to_jsonable(decision)
    if not isinstance(payload, dict):  # pragma: no cover - GateDecision is a dataclass
        raise TypeError("GateDecision did not serialize to an object.")
    payload["notice"] = NOTICE
    payload["execution_context_sha256"] = _context_digest(context)
    _atomic_write_text(path, dumps_json(payload))
    return path


def write_markdown_report(
    decision: GateDecision,
    output_dir: Path,
    *,
    context: ExecutionContext,
) -> Path:
    _validate_decision_context_identity(decision, context)
    output_dir = _prepare_output_dir(output_dir, context)
    path = output_dir / f"{_safe_component(decision.execution_id)}_quinta_ordem.md"
    _atomic_write_text(path, _consolidated_markdown(decision, _context_digest(context)))
    return path


def write_point_reports(
    decision: GateDecision,
    output_dir: Path,
    *,
    context: ExecutionContext,
) -> list[Path]:
    _validate_decision_context_identity(decision, context)
    output_dir = _prepare_output_dir(output_dir, context)
    point_dir = _safe_subdirectory(output_dir, "points", context)
    paths: list[Path] = []
    context_digest = _context_digest(context)

    for index, finding in enumerate(decision.findings, start=1):
        path = point_dir / f"{index:03d}_{_safe_component(finding.point_id)}.md"
        _atomic_write_text(path, _point_markdown(decision, finding, context_digest))
        paths.append(path)

    return paths


def write_manifest(
    decision: GateDecision,
    report_paths: list[Path] | tuple[Path, ...],
    output_dir: Path,
    *,
    context: ExecutionContext,
) -> Path:
    _validate_decision_context_identity(decision, context)
    output_dir = _prepare_output_dir(output_dir, context)
    entries = []

    for path in sorted(report_paths, key=lambda item: item.as_posix()):
        resolved = path.resolve(strict=True)
        _assert_descendant(resolved, output_dir)
        data = resolved.read_bytes()
        relative_path = resolved.relative_to(output_dir).as_posix()
        entries.append(
            {
                "path": relative_path,
                "kind": _report_kind(relative_path),
                "media_type": _media_type(resolved),
                "size_bytes": len(data),
                "sha256": sha256(data).hexdigest(),
            }
        )

    payload = {
        "schema_version": "1.0",
        "execution_id": decision.execution_id,
        "execution_context_sha256": _context_digest(context),
        "algorithm": "sha256",
        "notice": NOTICE,
        "files": entries,
    }
    path = output_dir / f"{_safe_component(decision.execution_id)}_manifest.json"
    _atomic_write_text(path, dumps_json(payload))
    return path


def write_report_bundle(
    decision: GateDecision,
    context: ExecutionContext,
    output_root: Path,
) -> ReportBundle:
    """Atomically publish all derived reports and the manifest as the final file."""

    _validate_decision_context_identity(decision, context)
    output_root = _prepare_output_dir(output_root, context)
    bundle_name = _safe_component(decision.execution_id)
    final_root = output_root / bundle_name
    _assert_descendant(final_root.resolve(strict=False), output_root)
    _assert_no_evidence_overlap(final_root.resolve(strict=False), context)

    stage = Path(tempfile.mkdtemp(prefix=f".{bundle_name}-", dir=output_root))
    try:
        json_report = write_json_report(decision, stage, context=context)
        markdown_report = write_markdown_report(decision, stage, context=context)
        point_reports = write_point_reports(decision, stage, context=context)
        derived_reports = [json_report, markdown_report, *point_reports]
        manifest = write_manifest(decision, derived_reports, stage, context=context)

        relative_json = json_report.relative_to(stage)
        relative_markdown = markdown_report.relative_to(stage)
        relative_points = tuple(path.relative_to(stage) for path in point_reports)
        relative_manifest = manifest.relative_to(stage)

        if final_root.exists() or final_root.is_symlink():
            if (
                final_root.is_dir()
                and not final_root.is_symlink()
                and _trees_identical(stage, final_root)
            ):
                shutil.rmtree(stage)
                return ReportBundle(
                    root=final_root,
                    json_report=final_root / relative_json,
                    markdown_report=final_root / relative_markdown,
                    point_reports=tuple(final_root / path for path in relative_points),
                    manifest=final_root / relative_manifest,
                )
            raise FileExistsError(f"Different report bundle already exists: {final_root}")

        stage.rename(final_root)
        return ReportBundle(
            root=final_root,
            json_report=final_root / relative_json,
            markdown_report=final_root / relative_markdown,
            point_reports=tuple(final_root / path for path in relative_points),
            manifest=final_root / relative_manifest,
        )
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def _prepare_output_dir(
    output_dir: Path,
    context: ExecutionContext,
) -> Path:
    resolved = Path(output_dir).resolve(strict=False)
    for protected_root in _protected_evidence_roots(context):
        if _is_relative_to(resolved, protected_root):
            raise UnsafeOutputPathError(
                f"Report output overlaps protected evidence root: {protected_root}"
            )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _protected_evidence_roots(context: ExecutionContext) -> set[Path]:
    roots: set[Path] = set()
    if not isinstance(context.metadata, Mapping):
        raise UnsafeOutputPathError("context.metadata must be a mapping.")
    metadata_roots = context.metadata.get("evidence_roots", [])
    if not isinstance(metadata_roots, list):
        raise UnsafeOutputPathError("metadata.evidence_roots must be a list.")
    for value in metadata_roots:
        path = _local_path(value)
        if path is None:
            raise UnsafeOutputPathError(
                "Every metadata.evidence_roots item must be an absolute local path."
            )
        roots.add(path.resolve(strict=False))

    if not isinstance(context.evidence, list):
        raise UnsafeOutputPathError("context.evidence must be a list.")
    for item in context.evidence:
        if not isinstance(item, Mapping):
            raise UnsafeOutputPathError("Every evidence item must be a mapping.")
        declared_sources = [
            item.get(key) for key in ("source_path", "original_path", "path", "source")
        ]
        if not any(isinstance(value, str) and value.strip() for value in declared_sources):
            raise UnsafeOutputPathError("Every evidence item must declare its origin.")
        for key in ("source_path", "original_path", "path", "source"):
            raw_value = item.get(key)
            path = _local_path(raw_value)
            if path is None:
                if raw_value is not None and (key != "source" or not _is_nonlocal_uri(raw_value)):
                    raise UnsafeOutputPathError(
                        f"Evidence {key} must be an absolute local path when declared."
                    )
                continue
            resolved = path.resolve(strict=False)
            roots.add(resolved if resolved.is_dir() else resolved.parent)

    return roots


def _local_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = urlparse(value)
    if parsed.scheme.lower() == "file":
        return Path(unquote(parsed.path)) if parsed.path else None
    if parsed.scheme:
        return None
    path = Path(value)
    return path if path.is_absolute() else None


def _is_nonlocal_uri(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return bool(parsed.scheme and parsed.scheme.lower() != "file")


def _assert_descendant(path: Path, root: Path) -> None:
    if not _is_relative_to(path, root) or path == root:
        raise UnsafeOutputPathError(f"Derived path escapes output root: {path}")


def _safe_subdirectory(root: Path, name: str, context: ExecutionContext) -> Path:
    path = root / name
    if path.is_symlink():
        raise UnsafeOutputPathError(f"Derived directory cannot be a symlink: {path}")
    resolved = path.resolve(strict=False)
    _assert_descendant(resolved, root)
    for protected_root in _protected_evidence_roots(context):
        if _is_relative_to(resolved, protected_root):
            raise UnsafeOutputPathError(
                f"Derived directory overlaps protected evidence root: {protected_root}"
            )
    resolved.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.resolve(strict=True) != resolved:
        raise UnsafeOutputPathError(f"Derived directory changed during creation: {path}")
    return resolved


def _assert_no_evidence_overlap(path: Path, context: ExecutionContext) -> None:
    for protected_root in _protected_evidence_roots(context):
        if _is_relative_to(path, protected_root) or _is_relative_to(protected_root, path):
            raise UnsafeOutputPathError(
                f"Derived path overlaps protected evidence root: {protected_root}"
            )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_component(value: object, *, max_base_length: int = 48) -> str:
    raw = str(value)
    normalized = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", normalized).strip("-._")
    base = re.sub(r"[-_.]{2,}", "-", base)[:max_base_length].rstrip("-._")
    if not base:
        base = "item"
    digest = sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"{base}-{digest}"


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _consolidated_markdown(decision: GateDecision, context_digest: str) -> str:
    lines = [
        "# Quinta Ordem - Relatório Consolidado",
        "",
        f"**Execução:** {_md(decision.execution_id)}  ",
        f"**Status:** `{decision.status.value}`  ",
        f"**Confiança verificável:** `{decision.confidence:.4f}`  ",
        f"**SHA-256 do ExecutionContext:** `{context_digest}`  ",
        f"**Revisão humana necessária:** {'sim' if decision.human_review_required else 'não'}",
        "",
        "## Dimensões verificadas",
        "",
        "| Dimensão | Pontuação |",
        "| --- | ---: |",
    ]
    for name, value in decision.breakdown.as_dict().items():
        lines.append(f"| {_md(name)} | `{value:.4f}` |")

    lines.extend(
        [
            "",
            "**Verificadores executados:** "
            + (", ".join(f"`{_md(name)}`" for name in decision.evaluated_verifiers) or "nenhum"),
            "",
            "## Findings",
            "",
        ]
    )

    if not decision.findings:
        lines.append("Nenhum finding registrado.")
    else:
        for index, finding in enumerate(decision.findings, start=1):
            lines.extend(_finding_markdown(index, finding))

    lines.extend(["", "## Incertezas remanescentes", ""])
    if decision.remaining_uncertainties:
        lines.extend(f"- {_md(item)}" for item in decision.remaining_uncertainties)
    else:
        lines.append("Nenhuma incerteza remanescente registrada.")

    lines.extend(["", "## Observação de integridade", "", NOTICE, ""])
    return "\n".join(lines)


def _point_markdown(
    decision: GateDecision,
    finding: Finding,
    context_digest: str,
) -> str:
    lines = [
        "# Quinta Ordem - Registro de Decisão",
        "",
        f"**Execução:** {_md(decision.execution_id)}  ",
        f"**SHA-256 do ExecutionContext:** `{context_digest}`  ",
        f"**Ponto:** {_md(finding.point_id)}  ",
        f"**Verificador:** `{_md(finding.verifier)}`  ",
        f"**Código:** `{_md(finding.code)}`  ",
        f"**Severidade:** `{finding.severity.value}`",
        "",
        "## Decisão do ponto",
        "",
        _md(finding.message),
        "",
        "## Referências",
        "",
    ]
    lines.extend(_evidence_reference_lines(finding))
    lines.extend(
        [
            "",
            "## Encaminhamento",
            "",
            f"- **Retornar para:** {_md(finding.return_to or 'não aplicável')}",
            f"- **Ação necessária:** {_md(finding.required_action or 'nenhuma ação específica')}",
            "",
            "## Detalhes",
            "",
            *_indented_json(finding.details),
            "",
            "## Observação de integridade",
            "",
            NOTICE,
            "",
        ]
    )
    return "\n".join(lines)


def _finding_markdown(index: int, finding: Finding) -> list[str]:
    lines = [
        f"### {index}. `{_md(finding.code)}`",
        "",
        f"- **Ponto:** {_md(finding.point_id)}",
        f"- **Verificador:** `{_md(finding.verifier)}`",
        f"- **Severidade:** `{finding.severity.value}`",
        f"- **Mensagem:** {_md(finding.message)}",
        f"- **Retornar para:** {_md(finding.return_to or 'não aplicável')}",
        f"- **Ação necessária:** {_md(finding.required_action or 'nenhuma ação específica')}",
        "- **Referências:**",
    ]
    lines.extend(f"  {line}" for line in _evidence_reference_lines(finding))
    lines.extend(["- **Detalhes:**", *_indented_json(finding.details, prefix="  "), ""])
    return lines


def _evidence_reference_lines(finding: Finding) -> list[str]:
    if not finding.evidence_refs:
        return ["- nenhuma referência declarada"]
    lines = []
    for ref in finding.evidence_refs:
        suffix = f"; sha256={_md(ref.sha256)}" if ref.sha256 else ""
        lines.append(f"- {_md(ref.artifact_id)}{suffix}")
    return lines


def _indented_json(value: object, *, prefix: str = "") -> list[str]:
    serialized = dumps_json(value).rstrip("\n")
    return [f"{prefix}    {line}" for line in serialized.splitlines()]


def _md(value: object) -> str:
    flattened = " ".join(str(value).splitlines())
    escaped_html = html.escape(flattened, quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>\-])", r"\\\1", escaped_html)


def _report_kind(relative_path: str) -> str:
    if relative_path.startswith("points/"):
        return "finding_markdown"
    if relative_path.endswith(".json"):
        return "consolidated_json"
    return "consolidated_markdown"


def _media_type(path: Path) -> str:
    return "application/json" if path.suffix == ".json" else "text/markdown"


def _trees_identical(left: Path, right: Path) -> bool:
    left_files = _regular_tree_files(left)
    right_files = _regular_tree_files(right)
    if left_files is None or right_files is None:
        return False
    if left_files != right_files:
        return False
    return all((left / path).read_bytes() == (right / path).read_bytes() for path in left_files)


def _regular_tree_files(root: Path) -> list[Path] | None:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            return None
        if path.is_file():
            resolved = path.resolve(strict=True)
            if not _is_relative_to(resolved, root):
                return None
            files.append(path.relative_to(root))
    return sorted(files)


def _context_digest(context: ExecutionContext) -> str:
    return sha256(dumps_json(context).encode("utf-8")).hexdigest()


def _validate_decision_context_identity(
    decision: GateDecision,
    context: ExecutionContext,
) -> None:
    if decision.execution_id != context.execution_id:
        raise ValueError("GateDecision and ExecutionContext execution_id must match.")
    context_digest = _context_digest(context)
    if decision.execution_context_sha256 != context_digest:
        raise ValueError("GateDecision was not produced from this ExecutionContext snapshot.")
