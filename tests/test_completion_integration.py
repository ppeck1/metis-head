from __future__ import annotations

import sys
import types
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from metis_head import brain
from metis_head.llm_providers import LLMResult
from metis_head.stt import LocalFasterWhisperSTT, _WHISPER_MODELS
from metis_head.connectors.google_access import CALENDAR_SCOPE, GoogleReadBroker, GoogleReadGrant
from metis_head.model_adapters.ollama_local import BoundedUrllibJsonTransport


class RecordingProvider:
    def __init__(self, calls):
        self.calls = calls

    def generate(self, messages, state, options):
        self.calls.append(messages)
        return LLMResult(text="Context received.", provider="recording", model="fixture")


def test_spoken_turn_stays_private_but_supports_contextual_followup(monkeypatch):
    calls = []
    monkeypatch.setattr(brain, "provider_from_config", lambda options: RecordingProvider(calls))
    with TestClient(brain.app) as client:
        session = client.post("/metis/sessions", json={"client_id": "tab-context"}).json()["session_id"]
        first = client.post(
            "/metis/voice/command",
            json={"text": "My dentist appointment is tomorrow", "options": {"session_id": session, "voice": {"speak_response": False}}},
        )
        assert first.status_code == 200
        second = client.post("/metis/chat", json={"message": "What about Friday?", "session_id": session})
        assert second.status_code == 200

    prior_user_messages = [item["content"] for item in calls[-1] if item["role"] == "user"]
    assert "My dentist appointment is tomorrow" in prior_user_messages
    assert "What about Friday?" in prior_user_messages
    assert "My dentist appointment is tomorrow" not in repr(first.json()["state"]["chat_history"])
    assert "dentist" not in repr(second.json()["session"])


def test_typed_private_session_content_is_absent_from_global_diagnostics(monkeypatch):
    sentinel = "PRIVATE-TYPED-SENTINEL-9234"
    monkeypatch.setattr(brain, "provider_from_config", lambda options: RecordingProvider([]))
    with TestClient(brain.app) as client:
        client.post("/metis/state/reset")
        session = client.post("/metis/sessions", json={"client_id": "tab-private"}).json()["session_id"]
        response = client.post("/metis/chat", json={"message": sentinel, "session_id": session})
        diagnostics = client.get("/metis/state").json()

    assert response.status_code == 200
    assert response.json()["message"] == "Context received."
    assert sentinel not in repr(response.json()["state"])
    assert sentinel not in repr(diagnostics)


def test_faster_whisper_model_is_reused(monkeypatch):
    loads = []

    class Segment:
        text = "hello"

    class Info:
        language_probability = 0.9

    class FakeModel:
        def __init__(self, *args, **kwargs): loads.append((args, kwargs))
        def transcribe(self, path, beam_size): return [Segment()], Info()

    monkeypatch.setenv("METIS_STT_ALLOW_LOCAL", "true")
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))
    _WHISPER_MODELS.clear()
    capture = types.SimpleNamespace(_wav_bytes=b"RIFF-not-decoded-by-fixture")
    provider = LocalFasterWhisperSTT()
    assert provider.transcribe(capture).status == "complete"
    assert provider.transcribe(capture).status == "complete"
    assert len(loads) == 1
    _WHISPER_MODELS.clear()


def test_browser_capture_authorizes_before_microphone_and_emits_wav():
    source = (Path(__file__).resolve().parents[1] / "metis_head" / "static" / "voice_capture.js").read_text(encoding="utf-8")
    assert source.index("await this.authorize()") < source.index("getUserMedia")
    assert "track.stop()" in source
    assert "audio/wav" in source
    dashboard = (Path(__file__).resolve().parents[1] / "metis_head" / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert '<script src="/static/voice_capture.js?v=' in dashboard
    assert "form.append('audio', wav" in dashboard
    assert 'id="vcFixtureControls"' in dashboard
    assert "Hold to Talk (browser mic)" in dashboard
    assert "Microphone capture completed; the model reply failed:" in dashboard


def test_local_ollama_timeout_is_long_enough_for_model_warmup(monkeypatch):
    monkeypatch.setenv("METIS_OLLAMA_TIMEOUT_SECONDS", "175")
    coordinator = brain._build_personal_coordinator(
        {"model": "fixture"},
        broker=GoogleReadBroker({}, {}),
    )

    assert coordinator._limits.max_total_seconds == 175


def test_llm_options_uses_persisted_setup_when_environment_is_unset(monkeypatch):
    class SetupFixture:
        def load(self):
            return {
                "provider": {
                    "choice": "ollama",
                    "model": "saved-model:latest",
                    "base_url": "http://127.0.0.1:11434",
                }
            }

    monkeypatch.delenv("METIS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("METIS_OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("METIS_OLLAMA_BASE_URL", raising=False)
    monkeypatch.setattr(brain, "_setup_store", lambda: SetupFixture())
    monkeypatch.setattr(brain, "list_ollama_models", lambda base_url: {
        "available": True,
        "base_url": base_url,
        "models": [{"name": "saved-model:latest"}],
        "error": None,
    })

    options = brain.llm_options()

    assert options["selected_provider"] == "ollama"
    assert options["ollama_model"] == "saved-model:latest"
    assert options["ollama_base_url"] == "http://127.0.0.1:11434"


def test_legacy_local_mic_ptt_is_explicitly_disabled_until_press_time_capture_exists():
    with TestClient(brain.app) as client:
        client.post("/metis/state/reset")
        client.post("/metis/event", json={"type": "button_event", "button": "audio_input", "state": "on"})
        client.post("/metis/event", json={"type": "button_event", "button": "listen_mode", "state": "push_to_talk"})
        pressed = client.post("/metis/audio/ptt", json={"action": "press"})
        assert pressed.json()["status"] == "ptt_pressed"
        released = client.post("/metis/audio/ptt", json={"action": "release", "provider": "local_mic"})
    assert released.json()["status"] == "unsupported_local_ptt"
    assert released.json()["state"]["listen_session_active"] is False


def test_browser_ptt_cancel_clears_server_press_state():
    with TestClient(brain.app) as client:
        client.post("/metis/state/reset")
        client.post("/metis/event", json={"type": "button_event", "button": "audio_input", "state": "on"})
        client.post("/metis/event", json={"type": "button_event", "button": "listen_mode", "state": "push_to_talk"})
        pressed = client.post("/metis/audio/ptt", json={"action": "press"})
        cancelled = client.post("/metis/audio/ptt", json={"action": "cancel"})

    assert pressed.json()["listen_session_active"] is True
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "ptt_cancelled"
    assert cancelled.json()["state"]["listen_session_active"] is False


def test_ordinary_chat_route_runs_real_ollama_adapter_tool_result_round_trip(monkeypatch):
    provider_payloads = []

    class CalendarFixture:
        def list_events(self, **kwargs):
            return {
                "items": [{
                    "id": "event-1", "summary": "Dentist", "status": "confirmed",
                    "start": {"dateTime": "2026-09-17T14:00:00-04:00"},
                    "end": {"dateTime": "2026-09-17T15:00:00-04:00"},
                    "htmlLink": "https://calendar.google.com/event?eid=fixture",
                    "updated": "2026-09-16T12:00:00Z",
                }]
            }

    broker = GoogleReadBroker(
        {"personal": CalendarFixture()},
        {"personal": GoogleReadGrant("personal", frozenset({CALENDAR_SCOPE}), frozenset({"primary"}))},
        clock=lambda: datetime(2026, 9, 16, 12, tzinfo=UTC),
    )
    monkeypatch.setattr(brain, "_google_read_broker", lambda: broker)

    def fake_post(self, *, url, payload, timeout_seconds, cancellation):
        provider_payloads.append(payload)
        if len(provider_payloads) in {1, 3}:
            calendar_tool = next(
                item for item in payload["tools"]
                if "start" in item["function"]["parameters"].get("required", [])
                and "calendar_ids" in item["function"]["parameters"].get("required", [])
            )
            friday = len(provider_payloads) == 3
            return {
                "choices": [{"message": {"content": None, "tool_calls": [{
                    "id": "call-calendar-friday" if friday else "call-calendar-1", "type": "function",
                    "function": {
                        "name": calendar_tool["function"]["name"],
                        "arguments": json.dumps({
                            "account_id": "personal", "calendar_ids": ["primary"],
                            "start": "2026-09-18T00:00:00-04:00" if friday else "2026-09-17T00:00:00-04:00",
                            "end": "2026-09-19T00:00:00-04:00" if friday else "2026-09-18T00:00:00-04:00",
                            "timezone": "America/New_York",
                        }),
                    },
                }]}}],
            }
        message = "Friday has no matching events." if len(provider_payloads) == 4 else "You have a dentist appointment at 2 PM tomorrow."
        return {"choices": [{"message": {"content": message}}]}

    monkeypatch.setattr(BoundedUrllibJsonTransport, "post_json", fake_post)
    with TestClient(brain.app) as client:
        session_id = client.post("/metis/sessions", json={"client_id": "tab-tools"}).json()["session_id"]
        response = client.post(
            "/metis/chat",
            json={
                "message": "What's on my calendar tomorrow?",
                "session_id": session_id,
                "options": {"provider": "ollama", "model": "fixture-tools", "voice": {"speak_response": False}},
            },
        )
        followup = client.post(
            "/metis/chat",
            json={
                "message": "What about Friday?",
                "session_id": session_id,
                "options": {"provider": "ollama", "model": "fixture-tools", "voice": {"speak_response": False}},
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message"] == "You have a dentist appointment at 2 PM tomorrow."
    assert body["metadata"]["tool_orchestration"] is True
    assert body["metadata"]["tool_calls"] == 1
    assert followup.status_code == 200
    assert len(provider_payloads) == 4
    tool_message = next(message for message in provider_payloads[1]["messages"] if message["role"] == "tool")
    assert tool_message["tool_call_id"] == "call-calendar-1"
    assert "Dentist" in tool_message["content"]
    followup_text = " ".join(str(message.get("content") or "") for message in provider_payloads[2]["messages"])
    assert "What's on my calendar tomorrow?" in followup_text
    assert "You have a dentist appointment at 2 PM tomorrow." in followup_text
    assert "What about Friday?" in followup_text
    friday_tool_message = next(message for message in provider_payloads[3]["messages"] if message["role"] == "tool")
    friday_assistant = next(message for message in provider_payloads[3]["messages"] if message.get("tool_calls"))
    assert "2026-09-18" in friday_assistant["tool_calls"][0]["function"]["arguments"]
    assert friday_tool_message["tool_call_id"] != tool_message["tool_call_id"]
