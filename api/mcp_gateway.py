from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, status

app = FastAPI(
    title="TCRIA MCP HTTP Gateway — retired",
    version="1.0.0",
    description="TCRIA MCP was removed from the UOMS Audit Plane.",
)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "retired_from_audit_plane",
        "service": "tcria-mcp-http-gateway-retired",
        "replacement": "precision_gate.mcp_server after Precision CLOSED",
    }


@app.api_route(
    "/{retired_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
def retired_gateway(retired_path: str) -> None:
    del retired_path
    raise HTTPException(
        status.HTTP_410_GONE,
        "TCRIA MCP audit access was retired from the UOMS Audit Plane. "
        "Use the Precision Interpretation MCP only after Precision CLOSED.",
    )
