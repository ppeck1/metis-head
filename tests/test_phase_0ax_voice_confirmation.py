from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def _queue_git_status(client: TestClient) -> str:
    queued = client.post("/metis/voice/command", json={"text": "git status", "options": {"voice": {"speak_response": False}}}).json()
    return queued["state"]["approval_queue"][0]["proposal_id"]


def test_voice_confirmation_readback_requires_explicit_phrase() -> None:
    client = _client()
    proposal_id = _queue_git_status(client)

    response = client.post("/metis/voice/confirm", json={"text": f"yes {proposal_id}", "options": {"voice": {"speak_response": False}}})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "readback_required"
    assert body["voice_confirmation"]["confirmation_accepted"] is False
    assert body["voice_confirmation"]["requires_explicit_phrase"] is True
    assert body["readback"]["proposal_id"] == proposal_id
    assert "confirm approve" in body["readback"]["readback"]
    assert body["state"]["approval_queue"][0]["review_status"] == "pending"
    assert body["state"]["execution_audit_log"] == []
    assert body["state"]["external_action_executed"] is False


def test_voice_confirmation_requires_proposal_id_even_with_approve_phrase() -> None:
    client = _client()
    proposal_id = _queue_git_status(client)

    response = client.post("/metis/voice/confirm", json={"text": "confirm approve", "options": {"voice": {"speak_response": False}}})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "readback_required"
    assert body["voice_confirmation"]["confirmation_accepted"] is False
    assert body["voice_confirmation"]["requires_explicit_proposal_id"] is True
    assert body["readback"]["proposal_id"] == proposal_id
    assert body["state"]["approval_queue"][0]["review_status"] == "pending"
    assert body["state"]["execution_audit_log"] == []


def test_voice_confirmation_can_approve_single_pending_proposal_without_execution() -> None:
    client = _client()
    proposal_id = _queue_git_status(client)

    response = client.post(
        "/metis/voice/confirm",
        json={"text": f"confirm approve {proposal_id}", "options": {"voice": {"speak_response": False}}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "proposal_approved"
    assert body["input_mode"] == "simulated_voice_confirmation"
    assert body["voice_confirmation"]["confirmation_accepted"] is True
    assert body["voice_confirmation"]["standing_approval"] is False
    assert body["voice_confirmation"]["execution_allowed"] is False
    assert body["proposal"]["review_status"] == "approved"
    assert body["proposal"]["review_receipt"]["review_scope"]["standing_approval"] is False
    assert body["state"]["pending_approval_count"] == 0
    assert body["state"]["execution_audit_log"] == []
    assert body["state"]["external_action_executed"] is False


def test_voice_confirmation_cancel_leaves_proposal_pending() -> None:
    client = _client()
    proposal_id = _queue_git_status(client)

    response = client.post(
        "/metis/voice/confirm",
        json={"text": f"cancel {proposal_id}", "options": {"voice": {"speak_response": False}}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["voice_confirmation"]["confirmation_accepted"] is False
    assert body["state"]["approval_queue"][0]["review_status"] == "pending"
    assert body["state"]["pending_approval_count"] == 1
    assert body["state"]["execution_audit_log"] == []


def test_voice_confirmation_can_deny_with_explicit_phrase() -> None:
    client = _client()
    proposal_id = _queue_git_status(client)

    response = client.post(
        "/metis/voice/confirm",
        json={"text": f"deny proposal {proposal_id}", "options": {"voice": {"speak_response": False}}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "proposal_denied"
    assert body["voice_confirmation"]["decision"] == "denied"
    assert body["proposal"]["review_status"] == "denied"
    assert body["state"]["pending_approval_count"] == 0
    assert body["state"]["external_action_executed"] is False


def test_voice_confirmation_mic_cutoff_blocks_without_review() -> None:
    client = _client()
    proposal_id = _queue_git_status(client)
    client.post("/metis/event", json={"type": "hardware_privacy", "device": "mic", "enabled": False})

    response = client.post("/metis/voice/confirm", json={"text": f"confirm approve {proposal_id}"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert body["voice_confirmation"]["recognized"] is False
    assert body["state"]["approval_queue"][0]["review_status"] == "pending"
    assert body["state"]["pending_approval_count"] == 1
    assert body["state"]["execution_audit_log"] == []
    assert body["state"]["external_action_executed"] is False
