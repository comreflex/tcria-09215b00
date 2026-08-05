from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any


class SerializationError(ValueError):
    """Raised when a value cannot be serialized without guessing its meaning."""


def to_jsonable(value: Any) -> Any:
    """Convert supported domain values to deterministic JSON primitives.

    Unknown objects, non-string mapping keys, cycles, sets and non-finite floats are
    rejected. In particular, this function never falls back to ``str(value)``.
    """

    return _to_jsonable(value, path="$", active_ids=set())


def _to_jsonable(value: Any, *, path: str, active_ids: set[int]) -> Any:
    if isinstance(value, Enum):
        return _to_jsonable(value.value, path=path, active_ids=active_ids)

    if value is None or isinstance(value, (bool, int)):
        return value

    if isinstance(value, str):
        _validate_utf8(value, path)
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            raise SerializationError(f"Non-finite float at {path}.")
        return value

    if is_dataclass(value) and not isinstance(value, type):
        object_id = id(value)
        _enter(object_id, path, active_ids)
        try:
            return {
                item.name: _to_jsonable(
                    getattr(value, item.name),
                    path=f"{path}.{item.name}",
                    active_ids=active_ids,
                )
                for item in fields(value)
            }
        finally:
            active_ids.remove(object_id)

    if isinstance(value, Mapping):
        object_id = id(value)
        _enter(object_id, path, active_ids)
        try:
            converted: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise SerializationError(
                        f"Mapping key at {path} must be a string, got {type(key).__name__}."
                    )
                _validate_utf8(key, f"{path}.<key>")
                converted[key] = _to_jsonable(
                    item,
                    path=f"{path}.{key}",
                    active_ids=active_ids,
                )
            return converted
        finally:
            active_ids.remove(object_id)

    if isinstance(value, (list, tuple)):
        object_id = id(value)
        _enter(object_id, path, active_ids)
        try:
            return [
                _to_jsonable(item, path=f"{path}[{index}]", active_ids=active_ids)
                for index, item in enumerate(value)
            ]
        finally:
            active_ids.remove(object_id)

    raise SerializationError(f"Unsupported type at {path}: {type(value).__name__}.")


def _enter(object_id: int, path: str, active_ids: set[int]) -> None:
    if object_id in active_ids:
        raise SerializationError(f"Cyclic reference at {path}.")
    active_ids.add(object_id)


def _validate_utf8(value: str, path: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise SerializationError(f"String at {path} is not valid UTF-8.") from exc


def dumps_json(value: Any) -> str:
    """Serialize a supported value as stable UTF-8 JSON text."""

    payload = to_jsonable(value)
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
