from __future__ import annotations

from tcria.runtime import GovernanceEventType, GovernanceRuntime, GovernanceState
from tcria.runtime.policies import evaluate_governance_policies


def test_policy_reads_accusation_set_and_blocks_promotion() -> None:
    bundle = {
        "accusation_set": [
            {
                "overall_outcome": "BLOCKED (complianceGate)",
                "gates": {
                    "complianceGate": {"status": "BLOCKED", "reason": "missing metadata"},
                },
            }
        ]
    }
    result = evaluate_governance_policies(bundle)
    assert result.allow_promotion is False
    assert result.blocked_records == 1
    assert result.total_records == 1


def test_skip_audit_transition_path_is_valid() -> None:
    runtime = GovernanceRuntime()
    runtime.transition(GovernanceState.CLASSIFIED)
    runtime.transition(GovernanceState.UNDER_REVIEW)
    runtime.transition(GovernanceState.POLICY_EVALUATED)
    runtime.transition(GovernanceState.COMPLETED)
    assert runtime.state.current == GovernanceState.COMPLETED


def test_telemetry_counts_artifact_keys() -> None:
    runtime = GovernanceRuntime()
    runtime.emit(
        event_type=GovernanceEventType.ARTIFACT_GENERATED,
        message="artifact emitted",
        payload={
            "audit_json": "/tmp/audit.json",
            "review_json": "/tmp/review.json",
            "review_md": "/tmp/review.md",
        },
    )
    snapshot = runtime.telemetry.snapshot()
    assert snapshot.event_count == 1
    assert snapshot.artifact_count == 3


def test_telemetry_counts_blocked_from_payload_signals() -> None:
    runtime = GovernanceRuntime()
    runtime.emit(
        event_type=GovernanceEventType.POLICY_EVALUATED,
        message="policy evaluated with blocked records",
        payload={"allow_promotion": False, "blocked_records": 2, "total_records": 3},
    )
    snapshot = runtime.telemetry.snapshot()
    assert snapshot.event_count == 1
    assert snapshot.blocked_event_count == 1
