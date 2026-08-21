from __future__ import annotations

import json
import os
import tempfile
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from tcria.institutional_output import render_institutional_markdown


def render_markdown_report(bundle: dict[str, object]) -> str:
    lines: list[str] = []
    lines.append("# TCRIA Audit Report")
    lines.append("")
    lines.append(f"- Generated at: `{bundle.get('generated_at')}`")
    lines.append(f"- Input path: `{bundle.get('input_path')}`")
    lines.append(f"- Mode: `{bundle.get('mode')}`")
    lines.append(f"- Total files scanned: `{bundle.get('total_files_scanned')}`")
    lines.append(f"- Accusation set count: `{bundle.get('accusation_set_count')}`")
    lines.append(f"- Classification counts: `{bundle.get('classification_counts')}`")
    lines.append(f"- Route counts: `{bundle.get('route_counts')}`")
    lines.append(f"- Document role counts: `{bundle.get('document_role_counts')}`")
    lines.append("")
    lines.append("## Accusation Set")
    lines.append("")
    for rec in bundle.get("accusation_set", []):
        doc = rec.get("document", {})
        interpretation = rec.get("interpretation") or {}
        route = ((interpretation.get("route_selection") or {}).get("selected_route")) or "UNDETERMINED"
        role = ((interpretation.get("document_role") or {}).get("value")) or "UNDETERMINED"
        posture = ((interpretation.get("discursive_posture") or {}).get("value")) or "NEUTRAL_OR_UNCLEAR"
        lines.append(f"### {doc.get('relative_path') or doc.get('path')}")
        lines.append(f"- Outcome: `{rec.get('overall_outcome')}`")
        lines.append(f"- Classification: `{rec.get('classification')}`")
        lines.append(f"- Route: `{route}`")
        lines.append(f"- Document role: `{role}`")
        lines.append(f"- Discursive posture: `{posture}`")
        lines.append(f"- Reasons: {', '.join(rec.get('classification_reasons', []))}")
        gates = rec.get("gates") or {}
        for gate_name, gate in gates.items():
            lines.append(f"- `{gate_name}`: `{gate.get('status')}` - {gate.get('reason')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _write_pdf_from_markdown(markdown: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    _, height = A4
    y = height - 40
    for raw_line in markdown.splitlines():
        line = raw_line[:110]
        c.drawString(30, y, line)
        y -= 14
        if y < 40:
            c.showPage()
            y = height - 40
    c.save()
    _atomic_write_bytes(output_path, buffer.getvalue())


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_text(path: Path, payload: str) -> None:
    _atomic_write_bytes(path, payload.encode("utf-8"))


def write_audit_artifacts(
    bundle: dict[str, object],
    out_dir: str | Path,
    output_stem: str = "audit",
    include_pdf: bool = True,
    institutional_output: dict[str, object] | None = None,
) -> dict[str, str]:
    out_path = Path(out_dir).expanduser().resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    json_path = out_path / f"{output_stem}.json"
    md_path = out_path / f"{output_stem}.md"
    pdf_path = out_path / f"{output_stem}_report.pdf"
    institutional_md_path = out_path / f"{output_stem}_institutional.md"

    markdown = render_markdown_report(bundle)
    _atomic_write_text(json_path, json.dumps(bundle, ensure_ascii=False, indent=2))
    _atomic_write_text(md_path, markdown)
    artifacts = {"json": str(json_path), "markdown": str(md_path)}

    if institutional_output is not None:
        _atomic_write_text(
            institutional_md_path,
            render_institutional_markdown(institutional_output),
        )
        artifacts["institutional_markdown"] = str(institutional_md_path)

    if include_pdf:
        _write_pdf_from_markdown(markdown, pdf_path)
        artifacts["pdf"] = str(pdf_path)
    return artifacts
