from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_tool_catalog_exposes_operator_lifecycle_labels() -> None:
    client = _client()

    response = client.get("/metis/tools")

    assert response.status_code == 200
    tools = {tool["tool_id"]: tool for tool in response.json()["tools"]}
    assert tools["math.calculate"]["lifecycle"]["lifecycle_label"] == "dry_run_available"
    assert tools["math.calculate"]["lifecycle"]["execution_result"] == "dry_run_only_not_executed"
    assert tools["git.status"]["lifecycle"]["lifecycle_label"] == "approved_read_only"
    assert "approved_read_only" in tools["filesystem.read"]["lifecycle"]["lifecycle_tags"]
    assert tools["fetch.url_proposed"]["lifecycle"]["lifecycle_label"] == "proposal_only"
    assert "future_only" in tools["fetch.url_proposed"]["lifecycle"]["lifecycle_tags"]
    assert tools["fetch.url_proposed"]["lifecycle"]["execution_result"] == "blocked_after_review"


def test_tool_detail_exposes_same_lifecycle_without_broadening_execution() -> None:
    client = _client()

    detail = client.get("/metis/tools/fetch.url_proposed")
    direct = client.post("/metis/tools/fetch.url_proposed/execute", json={"arguments": {"url": "https://example.com"}})

    assert detail.status_code == 200
    body = detail.json()
    assert body["permission_mode"] == "proposal_only"
    assert body["lifecycle"]["execution_request_allowed"] is False
    assert body["lifecycle"]["execution_result"] == "blocked_after_review"
    assert direct.status_code == 200
    assert direct.json()["execution_allowed"] is False
    assert direct.json()["execution_status"] == "blocked_pending_review"
    assert direct.json()["state"]["external_action_executed"] is False


def test_dashboard_renders_tool_lifecycle_field() -> None:
    client = _client()

    dashboard = client.get("/").text

    assert "tool.lifecycle" in dashboard
    assert "lifecycle_label" in dashboard
