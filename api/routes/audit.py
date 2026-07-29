from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tcria.engine import TCRIAEngine
from tcria.institutional_output import render_institutional_markdown
from tcria.openai_responses import (
    list_available_institutional_chat_profiles,
    list_audit_prompt_presets,
    run_institutional_output_prompt,
    run_audit_prompt,
)


class AuditRequest(BaseModel):
    path: str = Field(..., description="File or folder path to audit.")
    strict: bool = True
    out_dir: str = "output/audit"
    output_stem: str = "audit"
    include_pdf: bool = True
    max_files: int = Field(2000, ge=1, le=20000)
    max_total_bytes: int = Field(250_000_000, ge=1024, le=2_000_000_000)


class OpenAIResponsesAuditRequest(AuditRequest):
    model: str = Field("gpt-4.1-mini", description="OpenAI model used to explain the audit bundle.")
    audit_type: str = Field(
        "general_governance",
        description="Prompt preset used to analyze the audit bundle through the OpenAI Responses API.",
    )
    max_items: int = Field(8, ge=1, le=50, description="How many example records to send to OpenAI.")
    user_context: str | None = Field(
        default=None,
        description="Optional instruction that overrides or complements the preset prompt.",
    )


class InstitutionalOutputRequest(BaseModel):
    audit_data: dict[str, Any] = Field(
        ...,
        description="Structured process audit data used to build an institutional dispatch-ready output.",
    )
    chat_profile: str = Field(
        "fazendario_institucional",
        description="Named chat profile used to define the institutional drafting behavior.",
    )
    model: str = Field("gpt-4.1-mini", description="OpenAI model used for institutional drafting.")
    user_context: str | None = Field(
        default=None,
        description="Optional extra instruction for the institutional drafting module.",
    )
    system_prompt_override: str | None = Field(
        default=None,
        description="Optional system-prompt override when you want to define the chat behavior explicitly.",
    )


class LegacyGatewayAuditRequest(BaseModel):
    path: str = Field(..., description="File or folder path to audit with the legacy accusation gateway.")
    strict: bool = True
    output_dir: str = "output/audit"
    output_stem: str | None = None
    discovery_root: str | None = None


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


def _resolve_and_validate_input_path(path_value: str) -> Path:
    resolved = Path(path_value).expanduser().resolve()
    if not resolved.exists():
        raise HTTPException(status_code=400, detail=f"Input path does not exist: {resolved}")
    allowed_roots = _allowed_input_roots()
    if not any(_is_within(resolved, root) for root in allowed_roots):
        joined = ", ".join(str(root) for root in allowed_roots)
        raise HTTPException(
            status_code=403,
            detail=f"Input path is outside allowed roots. Allowed roots: {joined}",
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


def _parse_labeled_line(text: str, label: str) -> str | None:
    match = re.search(rf"^{re.escape(label)}\s*(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _run_legacy_gateway_audit(payload: LegacyGatewayAuditRequest) -> dict[str, object]:
    script_path = (Path(__file__).resolve().parent.parent.parent / "audit_accusation_bundle_with_tcr_gateway.py").resolve()
    cmd = [
        sys.executable,
        str(script_path),
        "--path",
        str(_resolve_and_validate_input_path(payload.path)),
        "--output-dir",
        payload.output_dir,
    ]
    if payload.strict:
        cmd.append("--strict")
    if payload.output_stem:
        cmd.extend(["--output-stem", payload.output_stem])
    if payload.discovery_root:
        cmd.extend(["--discovery-root", payload.discovery_root])
    cp = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parent.parent.parent), text=True, capture_output=True)
    if cp.returncode != 0:
        raise HTTPException(status_code=400, detail=cp.stderr or cp.stdout or "Legacy gateway audit failed.")
    json_report = _parse_labeled_line(cp.stdout, "JSON report:")
    markdown_report = _parse_labeled_line(cp.stdout, "Markdown report:")
    if not json_report or not markdown_report:
        raise HTTPException(status_code=400, detail="Could not parse legacy gateway output artifact paths.")
    payload_json = _load_json(json_report)
    return {"stdout": cp.stdout, "json_report": json_report, "markdown_report": markdown_report, "bundle": payload_json}


def create_audit_router(*, engine: TCRIAEngine) -> APIRouter:
    router = APIRouter()

    @router.get("/responses/audit-types")
    def get_response_audit_types() -> dict[str, object]:
        return {"audit_types": list_audit_prompt_presets()}

    @router.get("/responses/institutional-profiles")
    def get_institutional_chat_profiles() -> dict[str, object]:
        return {"chat_profiles": list_available_institutional_chat_profiles()}

    @router.post("/audit")
    def run_audit(payload: AuditRequest) -> dict[str, object]:
        validated_path = _resolve_and_validate_input_path(payload.path)
        try:
            return engine.run_audit(
                input_path=str(validated_path),
                strict=payload.strict,
                out_dir=payload.out_dir,
                output_stem=payload.output_stem,
                include_pdf=payload.include_pdf,
                max_files=payload.max_files,
                max_total_bytes=payload.max_total_bytes,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/audit/official-pipeline")
    def run_official_pipeline(payload: AuditRequest) -> dict[str, str]:
        validated_path = _resolve_and_validate_input_path(payload.path)
        try:
            return engine.run_official_pipeline(
                input_path=str(validated_path),
                strict=payload.strict,
                output_stem=payload.output_stem,
                max_files=payload.max_files,
                max_total_bytes=payload.max_total_bytes,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/responses/audit")
    def run_responses_audit(payload: OpenAIResponsesAuditRequest) -> dict[str, object]:
        validated_path = _resolve_and_validate_input_path(payload.path)
        try:
            result = engine.run_audit(
                input_path=str(validated_path),
                strict=payload.strict,
                out_dir=payload.out_dir,
                output_stem=payload.output_stem,
                include_pdf=payload.include_pdf,
                max_files=payload.max_files,
                max_total_bytes=payload.max_total_bytes,
            )
            bundle = result.get("bundle")
            if not isinstance(bundle, dict):
                raise RuntimeError("Audit result did not contain a bundle.")
            responses_result = run_audit_prompt(
                bundle,
                audit_type=payload.audit_type,
                model=payload.model,
                user_context=payload.user_context,
                max_items=payload.max_items,
            )
            return {"audit": result, "responses_analysis": responses_result}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/audit/openai-summary")
    def run_audit_openai_summary(payload: OpenAIResponsesAuditRequest) -> dict[str, object]:
        return run_responses_audit(payload)

    @router.post("/responses/institutional-output")
    def api_run_institutional_output(payload: InstitutionalOutputRequest) -> dict[str, object]:
        result = run_institutional_output_prompt(
            payload.audit_data,
            model=payload.model,
            user_context=payload.user_context,
            chat_profile=payload.chat_profile,
            system_prompt_override=payload.system_prompt_override,
        )
        output = result["institutional_output"]
        return {
            "institutional_output": output,
            "markdown": render_institutional_markdown(output),
            "response_metadata": result["response_metadata"],
        }

    @router.post("/gateways/legacy-accusation-audit")
    def api_legacy_gateway_audit(payload: LegacyGatewayAuditRequest) -> dict[str, object]:
        return _run_legacy_gateway_audit(payload)

    return router
