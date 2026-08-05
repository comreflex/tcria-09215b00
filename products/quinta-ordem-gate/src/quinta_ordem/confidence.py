from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

from quinta_ordem.models import ConfidenceBreakdown, ExecutionContext, Finding, Severity

DIMENSIONS = (
    "integrity",
    "traceability",
    "evidence_support",
    "logical_consistency",
    "resolution",
)

PENALTIES = {
    Severity.INFO: 0.01,
    Severity.WARNING: 0.08,
    Severity.HIGH: 0.20,
    Severity.CRITICAL: 1.0,
}


def calculate_breakdown(
    findings: list[Finding],
    context: ExecutionContext | None = None,
    evaluated_verifiers: set[str] | None = None,
) -> ConfidenceBreakdown:
    """Calculate satisfied, evaluated requirements rather than assumed certainty."""

    scores = _coverage_scores(context, evaluated_verifiers)
    grouped: dict[str, list[Finding]] = defaultdict(list)

    if any(
        finding.verifier == "context_validation" and finding.severity == Severity.CRITICAL
        for finding in findings
    ):
        scores = {name: 0.0 for name in DIMENSIONS}

    for finding in findings:
        grouped[finding.verifier].append(finding)

    for verifier, verifier_findings in grouped.items():
        if verifier not in scores:
            continue
        for finding in verifier_findings:
            scores[verifier] = max(0.0, scores[verifier] - PENALTIES[finding.severity])

    return ConfidenceBreakdown(**{key: round(scores[key], 4) for key in DIMENSIONS})


def _coverage_scores(
    context: ExecutionContext | None,
    evaluated_verifiers: set[str] | None,
) -> dict[str, float]:
    if context is None:
        if evaluated_verifiers is None:
            return {name: 1.0 for name in DIMENSIONS}
        return {name: 0.0 for name in DIMENSIONS}

    evaluated = evaluated_verifiers or set()
    metadata = context.metadata if isinstance(context.metadata, Mapping) else {}
    has_decisions = isinstance(context.decisions, list) and bool(context.decisions)
    has_evidence = isinstance(context.evidence, list) and bool(context.evidence)

    return {
        "integrity": float("integrity" in evaluated and has_evidence),
        "traceability": float("traceability" in evaluated and has_decisions),
        "evidence_support": float("evidence_support" in evaluated and has_decisions),
        "logical_consistency": float("logical_consistency" in evaluated),
        "resolution": float(
            "resolution" in evaluated
            and "open_points" in metadata
            and isinstance(metadata.get("open_points"), list)
        ),
    }


def calculate_total(breakdown: ConfidenceBreakdown) -> float:
    weights = {
        "integrity": 0.25,
        "traceability": 0.20,
        "evidence_support": 0.25,
        "logical_consistency": 0.20,
        "resolution": 0.10,
    }

    values = breakdown.as_dict()
    return round(sum(values[key] * weight for key, weight in weights.items()), 4)
