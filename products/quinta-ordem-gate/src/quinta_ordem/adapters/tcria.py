from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, ClassVar

from quinta_ordem.models import DecisionStatus, ExecutionContext


class TCRIAAdapterError(ValueError):
    """Raised when a TCRIA payload cannot be mapped without inference."""


class TCRIAExecutionContextAdapter:
    """Pure adapter for the documented, normalized TCRIA hand-off contract.

    The adapter performs no filesystem access, hashing, network access or status promotion.
    It creates a deep, detached copy so the TCRIA payload remains unchanged.
    """

    adapter_schema_version: ClassVar[str] = "1.0"

    def adapt(
        self,
        payload: Mapping[str, Any],
        *,
        execution_id: str | None = None,
    ) -> ExecutionContext:
        if not isinstance(payload, Mapping):
            raise TCRIAAdapterError("payload must be a mapping.")

        source = deepcopy(dict(payload))
        declared_version = source.get("quinta_ordem_adapter_version")
        if declared_version is None:
            raise TCRIAAdapterError("quinta_ordem_adapter_version is required.")
        if declared_version != self.adapter_schema_version:
            raise TCRIAAdapterError(
                f"Unsupported quinta_ordem_adapter_version: {declared_version!r}."
            )

        resolved_execution_id = execution_id or source.get("execution_id")
        if not isinstance(resolved_execution_id, str) or not resolved_execution_id.strip():
            raise TCRIAAdapterError("execution_id is required.")

        evidence = _mapping_list(source, "evidence")
        artifacts = _mapping_list(source, "artifacts")
        gate_results = _mapping_list(source, "gate_results")
        logs = _mapping_list(source, "logs")
        decisions = _mapping_list(source, "decisions")
        signals = _mapping_list(source, "signals_for_verification", required=False)
        metadata = _metadata(source)

        for index, result in enumerate(gate_results):
            status = result.get("status")
            if not isinstance(status, str):
                raise TCRIAAdapterError(f"gate_results[{index}].status must be a string.")
            normalized = status.strip().lower()
            allowed = {
                DecisionStatus.APPROVED.value,
                DecisionStatus.CONDITIONAL.value,
                DecisionStatus.RETURNED.value,
                DecisionStatus.BLOCKED.value,
                "returned",
            }
            if normalized not in allowed:
                raise TCRIAAdapterError(
                    f"Unknown gate status at gate_results[{index}]: {status!r}."
                )
            result["status"] = normalized

        signal_points = []
        for index, signal in enumerate(signals):
            signal_id = signal.get("signal_id")
            if not isinstance(signal_id, str) or not signal_id.strip():
                raise TCRIAAdapterError(f"signals_for_verification[{index}].signal_id is required.")
            decision = {
                "decision_id": signal_id,
                "classification": "signal",
                "promoted": False,
            }
            for key in ("support_level", "evidence_refs", "message", "details"):
                if key in signal:
                    decision[key] = deepcopy(signal[key])
            decisions.append(decision)
            signal_points.append(
                {
                    "id": signal_id,
                    "status": "open",
                    "return_to": "human_review",
                    "evidence_refs": deepcopy(signal.get("evidence_refs", [])),
                }
            )

        if signal_points:
            existing_points = metadata.get("open_points")
            if existing_points is None:
                metadata["open_points"] = signal_points
            elif isinstance(existing_points, list):
                metadata["open_points"] = [*existing_points, *signal_points]
            else:
                raise TCRIAAdapterError("metadata.open_points must be a list.")

        return ExecutionContext(
            execution_id=resolved_execution_id,
            evidence=evidence,
            artifacts=artifacts,
            gate_results=gate_results,
            logs=logs,
            decisions=decisions,
            metadata=metadata,
        )


def _mapping_list(
    payload: dict[str, Any],
    key: str,
    *,
    required: bool = True,
) -> list[dict[str, Any]]:
    if required and key not in payload:
        raise TCRIAAdapterError(f"{key} is required.")
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise TCRIAAdapterError(f"{key} must be a list.")
    copied: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise TCRIAAdapterError(f"{key}[{index}] must be a mapping.")
        copied.append(deepcopy(dict(item)))
    return copied


def _metadata(payload: dict[str, Any]) -> dict[str, Any]:
    if "metadata" not in payload:
        raise TCRIAAdapterError("metadata is required.")
    value = payload["metadata"]
    if not isinstance(value, Mapping):
        raise TCRIAAdapterError("metadata must be a mapping.")
    copied = deepcopy(dict(value))
    if "open_points" in payload:
        if "open_points" in copied:
            raise TCRIAAdapterError("open_points must be declared in only one location.")
        copied["open_points"] = deepcopy(payload["open_points"])
    return copied
