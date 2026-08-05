"""API Output Adapter: converts external model outputs to custody decision records."""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class APIOutputAdapter:
    """Convert external model API outputs to Precision Gate decision records.

    Decision records are immutable snapshots that preserve:
    - Original API output (never mutated)
    - Input hash for integrity verification
    - Timestamp and schema version
    """

    schema_version = "1.0"

    def to_decision_record(
        self,
        api_output: Mapping[str, Any],
        *,
        source_model: str = "unknown",
    ) -> dict[str, Any]:
        """Convert an external API output to a decision record.

        Args:
            api_output: The raw output from an external model API.
            source_model: Name of the model that produced the output.

        Returns:
            An immutable decision record dict.
        """
        if not isinstance(api_output, Mapping):
            raise ValueError("api_output must be a mapping.")

        snapshot = deepcopy(dict(api_output))
        input_sha = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, ensure_ascii=False, default=str).encode()
        ).hexdigest()

        record: dict[str, Any] = {
            "schema_version": self.schema_version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_model": source_model,
            "input_sha256": input_sha,
            "api_output_snapshot": snapshot,
        }

        logger.info(
            "APIOutputAdapter: decision record created from model=%s input_sha=%s",
            source_model,
            input_sha,
        )
        return record
