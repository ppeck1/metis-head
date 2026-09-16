from __future__ import annotations

from metis_head import brain
from metis_head.connectors.google_access import GoogleReadBroker
from metis_head.orchestration import AuthorizationContext, CancellationToken, ToolExecutor, ToolRequest
from metis_head.reducer import replay_events
from metis_head.schemas import baseline_state


def test_atlas_off_blocks_stale_ordinary_registry_handler_before_transport(monkeypatch) -> None:
    monkeypatch.setenv("METIS_MCP_ENABLED", "true")
    monkeypatch.setenv("METIS_MCP_ATLAS_ENABLED", "true")
    monkeypatch.setenv("METIS_MCP_ATLAS_COMMAND", r"C:\private\atlas-mcp.exe")
    enabled = replay_events(
        baseline_state(),
        [
            {"type": "tool_control_toggle", "control": "tool_usage", "mode": "read", "enabled": True},
            {"type": "tool_control_toggle", "control": "project_atlas_mcp", "mode": "read", "enabled": True},
        ],
    )
    monkeypatch.setattr(brain, "STATE", enabled)
    entries = brain._personal_tool_entries(GoogleReadBroker({}, {}))
    assert "atlas.project.status" in entries

    calls = []

    def forbidden_transport(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Atlas transport must not run after the operator turns Atlas Off")

    monkeypatch.setattr(brain, "call_configured_mcp_tool", forbidden_transport)
    monkeypatch.setattr(brain, "STATE", baseline_state())
    result = ToolExecutor(entries).execute(
        ToolRequest(
            "atlas-off", "session-1", "turn-1", "atlas.project.status", "1",
            {"project": "Space Nurse"},
        ),
        AuthorizationContext(accounts={}),
        CancellationToken(),
    )

    assert result.status.value == "unavailable"
    assert calls == []


def test_atlas_tools_are_not_advertised_while_control_center_is_off(monkeypatch) -> None:
    monkeypatch.setenv("METIS_MCP_ENABLED", "true")
    monkeypatch.setenv("METIS_MCP_ATLAS_ENABLED", "true")
    monkeypatch.setenv("METIS_MCP_ATLAS_COMMAND", r"C:\private\atlas-mcp.exe")
    monkeypatch.setattr(brain, "STATE", baseline_state())

    entries = brain._personal_tool_entries(GoogleReadBroker({}, {}))

    assert not any(name.startswith("atlas.") for name in entries)
