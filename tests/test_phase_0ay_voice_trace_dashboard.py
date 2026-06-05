from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_dashboard_contains_voice_trace_panel_and_hooks() -> None:
    client = _client()

    dashboard = client.get("/").text

    assert "Voice Trace" in dashboard
    assert "voiceTrace" in dashboard
    assert "renderVoiceTrace" in dashboard
    assert "safeVoiceTraceEvents" in dashboard
    assert "metis_voice_confirmation.v0.1" in dashboard
    assert "raw transcript text and audio are not stored here" in dashboard


def test_voice_trace_source_events_are_redacted_for_commands_and_confirmations() -> None:
    client = _client()
    queued = client.post("/metis/voice/command", json={"text": "git status", "options": {"voice": {"speak_response": False}}}).json()
    proposal_id = queued["state"]["approval_queue"][0]["proposal_id"]

    confirmed = client.post(
        "/metis/voice/confirm",
        json={"text": f"confirm approve {proposal_id}", "options": {"voice": {"speak_response": False}}},
    ).json()

    stt_events = [event for event in confirmed["state"]["event_log"] if event.get("provider") == "stt"]
    assert stt_events
    assert any(event.get("input_mode") == "simulated_voice_command" for event in stt_events)
    assert any(event.get("voice_confirmation_schema") == "metis_voice_confirmation.v0.1" for event in stt_events)
    assert all(event.get("text_redacted") is True for event in stt_events)
    assert all("text" not in event for event in stt_events)
    assert all("transcript" not in event for event in stt_events)
    assert confirmed["state"]["external_action_executed"] is False
