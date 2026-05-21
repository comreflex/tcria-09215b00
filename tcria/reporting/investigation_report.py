"""
TCRIA reporting adapter for the legacy investigation report script.

This module lets other components import reporting functions without directly
reaching into CLI scripts.

Refs #35.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


_LEGACY_REPORT_MODULE: Any | None = None


def _legacy() -> Any:
    """Load legacy investigation report builder module from scripts/."""
    global _LEGACY_REPORT_MODULE
    if _LEGACY_REPORT_MODULE is not None:
        return _LEGACY_REPORT_MODULE

    root = Path(__file__).resolve().parents[2]
    legacy_path = root / "scripts" / "generate_investigation_report.py"

    spec = importlib.util.spec_from_file_location(
        "scripts.generate_investigation_report", legacy_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load legacy module at {legacy_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["scripts.generate_investigation_report"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    _LEGACY_REPORT_MODULE = module
    return module


def load_json(path: str):
    return _legacy().load_json(path)


def build_report(audit_path: str, evidence_path: str, timeline_path: str):
    return _legacy().build_report(audit_path, evidence_path, timeline_path)


def build_markdown(report: dict) -> str:
    return _legacy().build_markdown(report)


def build_pdf(markdown: str, output_path: str) -> str:
    return _legacy().build_pdf(markdown, output_path)
