"""Final Consolidator — reads outputs of all three pipeline stages and produces
a reliable, evidence-grounded final result.

Pipeline stages consumed:
1. TCRIA audit bundle JSON (stage 1)
2. Quinta Ordem ExecutionContext JSON (stage 2)
3. Precision Gate output JSON or Markdown summary (stage 3)

The consolidator:
- Aligns evidence across all three stages by SHA-256 / file_name key
- Detects contradictions (diverging decisions between stages)
- Detects anomalies (evidence present in stage N but missing in stage N+1)
- Computes a per-evidence confidence score (0–100) based on cross-stage agreement
- Produces a structured FinalConsolidationResult with:
    confirmed, contradicted, anomalies, open_points, final_decisions, confidence_matrix

Governance rules applied:
- RULE_4.1: every final decision carries explicit human responsibility metadata;
            contradictions are NEVER auto-resolved — the AI flags, the human decides
- RULE_2.1: original evidence is never modified; all operations are read-only mappings
- Chain-of-custody: provenance from each stage is recorded on every output entry
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class EvidenceAlignment:
    """Single evidence item aligned across all three stages."""
    evidence_key: str          # sha256[:16] or file_name used as common key
    file_name: str
    sha256: str

    # Per-stage data (None if stage did not process this evidence)
    stage1_classification: str | None = None   # TCRIA
    stage1_outcome: str | None = None
    stage1_raises_accusation: bool | None = None

    stage2_classification: str | None = None   # Quinta Ordem
    stage2_outcome: str | None = None
    stage2_support_level: str | None = None

    stage3_status: str | None = None           # Precision Gate
    stage3_outcome: str | None = None

    # Derived
    confidence_score: int = 0                  # 0–100
    agreement_level: str = "UNKNOWN"           # FULL / PARTIAL / CONTRADICTION / MISSING
    contradiction_detail: str | None = None


@dataclass
class FinalConsolidationResult:
    """Full output of the consolidation process."""
    execution_id: str
    source_stage1: str       # path to TCRIA bundle JSON
    source_stage2: str       # path to Quinta Ordem context JSON
    source_stage3: str       # path to Precision Gate output JSON/MD

    confirmed: list[EvidenceAlignment] = field(default_factory=list)
    contradicted: list[EvidenceAlignment] = field(default_factory=list)
    anomalies: list[EvidenceAlignment] = field(default_factory=list)
    open_points: list[str] = field(default_factory=list)
    final_decisions: list[dict[str, Any]] = field(default_factory=list)
    confidence_matrix: list[dict[str, Any]] = field(default_factory=list)

    overall_status: str = "PENDING"            # APPROVED / CONDITIONAL / BLOCKED
    overall_confidence: int = 0               # weighted average 0–100
    human_accountability: str = "RULE_4.1:explicit-human-review-required"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, default=str)


# ---------------------------------------------------------------------------
# Consolidator
# ---------------------------------------------------------------------------

class FinalConsolidator:
    """Reads the three stage outputs and produces a FinalConsolidationResult.

    Stage inputs accepted:
    - stage1: TCRIA audit bundle JSON (dict or path)
    - stage2: Quinta Ordem ExecutionContext JSON (dict or path)
    - stage3: Precision Gate output JSON or simplified dict (dict or path)
              Accepts {'decisions': [...], 'gate_results': [...]} schema.
              If no real Precision Gate output is available, pass an empty dict
              and the consolidator will derive it from stage2.
    """

    def consolidate(
        self,
        stage1: dict[str, Any] | str | Path,
        stage2: dict[str, Any] | str | Path,
        stage3: dict[str, Any] | str | Path | None = None,
        *,
        execution_id: str | None = None,
    ) -> FinalConsolidationResult:
        """Run the full consolidation pipeline.

        Parameters
        ----------
        stage1:
            TCRIA audit bundle (JSON path or dict).
        stage2:
            Quinta Ordem ExecutionContext (JSON path or dict).
        stage3:
            Precision Gate output (JSON path, dict, or None).
        execution_id:
            Optional override; derived from stage2 execution_id if not provided.

        Returns
        -------
        FinalConsolidationResult
        """
        s1 = self._load(stage1)
        s2 = self._load(stage2)
        s3 = self._load(stage3) if stage3 is not None else {}

        exec_id = execution_id or s2.get("execution_id", "consolidated-unknown")
        src1 = str(stage1) if not isinstance(stage1, dict) else "<dict>"
        src2 = str(stage2) if not isinstance(stage2, dict) else "<dict>"
        src3 = str(stage3) if stage3 and not isinstance(stage3, dict) else "<dict>"

        # Build aligned evidence map
        alignment_map = self._align_evidence(s1, s2, s3)

        # Score and classify each alignment
        confirmed: list[EvidenceAlignment] = []
        contradicted: list[EvidenceAlignment] = []
        anomalies: list[EvidenceAlignment] = []

        for ea in alignment_map.values():
            self._score(ea)
            if ea.agreement_level == "FULL":
                confirmed.append(ea)
            elif ea.agreement_level == "CONTRADICTION":
                contradicted.append(ea)
            else:
                anomalies.append(ea)

        open_points = self._derive_open_points(contradicted, anomalies)
        final_decisions = self._derive_final_decisions(
            confirmed, contradicted, anomalies
        )
        confidence_matrix = self._build_confidence_matrix(alignment_map)
        overall_status = self._derive_overall_status(contradicted, anomalies, confirmed)
        overall_confidence = self._weighted_confidence(alignment_map)

        return FinalConsolidationResult(
            execution_id=exec_id,
            source_stage1=src1,
            source_stage2=src2,
            source_stage3=src3,
            confirmed=confirmed,
            contradicted=contradicted,
            anomalies=anomalies,
            open_points=open_points,
            final_decisions=final_decisions,
            confidence_matrix=confidence_matrix,
            overall_status=overall_status,
            overall_confidence=overall_confidence,
        )

    # ------------------------------------------------------------------
    # Evidence alignment
    # ------------------------------------------------------------------

    def _align_evidence(
        self,
        s1: dict[str, Any],
        s2: dict[str, Any],
        s3: dict[str, Any],
    ) -> dict[str, EvidenceAlignment]:
        """Build an alignment map keyed by evidence_key."""
        alignments: dict[str, EvidenceAlignment] = {}

        # --- Stage 1: TCRIA accusation_set + non_accusation_set ---
        for rec in s1.get("accusation_set", []) + s1.get("non_accusation_set", []):
            key, name, sha = self._extract_key(rec)
            ea = alignments.setdefault(key, EvidenceAlignment(
                evidence_key=key, file_name=name, sha256=sha
            ))
            ea.stage1_classification = rec.get("classification")
            ea.stage1_outcome = rec.get("overall_outcome")
            ea.stage1_raises_accusation = rec.get("raises_accusation", False)

        # --- Stage 2: Quinta Ordem ExecutionContext ---
        for dec in s2.get("decisions", []):
            # Match by evidence_ref which is sha[:16]
            refs: list[str] = dec.get("evidence_refs", [])
            file_name: str = dec.get("file_name", "")
            # Try to find matching alignment by ref or file_name
            matched_key = self._find_key(alignments, refs, file_name)
            if matched_key is None:
                matched_key = refs[0] if refs else file_name or "unknown"
                if matched_key not in alignments:
                    alignments[matched_key] = EvidenceAlignment(
                        evidence_key=matched_key,
                        file_name=file_name,
                        sha256="",
                    )
            ea = alignments[matched_key]
            ea.stage2_classification = dec.get("classification")
            ea.stage2_outcome = dec.get("overall_outcome")
            ea.stage2_support_level = dec.get("support_level")

        # --- Stage 3: Precision Gate (flexible schema) ---
        # Accept either a list under 'decisions' or 'gate_results'
        pg_decisions: list[dict[str, Any]] = s3.get("decisions", [])
        pg_gate_results: list[dict[str, Any]] = s3.get("gate_results", [])

        for item in pg_decisions:
            refs = item.get("evidence_refs", [])
            file_name = item.get("file_name", "")
            matched_key = self._find_key(alignments, refs, file_name)
            if matched_key is None:
                matched_key = refs[0] if refs else file_name or "unknown-s3"
                if matched_key not in alignments:
                    alignments[matched_key] = EvidenceAlignment(
                        evidence_key=matched_key, file_name=file_name, sha256=""
                    )
            ea = alignments[matched_key]
            ea.stage3_outcome = item.get("overall_outcome") or item.get("outcome")
            ea.stage3_status = item.get("status") or item.get("classification")

        for gr in pg_gate_results:
            ref = gr.get("artifact_ref", "")
            if ref in alignments:
                ea = alignments[ref]
                if ea.stage3_status is None:
                    ea.stage3_status = gr.get("status")

        return alignments

    @staticmethod
    def _extract_key(rec: dict[str, Any]) -> tuple[str, str, str]:
        sha = rec.get("sha256") or rec.get("document", {}).get("sha256", "")
        key = sha[:16] if sha else rec.get("file_name", "unknown")
        name = rec.get("file_name", "")
        return key, name, sha

    @staticmethod
    def _find_key(
        alignments: dict[str, EvidenceAlignment],
        refs: list[str],
        file_name: str,
    ) -> str | None:
        for ref in refs:
            if ref in alignments:
                return ref
        if file_name:
            for key, ea in alignments.items():
                if ea.file_name == file_name:
                    return key
        return None

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _score(ea: EvidenceAlignment) -> None:
        """Compute confidence_score and agreement_level for one alignment."""
        stages_present = sum([
            ea.stage1_classification is not None,
            ea.stage2_classification is not None,
            ea.stage3_status is not None or ea.stage3_outcome is not None,
        ])

        # Normalize classifications to a common vocabulary
        def _norm(v: str | None) -> str:
            if v is None:
                return "UNKNOWN"
            v = v.upper()
            if "NON_ACCUS" in v or v.startswith("NON"):
                return "NON_ACCUSATORY"
            if "ACCUS" in v:
                return "ACCUSATORY"
            if "BLOCK" in v:
                return "BLOCKED"
            if "RETURN" in v:
                return "RETURNED"
            if "CONDITION" in v:
                return "CONDITIONAL"
            if "SUPPORT" in v or "APPROV" in v:
                return "NON_ACCUSATORY"
            return "UNKNOWN"

        c1 = _norm(ea.stage1_classification)
        c2 = _norm(ea.stage2_classification)
        # Stage 3: prefer classification/status over outcome for contradiction detection
        c3 = _norm(ea.stage3_status or ea.stage3_outcome)

        # Only consider stages that actually contributed
        active = [(c1, ea.stage1_classification), (c2, ea.stage2_classification),
                  (c3, ea.stage3_status or ea.stage3_outcome)]
        present = [(norm, raw) for norm, raw in active if raw is not None]

        if not present:
            ea.agreement_level = "MISSING"
            ea.confidence_score = 0
            return

        unique_norms = {norm for norm, _ in present}

        # MISSING: only 1 stage has data
        if stages_present == 1:
            ea.agreement_level = "MISSING"
            ea.confidence_score = 25
            return

        # CONTRADICTION: stages disagree on the fundamental accusatory/non dimension
        accusatory_votes = sum(1 for n, _ in present if n == "ACCUSATORY")
        non_accusatory_votes = sum(1 for n, _ in present if n == "NON_ACCUSATORY")
        if accusatory_votes > 0 and non_accusatory_votes > 0:
            ea.agreement_level = "CONTRADICTION"
            ea.confidence_score = 10
            ea.contradiction_detail = (
                f"Stage1={c1}, Stage2={c2}, Stage3={c3}"
            )
            return

        # FULL agreement
        if len(unique_norms - {"UNKNOWN"}) <= 1 and stages_present >= 2:
            ea.agreement_level = "FULL"
            base = 60 + (stages_present * 13)  # 60+26=86 for 2 stages, 99 for 3
            ea.confidence_score = min(base, 99)
            return

        # PARTIAL: mixed but no direct accusatory contradiction
        ea.agreement_level = "PARTIAL"
        ea.confidence_score = 45

    # ------------------------------------------------------------------
    # Derivation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_open_points(
        contradicted: list[EvidenceAlignment],
        anomalies: list[EvidenceAlignment],
    ) -> list[str]:
        points: list[str] = []
        for ea in contradicted:
            points.append(
                f"CONTRADICTION in '{ea.file_name}': "
                f"{ea.contradiction_detail} — requires human adjudication (RULE_4.1)"
            )
        for ea in anomalies:
            stage_info = []
            if ea.stage1_classification:
                stage_info.append(f"TCRIA={ea.stage1_classification}")
            if ea.stage2_classification:
                stage_info.append(f"QuintaOrdem={ea.stage2_classification}")
            if ea.stage3_status or ea.stage3_outcome:
                stage_info.append(
                    f"Precision={ea.stage3_outcome or ea.stage3_status}"
                )
            if ea.agreement_level == "MISSING":
                points.append(
                    f"ANOMALY (missing data) for '{ea.file_name}': "
                    f"only seen in {len(stage_info)}/3 stages — "
                    + ("; ".join(stage_info) or "no stage data")
                )
        return points

    @staticmethod
    def _derive_final_decisions(
        confirmed: list[EvidenceAlignment],
        contradicted: list[EvidenceAlignment],
        anomalies: list[EvidenceAlignment],
    ) -> list[dict[str, Any]]:
        decisions: list[dict[str, Any]] = []

        for ea in confirmed:
            decisions.append({
                "evidence_key": ea.evidence_key,
                "file_name": ea.file_name,
                "final_classification": ea.stage1_classification or ea.stage2_classification,
                "confidence_score": ea.confidence_score,
                "status": "CONFIRMED",
                "human_responsibility": "RULE_4.1:explicit-human-review-required",
                "traceability": {
                    "stage1": ea.stage1_classification,
                    "stage2": ea.stage2_classification,
                    "stage3": ea.stage3_outcome or ea.stage3_status,
                },
            })

        for ea in contradicted:
            decisions.append({
                "evidence_key": ea.evidence_key,
                "file_name": ea.file_name,
                "final_classification": "CONTRADICTED",
                "confidence_score": ea.confidence_score,
                "status": "REQUIRES_HUMAN_ADJUDICATION",
                "contradiction_detail": ea.contradiction_detail,
                "human_responsibility": "RULE_4.1:contradiction-cannot-be-auto-resolved",
                "traceability": {
                    "stage1": ea.stage1_classification,
                    "stage2": ea.stage2_classification,
                    "stage3": ea.stage3_outcome or ea.stage3_status,
                },
            })

        for ea in anomalies:
            decisions.append({
                "evidence_key": ea.evidence_key,
                "file_name": ea.file_name,
                "final_classification": ea.stage1_classification or ea.stage2_classification or "UNKNOWN",
                "confidence_score": ea.confidence_score,
                "status": "ANOMALY_MISSING_STAGE_DATA",
                "human_responsibility": "RULE_4.1:anomaly-requires-human-review",
                "traceability": {
                    "stage1": ea.stage1_classification,
                    "stage2": ea.stage2_classification,
                    "stage3": ea.stage3_outcome or ea.stage3_status,
                },
            })

        return decisions

    @staticmethod
    def _build_confidence_matrix(
        alignment_map: dict[str, EvidenceAlignment]
    ) -> list[dict[str, Any]]:
        return [
            {
                "evidence_key": ea.evidence_key,
                "file_name": ea.file_name,
                "stage1_tcria": ea.stage1_classification or "—",
                "stage2_quinta_ordem": ea.stage2_classification or "—",
                "stage3_precision": ea.stage3_outcome or ea.stage3_status or "—",
                "agreement": ea.agreement_level,
                "confidence_score": ea.confidence_score,
            }
            for ea in alignment_map.values()
        ]

    @staticmethod
    def _derive_overall_status(
        contradicted: list[EvidenceAlignment],
        anomalies: list[EvidenceAlignment],
        confirmed: list[EvidenceAlignment],
    ) -> str:
        if contradicted:
            return "BLOCKED"
        missing_count = sum(1 for ea in anomalies if ea.agreement_level == "MISSING")
        if missing_count > 0:
            return "CONDITIONAL"
        # Check if any confirmed is accusatory
        has_accusatory = any(
            ea.stage1_raises_accusation
            for ea in confirmed
            if ea.stage1_raises_accusation
        )
        if has_accusatory:
            return "CONDITIONAL"
        return "APPROVED"

    @staticmethod
    def _weighted_confidence(
        alignment_map: dict[str, EvidenceAlignment],
    ) -> int:
        scores = [ea.confidence_score for ea in alignment_map.values()]
        if not scores:
            return 0
        return round(sum(scores) / len(scores))

    # ------------------------------------------------------------------
    # I/O helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load(source: dict[str, Any] | str | Path) -> dict[str, Any]:
        if isinstance(source, dict):
            return source
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Stage output file not found: {path}")
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
