"""Adapters: convert between product output formats."""
from __future__ import annotations

from .tcria_adapter import TCRIAAdapter
from .quinta_ordem_adapter import QuintaOrdemAdapter
from .api_output_adapter import APIOutputAdapter

__all__ = ["TCRIAAdapter", "QuintaOrdemAdapter", "APIOutputAdapter"]
