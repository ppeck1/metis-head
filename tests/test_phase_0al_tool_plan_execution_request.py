from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.reducer import replay_events
from metis_head.schemas import baseline_state
from metis_head.tool_registry import build_tool_proposal_event
from metis_head.tool_task_planner import plan_tool_task


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def _approved_plan_with_queued_git_step(client: TestClient) -> tuple[str, str]:
    queued = client.post("/metis/tools/task/plan", json={"task": "Check git status"}).json()
    plan_id = queued["plan"]["plan_id"]
    client.post(f"/metis/tools/plans/{plan_id}/approve", json={"reason": "reviewed plan"})
    materialized = client.post(f"/metis/tools/plans/{plan_id}/queue_steps", json={"reason": "queue step proposals"}).json()
    proposal_id = materialized["queued_proposals"][0]["proposal_id"]
    return plan_id, proposal_id


def test_approved_plan_requests_execution_for_approved_step_proposals_only() -> None:
    client = _client()
    plan_id, proposal_id = _approved_plan_with_queued_git_step(client)
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "approve read-only step"})

    response = client.post(f"/metis/tools/plans/{plan_id}/request_execution", json={"reason": "run approved read-only plan step"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "plan_execution_requested"
    assert len(body["executed_steps"]) == 1
    assert body["receipts"][0]["proposal_id"] == proposal_id
    assert body["receipts"][0]["execution_status"] == "executed_read_only"
    assert body["receipts"][0]["execution_allowed"] is False
    assert body["plan"]["status"] == "execution_requested"
    assert body["plan"]["execution_request_count"] == 1
    assert body["state"]["external_action_executed"] is False


def test_plan_execution_request_skips_unapproved_step_proposals() -> None:
    client = _client()
    plan_id, proposal_id = _approved_plan_with_queued_git_step(client)

    response = client.post(f"/metis/tools/plans/{plan_id}/request_execution", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_plan_execution_requested"
    assert body["receipts"] == []
    assert body["skipped_steps"][0]["proposal_id"] == proposal_id
    assert body["skipped_steps"][0]["reason"] == "proposal_not_approved"
    assert body["state"]["execution_audit_log"] == []


def test_plan_execution_request_is_idempotent_for_already_requested_steps() -> None:
    client = _client()
    plan_id, proposal_id = _approved_plan_with_queued_git_step(client)
    client.post(f"/metis/proposals/{proposal_id}/approve", json={})

    first = client.post(f"/metis/tools/plans/{plan_id}/request_execution", json={}).json()
    second = client.post(f"/metis/tools/plans/{plan_id}/request_execution", json={}).json()

    assert first["status"] == "plan_execution_requested"
    assert second["status"] == "no_plan_execution_requested"
    assert second["skipped_steps"][0]["reason"] == "already_requested"
    assert second["state"]["external_action_executed"] is False


def test_tool_plan_execution_request_replay_is_deterministic() -> None:
    base = baseline_state()
    plan = plan_tool_task("Check git status", base)
    plan_event = {"type": "tool_plan", "plan": plan}
    review_event = {
        "type": "tool_plan_review",
        "plan_id": plan["plan_id"],
        "decision": "approved",
        "reason": "fixed review",
        "reviewed_at": "2026-06-03T12:00:00Z",
    }
    reviewed = replay_events(base, [plan_event, review_event])
    step = reviewed["tool_plan_queue"][0]["steps"][0]
    proposal_event = build_tool_proposal_event(step["tool_id"], step.get("arguments") or {}, reviewed, "plan step")
    proposed = replay_events(base, [plan_event, review_event, proposal_event])
    proposal_id = proposed["approval_queue"][0]["proposal_id"]
    queue_event = {
        "type": "tool_plan_step_queue",
        "plan_id": plan["plan_id"],
        "queued_steps": [{"step_id": step["step_id"], "tool_id": step["tool_id"], "proposal_id": proposal_id}],
        "queued_at": "2026-06-03T12:01:00Z",
    }
    proposal_review_event = {
        "type": "proposal_review",
        "proposal_id": proposal_id,
        "decision": "approved",
        "reason": "fixed step review",
        "reviewed_at": "2026-06-03T12:02:00Z",
    }
    execution_event = {
        "type": "execution_request",
        "proposal_id": proposal_id,
        "reason": "fixed execution request",
        "requested_at": "2026-06-03T12:03:00Z",
        "read_only_result": {"branch": "main", "status": "clean"},
    }
    receipt_id = replay_events(base, [plan_event, review_event, proposal_event, queue_event, proposal_review_event, execution_event])[
        "execution_audit_log"
    ][0]["receipt_id"]
    plan_execution_event = {
        "type": "tool_plan_execution_request",
        "plan_id": plan["plan_id"],
        "executed_steps": [
            {"step_id": step["step_id"], "proposal_id": proposal_id, "receipt_id": receipt_id, "execution_status": "executed_read_only"}
        ],
        "requested_at": "2026-06-03T12:04:00Z",
    }

    events = [plan_event, review_event, proposal_event, queue_event, proposal_review_event, execution_event, plan_execution_event]
    first = replay_events(base, events)
    second = replay_events(base, events)

    assert first == second
    assert first["tool_plan_queue"][0]["execution_request_count"] == 1
    assert first["tool_plan_queue"][0]["steps"][0]["execution_status"] == "executed_read_only"
    assert first["external_action_executed"] is False


def test_dashboard_contains_tool_plan_execution_request_control() -> None:
    client = _client()

    dashboard = client.get("/").text

    assert "requestToolPlanExecution" in dashboard
    assert "request_execution" in dashboard
