from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.tool_plan_runner import PLAN_ADVANCE_VERSION, next_plan_action
from metis_head.tool_task_planner import plan_tool_task
from metis_head.schemas import baseline_state


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_advance_reports_plan_review_gate_without_mutation() -> None:
    client = _client()
    queued = client.post("/metis/tools/task/plan", json={"task": "Check git status"}).json()
    plan_id = queued["plan"]["plan_id"]

    response = client.post(f"/metis/tools/plans/{plan_id}/advance", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "waiting"
    assert body["next_action"]["schema_version"] == PLAN_ADVANCE_VERSION
    assert body["next_action"]["action"] == "needs_plan_review"
    assert body["state"]["approval_queue"] == []
    assert body["state"]["external_action_executed"] is False


def test_advance_queues_step_proposals_after_plan_approval() -> None:
    client = _client()
    queued = client.post("/metis/tools/task/plan", json={"task": "Check git status"}).json()
    plan_id = queued["plan"]["plan_id"]
    client.post(f"/metis/tools/plans/{plan_id}/approve", json={"reason": "reviewed plan"})

    response = client.post(f"/metis/tools/plans/{plan_id}/advance", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "advanced"
    assert body["advanced_action"]["action"] == "can_queue_step_proposals"
    assert body["result"]["status"] == "plan_step_proposals_queued"
    assert body["next_action"]["action"] == "needs_step_proposal_review"
    assert body["result"]["state"]["pending_approval_count"] == 1
    assert body["result"]["state"]["external_action_executed"] is False


def test_advance_requests_execution_only_after_step_proposal_approval() -> None:
    client = _client()
    queued = client.post("/metis/tools/task/plan", json={"task": "Check git status"}).json()
    plan_id = queued["plan"]["plan_id"]
    client.post(f"/metis/tools/plans/{plan_id}/approve", json={})
    advanced = client.post(f"/metis/tools/plans/{plan_id}/advance", json={}).json()
    proposal_id = advanced["result"]["queued_proposals"][0]["proposal_id"]

    waiting = client.post(f"/metis/tools/plans/{plan_id}/advance", json={}).json()
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "approve step"})
    executed = client.post(f"/metis/tools/plans/{plan_id}/advance", json={}).json()

    assert waiting["status"] == "waiting"
    assert waiting["next_action"]["action"] == "needs_step_proposal_review"
    assert executed["status"] == "advanced"
    assert executed["advanced_action"]["action"] == "can_request_step_execution"
    assert executed["result"]["receipts"][0]["execution_status"] == "executed_read_only"
    assert executed["next_action"]["action"] == "complete_for_current_scope"
    assert executed["result"]["state"]["external_action_executed"] is False


def test_advance_binds_results_before_dependent_step_review() -> None:
    client = _client()
    queued = client.post("/metis/tools/task/plan", json={"task": "Summarize pyproject.toml"}).json()
    plan_id = queued["plan"]["plan_id"]
    client.post(f"/metis/tools/plans/{plan_id}/approve", json={})
    materialized = client.post(f"/metis/tools/plans/{plan_id}/advance", json={}).json()
    fs_proposal = next(proposal for proposal in materialized["result"]["queued_proposals"] if proposal["tool_id"] == "filesystem.read")
    client.post(f"/metis/proposals/{fs_proposal['proposal_id']}/approve", json={"reason": "approve source read"})
    client.post(f"/metis/tools/plans/{plan_id}/advance", json={})

    bound = client.post(f"/metis/tools/plans/{plan_id}/advance", json={}).json()

    assert bound["status"] == "advanced"
    assert bound["advanced_action"]["action"] == "can_bind_results"
    assert bound["result"]["status"] == "plan_results_bound"
    assert bound["next_action"]["action"] == "needs_step_proposal_review"
    summary_proposals = [proposal for proposal in bound["result"]["state"]["approval_queue"] if proposal["tool_id"] == "text.summarize"]
    assert "Governed receipt summary" in summary_proposals[0]["tool_arguments"]["text"]
    assert bound["result"]["state"]["external_action_executed"] is False


def test_next_plan_action_is_deterministic_for_same_state() -> None:
    state = baseline_state()
    plan = plan_tool_task("Check git status", state)

    first = next_plan_action(plan, state)
    second = next_plan_action(plan, state)

    assert first == second
    assert first["execution_allowed"] is False
    assert first["autonomous_execution_allowed"] is False


def test_dashboard_contains_tool_plan_advance_control() -> None:
    client = _client()

    dashboard = client.get("/").text

    assert "advanceToolPlan" in dashboard
    assert "/metis/tools/plans/" in dashboard
    assert "advance" in dashboard
