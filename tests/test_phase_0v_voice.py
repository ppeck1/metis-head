from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from metis_head.brain import app


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def _provider_events(state: dict[str, Any], provider: str) -> list[dict[str, Any]]:
    return [
        event
        for event in state.get("event_log", [])
        if event.get("type") == "provider_event" and event.get("provider") == provider
    ]


def test_voice_profile_config_endpoint_exposes_mock_tts_profile() -> None:
    client = _client()

    response = client.get("/metis/voice")

    assert response.status_code == 200
    body = response.json()
    assert body["voice_schema"] == "metis_voice.v0.1"
    assert body["selected_provider"] == "mock"
    assert body["output_muted"] is False
    assert body["audio_state"] == "idle"
    assert body["profile"]["id"]
    assert body["profile"]["provider"] == "mock"
    assert body["profile"]["can_speak"] is True
    assert "TTS output only" in body["profile"]["boundary"]


def test_voice_options_endpoint_lists_current_and_candidate_voices() -> None:
    client = _client()

    response = client.get("/metis/voice/options")

    assert response.status_code == 200
    body = response.json()
    assert body["voice_options_version"] == "metis_voice_options.v0.1"
    assert body["selected_voice_id"] == "metis-counsel-mock"
    assert body["current_voice_is_audible"] is False
    options = {item["option_id"]: item for item in body["options"]}
    assert options["metis-counsel-mock"]["status"] == "available"
    assert options["metis-counsel-mock"]["privacy_class"] == "local_no_audio"
    assert options["windows-system-tts"]["status"] == "gated"
    assert options["piper-local"]["status"] == "candidate"
    assert options["openai-tts"]["privacy_class"] == "cloud_audio_external"


def test_mock_speak_returns_events_and_final_idle_state() -> None:
    client = _client()

    response = client.post("/metis/voice/speak", json={"text": "Phase 0V harness check.", "provider": "mock"})

    assert response.status_code == 200
    body = response.json()
    assert body["event_count"] == 4
    assert [event["status"] for event in body["events"]] == ["queued", "synthesizing", "speaking", "complete"]
    assert body["events"][0]["provider"] == "tts"
    assert body["events"][0]["text_redacted"] is True
    assert "text" not in body["events"][0]
    assert body["state"]["audio_state"] == "idle"
    assert body["state"]["voice_output_state"] == "complete"
    assert body["state"]["tts_output_count"] == 1
    assert body["state"]["active_failure"] is None


def test_output_muted_blocks_speech_without_privacy_changes() -> None:
    client = _client()
    muted = client.post(
        "/metis/event",
        json={"type": "button_event", "button": "loud", "state": "off"},
    ).json()["state"]

    response = client.post("/metis/voice/speak", json={"text": "This should not be spoken.", "provider": "mock"})

    assert response.status_code == 200
    body = response.json()
    assert body["speech_blocked"] is True
    assert body["block_reason"] == "output_muted"
    assert body["event_count"] == 1
    assert body["events"][0]["status"] == "muted"
    assert body["events"][0]["text_redacted"] is True
    state = body["state"]
    assert state["output_muted"] is True
    assert state["audio_state"] == "idle"
    assert state["voice_output_state"] == "muted"
    assert state["tts_muted_drop_count"] == 1
    assert state["mic_hardware_enabled"] == muted["mic_hardware_enabled"] is True
    assert state["camera_hardware_enabled"] == muted["camera_hardware_enabled"] is False
    assert state["logging_state"] == muted["logging_state"] == "session_logging_active"


def test_tts_provider_failure_is_visible() -> None:
    client = _client()

    response = client.post("/metis/voice/speak", json={"text": "Fail visibly.", "provider": "failed"})

    assert response.status_code == 502
    state = client.get("/metis/state").json()["state"]
    assert state["active_failure"] == "tts_failure"
    assert state["audio_state"] == "idle"
    assert state["voice_output_state"] == "failed"
    assert state["module_health"]["metis_audio"] == "tts_failure"


def test_chat_speak_response_speaks_after_text_completion(monkeypatch) -> None:
    monkeypatch.setenv("METIS_LLM_PROVIDER", "mock")
    client = _client()

    response = client.post(
        "/metis/chat",
        json={"message": "Say hello for the voice harness.", "options": {"voice": {"speak_response": True}}},
    )

    assert response.status_code == 200
    body = response.json()
    assert "Mock response" in body["message"]
    assert body["state"]["audio_state"] == "idle"
    tts_events = _provider_events(body["state"], "tts")
    assert [event["status"] for event in tts_events[-4:]] == ["queued", "synthesizing", "speaking", "complete"]
    assert tts_events[-4]["text_redacted"] is True
    assert tts_events[-4]["text_hash"]
    chat_complete_index = next(
        index
        for index, event in enumerate(body["state"]["event_log"])
        if event.get("type") == "chat_event" and event.get("status") == "complete"
    )
    first_tts_index = body["state"]["event_log"].index(tts_events[-4])
    assert chat_complete_index < first_tts_index


def test_chat_speak_response_never_speaks_when_muted(monkeypatch) -> None:
    monkeypatch.setenv("METIS_LLM_PROVIDER", "mock")
    client = _client()
    client.post("/metis/event", json={"type": "button_event", "button": "loud", "state": "off"})

    response = client.post(
        "/metis/chat",
        json={"message": "Do not speak this aloud.", "options": {"voice": {"speak_response": True}}},
    )

    assert response.status_code == 200
    body = response.json()
    assert "Mock response" in body["message"]
    assert body["state"]["output_muted"] is True
    assert body["state"]["audio_state"] == "idle"
    tts_events = _provider_events(body["state"], "tts")
    assert [event["status"] for event in tts_events] == ["muted"]
    assert body.get("voice", {}).get("speech_blocked") is True
    assert body.get("voice", {}).get("block_reason") == "output_muted"
