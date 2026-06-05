from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from metis_head.brain import app


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def _stt_events(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [event for event in state.get("event_log", []) if event.get("provider") == "stt"]


def test_voice_command_routes_tool_request_to_governed_tool_lane_and_speaks() -> None:
    client = _client()

    response = client.post("/metis/voice/command", json={"text": "git status"})

    assert response.status_code == 200
    body = response.json()
    assert body["input_mode"] == "simulated_voice_command"
    assert body["voice_command"]["recognized"] is True
    assert body["voice_command"]["speech_reply_requested"] is True
    assert body["provider"] == "tool_router"
    assert body["tool"]["tool_id"] == "git.status"
    assert body["proposal_queued"] is True
    assert body["voice"]["spoken"] is True
    assert body["state"]["approval_queue"][0]["tool_id"] == "git.status"
    assert body["state"]["external_action_executed"] is False
    events = _stt_events(body["state"])
    assert [event["status"] for event in events] == ["transcript", "complete"]
    assert all(event["text_redacted"] is True for event in events)
    assert all("text" not in event for event in events)


def test_voice_command_can_ask_about_next_governed_action() -> None:
    client = _client()
    queued = client.post("/metis/voice/command", json={"text": "git status"}).json()
    proposal_id = queued["tool"]["proposal"]["proposal_id"]

    response = client.post("/metis/voice/command", json={"text": "what should I do next"})

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "tool_planner"
    assert body["model"] == "metis_tool_next_action.v0.1"
    assert body["next_action"]["recommended_action"] == "review_proposal"
    assert body["next_action"]["target"] == {"type": "proposal", "id": proposal_id}
    assert body["voice"]["spoken"] is True
    assert body["state"]["approval_queue"][0]["review_status"] == "pending"
    assert body["state"]["execution_audit_log"] == []
    assert body["state"]["external_action_executed"] is False


def test_voice_command_lists_tool_awareness_without_direct_execution() -> None:
    client = _client()

    response = client.post("/metis/voice/command", json={"text": "what tools can you use", "options": {"provider": "mock"}})

    assert response.status_code == 200
    body = response.json()
    assert body["input_mode"] == "simulated_voice_command"
    assert body["voice"]["spoken"] is True
    assert body["state"]["external_action_executed"] is False
    assert body["voice_command"]["route"] == "metis_chat"
    assert body["policy"]["requires_approval"] is False


def test_voice_command_mic_cutoff_blocks_without_chat_or_tts() -> None:
    client = _client()
    client.post("/metis/event", json={"type": "hardware_privacy", "device": "mic", "enabled": False})

    response = client.post("/metis/voice/command", json={"text": "git status"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert body["voice_command"]["recognized"] is False
    assert body["state"]["approval_queue"] == []
    assert body["state"]["chat_history"] == []
    assert body["state"]["tts_output_count"] == 0
    assert body["state"]["audio_state"] == "capture_blocked"
    assert body["state"]["blocked_capture_count"] == 1
    assert body["state"]["external_action_executed"] is False
    events = _stt_events(body["state"])
    assert events[-1]["status"] == "blocked"
    assert events[-1]["text_redacted"] is True


def test_voice_command_accepts_transcript_alias_and_preserves_voice_options() -> None:
    client = _client()

    response = client.post(
        "/metis/voice/command",
        json={"transcript": "pending approvals", "options": {"voice": {"provider": "mock", "voice_id": "metis-counsel-mock", "speak_response": False}}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "metis_tool_approval_status.v0.1"
    assert body["voice"] is None
    assert body["voice_command"]["speech_reply_requested"] is False
    assert body["state"]["external_action_executed"] is False
