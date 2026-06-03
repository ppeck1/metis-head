from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.reducer import replay_events
from metis_head.schemas import baseline_state
from metis_head.tool_task_planner import plan_tool_task


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_tool_task_plan_endpoint_persists_reviewable_plan_without_execution() -> None:
    client = _client()

    response = client.post("/metis/tools/task/plan", json={"task": "Check git status and summarize README.md"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "plan_queued"
    assert body["plan"]["review_status"] == "pending"
    assert body["plan"]["execution_allowed"] is False
    assert body["state"]["tool_plan_queue"][0]["plan_id"] == body["plan"]["plan_id"]
    assert body["state"]["pending_approval_count"] == 1
    assert body["state"]["tool_queue_count"] == 1
    assert body["state"]["external_action_executed"] is False


def test_tool_plans_list_and_detail_return_persisted_plan() -> None:
    client = _client()
    queued = client.post("/metis/tools/task/plan", json={"task": "Fetch https://example.com and summarize it"}).json()
    plan_id = queued["plan"]["plan_id"]

    listed = client.get("/metis/tools/plans").json()
    detail = client.get(f"/metis/tools/plans/{plan_id}").json()

    assert listed["total_count"] == 1
    assert listed["plans"][0]["plan_id"] == plan_id
    assert detail["plan"]["plan_id"] == plan_id
    assert any(step["status"] == "future_only_blocked" for step in detail["plan"]["steps"])


def test_tool_plan_replay_is_deterministic() -> None:
    plan = plan_tool_task("Check git status and summarize README.md", baseline_state())
    event = {"type": "tool_plan", "plan": plan}

    first = replay_events(baseline_state(), [event])
    second = replay_events(baseline_state(), [event])

    assert first["tool_plan_queue"] == second["tool_plan_queue"]
    assert first["pending_approval_count"] == second["pending_approval_count"] == 1
    assert first["external_action_executed"] is False


def test_tool_task_plan_can_be_generated_without_persisting() -> None:
    client = _client()

    response = client.post("/metis/tools/task/plan", json={"task": "Plan: prepare a governed tool review", "persist": False})
    state = client.get("/metis/state").json()["state"]

    assert response.status_code == 200
    assert response.json()["status"] == "reviewable_plan"
    assert state["tool_plan_queue"] == []
    assert state["pending_approval_count"] == 0
