"""Phase 0BD — Push-to-talk and wake-word listen loop tests.

Hard boundaries verified here:
- Event-driven and bounded: one utterance per explicit trigger, never always-listening.
- Mic cutoff highest precedence (blocks both PTT and wake).
- Standby is not always-listening (no_listen blocks both).
- Recognized text redacted: never in state, event log, or responses.
- No background threads spawned by PTT or wake routes.
- No new execution authority: routing goes through /metis/voice/command only.
"""
from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

import metis_head.brain as _brain
from metis_head.brain import app
from metis_head.schemas import baseline_state


@pytest.fixture()
def client():
    _brain.STATE = baseline_state()
    return TestClient(app)


# ── helpers ──────────────────────────────────────────────────────────────────

def _reset(client: TestClient) -> None:
    _brain.STATE = baseline_state()


def _enable_audio(client: TestClient) -> None:
    client.post("/metis/event", json={"type": "button_event", "button": "audio_input", "state": "on"})


def _set_mode(client: TestClient, mode: str) -> None:
    client.post("/metis/event", json={"type": "button_event", "button": "listen_mode", "state": mode})


def _enable_and_mode(client: TestClient, mode: str) -> None:
    _enable_audio(client)
    _set_mode(client, mode)


def _no_raw_text(data: dict) -> None:
    """Assert no recognized transcript text appears in the response."""
    import json
    raw = json.dumps(data)
    # SimulatedSTT maps "git status" fixture; make sure raw text isn't there
    assert "git status" not in raw or data.get("status") in {"blocked", "wake_not_detected", "ptt_release_ignored", "wrong_mode"}


# ── PTT press tests ───────────────────────────────────────────────────────────

def test_ptt_press_requires_push_to_talk_mode(client):
    _reset(client)
    _enable_audio(client)
    _set_mode(client, "wake_word")
    r = client.post("/metis/audio/ptt", json={"action": "press"})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "wrong_mode"
    assert d["listen_mode"] == "wake_word"


def test_ptt_press_blocked_in_no_listen(client):
    _reset(client)
    _enable_audio(client)
    # listen_mode defaults to no_listen
    r = client.post("/metis/audio/ptt", json={"action": "press"})
    assert r.status_code == 200
    assert r.json()["status"] == "wrong_mode"


def test_ptt_press_blocked_when_mic_off(client):
    _reset(client)
    _enable_and_mode(client, "push_to_talk")
    # Cut mic hardware
    client.post("/metis/event", json={"type": "hardware_privacy", "device": "mic", "state": "off"})
    r = client.post("/metis/audio/ptt", json={"action": "press"})
    assert r.status_code == 200
    assert r.json()["status"] == "blocked"


def test_ptt_press_sets_session_active(client):
    _reset(client)
    _enable_and_mode(client, "push_to_talk")
    r = client.post("/metis/audio/ptt", json={"action": "press"})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ptt_pressed"
    assert d["state"]["listen_session_active"] is True


def test_ptt_press_does_not_produce_proposal(client):
    """Press alone must never queue a proposal."""
    _reset(client)
    _enable_and_mode(client, "push_to_talk")
    r = client.post("/metis/audio/ptt", json={"action": "press"})
    d = r.json()
    assert d["state"].get("tool_queue_count", 0) == 0
    assert d["state"].get("approval_queue", []) == []


# ── PTT release tests ─────────────────────────────────────────────────────────

def test_ptt_release_without_press_is_noop(client):
    _reset(client)
    _enable_and_mode(client, "push_to_talk")
    r = client.post("/metis/audio/ptt", json={"action": "release"})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ptt_release_ignored"
    assert d["state"].get("last_audio_capture") is None


def test_ptt_release_in_wrong_mode_is_noop(client):
    _reset(client)
    _enable_and_mode(client, "push_to_talk")
    client.post("/metis/audio/ptt", json={"action": "press"})
    # switch mode before release
    _set_mode(client, "wake_word")
    r = client.post("/metis/audio/ptt", json={"action": "release"})
    assert r.status_code == 200
    assert r.json()["status"] == "ptt_release_ignored"


def test_ptt_press_release_routes_git_status(client):
    _reset(client)
    _enable_and_mode(client, "push_to_talk")
    client.post("/metis/audio/ptt", json={"action": "press"})
    r = client.post("/metis/audio/ptt", json={"action": "release", "hint": "git status"})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "listen_complete"
    assert d["state"]["last_listen_trigger"] == "ptt"
    # proposal queued but NOT executed
    vc = d.get("voice_command") or {}
    tool_status = vc.get("metadata", {}).get("tool", {}).get("status")
    assert tool_status == "proposal_queued" or "message" in vc
    assert d["state"].get("external_action_executed") is False


def test_ptt_release_clears_session(client):
    _reset(client)
    _enable_and_mode(client, "push_to_talk")
    client.post("/metis/audio/ptt", json={"action": "press"})
    r = client.post("/metis/audio/ptt", json={"action": "release", "hint": "git status"})
    assert r.json()["state"]["listen_session_active"] is False


def test_ptt_redacts_recognized_text(client):
    _reset(client)
    _enable_and_mode(client, "push_to_talk")
    client.post("/metis/audio/ptt", json={"action": "press"})
    r = client.post("/metis/audio/ptt", json={"action": "release", "hint": "git status"})
    d = r.json()
    # STT dict must not contain raw text
    stt = d.get("stt") or {}
    assert "text" not in stt
    assert stt.get("text_redacted") is True
    # audio_input events in the event log must not expose raw transcript text
    for ev in d["state"].get("event_log", []):
        assert "recognized_text" not in ev
        if ev.get("provider") == "audio_input":
            assert "text" not in ev


def test_ptt_no_background_thread_spawned(client):
    before = threading.active_count()
    _reset(client)
    _enable_and_mode(client, "push_to_talk")
    client.post("/metis/audio/ptt", json={"action": "press"})
    client.post("/metis/audio/ptt", json={"action": "release", "hint": "git status"})
    after = threading.active_count()
    assert after <= before + 1  # allow 1 for TestClient internals


def test_ptt_blocked_by_mic_cutoff_after_press(client):
    """Even if session is active, mic cutoff before release must block capture."""
    _reset(client)
    _enable_and_mode(client, "push_to_talk")
    client.post("/metis/audio/ptt", json={"action": "press"})
    client.post("/metis/event", json={"type": "hardware_privacy", "device": "mic", "state": "off"})
    r = client.post("/metis/audio/ptt", json={"action": "release", "hint": "git status"})
    assert r.status_code == 200
    assert r.json()["status"] == "blocked"


def test_ptt_invalid_action_returns_400(client):
    _reset(client)
    r = client.post("/metis/audio/ptt", json={"action": "hold"})
    assert r.status_code == 400


# ── Wake-word tests ───────────────────────────────────────────────────────────

def test_wake_wrong_mode_returns_not_detected(client):
    _reset(client)
    _enable_audio(client)
    _set_mode(client, "push_to_talk")
    r = client.post("/metis/audio/wake", json={"text": "hey metis git status"})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "wake_not_detected"
    assert d["block_reason"] == "listen_mode_not_wake_word"


def test_wake_no_listen_mode_not_detected(client):
    _reset(client)
    _enable_audio(client)
    r = client.post("/metis/audio/wake", json={"text": "hey metis git status"})
    assert r.status_code == 200
    assert r.json()["status"] == "wake_not_detected"


def test_wake_wrong_phrase_not_detected(client):
    _reset(client)
    _enable_and_mode(client, "wake_word")
    r = client.post("/metis/audio/wake", json={"text": "ok google git status"})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "wake_not_detected"
    assert d["block_reason"] == "wake_phrase_not_detected"


def test_wake_wrong_phrase_no_capture(client):
    _reset(client)
    _enable_and_mode(client, "wake_word")
    r = client.post("/metis/audio/wake", json={"text": "ok google git status"})
    assert r.json()["state"].get("last_audio_capture") is None


def test_wake_phrase_routes_command(client):
    _reset(client)
    _enable_and_mode(client, "wake_word")
    r = client.post("/metis/audio/wake", json={"text": "hey metis git status"})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "listen_complete"
    assert d.get("wake_phrase_detected") is True
    assert d["state"]["last_listen_trigger"] == "wake"
    assert d["state"].get("external_action_executed") is False


def test_wake_case_insensitive(client):
    _reset(client)
    _enable_and_mode(client, "wake_word")
    r = client.post("/metis/audio/wake", json={"text": "HEY METIS git status"})
    assert r.status_code == 200
    assert r.json()["status"] == "listen_complete"


def test_wake_blocked_by_mic_cutoff(client):
    _reset(client)
    _enable_and_mode(client, "wake_word")
    client.post("/metis/event", json={"type": "hardware_privacy", "device": "mic", "state": "off"})
    r = client.post("/metis/audio/wake", json={"text": "hey metis git status"})
    assert r.status_code == 200
    assert r.json()["status"] == "blocked"


def test_wake_blocked_by_audio_input_disabled(client):
    _reset(client)
    # audio_input_enabled=False by default (no _enable_audio)
    _set_mode(client, "wake_word")
    r = client.post("/metis/audio/wake", json={"text": "hey metis git status"})
    assert r.status_code == 200
    assert r.json()["status"] == "blocked"


def test_wake_redacts_text(client):
    _reset(client)
    _enable_and_mode(client, "wake_word")
    r = client.post("/metis/audio/wake", json={"text": "hey metis git status"})
    d = r.json()
    stt = d.get("stt") or {}
    assert "text" not in stt
    assert stt.get("text_redacted") is True
    for ev in d["state"].get("event_log", []):
        assert "recognized_text" not in ev
        if ev.get("provider") == "audio_input":
            assert "text" not in ev


def test_wake_no_background_thread(client):
    before = threading.active_count()
    _reset(client)
    _enable_and_mode(client, "wake_word")
    client.post("/metis/audio/wake", json={"text": "hey metis git status"})
    after = threading.active_count()
    assert after <= before + 1


def test_wake_configurable_phrase(client):
    """Custom wake_phrase set via button_event should be honoured."""
    _reset(client)
    _enable_and_mode(client, "wake_word")
    client.post("/metis/event", json={"type": "button_event", "button": "wake_phrase", "state": "hello metis"})
    # default phrase should no longer trigger
    r_old = client.post("/metis/audio/wake", json={"text": "hey metis git status"})
    assert r_old.json()["status"] == "wake_not_detected"
    # new phrase should trigger
    r_new = client.post("/metis/audio/wake", json={"text": "hello metis git status"})
    assert r_new.json()["status"] == "listen_complete"


# ── GET /metis/audio/input state fields ──────────────────────────────────────

def test_audio_input_status_reports_trigger_fields(client):
    _reset(client)
    r = client.get("/metis/audio/input")
    assert r.status_code == 200
    d = r.json()
    assert "listen_session_active" in d
    assert "wake_phrase" in d
    assert "last_listen_trigger" in d
    assert "trigger_routes" in d
    routes = d["trigger_routes"]
    assert "ptt" in routes
    assert "wake" in routes


def test_audio_input_status_shows_wake_provider_scaffold(client):
    _reset(client)
    r = client.get("/metis/audio/input")
    providers = r.json().get("providers", {})
    wake_providers = providers.get("wake_word", [])
    assert any("local_wake_word" in str(p) for p in wake_providers)


# ── No new execution authority ────────────────────────────────────────────────

def test_ptt_does_not_execute_actions(client):
    _reset(client)
    _enable_and_mode(client, "push_to_talk")
    client.post("/metis/audio/ptt", json={"action": "press"})
    r = client.post("/metis/audio/ptt", json={"action": "release", "hint": "git status"})
    assert r.json()["state"]["external_action_executed"] is False


def test_wake_does_not_execute_actions(client):
    _reset(client)
    _enable_and_mode(client, "wake_word")
    r = client.post("/metis/audio/wake", json={"text": "hey metis git status"})
    assert r.json()["state"]["external_action_executed"] is False
