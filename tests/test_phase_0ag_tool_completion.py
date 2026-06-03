from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.schemas import baseline_state
from metis_head.tool_completion import TOOL_COMPLETION_VERSION, calculate_tool_completion


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_tool_completion_reaches_100_for_simulation_first_governed_track() -> None:
    completion = calculate_tool_completion(baseline_state())

    assert completion["schema_version"] == TOOL_COMPLETION_VERSION
    assert completion["domain"] == "governed_tool_track_completion"
    assert completion["track_scope"] == "simulation_first_governed_tool_substrate"
    assert completion["completion_percent"] == 100.0
    assert completion["status"] == "complete"
    assert completion["completed_count"] == completion["total_count"]


def test_tool_completion_is_computed_from_boundary_state() -> None:
    state = baseline_state()
    state["external_action_executed"] = True

    completion = calculate_tool_completion(state)

    assert completion["completion_percent"] < 100.0
    assert completion["status"] == "incomplete"
    assert any(criterion["criterion_id"] == "external_actions_not_executed" and not criterion["complete"] for criterion in completion["criteria"])


def test_tool_completion_keeps_future_live_lanes_out_of_scope() -> None:
    completion = calculate_tool_completion(baseline_state())

    assert "live_url_fetch" in completion["future_out_of_scope_lanes"]
    assert "boh_retrieval_as_tool" in completion["future_out_of_scope_lanes"]
    assert "autonomous_execution" in completion["future_out_of_scope_lanes"]
    assert "future live integrations remain explicitly out of scope" in completion["boundary"]


def test_tool_completion_endpoint_and_dashboard_hook_are_available() -> None:
    client = _client()

    response = client.get("/metis/tools/completion")
    dashboard = client.get("/").text

    assert response.status_code == 200
    assert response.json()["schema_version"] == TOOL_COMPLETION_VERSION
    assert response.json()["completion_percent"] == 100.0
    assert "refreshToolCompletion" in dashboard
    assert "/metis/tools/completion" in dashboard
