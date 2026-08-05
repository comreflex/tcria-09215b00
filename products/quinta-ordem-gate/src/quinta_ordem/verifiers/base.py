from __future__ import annotations

from abc import ABC, abstractmethod

from quinta_ordem.models import ExecutionContext, Finding


class Verifier(ABC):
    """Extension point for deterministic, side-effect-free checks."""

    name: str

    @abstractmethod
    def verify(self, context: ExecutionContext) -> list[Finding]:
        """Inspect a working snapshot and return explanatory findings."""

        raise NotImplementedError
