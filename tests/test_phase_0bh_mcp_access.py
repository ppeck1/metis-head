from __future__ import annotations

import json
import sys
from typing import Any

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.mcp_access import call_configured_mcp_tool, call_mcp_tool, list_mcp_tools, mcp_status


FAKE_MCP_SERVER = r'''
import json
import os
import sys


def send_message(payload):
    sys.stdout.write(json.dumps(payload, separators=(',', ':')) + '\n')
    sys.stdout.flush()


for line in sys.stdin:
    message = json.loads(line)
    method = message.get('method')
    if method == 'initialize':
        send_message({
            'jsonrpc': '2.0',
            'id': message.get('id'),
            'result': {
                'protocolVersion': '2024-11-05',
                'capabilities': {'tools': {}},
                'serverInfo': {'name': 'fake-mcp', 'version': '0.1'},
            },
        })
    elif method == 'tools/list':
        send_message({
            'jsonrpc': '2.0',
            'id': message.get('id'),
            'result': {
                'tools': [
                    {
                        'name': 'retrieve_context',
                        'description': 'fake read-only retrieval',
                        'inputSchema': {'type': 'object', 'properties': {}},
                    }
                ]
            },
        })
    elif method == 'tools/call':
        arguments = message.get('params', {}).get('arguments', {})
        send_message({
            'jsonrpc': '2.0',
            'id': message.get('id'),
            'result': {
                'content': [
                    {
                        'type': 'text',
                        'text': json.dumps({
                            'tool': message.get('params', {}).get('name'),
                            'query': arguments.get('query'),
                            'token_argument': arguments.get('token'),
                            'secret': os.environ.get('FAKE_TOKEN'),
                        }, sort_keys=True),
                    }
                ],
                'isError': False,
            },
        })
'''


def _enabled_env(server: str = "boh") -> dict[str, str]:
    prefix = "METIS_MCP_BOH" if server == "boh" else "METIS_MCP_ATLAS"
    return {
        "METIS_MCP_ENABLED": "true",
        f"{prefix}_ENABLED": "true",
    }


def test_mcp_status_disabled_by_default_never_exposes_command_values() -> None:
    env = {
        "METIS_MCP_ENABLED": "false",
        "METIS_MCP_BOH_COMMAND": r"C:\private\python.exe",
        "METIS_MCP_BOH_CWD": r"B:\private\Bag.of.holding",
        "METIS_MCP_ATLAS_COMMAND": r"C:\private\dart.exe",
        "METIS_MCP_ATLAS_CWD": r"B:\private\Project_Atlas",
    }

    status = mcp_status(env)
    rendered = json.dumps(status, sort_keys=True)

    assert status["enabled"] is False
    assert status["servers"]["boh"]["command_configured"] is True
    assert status["servers"]["project_atlas"]["cwd_configured"] is True
    assert "C:\\private" not in rendered
    assert "B:\\private" not in rendered
    assert "retrieve_context" in status["servers"]["boh"]["policy"]["read_only_tools"]
    assert "propose_status_change" in status["servers"]["project_atlas"]["policy"]["proposal_tools"]


def test_mcp_read_tool_with_fake_transport_scrubs_inputs_and_outputs() -> None:
    env = _enabled_env("boh") | {"METIS_TEST_SECRET": "secret-from-result"}
    seen: dict[str, Any] = {}

    def fake_transport(server_id: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        seen.update({"server_id": server_id, "tool_name": tool_name, "arguments": arguments})
        return {"body": "result contains secret-from-result", "api_key": "secret-from-result"}

    result = call_mcp_tool(
        "boh",
        "retrieve_context",
        {"query": "metis", "token": "secret-input-token"},
        transport=fake_transport,
        env=env,
    )
    rendered = json.dumps(result, sort_keys=True)

    assert result["status"] == "read_only_complete"
    assert seen["arguments"]["token"] == "***"
    assert "secret-from-result" not in rendered
    assert result["result"]["api_key"] == "***"


def test_atlas_proposal_tools_are_not_called_even_when_enabled() -> None:
    called = False

    def fail_transport(*_: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("proposal tools must not invoke transport")

    result = call_mcp_tool(
        "project_atlas",
        "propose_status_change",
        {"projectId": "metis-head", "status": "active"},
        transport=fail_transport,
        env=_enabled_env("project_atlas"),
    )

    assert result["status"] == "proposal_required"
    assert result["proposal_only"] is True
    assert called is False


def test_unallowlisted_mcp_tool_is_blocked() -> None:
    result = call_mcp_tool("boh", "promote_document", {}, env=_enabled_env("boh"))

    assert result["status"] == "blocked"
    assert result["blocked_reason"] == "mcp_tool_not_allowlisted"
    assert "boh_promotion" in result["blocked_capabilities"]


def test_mcp_tools_endpoint_lists_boh_and_atlas_lanes() -> None:
    tools = list_mcp_tools()["tools"]
    tool_keys = {(tool["server_id"], tool["tool_name"], tool["permission_mode"]) for tool in tools}

    assert ("boh", "retrieve_context", "read_only") in tool_keys
    assert ("project_atlas", "get_project_status", "read_only") in tool_keys
    assert ("project_atlas", "propose_status_change", "proposal_only") in tool_keys


def test_configured_stdio_mcp_endpoint_calls_allowlisted_tool_and_redacts(tmp_path, monkeypatch) -> None:
    server_script = tmp_path / "fake_mcp_server.py"
    server_script.write_text(FAKE_MCP_SERVER)
    monkeypatch.setenv("METIS_MCP_ENABLED", "true")
    monkeypatch.setenv("METIS_MCP_BOH_ENABLED", "true")
    monkeypatch.setenv("METIS_MCP_BOH_COMMAND", sys.executable)
    monkeypatch.setenv("METIS_MCP_BOH_ARGS_JSON", json.dumps([str(server_script)]))
    monkeypatch.setenv("METIS_MCP_BOH_CWD", str(tmp_path))
    monkeypatch.setenv("METIS_MCP_BOH_ENV_JSON", json.dumps({"FAKE_TOKEN": "stdio-secret"}))
    monkeypatch.setenv("METIS_MCP_TIMEOUT_SECONDS", "5")

    with TestClient(app) as client:
        status = client.get("/metis/mcp/status").json()
        response = client.post(
            "/metis/mcp/boh/tools/retrieve_context/call",
            json={"arguments": {"query": "metis", "token": "raw-token"}},
        )

    body = response.json()
    rendered_status = json.dumps(status, sort_keys=True)
    rendered_body = json.dumps(body, sort_keys=True)

    assert response.status_code == 200
    assert status["servers"]["boh"]["transport"] == "external_stdio_configured"
    assert str(server_script) not in rendered_status
    assert body["mcp"]["status"] == "read_only_complete"
    assert "raw-token" not in rendered_body
    assert "stdio-secret" not in rendered_body
    assert "***" in rendered_body


def test_configured_call_without_command_stays_not_configured() -> None:
    result = call_configured_mcp_tool("boh", "retrieve_context", {"query": "metis"}, env=_enabled_env("boh"))

    assert result["status"] == "not_configured"
    assert result["attempted"] is False
