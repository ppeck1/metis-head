"""Phase 0BE — Spoken confirmation routing in the audio listen path.

Hard boundaries verified here:
- _run_listen_cycle routes to voice_confirm when pending proposals exist and the
  recognized text contains an explicit confirmation phrase.
- explicit proposal ID required for approve/deny — ambiguous phrase returns readback_required.
- execution_allowed remains False after spoken confirmation.
- No standing approval granted.
- Mic cutoff blocks the listen path before any confirmation state mutation.
- Raw recognized text not persisted to state or event log.
- Normal commands route to voice_command regardless of pending proposals.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import metis_head.brain as _brain
from metis_head.brain import app
from metis_head.schemas import baseline_state


@pytest.fixture()
def client():
    _brain.STATE = baseline_state()
    return TestClient(app)


# ── helpers ───────────────────────────────────────────────────────────────────

def _reset(client: TestClient) -> None:
    _brain.STATE = baseline_state()


def _enable_audio(client: TestClient) -> None:
    client.post("/metis/event", json={"type": "button_event", "button": "audio_input", "state": "on"})


def _set_mode(client: TestClient, mode: str) -> None:
    client.post("/metis/event", json={"type": "button_event", "button": "listen_mode", "state": mode})


def _enable_ptt(client: TestClient) -> None:
    _enable_audio(client)
    _set_mode(client, "push_to_talk")


def _ptt_listen(client: TestClient, hint: str) -> dict:
    """Full PTT press+release cycle; returns the release response dict."""
    client.post("/metis/audio/ptt", json={"action": "press"})
    r = client.post("/metis/audio/ptt", json={"action": "release", "hint": hint})
    return r.json()


def _queue_proposal(client: TestClient) -> str:
    """Queue one proposal via voice/command and return its proposal_id."""
    r = client.post("/metis/voice/command", json={"text": "git status"})
    queue = r.json().get("state", {}).get("approval_queue", [])
    assert queue, "expected a proposal to be queued"
    return queue[-1]["proposal_id"]


def _cut_mic(client: TestClient) -> None:
    client.post("/metis/event", json={"type": "hardware_privacy", "device": "mic", "state": "off"})


# ── routing: confirm path ─────────────────────────────────────────────────────

def test_listen_routes_to_voice_confirm_with_explicit_approve_phrase(client):
    """Spoken 'confirm approve <id>' through PTT confirms a pending proposal."""
    _enable_ptt(client)
    proposal_id = _queue_proposal(client)
    d = _ptt_listen(client, f"confirm approve {proposal_id}")
    assert d["status"] == "listen_complete"
    assert d["route_used"] == "voice_confirm"
    vc = d["voice_command"]
    assert vc["voice_confirmation"]["confirmation_accepted"] is True
    assert vc["voice_confirmation"]["execution_allowed"] is False


def test_execution_allowed_remains_false_after_spoken_confirmation(client):
    """execution_allowed must never become True via the spoken confirmation path."""
    _enable_ptt(client)
    proposal_id = _queue_proposal(client)
    d = _ptt_listen(client, f"confirm approve {proposal_id}")
    assert d["state"].get("external_action_executed") is False
    assert d["voice_command"]["voice_confirmation"]["execution_allowed"] is False


def test_no_standing_approval_after_spoken_confirmation(client):
    _enable_ptt(client)
    proposal_id = _queue_proposal(client)
    d = _ptt_listen(client, f"confirm approve {proposal_id}")
    assert d["voice_command"]["voice_confirmation"].get("standing_approval") is False


def test_deny_with_explicit_proposal_id_routes_and_confirms_denial(client):
    """'deny proposal <id>' phrase confirms denial; execution_allowed remains False."""
    _enable_ptt(client)
    proposal_id = _queue_proposal(client)
    d = _ptt_listen(client, f"deny proposal {proposal_id}")
    assert d["status"] == "listen_complete"
    assert d["route_used"] == "voice_confirm"
    vc = d["voice_command"]
    assert vc["voice_confirmation"]["confirmation_accepted"] is True
    assert vc["voice_confirmation"]["decision"] == "denied"
    assert vc["voice_confirmation"]["execution_allowed"] is False


# ── routing: readback path ────────────────────────────────────────────────────

def test_approve_phrase_without_proposal_id_returns_readback(client):
    """Decision phrase present but no explicit proposal ID → readback_required."""
    _enable_ptt(client)
    _queue_proposal(client)
    d = _ptt_listen(client, "confirm approve")
    assert d["status"] == "listen_complete"
    assert d["route_used"] == "voice_confirm"
    vc = d["voice_command"]
    assert vc["status"] == "readback_required"
    assert vc["voice_confirmation"]["requires_explicit_proposal_id"] is True


# ── routing: voice_command fallback ──────────────────────────────────────────

def test_normal_command_routes_to_voice_command_when_no_pending_proposals(client):
    """No pending proposals → always routes to voice_command."""
    _enable_ptt(client)
    d = _ptt_listen(client, "git status")
    assert d["status"] == "listen_complete"
    assert d["route_used"] == "voice_command"


def test_normal_command_routes_to_voice_command_even_with_pending_proposals(client):
    """'git status' contains no confirmation phrase → routes to voice_command despite pending proposal."""
    _enable_ptt(client)
    _queue_proposal(client)
    d = _ptt_listen(client, "git status")
    assert d["status"] == "listen_complete"
    assert d["route_used"] == "voice_command"


def test_ambiguous_phrase_without_pending_routes_to_voice_command(client):
    """'cancel' phrase with no pending proposals → voice_command (decision present but no proposals)."""
    _enable_ptt(client)
    d = _ptt_listen(client, "cancel")
    assert d["route_used"] == "voice_command"


def test_audio_listen_routes_to_voice_confirm_with_explicit_phrase(client):
    """POST /metis/audio/listen also routes to voice_confirm when condition met."""
    _enable_audio(client)
    _set_mode(client, "push_to_talk")
    proposal_id = _queue_proposal(client)
    r = client.post("/metis/audio/listen", json={"hint": f"confirm approve {proposal_id}"})
    d = r.json()
    assert d["status"] == "listen_complete"
    assert d["route_used"] == "voice_confirm"
    assert d["voice_command"]["voice_confirmation"]["confirmation_accepted"] is True


# ── mic cutoff gate ───────────────────────────────────────────────────────────

def test_mic_cutoff_blocks_ptt_release_before_confirmation(client):
    """Mic cut after PTT press blocks the release; no confirmation state mutation."""
    _enable_ptt(client)
    proposal_id = _queue_proposal(client)
    client.post("/metis/audio/ptt", json={"action": "press"})
    assert _brain.STATE.get("listen_session_active") is True
    _cut_mic(client)
    r = client.post("/metis/audio/ptt", json={"action": "release", "hint": f"confirm approve {proposal_id}"})
    d = r.json()
    assert d["status"] == "blocked"
    assert d["block_reason"] == "mic_hardware_cutoff"
    q = _brain.STATE.get("approval_queue", [])
    assert q[0].get("review_status") == "pending"


def test_mic_cutoff_blocks_audio_listen_before_confirmation(client):
    """POST /metis/audio/listen with mic off → blocked before _run_listen_cycle."""
    _enable_audio(client)
    _set_mode(client, "push_to_talk")
    proposal_id = _queue_proposal(client)
    _cut_mic(client)
    r = client.post("/metis/audio/listen", json={"hint": f"confirm approve {proposal_id}"})
    d = r.json()
    assert d["status"] == "blocked"
    assert d["block_reason"] == "mic_hardware_cutoff"
    q = _brain.STATE.get("approval_queue", [])
    assert q[0].get("review_status") == "pending"


# ── redaction ─────────────────────────────────────────────────────────────────

def test_raw_transcript_not_in_event_log_after_voice_confirm_route(client):
    """The full confirmation phrase must not appear in any audio_input event log entry."""
    _enable_ptt(client)
    proposal_id = _queue_proposal(client)
    confirm_hint = f"confirm approve {proposal_id}"
    _ptt_listen(client, confirm_hint)
    for ev in _brain.STATE.get("event_log", []):
        if ev.get("provider") == "audio_input":
            assert "confirm approve" not in json.dumps(ev)


def test_stt_result_exposes_only_redacted_fields_on_confirm_route(client):
    """STTResult in the response must have text_redacted=True and no raw text field."""
    _enable_ptt(client)
    proposal_id = _queue_proposal(client)
    d = _ptt_listen(client, f"confirm approve {proposal_id}")
    stt = d.get("stt", {})
    assert stt.get("text_redacted") is True
    assert "text" not in stt or stt.get("text") is None
