from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quinta_ordem.models import EvidenceRef


def evidence_ref_from_raw(value: Any) -> EvidenceRef | None:
    if isinstance(value, EvidenceRef):
        return value
    if isinstance(value, str) and value.strip():
        return EvidenceRef(artifact_id=value)
    if not isinstance(value, Mapping):
        return None

    artifact_id = value.get("artifact_id") or value.get("id") or value.get("ref")
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        return None

    sha256 = value.get("sha256")
    source = value.get("source")
    metadata = {
        str(key): item
        for key, item in value.items()
        if key not in {"artifact_id", "id", "ref", "sha256", "source"}
    }
    return EvidenceRef(
        artifact_id=artifact_id,
        sha256=sha256 if isinstance(sha256, str) else None,
        source=source if isinstance(source, str) else None,
        metadata=metadata,
    )


def refs_from_decision(decision: Mapping[str, Any]) -> list[EvidenceRef]:
    raw_refs = decision.get("evidence_refs")
    if not isinstance(raw_refs, list):
        return []
    return [ref for value in raw_refs if (ref := evidence_ref_from_raw(value)) is not None]


def evidence_ref_for_item(item: Mapping[str, Any]) -> EvidenceRef | None:
    artifact_id = item.get("artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        return None
    sha256 = item.get("sha256")
    source = item.get("source") or item.get("source_path") or item.get("original_path")
    return EvidenceRef(
        artifact_id=artifact_id,
        sha256=sha256 if isinstance(sha256, str) else None,
        source=source if isinstance(source, str) else None,
    )
