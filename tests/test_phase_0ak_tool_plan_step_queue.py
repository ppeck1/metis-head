from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.reducer import reduce_metis_event, replay_events
from metis_head.schemas import baseline_state
from metis_head.tool_registry import build_tool_proposal_event
from metis_head.tool_task_planner import plan_tool_task


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def _approved_plan(client: TestClient, task: str = "Check git status and summarize README.md") -> str:
    queued = client.post("/metis/tools/task/plan", json={"task": task}).json()
    plan_id = queued["plan"]["plan_id"]
    reviewed = client.post(f"/metis/tools/plans/{plan_id}/approve", json={"reason": "reviewed plan"}).json()
    assert reviewed["plan"]["review_status"] == "approved"
    return plan_id


def test_approved_tool_plan_queues_step_proposals_without_execution() -> None:
    client = _client()
    plan_id = _approved_plan(client)

    response = client.post(f"/metis/tools/plans/{plan_id}/queue_steps", json={"reason": "operator requested step proposals"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "plan_step_proposals_queued"
    assert len(body["queued_steps"]) == 3
    assert [proposal["tool_id"] for proposal in body["queued_proposals"]] == ["git.status", "filesystem.read", "text.summarize"]
    assert all(proposal["execution_allowed"] is False for proposal in body["queued_proposals"])
    assert body["plan"]["status"] == "steps_queued"
    assert body["plan"]["materialized_step_count"] == 3
    assert body["state"]["pending_approval_count"] == 3
    assert body["state"]["tool_queue_count"] == 3
    assert body["state"]["external_action_executed"] is False


def test_tool_plan_steps_require_approved_plan() -> None:
    client = _client()
    queued = client.post("/metis/tools/task/plan", json={"task": "Check git status"}).json()
    plan_id = queued["plan"]["plan_id"]

    unreviewed = client.post(f"/metis/tools/plans/{plan_id}/queue_steps", json={})
    client.post(f"/metis/tools/plans/{plan_id}/deny", json={})
    denied = client.post(f"/metis/tools/plans/{plan_id}/queue_steps", json={})

    assert unreviewed.status_code == 409
    assert denied.status_code == 409


def test_tool_plan_step_queue_is_idempotent_for_already_queued_steps() -> None:
    client = _client()
    plan_id = _approved_plan(client)

    first = client.post(f"/metis/tools/plans/{plan_id}/queue_steps", json={}).json()
    second = client.post(f"/metis/tools/plans/{plan_id}/queue_steps", json={}).json()

    assert len(first["queued_steps"]) == 3
    assert second["status"] == "no_plan_steps_queued"
    assert second["queued_steps"] == []
    assert len(second["skipped_steps"]) == 3
    assert second["state"]["pending_approval_count"] == 3


def test_tool_plan_step_queue_replay_is_deterministic() -> None:
    base = baseline_state()
    plan = plan_tool_task("Check git status and summarize README.md", base)
    plan_event = {"type": "tool_plan", "plan": plan}
    review_event = {
        "type": "tool_plan_review",
        "plan_id": plan["plan_id"],
        "decision": "approved",
        "reason": "fixed review",
        "reviewed_at": "2026-06-03T12:00:00Z",
    }
    reviewed_state = replay_events(base, [plan_event, review_event])
    proposal_events = []
    queued_steps = []
    rolling_state = reviewed_state
    for step in reviewed_state["tool_plan_queue"][0]["steps"]:
        event = build_tool_proposal_event(step["tool_id"], step.get("arguments") or {}, rolling_state, f"plan {plan['plan_id']} {step['step_id']}")
        rolling_state = reduce_metis_event(rolling_state, event)
        proposal_events.append(event)
        queued_steps.append({"step_id": step["step_id"], "tool_id": step["tool_id"], "proposal_id": rolling_state["approval_queue"][-1]["proposal_id"]})
    materialized_event = {
        "type": "tool_plan_step_queue",
        "plan_id": plan["plan_id"],
        "queued_steps": queued_steps,
        "queued_at": "2026-06-03T12:01:00Z",
    }

    events = [plan_event, review_event, *proposal_events, materialized_event]
    first = replay_events(base, events)
    second = replay_events(base, events)

    assert first == second
    assert first["tool_plan_queue"][0]["materialized_step_count"] == 3
    assert first["pending_approval_count"] == 3
    assert first["external_action_executed"] is False


def test_dashboard_contains_tool_plan_step_queue_control() -> None:
    client = _client()

    dashboard = client.get("/").text

    assert "queueToolPlanSteps" in dashboard
    assert "/metis/tools/plans/" in dashboard
    assert "queue_steps" in dashboard
