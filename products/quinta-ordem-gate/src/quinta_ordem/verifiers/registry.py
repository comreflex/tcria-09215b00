from __future__ import annotations

from collections.abc import Iterable, Iterator

from quinta_ordem.verifiers.base import Verifier


class VerifierRegistry:
    """Insertion-ordered registry for deterministic verifier execution."""

    def __init__(self, verifiers: Iterable[Verifier] = ()) -> None:
        self._verifiers: dict[str, Verifier] = {}
        for verifier in verifiers:
            self.register(verifier)

    def register(self, verifier: Verifier, *, replace: bool = False) -> None:
        if not isinstance(verifier, Verifier):
            raise TypeError("verifier must implement Verifier.")
        name = getattr(verifier, "name", None)
        if not isinstance(name, str) or not name.strip():
            raise ValueError("verifier.name must be a non-empty string.")
        if name in self._verifiers and not replace:
            raise ValueError(f"Verifier already registered: {name}.")
        self._verifiers[name] = verifier

    def unregister(self, name: str) -> Verifier:
        try:
            return self._verifiers.pop(name)
        except KeyError as exc:
            raise KeyError(f"Verifier not registered: {name}.") from exc

    def get(self, name: str) -> Verifier:
        try:
            return self._verifiers[name]
        except KeyError as exc:
            raise KeyError(f"Verifier not registered: {name}.") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(self._verifiers)

    def values(self) -> tuple[Verifier, ...]:
        return tuple(self._verifiers.values())

    def __iter__(self) -> Iterator[Verifier]:
        return iter(self._verifiers.values())

    def __len__(self) -> int:
        return len(self._verifiers)
