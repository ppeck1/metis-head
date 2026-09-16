from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.reducer import replay_events
from metis_head.schemas import baseline_state


MCP_ENV_KEYS = (
    "METIS_MCP_ENABLED",
    "METIS_MCP_BOH_ENABLED",
    "METIS_MCP_BOH_COMMAND",
    "METIS_MCP_ATLAS_ENABLED",
    "METIS_MCP_ATLAS_COMMAND",
)


def _clear_mcp_env(monkeypatch) -> None:
    for key in MCP_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_control_center_modes_record_read_write_and_both_without_apply(monkeypatch) -> None:
    _clear_mcp_env(monkeypatch)
    with TestClient(app) as client:
        client.post("/metis/state/reset")
        client.post("/metis/control_center/modes", json={"control": "tool_usage", "mode": "read_write_proposal"})
        boh = client.post("/metis/control_center/modes", json={"control": "boh_mcp", "mode": "write_proposal"}).json()
        atlas = client.post("/metis/control_center/modes", json={"control": "project_atlas_mcp", "mode": "read_write_proposal"}).json()

    state = atlas["state"]["tool_control_center"]
    assert state["tool_usage_mode"] == "read_write_proposal"
    assert state["boh_mcp_mode"] == "write_proposal"
    assert state["project_atlas_mcp_mode"] == "read_write_proposal"
    assert boh["control_center"]["mcp"]["servers"]["boh"]["write_status"] == "proposal_ready"
    assert atlas["control_center"]["mcp"]["servers"]["project_atlas"]["read_status"] == "global_disabled"
    assert atlas["control_center"]["mcp"]["servers"]["project_atlas"]["write_status"] == "proposal_ready"
    assert atlas["control_center"]["write_apply_allowed"] is False
    assert atlas["state"]["external_action_executed"] is False


def test_read_write_mode_reports_ready_when_read_env_and_write_proposal_are_available(monkeypatch) -> None:
    _clear_mcp_env(monkeypatch)
    monkeypatch.setenv("METIS_MCP_ENABLED", "true")
    monkeypatch.setenv("METIS_MCP_ATLAS_ENABLED", "true")
    monkeypatch.setenv("METIS_MCP_ATLAS_COMMAND", r"C:\private\atlas-mcp.exe")
    with TestClient(app) as client:
        client.post("/metis/state/reset")
        client.post("/metis/control_center/modes", json={"control": "tool_usage", "mode": "read_write_proposal"})
        response = client.post("/metis/control_center/modes", json={"control": "project_atlas_mcp", "mode": "read_write_proposal"})

    atlas = response.json()["control_center"]["mcp"]["servers"]["project_atlas"]
    assert atlas["read_status"] == "usable"
    assert atlas["write_status"] == "proposal_ready"
    assert atlas["status"] == "read_write_ready"
    assert atlas["write_apply_allowed"] is False


def test_invalid_control_center_mode_is_rejected() -> None:
    with TestClient(app) as client:
        client.post("/metis/state/reset")
        response = client.post("/metis/control_center/modes", json={"control": "boh_mcp", "mode": "write_apply"})

    assert response.status_code == 400
    assert "unknown control-center mode" in response.json()["detail"]


def test_tool_control_mode_replay_is_deterministic() -> None:
    events = [
        {"type": "tool_control_toggle", "control": "tool_usage", "mode": "read_write_proposal", "enabled": True},
        {"type": "tool_control_toggle", "control": "project_atlas_mcp", "mode": "write_proposal", "enabled": True},
    ]

    first = replay_events(baseline_state(), events)
    second = replay_events(baseline_state(), events)

    assert first == second
    assert first["tool_control_center"]["tool_usage_mode"] == "read_write_proposal"
    assert first["tool_control_center"]["project_atlas_mcp_mode"] == "write_proposal"
    assert first["tool_control_center"]["project_atlas_mcp_requested"] is True
    assert first["external_action_executed"] is False


def test_dashboard_uses_mode_selectors_for_control_center() -> None:
    with TestClient(app) as client:
        dashboard = client.get("/").text

    assert "toolUsageMode" in dashboard
    assert "bohMcpMode" in dashboard
    assert "atlasMcpMode" in dashboard
    assert "read_write_proposal" in dashboard
    assert "/metis/control_center/modes" in dashboard
