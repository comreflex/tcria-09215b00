from __future__ import annotations

import hmac
import os
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from tcria.handoff import HandoffError, run_tcria_handoff

router = APIRouter(prefix="/uoms", tags=["uoms-handoff"])


class TCRIAOpenRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=128)
    paths: list[str] = Field(min_length=1)
    custody_root: str
    strict: bool = True
    include_pdf: bool = True
    output_stem: str = "tcria_audit"
    max_files: int = Field(default=1_000, ge=1, le=10_000)
    max_total_bytes: int = Field(
        default=256 * 1024 * 1024,
        ge=1,
        le=2 * 1024 * 1024 * 1024,
    )


def _require_operator(authorization: str | None) -> None:
    expected = os.getenv("UOMS_API_TOKEN", "")
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "UOMS_API_TOKEN must be configured before enabling the handoff API.",
        )
    if len(expected.encode()) < 32:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "UOMS_API_TOKEN must contain at least 32 bytes.",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token required.")
    supplied = authorization.split(" ", 1)[1]
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid operator token.")


def _configured_custody_root(requested: str) -> Path:
    configured = os.getenv("UOMS_CUSTODY_ROOT", "").strip()
    if not configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "UOMS_CUSTODY_ROOT must be configured.",
        )
    root = Path(configured).expanduser().resolve()
    if Path(requested).expanduser().resolve() != root:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Custody root is not authorized.")
    return root


def _authorized_input_paths(values: list[str]) -> list[str]:
    configured = os.getenv("UOMS_EVIDENCE_ROOTS", "").strip()
    if not configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "UOMS_EVIDENCE_ROOTS must be configured.",
        )
    try:
        roots = [
            Path(value.strip()).expanduser().resolve(strict=True)
            for value in configured.split(os.pathsep)
            if value.strip()
        ]
        paths = [Path(value).expanduser().resolve(strict=True) for value in values]
    except OSError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "An evidence path is invalid.") from exc
    if not roots or any(not root.is_dir() for root in roots):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Every configured evidence root must be an existing directory.",
        )
    if any(not any(path == root or path.is_relative_to(root) for root in roots) for path in paths):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Evidence path is not authorized.")
    return [str(path) for path in paths]


@router.post("/tcria/open")
def open_tcria_stage(
    payload: TCRIAOpenRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    _require_operator(authorization)
    custody_root = _configured_custody_root(payload.custody_root)
    input_paths = _authorized_input_paths(payload.paths)
    try:
        return run_tcria_handoff(
            input_paths=input_paths,
            custody_root=custody_root,
            run_id=payload.run_id,
            strict=payload.strict,
            include_pdf=payload.include_pdf,
            output_stem=payload.output_stem,
            max_files=payload.max_files,
            max_total_bytes=payload.max_total_bytes,
        )
    except HandoffError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
