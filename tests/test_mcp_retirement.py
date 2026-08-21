from __future__ import annotations

from fastapi.testclient import TestClient

import mcp_server
from api.mcp_gateway import app


def test_retired_http_gateway_cannot_execute_an_audit() -> None:
    response = TestClient(app).post(
        "/tools/audit-paths",
        json={"paths": ["/tmp/evidence"]},
    )

    assert response.status_code == 410
    assert "retired" in response.json()["detail"]


def test_retired_mcp_exposes_only_retirement_health() -> None:
    assert mcp_server.health()["status"] == "retired_from_audit_plane"
