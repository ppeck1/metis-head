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


def _approved_plan_with_steps(client: TestClient) -> tuple[str, list[dict]]:
    queued = client.post("/metis/tools/task/plan", json={"task": "Summarize pyproject.toml"}).json()
    plan_id = queued["plan"]["plan_id"]
    client.post(f"/metis/tools/plans/{plan_id}/approve", json={"reason": "reviewed plan"})
    materialized = client.post(f"/metis/tools/plans/{plan_id}/queue_steps", json={}).json()
    return plan_id, materialized["queued_proposals"]


def test_plan_result_binding_updates_pending_dependent_step_without_raw_content() -> None:
    client = _client()
    plan_id, proposals = _approved_plan_with_steps(client)
    fs_proposal = next(proposal for proposal in proposals if proposal["tool_id"] == "filesystem.read")
    summary_proposal = next(proposal for proposal in proposals if proposal["tool_id"] == "text.summarize")
    client.post(f"/metis/proposals/{fs_proposal['proposal_id']}/approve", json={"reason": "approve read"})
    client.post(f"/metis/tools/plans/{plan_id}/request_execution", json={"reason": "request read"})

    response = client.post(f"/metis/tools/plans/{plan_id}/bind_results", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "plan_results_bound"
    assert len(body["bindings"]) == 1
    binding = body["bindings"][0]
    assert binding["proposal_id"] == summary_proposal["proposal_id"]
    assert binding["source_receipt_id"].startswith("execution_")
    assert binding["source_output_hash"]
    assert binding["arguments"]["max_words"] == 48
    assert "Governed receipt summary" in binding["arguments"]["text"]
    assert len(binding["arguments"]["text"]) <= 900
    assert "raw_file_contents" not in binding["arguments"]["text"]
    rebound = next(proposal for proposal in body["state"]["approval_queue"] if proposal["proposal_id"] == summary_proposal["proposal_id"])
    assert rebound["tool_arguments"] == binding["arguments"]
    assert rebound["result_binding"]["raw_content_included"] is False
    assert body["state"]["external_action_executed"] is False


def test_bound_summary_step_can_be_reviewed_and_requested() -> None:
    client = _client()
    plan_id, proposals = _approved_plan_with_steps(client)
    fs_proposal = next(proposal for proposal in proposals if proposal["tool_id"] == "filesystem.read")
    summary_proposal = next(proposal for proposal in proposals if proposal["tool_id"] == "text.summarize")
    client.post(f"/metis/proposals/{fs_proposal['proposal_id']}/approve", json={})
    client.post(f"/metis/tools/plans/{plan_id}/request_execution", json={})
    client.post(f"/metis/tools/plans/{plan_id}/bind_results", json={})
    client.post(f"/metis/proposals/{summary_proposal['proposal_id']}/approve", json={"reason": "approve bound summary"})

    response = client.post(f"/metis/tools/plans/{plan_id}/request_execution", json={"reason": "request bound summary"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "plan_execution_requested"
    assert body["receipts"][0]["proposal_id"] == summary_proposal["proposal_id"]
    assert body["receipts"][0]["execution_status"] == "dry_run_only_not_executed"
    assert body["receipts"][0]["dry_run_receipt"]["result"]["word_count"] > 0
    assert body["state"]["external_action_executed"] is False


def test_result_binding_skips_already_reviewed_dependent_proposal() -> None:
    client = _client()
    plan_id, proposals = _approved_plan_with_steps(client)
    fs_proposal = next(proposal for proposal in proposals if proposal["tool_id"] == "filesystem.read")
    summary_proposal = next(proposal for proposal in proposals if proposal["tool_id"] == "text.summarize")
    client.post(f"/metis/proposals/{fs_proposal['proposal_id']}/approve", json={})
    client.post(f"/metis/proposals/{summary_proposal['proposal_id']}/deny", json={"reason": "too early"})
    client.post(f"/metis/tools/plans/{plan_id}/request_execution", json={})

    response = client.post(f"/metis/tools/plans/{plan_id}/bind_results", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_plan_results_bound"
    assert body["skipped_steps"][0]["reason"] == "proposal_already_reviewed"


def test_tool_plan_result_binding_replay_is_deterministic() -> None:
    base = baseline_state()
    plan = plan_tool_task("Summarize pyproject.toml", base)
    plan_event = {"type": "tool_plan", "plan": plan}
    review_event = {
        "type": "tool_plan_review",
        "plan_id": plan["plan_id"],
        "decision": "approved",
        "reason": "fixed review",
        "reviewed_at": "2026-06-03T12:00:00Z",
    }
    reviewed = replay_events(base, [plan_event, review_event])
    proposal_events = []
    queued_steps = []
    rolling = reviewed
    for step in reviewed["tool_plan_queue"][0]["steps"]:
        event = build_tool_proposal_event(step["tool_id"], step.get("arguments") or {}, rolling, f"plan {plan['plan_id']} {step['step_id']}")
        rolling = replay_events(rolling, [event])
        proposal_events.append(event)
        queued_steps.append({"step_id": step["step_id"], "tool_id": step["tool_id"], "proposal_id": rolling["approval_queue"][-1]["proposal_id"]})
    queue_event = {"type": "tool_plan_step_queue", "plan_id": plan["plan_id"], "queued_steps": queued_steps, "queued_at": "2026-06-03T12:01:00Z"}
    summary_proposal_id = queued_steps[-1]["proposal_id"]
    binding_event = {
        "type": "tool_plan_result_binding",
        "plan_id": plan["plan_id"],
        "bindings": [
            {
                "step_id": "step_02",
                "proposal_id": summary_proposal_id,
                "source_step_id": "step_01",
                "source_receipt_id": "execution_0001_fixed",
                "source_output_hash": "abc123",
                "arguments": {"text": "Governed receipt summary from filesystem.read", "max_words": 48},
            }
        ],
        "bound_at": "2026-06-03T12:02:00Z",
    }

    events = [plan_event, review_event, *proposal_events, queue_event, binding_event]
    first = replay_events(base, events)
    second = replay_events(base, events)

    assert first == second
    proposal = next(item for item in first["approval_queue"] if item["proposal_id"] == summary_proposal_id)
    assert proposal["tool_arguments"]["max_words"] == 48
    assert proposal["result_binding"]["raw_content_included"] is False
    assert first["external_action_executed"] is False


def test_dashboard_contains_tool_plan_result_binding_control() -> None:
    client = _client()

    dashboard = client.get("/").text

    assert "bindToolPlanResults" in dashboard
    assert "bind_results" in dashboard
