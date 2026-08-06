"""Quinta Ordem Adapter — converts TCRIA audit bundles to ExecutionContext.

This adapter bridges TCRIA audit bundle JSON output to the ExecutionContext
schema expected by the Quinta Ordem Gate, preserving chain-of-custody integrity
and traceability metadata throughout the conversion.

Governance rules applied:
- RULE_4.1: human responsibility metadata is explicit and carried forward
- RULE_2.1: evidence references and traceability links are preserved
- Original evidence is never modified; only structural mapping is performed
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# ExecutionContext dataclass
# ---------------------------------------------------------------------------

class ExecutionContext:
    """Lightweight container for the Quinta Ordem Gate execution context.

    Attributes
    ----------
    execution_id:
        Deterministic identifier derived from the source audit bundle.
    evidence:
        List of evidence metadata entries, one per scanned artifact.
    artifacts:
        List of raw artifact descriptors from the audit.
    gate_results:
        List of gate evaluation results carried forward from TCRIA.
    logs:
        Structured log entries produced during the audit run.
    decisions:
        Decision records with classification, support_level, and evidence_refs.
    metadata:
        Supplementary metadata including open_points and traceability info.
    """

    def __init__(
        self,
        *,
        execution_id: str,
        evidence: list[dict[str, Any]],
        artifacts: list[dict[str, Any]],
        gate_results: list[dict[str, Any]],
        logs: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
        metadata: dict[str, Any],
    ) -> None:
        self.execution_id = execution_id
        self.evidence = evidence
        self.artifacts = artifacts
        self.gate_results = gate_results
        self.logs = logs
        self.decisions = decisions
        self.metadata = metadata

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "evidence": self.evidence,
            "artifacts": self.artifacts,
            "gate_results": self.gate_results,
            "logs": self.logs,
            "decisions": self.decisions,
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, default=str)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class QuintaOrdemAdapter:
    """Converts a TCRIA audit bundle dict to an ExecutionContext.

    The adapter maps:
    - accusation_set  → decisions with classification=ACCUSATORY
    - non_accusation_set → decisions with classification=NON_ACCUSATORY
    - gate results per artifact → gate_results list
    - document metadata → evidence list + artifacts list
    - top-level bundle fields → metadata + logs
    """

    # Maps TCRIA gate names to human-readable labels
    _GATE_LABEL_MAP: dict[str, str] = {
        "prescriptiveGate": "prescriptive_gate",
        "complianceGate": "compliance_gate",
        "traceabilityCheck": "traceability_check",
    }

    def from_bundle_dict(self, bundle: dict[str, Any]) -> ExecutionContext:
        """Convert a TCRIA audit bundle dict to ExecutionContext.

        Parameters
        ----------
        bundle:
            Parsed TCRIA audit JSON payload.

        Returns
        -------
        ExecutionContext
            Quinta Ordem-compatible execution context.
        """
        execution_id = self._derive_execution_id(bundle)

        accusation_set: list[dict[str, Any]] = bundle.get("accusation_set", [])
        non_accusation_set: list[dict[str, Any]] = bundle.get("non_accusation_set", [])
        all_records: list[dict[str, Any]] = accusation_set + non_accusation_set

        evidence = self._build_evidence(all_records)
        artifacts = self._build_artifacts(all_records)
        gate_results = self._build_gate_results(all_records)
        logs = self._build_logs(bundle)
        decisions = self._build_decisions(accusation_set, non_accusation_set)
        metadata = self._build_metadata(bundle)

        return ExecutionContext(
            execution_id=execution_id,
            evidence=evidence,
            artifacts=artifacts,
            gate_results=gate_results,
            logs=logs,
            decisions=decisions,
            metadata=metadata,
        )

    def from_bundle_json(self, json_path: str | Path) -> ExecutionContext:
        """Load a TCRIA audit bundle from a JSON file and convert it.

        Parameters
        ----------
        json_path:
            Path to the TCRIA audit JSON file.

        Returns
        -------
        ExecutionContext
        """
        with open(json_path, encoding="utf-8") as fh:
            bundle = json.load(fh)
        return self.from_bundle_dict(bundle)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_execution_id(bundle: dict[str, Any]) -> str:
        """Derive a deterministic execution ID from the bundle."""
        generated_at = bundle.get("generated_at", "")
        total_files = bundle.get("total_files_scanned", 0)
        accusation_count = bundle.get("accusation_set_count", 0)
        raw = f"{generated_at}|{total_files}|{accusation_count}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"tcria-exec-{digest}"

    @staticmethod
    def _safe_sha256(record: dict[str, Any]) -> str:
        return record.get("sha256") or record.get("document", {}).get("sha256", "")

    def _build_evidence(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        evidence = []
        for rec in records:
            sha = self._safe_sha256(rec)
            entry: dict[str, Any] = {
                "evidence_id": sha[:16] if sha else rec.get("file_name", "unknown"),
                "file_name": rec.get("file_name", ""),
                "file_path": rec.get("file_path", ""),
                "sha256": sha,
                "suffix": rec.get("suffix", ""),
                "size_bytes": rec.get("size_bytes", 0),
                "extraction_status": rec.get("extraction_status", ""),
                "extraction_method": rec.get("extraction_method", ""),
                "text_quality": rec.get("text_quality", ""),
                "classification": rec.get("classification", ""),
                "raises_accusation": rec.get("raises_accusation", False),
            }
            evidence.append(entry)
        return evidence

    def _build_artifacts(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        artifacts = []
        for rec in records:
            sha = self._safe_sha256(rec)
            artifact: dict[str, Any] = {
                "artifact_id": sha[:16] if sha else rec.get("file_name", "unknown"),
                "file_name": rec.get("file_name", ""),
                "artifact_type": rec.get("artifact_type", ""),
                "artifact_type_reason": rec.get("artifact_type_reason", ""),
                "classification": rec.get("classification", ""),
                "overall_outcome": rec.get("overall_outcome"),
                "sha256": sha,
                "key_signals": rec.get("key_signals", rec.get("signals", {})),
            }
            artifacts.append(artifact)
        return artifacts

    def _build_gate_results(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        gate_results = []
        for rec in records:
            sha = self._safe_sha256(rec)
            ref = sha[:16] if sha else rec.get("file_name", "unknown")
            gates: dict[str, Any] = rec.get("gates") or {}
            for raw_gate_name, gate_data in gates.items():
                gate_name = self._GATE_LABEL_MAP.get(raw_gate_name, raw_gate_name)
                if isinstance(gate_data, dict):
                    status = gate_data.get("status", "NOT_EVALUATED")
                    reason = gate_data.get("reason", "")
                    evidence_ref = gate_data.get("evidence")
                else:
                    status = "NOT_EVALUATED"
                    reason = str(gate_data)
                    evidence_ref = None
                gate_results.append({
                    "gate_name": gate_name,
                    "artifact_ref": ref,
                    "status": status,
                    "reason": reason,
                    "evidence_ref": evidence_ref,
                })
        return gate_results

    @staticmethod
    def _build_logs(bundle: dict[str, Any]) -> list[dict[str, Any]]:
        logs: list[dict[str, Any]] = [
            {
                "event": "audit_completed",
                "generated_at": bundle.get("generated_at", ""),
                "audit_basis": bundle.get("audit_basis", ""),
                "compliance_gate_mode": bundle.get("compliance_gate_mode", ""),
                "total_files_scanned": bundle.get("total_files_scanned", 0),
                "accusation_set_count": bundle.get("accusation_set_count", 0),
                "classification_counts": bundle.get("classification_counts", {}),
            }
        ]
        return logs

    @staticmethod
    def _build_decisions(
        accusation_set: list[dict[str, Any]],
        non_accusation_set: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        decisions: list[dict[str, Any]] = []

        for rec in accusation_set:
            sha = rec.get("sha256") or rec.get("document", {}).get("sha256", "")
            ref = sha[:16] if sha else rec.get("file_name", "unknown")
            reasons: list[str] = rec.get("classification_reasons", [])
            support_level = _derive_support_level(rec, "ACCUSATORY")
            decisions.append({
                "decision_id": f"dec-{ref}",
                "classification": "ACCUSATORY",
                "support_level": support_level,
                "evidence_refs": [ref],
                "reasons": reasons,
                "file_name": rec.get("file_name", ""),
                "overall_outcome": rec.get("overall_outcome"),
                "human_responsibility": "RULE_4.1:explicit-human-review-required",
            })

        for rec in non_accusation_set:
            sha = rec.get("sha256") or rec.get("document", {}).get("sha256", "")
            ref = sha[:16] if sha else rec.get("file_name", "unknown")
            reasons = rec.get("classification_reasons", [])
            support_level = _derive_support_level(rec, "NON_ACCUSATORY")
            decisions.append({
                "decision_id": f"dec-{ref}",
                "classification": "NON_ACCUSATORY",
                "support_level": support_level,
                "evidence_refs": [ref],
                "reasons": reasons,
                "file_name": rec.get("file_name", ""),
                "overall_outcome": rec.get("overall_outcome"),
                "human_responsibility": "RULE_4.1:explicit-human-review-required",
            })

        return decisions

    @staticmethod
    def _build_metadata(bundle: dict[str, Any]) -> dict[str, Any]:
        counts: dict[str, Any] = bundle.get("classification_counts", {})
        open_points: list[str] = []

        # Identify open points from unresolved or blocked records
        accusation_set = bundle.get("accusation_set", [])
        for rec in accusation_set:
            outcome = rec.get("overall_outcome")
            if outcome in (None, "BLOCKED", "CONDITIONAL", "RETURNED"):
                open_points.append(
                    f"Artifact '{rec.get('file_name', 'unknown')}' "
                    f"requires human review (outcome={outcome})"
                )

        return {
            "generated_at": bundle.get("generated_at", ""),
            "audit_basis": bundle.get("audit_basis", ""),
            "compliance_gate_mode": bundle.get("compliance_gate_mode", ""),
            "total_files_scanned": bundle.get("total_files_scanned", 0),
            "accusation_set_count": bundle.get("accusation_set_count", 0),
            "classification_counts": counts,
            "open_points": open_points,
            "traceability": {
                "source": "tcria-audit-bundle",
                "rules_applied": ["RULE_4.1", "RULE_2.1"],
                "chain_of_custody": "tcria-to-quinta-ordem",
                "adapter_version": "1.0.0",
            },
            "governance": {
                "human_accountability": "RULE_4.1:required-for-all-accusatory-decisions",
                "evidence_integrity": "RULE_2.1:no-modification-of-original-evidence",
            },
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _derive_support_level(record: dict[str, Any], classification: str) -> str:
    """Derive a support level descriptor from key signals."""
    signals = record.get("key_signals", record.get("signals", {}))
    if not isinstance(signals, dict):
        return "LOW"

    keyword_hits = signals.get("accusation_keyword_hits", {})
    hit_count = sum(keyword_hits.values()) if isinstance(keyword_hits, dict) else 0
    dates = signals.get("dates_found", 0)
    currency = signals.get("currency_values_found", 0)

    score = hit_count + (1 if dates > 0 else 0) + (1 if currency > 0 else 0)

    if score >= 10:
        return "HIGH"
    if score >= 4:
        return "MEDIUM"
    return "LOW"
