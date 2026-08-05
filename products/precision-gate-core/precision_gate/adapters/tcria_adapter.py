"""TCRIA Adapter: converts a TCRIA audit bundle into a Quinta Ordem ExecutionContext.

The adapter is stateless, versioned, and logs every conversion step.
It does not perform filesystem access, network calls, or status promotion.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, ClassVar

logger = logging.getLogger(__name__)

SUPPORTED_VERSIONS: frozenset[str] = frozenset({"1.0"})


class TCRIAAdapterError(ValueError):
    """Raised when a TCRIA bundle cannot be converted without inference."""


class TCRIAAdapter:
    """Convert a TCRIA audit bundle into a Quinta Ordem-compatible payload.

    The output payload is a plain dict that satisfies the
    ``TCRIAExecutionContextAdapter`` contract defined in the quinta-ordem-gate
    product (``quinta_ordem_adapter_version = "1.0"``).

    Every conversion is logged with:
    - Input bundle SHA-256
    - Adapter version applied
    - Output payload SHA-256
    - Non-abandonment checks performed
    """

    schema_version: ClassVar[str] = "1.0"

    def __init__(self, version: str = "1.0") -> None:
        if version not in SUPPORTED_VERSIONS:
            raise TCRIAAdapterError(
                f"Unsupported TCRIAAdapter version: {version!r}. "
                f"Supported: {sorted(SUPPORTED_VERSIONS)}"
            )
        self.version = version

    def to_execution_context_payload(
        self,
        bundle: Mapping[str, Any],
        *,
        execution_id: str | None = None,
    ) -> dict[str, Any]:
        """Convert a TCRIA audit bundle to a Quinta Ordem adapter payload.

        Args:
            bundle: The TCRIA audit bundle (output of ``TCRIAEngine.run_audit``).
            execution_id: Override the execution_id; defaults to the bundle's
                ``audit_id`` field.

        Returns:
            A dict conforming to the ``quinta_ordem_adapter_version = "1.0"`` contract.

        Raises:
            TCRIAAdapterError: When the bundle is structurally invalid.
        """
        if not isinstance(bundle, Mapping):
            raise TCRIAAdapterError("bundle must be a mapping.")

        source = deepcopy(dict(bundle))
        input_sha = _sha256_dict(source)
        logger.info(
            "TCRIAAdapter v%s: converting bundle sha256=%s", self.version, input_sha
        )

        resolved_id = execution_id or source.get("audit_id") or source.get("execution_id")
        if not isinstance(resolved_id, str) or not resolved_id.strip():
            raise TCRIAAdapterError(
                "bundle must contain 'audit_id' or 'execution_id' (non-empty string)."
            )

        # Non-abandonment check: prescriptive gate blocked
        prescriptive_status = _nested_status(source, "prescriptive_gate_status")
        non_abandonment_findings = []
        if prescriptive_status == "blocked":
            non_abandonment_findings.append(
                "TCRIA prescriptive gate is BLOCKED — human review required."
            )
            logger.warning(
                "TCRIAAdapter: non-abandonment check triggered — prescriptive gate blocked."
            )

        evidence = _extract_evidence(source)
        artifacts = _extract_artifacts(source)
        gate_results = _extract_gate_results(source, prescriptive_status)
        logs = _extract_logs(source)
        decisions = _extract_decisions(source)
        signals = _extract_signals(source)
        metadata = _build_metadata(source, non_abandonment_findings)

        payload: dict[str, Any] = {
            "quinta_ordem_adapter_version": self.version,
            "execution_id": resolved_id,
            "evidence": evidence,
            "artifacts": artifacts,
            "gate_results": gate_results,
            "logs": logs,
            "decisions": decisions,
            "metadata": metadata,
            "_precision_gate_meta": {
                "converted_at": datetime.now(timezone.utc).isoformat(),
                "input_sha256": input_sha,
                "adapter_version": self.version,
                "non_abandonment_checks": non_abandonment_findings,
            },
        }
        if signals:
            payload["signals_for_verification"] = signals

        output_sha = _sha256_dict(payload)
        logger.info(
            "TCRIAAdapter v%s: output payload sha256=%s, non_abandonment_checks=%d",
            self.version,
            output_sha,
            len(non_abandonment_findings),
        )
        payload["_precision_gate_meta"]["output_sha256"] = output_sha

        return payload


def _sha256_dict(d: dict[str, Any]) -> str:
    serialized = json.dumps(d, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _nested_status(bundle: dict[str, Any], key: str) -> str | None:
    value = bundle.get(key)
    if isinstance(value, str):
        return value.strip().lower()
    governance = bundle.get("governance", {})
    if isinstance(governance, Mapping):
        value = governance.get(key)
        if isinstance(value, str):
            return value.strip().lower()
    return None


def _extract_evidence(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    raw = bundle.get("files") or bundle.get("evidence") or []
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        artifact_id = item.get("artifact_id") or item.get("file_hash") or item.get("path", "")
        entry: dict[str, Any] = {
            "artifact_id": str(artifact_id),
        }
        for key in ("sha256", "source_path", "path", "source", "type", "size_bytes"):
            if key in item:
                entry[key] = item[key]
        result.append(entry)
    return result


def _extract_artifacts(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    raw = bundle.get("artifacts") or []
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if isinstance(item, Mapping):
            result.append(deepcopy(dict(item)))
    return result


def _extract_gate_results(
    bundle: dict[str, Any], prescriptive_status: str | None
) -> list[dict[str, Any]]:
    results = []
    for gate_name in ("prescriptive_gate", "compliance_gate", "traceability_gate"):
        status_key = f"{gate_name}_status"
        status = bundle.get(status_key) or (
            bundle.get("governance", {}).get(status_key) if isinstance(bundle.get("governance"), Mapping) else None
        )
        if status is not None:
            results.append({"gate": gate_name, "status": str(status).strip().lower()})

    # Ensure prescriptive block is always present if detected
    if prescriptive_status == "blocked" and not any(
        r["gate"] == "prescriptive_gate" for r in results
    ):
        results.append({"gate": "prescriptive_gate", "status": "blocked"})

    raw = bundle.get("gate_results") or []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, Mapping):
                results.append(deepcopy(dict(item)))

    return results


def _extract_logs(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    raw = bundle.get("logs") or bundle.get("warnings") or []
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if isinstance(item, str):
            result.append({"message": item})
        elif isinstance(item, Mapping):
            result.append(deepcopy(dict(item)))
    return result


def _extract_decisions(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    raw = bundle.get("decisions") or []
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if isinstance(item, Mapping):
            result.append(deepcopy(dict(item)))
    return result


def _extract_signals(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    raw = bundle.get("signals_for_verification") or bundle.get("signals") or []
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if isinstance(item, Mapping):
            result.append(deepcopy(dict(item)))
    return result


def _build_metadata(
    bundle: dict[str, Any], non_abandonment_findings: list[str]
) -> dict[str, Any]:
    meta: dict[str, Any] = {}

    governance = bundle.get("governance")
    if isinstance(governance, Mapping):
        meta.update(deepcopy(dict(governance)))

    for key in ("case_id", "responsible_human", "declared_purpose", "approved"):
        if key in bundle:
            meta[key] = bundle[key]

    raw_roots = bundle.get("evidence_roots") or bundle.get("input_paths") or []
    if isinstance(raw_roots, list) and raw_roots:
        meta["evidence_roots"] = raw_roots

    meta["non_abandonment_flags"] = non_abandonment_findings

    if "open_points" not in meta:
        meta["open_points"] = []

    return meta
