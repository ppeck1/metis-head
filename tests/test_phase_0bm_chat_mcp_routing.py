from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from metis_head import mcp_chat_bridge
from metis_head.brain import app
from metis_head.mcp_chat_bridge import clear_mcp_chat_cache, route_mcp_chat_read
from metis_head.reducer import replay_events
from metis_head.schemas import baseline_state


MCP_ENV_KEYS = (
    "METIS_MCP_ENABLED",
    "METIS_MCP_BOH_ENABLED",
    "METIS_MCP_BOH_COMMAND",
    "METIS_MCP_BOH_CWD",
    "METIS_MCP_BOH_ENV_JSON",
    "METIS_MCP_ATLAS_ENABLED",
    "METIS_MCP_ATLAS_COMMAND",
    "METIS_MCP_ATLAS_CWD",
    "METIS_MCP_ATLAS_ENV_JSON",
)


def _clear_mcp_env(monkeypatch) -> None:
    for key in MCP_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    clear_mcp_chat_cache()


def _enable_boh(monkeypatch) -> None:
    monkeypatch.setenv("METIS_MCP_ENABLED", "true")
    monkeypatch.setenv("METIS_MCP_BOH_ENABLED", "true")
    monkeypatch.setenv("METIS_MCP_BOH_COMMAND", r"C:\private\python.exe")
    monkeypatch.setenv("METIS_MCP_BOH_CWD", r"B:\private\Bag.of.holding")
    monkeypatch.setenv("METIS_MCP_BOH_ENV_JSON", json.dumps({"BOH_DB": r"B:\private\boh.sqlite", "TOKEN": "secret-token"}))


def _enable_atlas(monkeypatch) -> None:
    monkeypatch.setenv("METIS_MCP_ENABLED", "true")
    monkeypatch.setenv("METIS_MCP_ATLAS_ENABLED", "true")
    monkeypatch.setenv("METIS_MCP_ATLAS_COMMAND", r"C:\private\atlas-mcp.exe")
    monkeypatch.setenv("METIS_MCP_ATLAS_CWD", r"B:\private\Project_Atlas")
    monkeypatch.setenv("METIS_MCP_ATLAS_ENV_JSON", json.dumps({"ATLAS_DB": r"B:\private\atlas.sqlite"}))


def _set_mode(client: TestClient, control: str, mode: str) -> None:
    response = client.post("/metis/control_center/modes", json={"control": control, "mode": mode})
    assert response.status_code == 200


def test_chat_routes_boh_mcp_read_without_llm_or_execution(monkeypatch) -> None:
    _clear_mcp_env(monkeypatch)
    _enable_boh(monkeypatch)
    calls: list[dict[str, Any]] = []

    def fake_call(server_id: str, tool_name: str, arguments: dict[str, Any], *, env: dict[str, str]) -> dict[str, Any]:
        calls.append({"server_id": server_id, "tool_name": tool_name, "arguments": arguments})
        return {
            "status": "read_only_complete",
            "result_hash": "bohhash001",
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "context_packs": [
                                    {
                                        "title": "114 Microbiome Gardener",
                                        "snippet": "Speculative future role; tuning microbial communities through diagnostics and habitat care.",
                                    }
                                ]
                            }
                        ),
                    }
                ]
            },
        }

    monkeypatch.setattr(mcp_chat_bridge, "call_configured_mcp_tool", fake_call)
    with TestClient(app) as client:
        client.post("/metis/state/reset")
        _set_mode(client, "tool_usage", "read")
        _set_mode(client, "boh_mcp", "read")
        response = client.post("/metis/chat", json={"message": "Please check access to the BOH MCP, can you read me a random trade card occupation?"})

    body = response.json()
    rendered = json.dumps(body, sort_keys=True)
    assert response.status_code == 200
    assert body["provider"] == "mcp_chat_bridge"
    assert body["source_state"] == "sourced"
    assert body["mcp_chat_read"]["server_id"] == "boh"
    assert body["mcp_chat_read"]["tool_name"] == "retrieve_context"
    assert "Microbiome Gardener" in body["message"]
    assert "bohhash001" in body["message"]
    assert calls == [{"server_id": "boh", "tool_name": "retrieve_context", "arguments": {"query": "a random trade card occupation", "limit": 3}}]
    assert body["proposal_queued"] is False
    assert body["state"]["approval_queue"] == []
    assert body["state"]["external_action_executed"] is False
    assert body["state"]["event_log"][-2]["type"] == "mcp_chat_read"
    assert body["state"]["event_log"][-2]["result_hash"] == "bohhash001"
    assert body["state"]["event_log"][-1]["provider"] == "mcp_chat_bridge"
    assert r"C:\private" not in rendered
    assert r"B:\private" not in rendered
    assert "secret-token" not in rendered


def test_chat_routes_project_atlas_mcp_read_without_llm(monkeypatch) -> None:
    _clear_mcp_env(monkeypatch)
    _enable_atlas(monkeypatch)
    calls: list[dict[str, Any]] = []

    def fake_call(server_id: str, tool_name: str, arguments: dict[str, Any], *, env: dict[str, str]) -> dict[str, Any]:
        calls.append({"server_id": server_id, "tool_name": tool_name, "arguments": arguments})
        return {
            "status": "read_only_complete",
            "result_hash": "atlashash001",
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"result": {"projects": [{"title": "Metis Head", "status": "active"}]}}),
                    }
                ]
            },
        }

    monkeypatch.setattr(mcp_chat_bridge, "call_configured_mcp_tool", fake_call)
    with TestClient(app) as client:
        client.post("/metis/state/reset")
        _set_mode(client, "tool_usage", "read")
        _set_mode(client, "project_atlas_mcp", "read")
        response = client.post("/metis/chat", json={"message": "Please read Project Atlas MCP project list"})

    body = response.json()
    rendered = json.dumps(body, sort_keys=True)
    assert response.status_code == 200
    assert body["provider"] == "mcp_chat_bridge"
    assert body["mcp_chat_read"]["server_id"] == "project_atlas"
    assert body["mcp_chat_read"]["tool_name"] == "list_projects"
    assert "Metis Head" in body["message"]
    assert calls == [{"server_id": "project_atlas", "tool_name": "list_projects", "arguments": {"limit": 5}}]
    assert r"C:\private" not in rendered
    assert r"B:\private" not in rendered


def test_chat_mcp_read_blocks_when_control_center_read_is_off(monkeypatch) -> None:
    _clear_mcp_env(monkeypatch)
    _enable_boh(monkeypatch)
    called = False

    def fake_call(*_: Any, **__: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("MCP transport should not be called when read mode is off")

    monkeypatch.setattr(mcp_chat_bridge, "call_configured_mcp_tool", fake_call)
    with TestClient(app) as client:
        client.post("/metis/state/reset")
        response = client.post("/metis/chat", json={"message": "Read BOH MCP current state"})

    body = response.json()
    assert response.status_code == 200
    assert body["provider"] == "mcp_chat_bridge"
    assert body["source_state"] == "unsourced"
    assert body["mcp_chat_read"]["status"] == "blocked"
    assert body["mcp_chat_read"]["blocked_reason"] == "mcp_read_off"
    assert called is False
    assert body["state"]["event_log"][-2]["type"] == "mcp_chat_read"


def test_chat_mcp_write_request_remains_proposal_only_without_transport(monkeypatch) -> None:
    _clear_mcp_env(monkeypatch)
    _enable_boh(monkeypatch)
    called = False

    def fake_call(*_: Any, **__: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("write proposal requests must not call MCP transport")

    monkeypatch.setattr(mcp_chat_bridge, "call_configured_mcp_tool", fake_call)
    with TestClient(app) as client:
        client.post("/metis/state/reset")
        _set_mode(client, "tool_usage", "read_write_proposal")
        _set_mode(client, "boh_mcp", "read_write_proposal")
        response = client.post("/metis/chat", json={"message": "Please write an update through BOH MCP"})

    body = response.json()
    assert response.status_code == 200
    assert body["provider"] == "mcp_chat_bridge"
    assert "proposal-only" in body["message"]
    assert body["mcp_chat_read"]["blocked_reason"] == "mcp_write_is_proposal_only"
    assert called is False
    assert body["state"]["external_action_executed"] is False


def test_chat_routes_combined_boh_and_project_atlas_mcp_access(monkeypatch) -> None:
    _clear_mcp_env(monkeypatch)
    _enable_boh(monkeypatch)
    _enable_atlas(monkeypatch)
    calls: list[dict[str, Any]] = []

    def fake_call(server_id: str, tool_name: str, arguments: dict[str, Any], *, env: dict[str, str]) -> dict[str, Any]:
        calls.append({"server_id": server_id, "tool_name": tool_name, "arguments": arguments})
        if server_id == "boh":
            return {
                "status": "read_only_complete",
                "result_hash": "bohstate001",
                "result": {"content": [{"type": "text", "text": json.dumps({"current_state_resource": {"text": "BOH current state ok"}})}]},
            }
        return {
            "status": "read_only_complete",
            "result_hash": "atlashash001",
            "result": {"content": [{"type": "text", "text": json.dumps({"result": {"projects": [{"title": "Metis Head", "status": "active"}]}})}]},
        }

    monkeypatch.setattr(mcp_chat_bridge, "call_configured_mcp_tool", fake_call)
    with TestClient(app) as client:
        client.post("/metis/state/reset")
        _set_mode(client, "tool_usage", "read")
        _set_mode(client, "boh_mcp", "read")
        _set_mode(client, "project_atlas_mcp", "read")
        response = client.post("/metis/chat", json={"message": "test MCP access to BOH and Project Atlas"})

    body = response.json()
    assert response.status_code == 200
    assert body["provider"] == "mcp_chat_bridge"
    assert body["source_state"] == "sourced"
    assert body["mcp_chat_read"]["status"] == "multi_read_complete"
    assert body["mcp_chat_read"]["server_ids"] == ["boh", "project_atlas"]
    assert [read["tool_name"] for read in body["mcp_chat_read"]["reads"]] == ["get_current_state", "list_projects"]
    assert "Combined MCP read complete" in body["message"]
    assert "BOH MCP read complete" in body["message"]
    assert "Project Atlas MCP read complete" in body["message"]
    assert "bohstate001" in body["message"]
    assert "atlashash001" in body["message"]
    assert calls == [
        {"server_id": "boh", "tool_name": "get_current_state", "arguments": {}},
        {"server_id": "project_atlas", "tool_name": "list_projects", "arguments": {"limit": 5}},
    ]
    latest_events = body["state"]["event_log"][-3:]
    assert [event["type"] for event in latest_events] == ["mcp_chat_read", "mcp_chat_read", "chat_event"]
    assert [event["server_id"] for event in latest_events[:2]] == ["boh", "project_atlas"]
    assert body["state"]["external_action_executed"] is False


def test_mcp_chat_bridge_uses_short_ttl_cache_for_identical_reads(monkeypatch) -> None:
    _clear_mcp_env(monkeypatch)
    env = {
        "METIS_MCP_ENABLED": "true",
        "METIS_MCP_BOH_ENABLED": "true",
        "METIS_MCP_BOH_COMMAND": r"C:\private\python.exe",
    }
    state = replay_events(
        baseline_state(),
        [
            {"type": "tool_control_toggle", "control": "tool_usage", "mode": "read", "enabled": True},
            {"type": "tool_control_toggle", "control": "boh_mcp", "mode": "read", "enabled": True},
        ],
    )
    call_count = 0

    def fake_call(server_id: str, tool_name: str, arguments: dict[str, Any], *, env: dict[str, str]) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return {
            "status": "read_only_complete",
            "result_hash": "cachehash001",
            "result": {"content": [{"type": "text", "text": json.dumps({"context_packs": [{"title": "Cached Card"}]})}]},
        }

    first = route_mcp_chat_read("read BOH MCP trade card occupation", state, env=env, call_tool=fake_call)
    second = route_mcp_chat_read("read BOH MCP trade card occupation", state, env=env, call_tool=fake_call)

    assert first is not None
    assert second is not None
    assert call_count == 1
    assert first["metadata"]["cache_hit"] is False
    assert second["metadata"]["cache_hit"] is True
