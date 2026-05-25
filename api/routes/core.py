from __future__ import annotations

import os

from fastapi import APIRouter


router = APIRouter()


@router.get("/")
def root() -> dict[str, str]:
    return {"service": "tcria-api", "status": "online"}


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/capabilities")
def capabilities() -> dict[str, object]:
    return {
        "security": {
            "uploads_token_required": bool(os.getenv("TCRIA_API_TOKEN", "").strip()),
        },
        "api": [
            "audit",
            "official_pipeline",
            "responses_audit",
            "responses_institutional_profiles",
            "case_init",
            "case_run",
            "case_investigate",
            "bundle_conclusions",
            "responses_institutional_output",
            "legacy_gateway_audit",
            "uploads_scan",
            "uploads_status",
        ]
    }
