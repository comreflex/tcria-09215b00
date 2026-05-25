from __future__ import annotations

from fastapi import APIRouter


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/capabilities")
def capabilities() -> dict[str, object]:
    return {
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
