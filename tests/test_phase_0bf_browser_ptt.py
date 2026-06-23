"""Phase 0BF — Browser held-to-talk verbal conversation.

Hard boundaries verified here:
- audio_browser_ptt is blocked when audio_input_enabled is False.
- audio_browser_ptt is blocked when mic_hardware_enabled is False.
- audio_browser_ptt is blocked when listen_mode is not push_to_talk.
- A simulated audio upload routes to voice_command (no pending proposals).
- A confirmation phrase upload routes to voice_confirm (pending proposal present).
- Raw transcript is not persisted to state or the event log.
- execution_allowed remains False after browser PTT cycle.
"""
from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

import metis_head.brain as _brain
from metis_head.brain import app
from metis_head.schemas import baseline_state

# ── minimal synthetic WAV (44 bytes, 16 kHz mono) ─────────────────────────────

_WAV_HEADER = (
    b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00"
    b"\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00"
    b"\x02\x00\x10\x00data\x00\x00\x00\x00"
)


@pytest.fixture()
def client():
    _brain.STATE = baseline_state()
    return TestClient(app)


# ── helpers ───────────────────────────────────────────────────────────────────

def _enable_audio(client: TestClient) -> None:
    client.post("/metis/event", json={"type": "button_event", "button": "audio_input", "state": "on"})


def _enable_mic(client: TestClient) -> None:
    client.post("/metis/event", json={"type": "hardware_privacy", "device": "mic", "enabled": True})


def _set_mode(client: TestClient, mode: str) -> None:
    client.post("/metis/event", json={"type": "button_event", "button": "listen_mode", "state": mode})


def _enable_ptt(client: TestClient) -> None:
    _enable_audio(client)
    _enable_mic(client)
    _set_mode(client, "push_to_talk")


def _upload(client: TestClient, hint: str = "git status", audio: bytes = _WAV_HEADER) -> dict:
    return client.post(
        "/metis/audio/browser_ptt",
        files={"audio": ("ptt.wav", io.BytesIO(audio), "audio/wav")},
        data={"stt_provider": "simulated", "stt_hint": hint, "options_json": "{}"},
    ).json()


def _upload_response(
    client: TestClient,
    *,
    hint: str = "git status",
    audio: bytes = _WAV_HEADER,
    content_type: str = "audio/wav",
):
    return client.post(
        "/metis/audio/browser_ptt",
        files={"audio": ("ptt.wav", io.BytesIO(audio), content_type)},
        data={"stt_provider": "simulated", "stt_hint": hint, "options_json": "{}"},
    )


def _queue_proposal(client: TestClient) -> str:
    r = client.post("/metis/voice/command", json={"text": "git status"})
    queue = r.json().get("state", {}).get("approval_queue", [])
    assert queue, "expected a proposal to be queued"
    return queue[-1]["proposal_id"]


# ── governance blocks ─────────────────────────────────────────────────────────

def test_blocked_when_audio_input_disabled(client):
    """Upload is blocked when audio_input_enabled is False (default)."""
    _enable_mic(client)
    _set_mode(client, "push_to_talk")
    # audio_input NOT enabled
    d = _upload(client)
    assert d["status"] == "blocked"
    assert d["block_reason"] == "audio_input_disabled"


def test_blocked_when_mic_hardware_off(client):
    """Upload is blocked when mic_hardware_enabled is False."""
    _enable_audio(client)
    _set_mode(client, "push_to_talk")
    # explicitly cut mic hardware
    client.post("/metis/event", json={"type": "hardware_privacy", "device": "mic", "state": "off"})
    d = _upload(client)
    assert d["status"] == "blocked"
    assert d["block_reason"] == "mic_hardware_cutoff"


def test_blocked_when_listen_mode_not_push_to_talk(client):
    """Upload is blocked when listen_mode is not push_to_talk."""
    _enable_audio(client)
    _enable_mic(client)
    _set_mode(client, "no_listen")
    d = _upload(client)
    assert d["status"] == "wrong_mode"
    assert d["block_reason"] == "listen_mode_not_push_to_talk"


def test_blocked_when_listen_mode_wake_word(client):
    """Upload is blocked even in wake_word mode — PTT semantics require push_to_talk."""
    _enable_audio(client)
    _enable_mic(client)
    _set_mode(client, "wake_word")
    d = _upload(client)
    assert d["status"] == "wrong_mode"
    assert d["block_reason"] == "listen_mode_not_push_to_talk"


# ── routing ───────────────────────────────────────────────────────────────────

def test_upload_routes_to_voice_command(client):
    """A normal command hint routes to voice_command when no proposals are pending."""
    _enable_ptt(client)
    d = _upload(client, hint="git status")
    assert d["status"] == "listen_complete"
    assert d["route_used"] == "voice_command"
    assert d["voice_command"] is not None


def test_upload_confirmation_phrase_routes_to_voice_confirm(client):
    """A confirmation phrase routes to voice_confirm when a proposal is pending."""
    _enable_ptt(client)
    proposal_id = _queue_proposal(client)
    d = _upload(client, hint=f"confirm approve {proposal_id}")
    assert d["status"] == "listen_complete"
    assert d["route_used"] == "voice_confirm"
    vc = d["voice_command"]
    assert vc["voice_confirmation"]["confirmation_accepted"] is True
    assert vc["voice_confirmation"]["execution_allowed"] is False


# ── redaction ─────────────────────────────────────────────────────────────────

def test_raw_transcript_not_in_event_log(client):
    """audio_input events in the log must not contain the raw recognized text."""
    _enable_ptt(client)
    d = _upload(client, hint="git status")
    event_log = d.get("state", {}).get("event_log", [])
    audio_events = [
        e for e in event_log if e.get("type") == "provider_event" and e.get("provider") == "audio_input"
    ]
    assert audio_events
    for ev in audio_events:
        stt = ev.get("stt_result") or {}
        assert "text" not in stt, f"raw text found in event: {ev}"
        assert "text_redacted" in stt or not stt, "expected text_redacted key"


def test_voice_origin_sentinel_does_not_persist_in_state_or_logs(client):
    """Voice-origin recognized text is transient and must not persist raw in canonical state."""
    _enable_ptt(client)
    sentinel = "VOICE_SENTINEL_SHOULD_NOT_PERSIST_0BG"
    d = _upload(client, hint=f"please repeat {sentinel}")
    assert d["status"] == "listen_complete"

    persisted_state = json.dumps(d["state"], sort_keys=True)
    assert sentinel not in persisted_state

    event_log = d["state"]["event_log"]
    provider_events = [e for e in event_log if e.get("type") == "provider_event"]
    assert provider_events
    for ev in provider_events:
        assert sentinel not in json.dumps(ev, sort_keys=True)
    assert any(
        entry.get("role") == "user" and "voice transcript redacted" in entry.get("content", "")
        for entry in d["state"]["chat_history"]
    )


def test_browser_ptt_rejects_oversized_upload(client):
    _enable_ptt(client)
    oversized = _WAV_HEADER + (b"\x00" * (_brain.BROWSER_PTT_MAX_UPLOAD_BYTES + 1))
    response = _upload_response(client, audio=oversized)
    assert response.status_code == 413
    assert "exceeds" in response.json()["detail"]


def test_browser_ptt_rejects_invalid_content_type(client):
    _enable_ptt(client)
    response = _upload_response(client, content_type="text/plain")
    assert response.status_code == 415
    assert "unsupported audio content type" in response.json()["detail"]


def test_browser_ptt_rejects_invalid_wav_payload(client):
    _enable_ptt(client)
    response = _upload_response(client, audio=b"not a wav payload", content_type="audio/wav")
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid WAV upload"


# ── governance invariant ──────────────────────────────────────────────────────

def test_execution_allowed_remains_false(client):
    """execution_allowed must be False after a browser PTT cycle."""
    _enable_ptt(client)
    proposal_id = _queue_proposal(client)
    d = _upload(client, hint=f"confirm approve {proposal_id}")
    vc = d["voice_command"]
    assert vc["voice_confirmation"]["execution_allowed"] is False
