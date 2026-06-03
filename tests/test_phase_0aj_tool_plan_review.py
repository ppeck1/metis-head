from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.reducer import replay_events
from metis_head.schemas import baseline_state
from metis_head.tool_task_planner import TOOL_PLAN_REVIEW_VERSION, plan_tool_task


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_approve_tool_plan_reviews_without_execution() -> None:
    client = _client()
    queued = client.post("/metis/tools/task/plan", json={"task": "Check git status and summarize README.md"}).json()
    plan_id = queued["plan"]["plan_id"]

    response = client.post(f"/metis/tools/plans/{plan_id}/approve", json={"reason": "operator reviewed plan"})

    assert response.status_code == 200
    body = response.json()
    plan = body["plan"]
    assert body["status"] == "tool_plan_approved"
    assert plan["review_status"] == "approved"
    assert plan["status"] == "reviewed"
    assert plan["execution_allowed"] is False
    assert all(step["execution_allowed"] is False for step in plan["steps"])
    assert body["review_receipt"]["schema_version"] == TOOL_PLAN_REVIEW_VERSION
    assert body["review_receipt"]["execution_allowed"] is False
    assert body["review_receipt"]["execution_status"] == "not_executed"
    assert body["state"]["pending_approval_count"] == 0
    assert body["state"]["tool_queue_count"] == 0
    assert body["state"]["external_action_executed"] is False


def test_deny_tool_plan_updates_counts_and_receipt() -> None:
    client = _client()
    queued = client.post("/metis/tools/task/plan", json={"task": "Fetch https://example.com and summarize it"}).json()
    plan_id = queued["plan"]["plan_id"]

    response = client.post(f"/metis/tools/plans/{plan_id}/deny", json={"reason": "fetch remains future-only"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "tool_plan_denied"
    assert body["plan"]["review_status"] == "denied"
    assert body["plan"]["review_reason"] == "fetch remains future-only"
    assert body["review_receipt"]["decision"] == "denied"
    assert body["review_receipt"]["next_allowed_action"] == "none"
    assert body["state"]["pending_approval_count"] == 0


def test_review_unknown_or_already_reviewed_tool_plan_returns_error() -> None:
    client = _client()

    missing = client.post("/metis/tools/plans/nope/approve", json={})
    assert missing.status_code == 404

    queued = client.post("/metis/tools/task/plan", json={"task": "Plan: prepare a governed tool review"}).json()
    plan_id = queued["plan"]["plan_id"]
    first = client.post(f"/metis/tools/plans/{plan_id}/deny", json={})
    second = client.post(f"/metis/tools/plans/{plan_id}/approve", json={})

    assert first.status_code == 200
    assert second.status_code == 409


def test_tool_plan_review_replay_is_deterministic() -> None:
    plan = plan_tool_task("Check git status and summarize README.md", baseline_state())
    plan_event = {"type": "tool_plan", "plan": plan}
    review_event = {
        "type": "tool_plan_review",
        "plan_id": plan["plan_id"],
        "decision": "approved",
        "reason": "fixed review",
        "reviewed_at": "2026-06-03T12:00:00Z",
    }

    first = replay_events(baseline_state(), [plan_event, review_event])
    second = replay_events(baseline_state(), [plan_event, review_event])

    assert first == second
    assert first["tool_plan_queue"][0]["review_status"] == "approved"
    assert first["tool_plan_queue"][0]["execution_allowed"] is False
    assert first["pending_approval_count"] == 0


def test_dashboard_contains_tool_plan_review_controls() -> None:
    client = _client()

    dashboard = client.get("/").text

    assert "toolPlanSelect" in dashboard
    assert "approveToolPlan" in dashboard
    assert "denyToolPlan" in dashboard
    assert "/metis/tools/plans/" in dashboard
