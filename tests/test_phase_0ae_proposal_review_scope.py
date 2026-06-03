from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.proposals import PROPOSAL_REVIEW_SCOPE_VERSION


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_approved_proposal_review_scope_is_single_proposal_and_not_standing() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "time.now", "arguments": {"timezone": "UTC"}}).json()
    proposal_id = queued["proposal"]["proposal_id"]

    reviewed = client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "safe one-shot review"}).json()

    scope = reviewed["proposal"]["review_scope"]
    receipt_scope = reviewed["review_receipt"]["review_scope"]
    assert scope == receipt_scope
    assert scope["schema_version"] == PROPOSAL_REVIEW_SCOPE_VERSION
    assert scope["scope_type"] == "single_proposal"
    assert scope["proposal_id"] == proposal_id
    assert scope["tool_id"] == "time.now"
    assert scope["standing_approval"] is False
    assert scope["transferable"] is False
    assert scope["execution_allowed"] is False


def test_denied_proposal_review_scope_still_blocks_execution_transfer() -> None:
    client = _client()
    queued = client.post(
        "/metis/tools/propose",
        json={"tool_id": "fetch.url_proposed", "arguments": {"url": "https://example.com"}},
    ).json()
    proposal_id = queued["proposal"]["proposal_id"]

    reviewed = client.post(f"/metis/proposals/{proposal_id}/deny", json={"reason": "network still blocked"}).json()
    requested = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={"reason": "confirm denied block"}).json()

    scope = reviewed["proposal"]["review_scope"]
    assert scope["standing_approval"] is False
    assert scope["transferable"] is False
    assert scope["execution_allowed"] is False
    assert requested["receipt"]["execution_status"] == "blocked_denied"
    assert requested["receipt"]["execution_allowed"] is False
    assert requested["state"]["external_action_executed"] is False


def test_review_scope_surfaces_in_proposal_detail() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "math.calculate", "arguments": {"operation": "add", "a": 1, "b": 2}}).json()
    proposal_id = queued["proposal"]["proposal_id"]
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "review scope detail"})

    detail = client.get(f"/metis/proposals/{proposal_id}").json()["proposal"]

    assert detail["review_scope"]["schema_version"] == PROPOSAL_REVIEW_SCOPE_VERSION
    assert detail["review_scope"]["scope_type"] == "single_proposal"
