from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "tcria-mcp-retired",
    instructions=(
        "The TCRIA MCP audit tools were retired from the UOMS Audit Plane. "
        "Use the Precision Interpretation MCP only after Precision CLOSED."
    ),
)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    }
)
def health() -> dict[str, Any]:
    """Report that TCRIA no longer exposes audit execution through MCP."""

    return {
        "server": "tcria-mcp-retired",
        "status": "retired_from_audit_plane",
        "replacement": "precision_gate.mcp_server after Precision CLOSED",
    }


if __name__ == "__main__":
    mcp.run()
