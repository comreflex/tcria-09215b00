from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tcria.cli import case_init, case_run, investigate, load_manifest, resolve_case_dir
from tcria.conclusion_engine import build_conclusion_report, render_final_conclusions_md
from tcria.openai_responses import run_audit_prompt


class CaseInitRequest(BaseModel):
    case: str = Field(..., description="Case id or absolute/relative case directory.")
    root: str = Field("cases", description="Root directory for case ids.")


class CaseRunRequest(CaseInitRequest):
    strict: bool = True
    paths: list[str] = Field(default_factory=list, description="Optional input paths. Defaults to case input dir.")
    top_k: int = Field(10, ge=1, le=100)
    output_stem: str | None = None


class CaseInvestigateRequest(CaseInitRequest):
    audit: str | None = None
    blocked: str | None = None
    preparation: str | None = None
    timeline: str | None = None


class BundleConclusionRequest(BaseModel):
    bundle_json_path: str = Field(..., description="Path to an audit bundle JSON.")


class FullInvestigationRunRequest(CaseRunRequest):
    audit_type: str = Field(
        "civil_criminal_investigative",
        description="Responses API preset used when analyze_with_openai=true.",
    )
    model: str = Field("gpt-4.1-mini", description="OpenAI model used for the final Responses API analysis.")
    analyze_with_openai: bool = Field(
        False,
        description="When true, run a final Responses API analysis over the resulting audit bundle.",
    )
    user_context: str | None = Field(
        default=None,
        description="Optional instruction that overrides or complements the preset prompt.",
    )
    max_items: int = Field(8, ge=1, le=50, description="How many example records to send to OpenAI.")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _allowed_input_roots() -> list[Path]:
    raw = os.getenv("TCRIA_ALLOWED_INPUT_ROOTS", "").strip()
    if not raw:
        return [Path.cwd().resolve()]
    return [Path(part.strip()).expanduser().resolve() for part in raw.split(",") if part.strip()]


def _resolve_case_path(case_value: str, root: str) -> Path:
    resolved = resolve_case_dir(case_value, root)
    allowed_roots = _allowed_input_roots()
    if not any(_is_within(resolved, allowed_root) for allowed_root in allowed_roots):
        joined = ", ".join(str(root_path) for root_path in allowed_roots)
        raise HTTPException(
            status_code=403,
            detail=f"Case path is outside allowed roots. Allowed roots: {joined}",
        )
    return resolved


def _load_json(path_value: str | Path) -> dict[str, object]:
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"JSON path does not exist: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read JSON: {path}: {exc}") from exc


def _load_case_outputs(case_dir: Path, manifest: dict[str, Any]) -> dict[str, object]:
    latest_outputs = manifest.get("latest_outputs", {})

    def read_latest_json(key: str) -> dict[str, object] | None:
        rel = latest_outputs.get(key)
        if not isinstance(rel, str):
            return None
        path = case_dir / rel
        if not path.exists():
            return None
        return _load_json(path)

    audit_bundle = read_latest_json("official_audit_json")
    blocked_review = read_latest_json("blocked_review_json")
    preparation = read_latest_json("case_preparation_json")
    timeline = read_latest_json("timeline_json")
    investigation_report = read_latest_json("investigation_report_json")
    conclusions = build_conclusion_report(audit_bundle) if isinstance(audit_bundle, dict) else None
    return {
        "latest_outputs": latest_outputs,
        "audit_bundle": audit_bundle,
        "blocked_review": blocked_review,
        "preparation": preparation,
        "timeline": timeline,
        "investigation_report": investigation_report,
        "gateway_conclusions": conclusions,
        "gateway_conclusions_markdown": render_final_conclusions_md(conclusions) if isinstance(conclusions, dict) else None,
    }


def create_cases_router() -> APIRouter:
    router = APIRouter()

    @router.post("/cases/init")
    def api_case_init(payload: CaseInitRequest) -> dict[str, object]:
        case_dir = _resolve_case_path(payload.case, payload.root)
        try:
            case_init(case_dir)
            manifest = load_manifest(case_dir / "case_manifest.json")
            return {
                "case_dir": str(case_dir),
                "manifest_path": str(case_dir / "case_manifest.json"),
                "manifest": manifest,
            }
        except SystemExit as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/cases/run")
    def api_case_run(payload: CaseRunRequest) -> dict[str, object]:
        case_dir = _resolve_case_path(payload.case, payload.root)
        try:
            case_run(
                case_dir,
                strict=payload.strict,
                paths=payload.paths,
                top_k=payload.top_k,
                output_stem=payload.output_stem,
            )
            manifest = load_manifest(case_dir / "case_manifest.json")
            return {"case_dir": str(case_dir), "manifest": manifest, "latest_outputs": manifest.get("latest_outputs", {})}
        except SystemExit as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/cases/investigate")
    def api_case_investigate(payload: CaseInvestigateRequest) -> dict[str, object]:
        case_dir = _resolve_case_path(payload.case, payload.root)
        try:
            investigate(
                case_dir,
                audit=payload.audit,
                blocked=payload.blocked,
                preparation=payload.preparation,
                timeline=payload.timeline,
            )
            manifest = load_manifest(case_dir / "case_manifest.json")
            latest_outputs = manifest.get("latest_outputs", {})
            report_json = latest_outputs.get("investigation_report_json")
            report = _load_json(case_dir / report_json) if isinstance(report_json, str) else None
            return {"case_dir": str(case_dir), "manifest": manifest, "investigation_report": report}
        except SystemExit as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/conclusions/from-bundle")
    def api_bundle_conclusions(payload: BundleConclusionRequest) -> dict[str, object]:
        bundle = _load_json(payload.bundle_json_path)
        conclusions = build_conclusion_report(bundle)
        return {"conclusions": conclusions, "markdown": render_final_conclusions_md(conclusions)}

    @router.post("/investigations/full-run")
    def api_full_investigation_run(payload: FullInvestigationRunRequest) -> dict[str, object]:
        case_dir = _resolve_case_path(payload.case, payload.root)
        manifest_path = case_dir / "case_manifest.json"
        try:
            if not manifest_path.exists():
                case_init(case_dir)
            case_run(
                case_dir,
                strict=payload.strict,
                paths=payload.paths,
                top_k=payload.top_k,
                output_stem=payload.output_stem,
            )
            investigate(case_dir, audit=None, blocked=None, preparation=None, timeline=None)
            manifest = load_manifest(manifest_path)
            outputs = _load_case_outputs(case_dir, manifest)
            responses_analysis = None
            audit_bundle = outputs.get("audit_bundle")
            if payload.analyze_with_openai and isinstance(audit_bundle, dict):
                responses_analysis = run_audit_prompt(
                    audit_bundle,
                    audit_type=payload.audit_type,
                    model=payload.model,
                    max_items=payload.max_items,
                    user_context=payload.user_context,
                )
            return {"case_dir": str(case_dir), "manifest": manifest, **outputs, "responses_analysis": responses_analysis}
        except SystemExit as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
