from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_tool_catalog_exposes_permission_requirements() -> None:
    client = _client()

    response = client.get("/metis/tools")

    assert response.status_code == 200
    tools = {tool["tool_id"]: tool for tool in response.json()["tools"]}
    assert tools["math.calculate"]["permission_requirements"]["required_gates"] == ["schema_valid_arguments", "dry_run_receipt"]
    assert tools["math.calculate"]["permission_requirements"]["requires_human_review"] is False
    assert tools["git.status"]["permission_requirements"]["mode"] == "approved_read_only"
    assert "fixed_no_shell_arguments" in tools["git.status"]["permission_requirements"]["required_gates"]
    assert "arbitrary_git_command" in tools["git.status"]["permission_requirements"]["blocked_capabilities"]
    assert "boh_http_call" in tools["boh.retrieve_proposed"]["permission_requirements"]["blocked_capabilities"]
    assert "operator_token_use" in tools["boh.retrieve_proposed"]["permission_requirements"]["blocked_capabilities"]
    assert tools["boh.retrieve_proposed"]["permission_requirements"]["standing_approval_supported"] is False


def test_tool_detail_permission_requirements_are_visibility_only() -> None:
    client = _client()

    detail = client.get("/metis/tools/boh.retrieve_proposed")
    queued = client.post("/metis/tools/boh.retrieve_proposed/execute", json={"arguments": {"query": "permission test"}})

    assert detail.status_code == 200
    requirements = detail.json()["permission_requirements"]
    assert requirements["requires_human_review"] is True
    assert "execution_after_review" in requirements["blocked_capabilities"]
    assert queued.status_code == 200
    assert queued.json()["execution_allowed"] is False
    assert queued.json()["execution_status"] == "blocked_pending_review"
    assert queued.json()["state"]["external_action_executed"] is False


def test_dashboard_contains_permission_requirements_metadata() -> None:
    client = _client()

    dashboard = client.get("/").text

    assert "permission_requirements" in dashboard
