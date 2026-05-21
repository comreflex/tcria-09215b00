from __future__ import annotations

from enum import Enum


class GovernanceState(str, Enum):
    INGESTED = "INGESTED"
    CLASSIFIED = "CLASSIFIED"
    UNDER_REVIEW = "UNDER_REVIEW"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    PROMOTION_BLOCKED = "PROMOTION_BLOCKED"
    COMPLETED = "COMPLETED"


_TRANSITIONS: dict[GovernanceState, set[GovernanceState]] = {
    GovernanceState.INGESTED: {GovernanceState.CLASSIFIED},
    GovernanceState.CLASSIFIED: {GovernanceState.UNDER_REVIEW},
    GovernanceState.UNDER_REVIEW: {GovernanceState.POLICY_EVALUATED},
    GovernanceState.POLICY_EVALUATED: {GovernanceState.PROMOTION_BLOCKED, GovernanceState.COMPLETED},
    GovernanceState.PROMOTION_BLOCKED: set(),
    GovernanceState.COMPLETED: set(),
}


class GovernanceStateMachine:
    def __init__(self) -> None:
        self.current = GovernanceState.INGESTED

    def transition(self, target: GovernanceState) -> None:
        if target == self.current:
            return
        allowed = _TRANSITIONS.get(self.current, set())
        if target not in allowed:
            raise ValueError(f"Invalid transition: {self.current.value} -> {target.value}")
        self.current = target
