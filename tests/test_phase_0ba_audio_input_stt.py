"""Phase 0BA — Audio Input + STT Adapter tests.

All tests run with no hardware, no real microphone, and no new runtime
dependencies. Covers plan §7 assertions 1–9.
"""

from __future__ import annotations

import json
from copy import deepcopy

from fastapi.testclient import TestClient

from metis_head.audio_input import (
    CaptureContext,
    LocalMicAudioInput,
    NoneAudioInput,
    SimulatedAudioInput,
    audio_input_provider_from_config,
)
from metis_head.brain import app
from metis_head.reducer import reduce_metis_event, replay_events
from metis_head.schemas import baseline_state
from metis_head.stt import (
    LocalWhisperSTT,
    NoneSTT,
    SimulatedSTT,
    get_recognized_text,
    stt_provider_from_config,
)


# ---------------------------------------------------------------------------
# Test 1: mic cutoff blocks capture; blocked_capture_count increments; redacted event only
# ---------------------------------------------------------------------------


def test_mic_cutoff_blocks_capture_via_endpoint() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")
    client.post("/metis/event", json={"type": "hardware_privacy", "device": "mic", "enabled": False})

    resp = client.post("/metis/audio/input/capture")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "blocked"
    assert body["block_reason"] == "mic_hardware_cutoff"
    assert body["captured"] is False
    state = body["state"]
    assert state["blocked_capture_count"] >= 1
    assert state["mic_hardware_enabled"] is False


def test_mic_cutoff_increments_blocked_count_in_state() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")
    client.post("/metis/event", json={"type": "hardware_privacy", "device": "mic", "enabled": False})

    resp1 = client.post("/metis/audio/input/capture")
    resp2 = client.post("/metis/audio/input/capture")

    state1 = resp1.json()["state"]
    state2 = resp2.json()["state"]
    assert state2["blocked_capture_count"] == state1["blocked_capture_count"] + 1


def test_mic_cutoff_event_is_redacted_only() -> None:
    """audio_input blocked events must not contain raw audio data."""
    client = TestClient(app)
    client.post("/metis/state/reset")
    client.post("/metis/event", json={"type": "hardware_privacy", "device": "mic", "enabled": False})

    resp = client.post("/metis/audio/input/capture")

    state = resp.json()["state"]
    audio_events = [
        e for e in state["event_log"]
        if isinstance(e, dict) and e.get("provider") == "audio_input"
    ]
    assert audio_events, "expected at least one audio_input provider_event in log"
    for event in audio_events:
        assert "audio_path" not in event
        assert "pcm_data" not in event
        assert "raw_audio" not in event
        assert "text" not in event


# ---------------------------------------------------------------------------
# Test 2: audio_input_enabled=false blocks capture with audio_input_disabled reason
# ---------------------------------------------------------------------------


def test_audio_input_disabled_blocks_capture() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")
    # baseline: mic is on (True) but audio_input_enabled=False by default

    resp = client.post("/metis/audio/input/capture")

    body = resp.json()
    assert body["status"] == "blocked"
    assert body["block_reason"] == "audio_input_disabled"
    assert body["captured"] is False


def test_audio_input_disabled_reason_correct_for_listen() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")

    resp = client.post("/metis/audio/listen")

    body = resp.json()
    assert body["status"] == "blocked"
    assert body["block_reason"] == "audio_input_disabled"


# ---------------------------------------------------------------------------
# Test 3: SimulatedAudioInput.capture() returns deterministic frames/levels/duration
# ---------------------------------------------------------------------------


def test_simulated_capture_returns_metadata() -> None:
    provider = SimulatedAudioInput()
    context = CaptureContext(fixture_id="sine_440", sample_rate=16000, duration_ms=500)

    result = provider.capture(context)

    assert result.captured is True
    assert result.provider_id == "simulated"
    assert result.status == "ok"
    assert result.audio_duration_ms > 0
    assert len(result.audio_levels) > 0
    assert all(0.0 <= level <= 1.0 for level in result.audio_levels)
    assert len(result.audio_spectrum_frames) > 0
    assert result.frame_count == len(result.audio_spectrum_frames)
    assert result.sample_rate == 16000


def test_simulated_capture_is_deterministic() -> None:
    provider = SimulatedAudioInput()
    context = CaptureContext(fixture_id="sine_440", sample_rate=16000, duration_ms=500)

    r1 = provider.capture(context)
    r2 = provider.capture(context)

    assert r1.audio_levels == r2.audio_levels
    assert r1.audio_spectrum_frames == r2.audio_spectrum_frames
    assert r1.audio_duration_ms == r2.audio_duration_ms


def test_simulated_capture_to_dict_no_raw_audio() -> None:
    provider = SimulatedAudioInput()
    result = provider.capture(CaptureContext(fixture_id="sine_440"))

    d = result.to_dict()
    dumped = json.dumps(d)

    assert "audio_path" not in dumped
    assert "pcm_data" not in dumped
    assert "raw_audio" not in dumped
    assert "audio_spectrum_frames" not in d, "spectrum frames omitted from to_dict by design"


def test_none_audio_input_returns_disabled() -> None:
    provider = NoneAudioInput()
    result = provider.capture(CaptureContext())

    assert result.captured is False
    assert result.status == "disabled"
    assert result.audio_levels == []
    assert result.block_reason == "audio_input_provider_none"


def test_audio_input_provider_from_config() -> None:
    assert isinstance(audio_input_provider_from_config("simulated"), SimulatedAudioInput)
    assert isinstance(audio_input_provider_from_config("local_mic"), LocalMicAudioInput)
    assert isinstance(audio_input_provider_from_config("none"), NoneAudioInput)
    assert isinstance(audio_input_provider_from_config("unknown"), NoneAudioInput)


# ---------------------------------------------------------------------------
# Test 4: SimulatedSTT is deterministic and returns canonical recognized text
# ---------------------------------------------------------------------------


def test_simulated_stt_is_deterministic() -> None:
    stt = SimulatedSTT()
    ctx = {"hint": "git_status"}

    r1 = stt.transcribe(None, ctx)
    r2 = stt.transcribe(None, ctx)

    assert r1.text_hash == r2.text_hash
    assert r1.text_len == r2.text_len
    assert get_recognized_text(r1) == get_recognized_text(r2)


def test_simulated_stt_canonical_text() -> None:
    stt = SimulatedSTT()

    assert get_recognized_text(stt.transcribe(None, {"hint": "git_status"})) == "git status"
    assert get_recognized_text(stt.transcribe(None, {"hint": "time_now"})) == "what time is it"
    assert get_recognized_text(stt.transcribe(None, {"hint": "default"})) == "git status"


def test_simulated_stt_to_dict_has_no_text_field() -> None:
    stt = SimulatedSTT()
    result = stt.transcribe(None, {"hint": "git_status"})

    d = result.to_dict()
    assert "text" not in d
    assert "_recognized_text" not in d
    assert "recognized_text" not in d
    assert d["text_redacted"] is True
    assert d["text_len"] > 0
    assert d["text_hash"] != ""


def test_none_stt_returns_unavailable() -> None:
    stt = NoneSTT()
    result = stt.transcribe(None, {})

    assert result.status == "unavailable"
    assert get_recognized_text(result) == ""


def test_stt_provider_from_config() -> None:
    assert isinstance(stt_provider_from_config("simulated"), SimulatedSTT)
    assert isinstance(stt_provider_from_config("local_whisper"), LocalWhisperSTT)
    assert isinstance(stt_provider_from_config("none"), NoneSTT)
    assert isinstance(stt_provider_from_config("unknown"), NoneSTT)


# ---------------------------------------------------------------------------
# Test 5: /metis/audio/listen routes "git status" through governed path → proposal queued
# ---------------------------------------------------------------------------


def _enable_audio_listen(client: TestClient) -> None:
    """Set state so audio/listen can proceed past all governance gates."""
    client.post("/metis/state/reset")
    client.post("/metis/event", json={"type": "button_event", "button": "audio_input", "state": "on"})
    client.post("/metis/event", json={"type": "button_event", "button": "listen_mode", "state": "push_to_talk"})


def test_audio_listen_routes_git_status_to_proposal() -> None:
    client = TestClient(app)
    _enable_audio_listen(client)

    resp = client.post("/metis/audio/listen", json={"hint": "git_status"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "listen_complete"
    assert body["stt"]["text_redacted"] is True

    # The governed voice_command route should have routed "git status" to a proposal
    state = body["state"]
    queue = state.get("approval_queue", [])
    git_proposals = [p for p in queue if p.get("tool_id") == "git.status"]
    assert git_proposals, "expected a git.status proposal in approval_queue"
    assert git_proposals[0].get("review_status") == "pending"


def test_audio_listen_proposal_has_no_execution_authority() -> None:
    client = TestClient(app)
    _enable_audio_listen(client)

    resp = client.post("/metis/audio/listen", json={"hint": "git_status"})

    body = resp.json()
    state = body["state"]
    assert state.get("external_action_executed") is False
    queue = state.get("approval_queue", [])
    for proposal in queue:
        assert proposal.get("review_status") != "executed"


# ---------------------------------------------------------------------------
# Test 6: No raw audio path, PCM, or transcript text in state/event_log/response
# ---------------------------------------------------------------------------


def test_no_raw_audio_or_transcript_in_audio_events() -> None:
    client = TestClient(app)
    _enable_audio_listen(client)

    resp = client.post("/metis/audio/listen", json={"hint": "git_status"})

    state = resp.json()["state"]
    audio_events = [
        e for e in state.get("event_log", [])
        if isinstance(e, dict) and e.get("provider") == "audio_input"
    ]
    for event in audio_events:
        dumped = json.dumps(event)
        assert "audio_path" not in dumped
        assert "pcm_data" not in dumped
        assert "raw_audio" not in dumped
        # recognized text must not appear in audio provider events
        assert "git status" not in dumped


def test_no_raw_audio_in_last_audio_capture() -> None:
    client = TestClient(app)
    _enable_audio_listen(client)

    resp = client.post("/metis/audio/listen", json={"hint": "git_status"})

    state = resp.json()["state"]
    last_capture = state.get("last_audio_capture")
    if last_capture is not None:
        dumped = json.dumps(last_capture)
        assert "audio_path" not in dumped
        assert "pcm_data" not in dumped
        assert "text" not in last_capture or last_capture.get("text_redacted") is True
        assert "git status" not in dumped


def test_stt_response_never_has_raw_transcript() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")

    resp = client.post("/metis/audio/transcribe", json={"hint": "git_status", "stt_provider": "simulated"})

    body = resp.json()
    stt = body["stt"]
    assert "text" not in stt
    assert "_recognized_text" not in stt
    assert stt.get("text_redacted") is True
    dumped = json.dumps(stt)
    assert "git status" not in dumped


def test_capture_response_has_no_raw_audio() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")
    client.post("/metis/event", json={"type": "button_event", "button": "audio_input", "state": "on"})

    resp = client.post("/metis/audio/input/capture", json={"hint": "sine_440"})

    body = resp.json()
    if body.get("capture"):
        dumped = json.dumps(body["capture"])
        assert "audio_path" not in dumped
        assert "pcm_data" not in dumped
        assert "audio_spectrum_frames" not in body["capture"]


# ---------------------------------------------------------------------------
# Test 7: LocalMicAudioInput / LocalWhisperSTT remain disabled / not-enabled
# ---------------------------------------------------------------------------


def test_local_mic_audio_input_is_disabled() -> None:
    provider = LocalMicAudioInput()

    health = provider.health()
    assert health["status"] == "disabled"

    result = provider.capture(CaptureContext())
    assert result.captured is False
    assert result.status == "not_enabled"
    assert "not_enabled" in (result.block_reason or "")


def test_local_whisper_stt_is_disabled() -> None:
    stt = LocalWhisperSTT()

    health = stt.health()
    assert health["status"] == "disabled"

    result = stt.transcribe(None, {})
    assert result.status == "not_enabled"
    assert get_recognized_text(result) == ""


def test_local_providers_no_import_side_effects() -> None:
    """Instantiating disabled providers must not import sounddevice/whisper/vosk."""
    import sys

    before = set(sys.modules.keys())
    LocalMicAudioInput().capture(CaptureContext())
    LocalWhisperSTT().transcribe(None, {})
    after = set(sys.modules.keys())
    new_modules = after - before
    for mod in new_modules:
        assert "sounddevice" not in mod
        assert "whisper" not in mod
        assert "vosk" not in mod


# ---------------------------------------------------------------------------
# Test 8: Replay determinism — identical events → identical audio-input state
# ---------------------------------------------------------------------------


def test_audio_input_state_replay_determinism() -> None:
    events = [
        {"type": "hardware_privacy", "device": "mic", "enabled": False},
        {"type": "provider_event", "provider": "audio_input", "status": "blocked", "block_reason": "mic_hardware_cutoff", "input_mode": "simulated_audio_input", "audio_input_schema": "audio_input_adapter.v0.1"},
    ]
    initial = baseline_state()
    s1 = replay_events(deepcopy(initial), events)
    s2 = replay_events(deepcopy(initial), events)

    assert s1["audio_input_state"] == s2["audio_input_state"]
    assert s1["blocked_capture_count"] == s2["blocked_capture_count"]
    assert s1["mic_hardware_enabled"] == s2["mic_hardware_enabled"]


def test_audio_input_capture_complete_determinism() -> None:
    events = [
        {"type": "button_event", "button": "audio_input", "state": "on"},
        {
            "type": "provider_event",
            "provider": "audio_input",
            "status": "complete",
            "input_mode": "simulated_audio_input",
            "audio_input_schema": "audio_input_adapter.v0.1",
            "captured": True,
            "audio_duration_ms": 500,
            "frame_count": 8,
            "sample_rate": 16000,
            "audio_provider_id": "simulated",
        },
    ]
    initial = baseline_state()
    s1 = replay_events(deepcopy(initial), events)
    s2 = replay_events(deepcopy(initial), events)

    assert s1["audio_input_state"] == "idle"
    assert s1["capture_count"] == s2["capture_count"]
    assert s1["last_audio_capture"] == s2["last_audio_capture"]


# ---------------------------------------------------------------------------
# Test 9: No new external_action_executed; no execution authority added
# ---------------------------------------------------------------------------


def test_listen_does_not_set_external_action_executed() -> None:
    client = TestClient(app)
    _enable_audio_listen(client)

    resp = client.post("/metis/audio/listen", json={"hint": "git_status"})

    state = resp.json()["state"]
    assert state.get("external_action_executed") is False


def test_listen_blocked_no_execution_authority() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")
    # audio_input_enabled defaults to False — listen must be blocked
    resp = client.post("/metis/audio/listen")

    body = resp.json()
    assert body["status"] == "blocked"
    assert body["state"].get("external_action_executed") is False


def test_listen_mode_no_listen_blocks_audio_listen() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")
    client.post("/metis/event", json={"type": "button_event", "button": "audio_input", "state": "on"})
    # listen_mode defaults to "no_listen" → must block

    resp = client.post("/metis/audio/listen")

    body = resp.json()
    assert body["status"] == "blocked"
    assert body["block_reason"] == "listen_mode_no_listen"


# ---------------------------------------------------------------------------
# Endpoint shape / status tests
# ---------------------------------------------------------------------------


def test_audio_input_status_endpoint_shape() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")

    resp = client.get("/metis/audio/input")

    assert resp.status_code == 200
    body = resp.json()
    assert body["audio_input_adapter_version"] == "audio_input_adapter.v0.1"
    assert body["stt_engine_version"] == "stt_engine.v0.1"
    assert "audio_input_state" in body
    assert "listen_mode" in body
    assert "mic_hardware_enabled" in body
    assert body["audio_provider_health"]["provider_id"] == "simulated"
    assert body["stt_provider_health"]["provider_id"] == "simulated"


def test_audio_input_state_in_baseline() -> None:
    state = baseline_state()
    assert state["audio_input_state"] == "disabled"
    assert state["audio_input_enabled"] is False
    assert state["listen_mode"] == "no_listen"
    assert state["last_audio_capture"] is None


def test_audio_input_adapter_in_input_adapters() -> None:
    state = baseline_state()
    assert "audio_input" in state["input_adapters"]
    adapter = state["input_adapters"]["audio_input"]
    assert adapter["schema_version"] == "audio_input_adapter.v0.1"
    assert adapter["schema_supported"] is True
    assert "capture" in adapter["capabilities"]


def test_button_event_enables_audio_input() -> None:
    state = baseline_state()
    state = reduce_metis_event(state, {"type": "button_event", "button": "audio_input", "state": "on"})

    assert state["audio_input_enabled"] is True
    assert state["audio_input_state"] == "idle"


def test_button_event_sets_listen_mode() -> None:
    state = baseline_state()
    state = reduce_metis_event(state, {"type": "button_event", "button": "listen_mode", "state": "push_to_talk"})

    assert state["listen_mode"] == "push_to_talk"


def test_button_event_listen_mode_ignores_invalid_values() -> None:
    state = baseline_state()
    state = reduce_metis_event(state, {"type": "button_event", "button": "listen_mode", "state": "always_on"})

    assert state["listen_mode"] == "no_listen"
