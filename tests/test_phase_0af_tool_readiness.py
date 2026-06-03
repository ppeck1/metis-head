from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.schemas import baseline_state
from metis_head.tool_readiness import TOOL_READINESS_VERSION, calculate_tool_readiness


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_tool_readiness_score_is_computed_and_domain_labeled() -> None:
    readiness = calculate_tool_readiness(baseline_state())

    assert readiness["schema_version"] == TOOL_READINESS_VERSION
    assert readiness["domain"] == "governed_tool_readiness"
    assert readiness["score"] == readiness["passed_count"] / readiness["total_count"]
    assert readiness["status"] == "ready"
    assert {check["domain"] for check in readiness["checks"]} >= {"registry", "schema", "governance", "execution_boundary", "review", "audit"}


def test_tool_readiness_reflects_failed_execution_boundary() -> None:
    state = baseline_state()
    state["external_action_executed"] = True

    readiness = calculate_tool_readiness(state)
    failed = [check for check in readiness["checks"] if not check["passed"]]

    assert readiness["status"] == "incomplete"
    assert readiness["score"] < 1.0
    assert failed[0]["check_id"] == "no_external_action_executed"


def test_tool_readiness_endpoint_tracks_review_scope_and_dashboard_hook() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "time.now", "arguments": {"timezone": "UTC"}}).json()
    proposal_id = queued["proposal"]["proposal_id"]
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "readiness scope"})

    response = client.get("/metis/tools/readiness")
    dashboard = client.get("/").text

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == TOOL_READINESS_VERSION
    assert body["status"] == "ready"
    assert "refreshToolReadiness" in dashboard
    assert "/metis/tools/readiness" in dashboard
