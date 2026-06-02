from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.reducer import reduce_metis_event, replay_events
from metis_head.schemas import baseline_state
from metis_head.tool_registry import build_tool_proposal_event, dry_run_tool


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def _first_proposal_id(state: dict) -> str:
    return state["approval_queue"][0]["proposal_id"]


def test_fetch_proposal_execution_receipt_is_listed_and_detail_safe() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "fetch.url_proposed", "arguments": {"url": "https://example.com", "token": "abc"}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "reviewed fetch proposal"})

    requested = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={"reason": "confirm blocked"})

    assert requested.status_code == 200
    receipt = requested.json()["receipt"]
    assert receipt["tool_id"] == "fetch.url_proposed"
    assert receipt["execution_status"] == "blocked_side_effect"
    assert receipt["execution_allowed"] is False
    assert "abc" not in str(receipt)
    assert "external_receipts" in receipt["redactions"]

    listing = client.get("/metis/execution/receipts")
    detail = client.get(f"/metis/execution/receipts/{receipt['receipt_id']}")

    assert listing.status_code == 200
    assert listing.json()["receipt_count"] == 1
    assert detail.status_code == 200
    assert detail.json()["receipt"] == receipt


def test_fetch_proposal_replay_is_deterministic_and_non_executing() -> None:
    proposal_event = build_tool_proposal_event("fetch.url_proposed", {"url": "https://example.com", "token": "abc"}, baseline_state())
    queued = reduce_metis_event(baseline_state(), proposal_event)
    proposal_id = _first_proposal_id(queued)
    review_event = {
        "type": "proposal_review",
        "proposal_id": proposal_id,
        "decision": "approved",
        "reason": "fixed fetch review",
        "reviewed_at": "2026-06-02T12:00:00Z",
    }
    execution_event = {
        "type": "execution_request",
        "proposal_id": proposal_id,
        "reason": "fixed blocked fetch execution request",
        "requested_at": "2026-06-02T12:01:00Z",
    }

    first = replay_events(baseline_state(), [proposal_event, review_event, execution_event])
    second = replay_events(baseline_state(), [proposal_event, review_event, execution_event])

    assert first == second
    assert first["external_action_executed"] is False
    assert first["execution_audit_log"][0]["execution_status"] == "blocked_side_effect"
    assert "abc" not in str(first["approval_queue"])
    assert "abc" not in str(first["execution_audit_log"])


def test_plan_outline_execution_request_replay_is_deterministic_dry_run_only() -> None:
    agent_state = baseline_state()
    agent_state["interaction_mode"] = "agent"
    arguments = {"task": "prepare a reviewable tool plan", "max_steps": 2}
    proposal_event = build_tool_proposal_event("thinking.plan_outline", arguments, agent_state)
    queued = reduce_metis_event(baseline_state(), proposal_event)
    proposal_id = _first_proposal_id(queued)
    review_event = {
        "type": "proposal_review",
        "proposal_id": proposal_id,
        "decision": "approved",
        "reason": "fixed visible plan review",
        "reviewed_at": "2026-06-02T12:00:00Z",
    }
    execution_event = {
        "type": "execution_request",
        "proposal_id": proposal_id,
        "reason": "fixed visible plan dry run request",
        "requested_at": "2026-06-02T12:01:00Z",
        "dry_run_receipt": dry_run_tool("thinking.plan_outline", arguments),
    }

    first = replay_events(baseline_state(), [proposal_event, review_event, execution_event])
    second = replay_events(baseline_state(), [proposal_event, review_event, execution_event])

    assert first == second
    receipt = first["execution_audit_log"][0]
    assert receipt["tool_id"] == "thinking.plan_outline"
    assert receipt["execution_status"] == "dry_run_only_not_executed"
    assert receipt["execution_allowed"] is False
    assert receipt["dry_run_receipt"]["result"]["execution_allowed"] is False
    assert receipt["dry_run_receipt"]["result"]["steps"] == ["Clarify the goal", "Identify constraints"]
    assert first["external_action_executed"] is False
