from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.reducer import reduce_metis_event, replay_events
from metis_head.schemas import baseline_state
from metis_head.tool_registry import build_tool_proposal_event


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def _first_proposal_id(state: dict) -> str:
    return state["approval_queue"][0]["proposal_id"]


def test_approved_time_now_executes_read_only_with_receipt() -> None:
    client = _client()
    client.post("/metis/event", json={"type": "button_event", "button": "am_fm", "state": "agent"})
    queued = client.post(
        "/metis/tools/time.now/dry_run",
        json={"arguments": {"now": "2026-06-02T12:34:56Z", "timezone": "UTC"}},
    ).json()
    proposal_id = _first_proposal_id(queued["state"])
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "approved internal time read"})

    response = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={"reason": "operator requested time"})

    assert response.status_code == 200
    body = response.json()
    receipt = body["receipt"]
    assert body["status"] == "executed_read_only"
    assert receipt["execution_status"] == "executed_read_only"
    assert receipt["policy_decision"] == "approved_read_only"
    assert receipt["execution_allowed"] is False
    assert receipt["tool_id"] == "time.now"
    assert receipt["output_summary"]["preview"]["iso_time"] == "2026-06-02T12:34:56Z"
    assert receipt["output_summary"]["preview"]["timezone"] == "UTC"
    assert len(receipt["output_hash"]) == 16
    assert "dry_run_receipt" not in receipt
    assert body["state"]["external_action_executed"] is False


def test_time_now_requires_review_before_read_only_execution() -> None:
    client = _client()
    client.post("/metis/event", json={"type": "button_event", "button": "am_fm", "state": "agent"})
    queued = client.post("/metis/tools/time.now/dry_run", json={"arguments": {"now": "2026-06-02T12:34:56Z"}}).json()
    proposal_id = _first_proposal_id(queued["state"])

    response = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={})

    assert response.status_code == 200
    receipt = response.json()["receipt"]
    assert receipt["execution_status"] == "blocked_unreviewed"
    assert receipt["operator_review_required"] is True
    assert receipt["execution_allowed"] is False


def test_filesystem_and_git_remain_blocked_after_approval() -> None:
    client = _client()
    fs = client.post("/metis/tools/propose", json={"tool_id": "filesystem.read_proposed", "arguments": {"path": "B:\\secret.txt"}}).json()
    fs_id = _first_proposal_id(fs["state"])
    client.post(f"/metis/proposals/{fs_id}/approve", json={"reason": "review only"})
    fs_exec = client.post(f"/metis/proposals/{fs_id}/request_execution", json={}).json()["receipt"]

    git = client.post("/metis/tools/propose", json={"tool_id": "git.status_proposed", "arguments": {"repository": "."}}).json()
    git_id = git["state"]["approval_queue"][-1]["proposal_id"]
    client.post(f"/metis/proposals/{git_id}/approve", json={"reason": "review only"})
    git_exec = client.post(f"/metis/proposals/{git_id}/request_execution", json={}).json()["receipt"]

    assert fs_exec["execution_status"] == "blocked_side_effect"
    assert git_exec["execution_status"] == "blocked_side_effect"
    assert fs_exec["execution_allowed"] is False
    assert git_exec["execution_allowed"] is False


def test_time_execution_replay_is_deterministic() -> None:
    proposal_event = build_tool_proposal_event("time.now", {"now": "2026-06-02T01:02:03Z", "timezone": "UTC"}, {"interaction_mode": "agent"})
    queued = reduce_metis_event(baseline_state(), proposal_event)
    proposal_id = _first_proposal_id(queued)
    review_event = {
        "type": "proposal_review",
        "proposal_id": proposal_id,
        "decision": "approved",
        "reason": "fixed review",
        "reviewed_at": "2026-06-02T12:00:00Z",
    }
    execution_event = {
        "type": "execution_request",
        "proposal_id": proposal_id,
        "reason": "fixed execution request",
        "requested_at": "2026-06-02T12:01:00Z",
        "read_only_result": {"iso_time": "2026-06-02T01:02:03Z", "timezone": "UTC"},
    }

    first = replay_events(baseline_state(), [proposal_event, review_event, execution_event])
    second = replay_events(baseline_state(), [proposal_event, review_event, execution_event])

    assert first == second
    assert first["execution_audit_log"][0]["execution_status"] == "executed_read_only"
    assert first["execution_audit_log"][0]["output_hash"] == second["execution_audit_log"][0]["output_hash"]


def test_policy_marks_time_and_git_status_active() -> None:
    client = _client()

    policy = client.get("/metis/execution/policy").json()
    lanes = {lane["lane"]: lane["status"] for lane in policy["candidate_lanes"]}

    assert lanes["time.now"] == "active_approved_read_only"
    assert lanes["git.status"] == "active_approved_read_only"
    assert lanes["filesystem.read"] == "active_approved_read_only"
    assert lanes["fetch.url"] == "future_only"
