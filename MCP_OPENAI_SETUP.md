# TCRIA MCP Server — retired from the Audit Plane

TCRIA no longer exposes audit execution or artifact access through MCP. The approved UOMS path is
the authenticated `POST /uoms/tcria/open` boundary, followed by a closed, hash-bound handoff to
Quinta Ordem.

`mcp_server.py` retains only a read-only `health` tool that reports the retirement. It cannot start
an audit or read an artifact. The retired FastAPI MCP gateway routes return HTTP 410.

MCP is available only from `precision_gate.mcp_server` after a complete
`TCRIA → Quinta Ordem → Precision` run has reached `Precision CLOSED`. Any model output produced
there is a new derived interpretation and never a native result of an auditor.
