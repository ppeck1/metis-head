from __future__ import annotations

import json

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.reducer import replay_events
from metis_head.schemas import baseline_state


MCP_ENV_KEYS = (
    "METIS_MCP_ENABLED",
    "METIS_MCP_BOH_ENABLED",
    "METIS_MCP_BOH_COMMAND",
    "METIS_MCP_BOH_CWD",
    "METIS_MCP_ATLAS_ENABLED",
    "METIS_MCP_ATLAS_COMMAND",
    "METIS_MCP_ATLAS_CWD",
)


def _clear_mcp_env(monkeypatch) -> None:
    for key in MCP_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_control_center_defaults_off_and_never_exposes_mcp_config(monkeypatch) -> None:
    _clear_mcp_env(monkeypatch)
    monkeypatch.setenv("METIS_MCP_BOH_COMMAND", r"C:\private\python.exe")
    monkeypatch.setenv("METIS_MCP_BOH_CWD", r"B:\private\Bag.of.holding")
    with TestClient(app) as client:
        client.post("/metis/state/reset")
        body = client.get("/metis/control_center").json()

    rendered = json.dumps(body, sort_keys=True)
    assert body["schema_version"] == "metis_control_center.v0.2"
    assert body["controls"]["tool_usage"]["status"] == "off"
    assert body["mcp"]["servers"]["boh"]["status"] == "off"
    assert body["mcp"]["servers"]["boh"]["configured"] is True
    assert body["execution_allowed"] is False
    assert "C:\\private" not in rendered
    assert "B:\\private" not in rendered


def test_control_center_toggle_records_operator_intent_without_execution(monkeypatch) -> None:
    _clear_mcp_env(monkeypatch)
    with TestClient(app) as client:
        client.post("/metis/state/reset")
        tool_response = client.post("/metis/control_center/toggles", json={"control": "tool_usage", "enabled": True})
        boh_response = client.post("/metis/control_center/toggles", json={"control": "boh_mcp", "enabled": True})

    tool_body = tool_response.json()
    boh_body = boh_response.json()
    state = boh_body["state"]
    assert tool_response.status_code == 200
    assert boh_response.status_code == 200
    assert tool_body["control_center"]["controls"]["tool_usage"]["status"] == "requested"
    assert state["tool_control_center"]["tool_usage_requested"] is True
    assert state["tool_control_center"]["boh_mcp_requested"] is True
    assert state["event_log"][-1]["type"] == "tool_control_toggle"
    assert state["external_action_executed"] is False
    assert boh_body["control_center"]["mcp"]["servers"]["boh"]["status"] == "global_disabled"


def test_control_center_reports_usable_when_mcp_env_gates_are_configured(monkeypatch) -> None:
    _clear_mcp_env(monkeypatch)
    monkeypatch.setenv("METIS_MCP_ENABLED", "true")
    monkeypatch.setenv("METIS_MCP_BOH_ENABLED", "true")
    monkeypatch.setenv("METIS_MCP_BOH_COMMAND", r"C:\private\python.exe")
    with TestClient(app) as client:
        client.post("/metis/state/reset")
        client.post("/metis/control_center/toggles", json={"control": "tool_usage", "enabled": True})
        response = client.post("/metis/control_center/toggles", json={"control": "boh_mcp", "enabled": True})

    body = response.json()
    rendered = json.dumps(body, sort_keys=True)
    boh = body["control_center"]["mcp"]["servers"]["boh"]
    assert response.status_code == 200
    assert boh["status"] == "usable"
    assert boh["running"] is True
    assert boh["usable"] is True
    assert body["control_center"]["execution_allowed"] is False
    assert "C:\\private" not in rendered


def test_tool_control_toggle_replay_is_deterministic() -> None:
    events = [
        {"type": "tool_control_toggle", "control": "tool_usage", "enabled": True, "toggled_at": "2026-07-01T00:00:00Z"},
        {"type": "tool_control_toggle", "control": "project_atlas_mcp", "enabled": True, "toggled_at": "2026-07-01T00:00:01Z"},
    ]

    first = replay_events(baseline_state(), events)
    second = replay_events(baseline_state(), events)

    assert first == second
    assert first["tool_control_center"]["tool_usage_requested"] is True
    assert first["tool_control_center"]["project_atlas_mcp_requested"] is True
    assert first["external_action_executed"] is False


def test_dashboard_contains_control_center_below_virtual_chat() -> None:
    with TestClient(app) as client:
        dashboard = client.get("/").text

    virtual_chat = dashboard.index("Virtual Chat")
    control_center = dashboard.index("toolControlCenter")
    voice_trace = dashboard.index("Voice Trace")
    assert virtual_chat < control_center < voice_trace
    assert "bohMcpMode" in dashboard
    assert "atlasMcpMode" in dashboard
    assert "/metis/control_center" in dashboard
