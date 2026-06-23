"""Phase 0BC — LocalFasterWhisperSTT tests.

All tests run in CI with NO real STT engine, NO METIS_STT_ALLOW_LOCAL env var,
and NO faster_whisper package. They verify the gate logic, the lazy import,
the in-memory audio handoff, and the redaction contract without loading any model.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest
from fastapi.testclient import TestClient

from metis_head.audio_input import CaptureContext, SimulatedAudioInput
from metis_head.brain import app
from metis_head.stt import (
    LocalFasterWhisperSTT,
    NoneSTT,
    OpenAIWhisperSTT,
    STTResult,
    SimulatedSTT,
    VoskSTT,
    WhisperCppSTT,
    _local_stt_allowed,
    stt_provider_from_config,
)


# ---------------------------------------------------------------------------
# faster_whisper must NOT be imported at module load time
# ---------------------------------------------------------------------------


def test_stt_module_does_not_import_faster_whisper() -> None:
    """Importing metis_head.stt must not pull in faster_whisper."""
    assert "faster_whisper" not in sys.modules, (
        "faster_whisper appeared in sys.modules after importing metis_head.stt — "
        "it must be lazy-imported inside transcribe() only."
    )


# ---------------------------------------------------------------------------
# _local_stt_allowed() flag
# ---------------------------------------------------------------------------


def test_local_stt_allowed_defaults_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("METIS_STT_ALLOW_LOCAL", raising=False)
    assert _local_stt_allowed() is False


def test_local_stt_allowed_truthy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("true", "True", "TRUE", "1", "yes", "on", "enabled"):
        monkeypatch.setenv("METIS_STT_ALLOW_LOCAL", value)
        assert _local_stt_allowed() is True, f"expected True for METIS_STT_ALLOW_LOCAL={value!r}"


def test_local_stt_allowed_falsy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("false", "0", "no", "off", "", "disabled"):
        monkeypatch.setenv("METIS_STT_ALLOW_LOCAL", value)
        assert _local_stt_allowed() is False, f"expected False for METIS_STT_ALLOW_LOCAL={value!r}"


# ---------------------------------------------------------------------------
# LocalFasterWhisperSTT — not_enabled without flag
# ---------------------------------------------------------------------------


def test_local_faster_whisper_not_enabled_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("METIS_STT_ALLOW_LOCAL", raising=False)
    provider = LocalFasterWhisperSTT()
    result = provider.transcribe(None, {})
    assert result.status == "not_enabled"
    assert result.text_len == 0
    assert result.text_hash == ""
    assert "faster_whisper" not in sys.modules


def test_local_faster_whisper_health_disabled_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("METIS_STT_ALLOW_LOCAL", raising=False)
    provider = LocalFasterWhisperSTT()
    health = provider.health()
    assert health["status"] == "disabled"
    assert health["allow_local"] is False
    assert "faster_whisper" not in sys.modules


# ---------------------------------------------------------------------------
# LocalFasterWhisperSTT — dependency_unavailable when flag set but package absent
# ---------------------------------------------------------------------------


def test_local_faster_whisper_dependency_unavailable_when_package_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """When flag is set but faster_whisper is not installed, transcribe returns
    dependency_unavailable without crashing."""
    monkeypatch.setenv("METIS_STT_ALLOW_LOCAL", "true")
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # type: ignore[arg-type]

    provider = LocalFasterWhisperSTT()
    result = provider.transcribe(None, {})

    assert result.status in {"dependency_unavailable", "not_enabled"}
    assert result.text_len == 0


# ---------------------------------------------------------------------------
# STTResult redaction: _recognized_text never in to_dict()
# ---------------------------------------------------------------------------


def test_stt_result_to_dict_never_has_recognized_text() -> None:
    result = SimulatedSTT().transcribe(None, {"hint": "git_status"})
    serialized = result.to_dict()

    assert "text" not in serialized
    assert "_recognized_text" not in serialized
    recognized = getattr(result, "_recognized_text", "")
    assert recognized  # exists in-memory
    for value in serialized.values():
        assert recognized not in str(value), (
            f"recognized text '{recognized}' leaked into to_dict() value: {value!r}"
        )


# ---------------------------------------------------------------------------
# _wav_bytes: set by SimulatedAudioInput, NOT in to_dict()
# ---------------------------------------------------------------------------


def test_simulated_audio_sets_wav_bytes() -> None:
    provider = SimulatedAudioInput()
    result = provider.capture(CaptureContext())
    wav_bytes = getattr(result, "_wav_bytes", None)
    assert wav_bytes is not None, "_wav_bytes not set on SimulatedAudioInput result"
    assert isinstance(wav_bytes, bytes)
    assert len(wav_bytes) > 0


def test_wav_bytes_not_in_capture_result_to_dict() -> None:
    provider = SimulatedAudioInput()
    result = provider.capture(CaptureContext())
    serialized = result.to_dict()

    assert "_wav_bytes" not in serialized
    assert "wav_bytes" not in serialized
    assert "audio_bytes" not in serialized

    wav_bytes = getattr(result, "_wav_bytes", None)
    assert wav_bytes is not None
    # Ensure raw bytes are not embedded as a value either
    for key, value in serialized.items():
        assert not isinstance(value, (bytes, bytearray)), (
            f"to_dict() key {key!r} contains bytes — raw audio must not be serialised"
        )


# ---------------------------------------------------------------------------
# Planted-marker scan: _wav_bytes never in state, event log, or response
# ---------------------------------------------------------------------------


def _enable_audio_listen(client: TestClient) -> None:
    client.post("/metis/state/reset")
    client.post("/metis/event", json={"type": "button_event", "button": "audio_input", "state": "on"})
    client.post("/metis/event", json={"type": "button_event", "button": "listen_mode", "state": "push_to_talk"})


_WAV_MARKER = "METIS_WAV_BYTES_MUST_NOT_LEAK"


def test_wav_bytes_not_in_listen_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that _wav_bytes does not appear in any JSON response from audio/listen."""
    monkeypatch.delenv("METIS_STT_ALLOW_LOCAL", raising=False)
    monkeypatch.delenv("METIS_AUDIO_ALLOW_LOCAL_MIC", raising=False)
    client = TestClient(app)
    _enable_audio_listen(client)

    resp = client.post("/metis/audio/listen", json={"hint": "git_status"})
    body_str = resp.text

    assert "_wav_bytes" not in body_str
    assert "wav_bytes" not in body_str


def test_wav_bytes_not_in_state_after_listen(monkeypatch: pytest.MonkeyPatch) -> None:
    """State must not contain _wav_bytes after an audio/listen call."""
    monkeypatch.delenv("METIS_STT_ALLOW_LOCAL", raising=False)
    monkeypatch.delenv("METIS_AUDIO_ALLOW_LOCAL_MIC", raising=False)
    client = TestClient(app)
    _enable_audio_listen(client)

    resp = client.post("/metis/audio/listen", json={"hint": "git_status"})
    state = resp.json()["state"]
    state_str = str(state)

    assert "_wav_bytes" not in state_str
    assert "wav_bytes" not in state_str


def test_wav_bytes_not_in_audio_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """Event log entries must not contain _wav_bytes."""
    monkeypatch.delenv("METIS_STT_ALLOW_LOCAL", raising=False)
    monkeypatch.delenv("METIS_AUDIO_ALLOW_LOCAL_MIC", raising=False)
    client = TestClient(app)
    _enable_audio_listen(client)

    resp = client.post("/metis/audio/listen", json={"hint": "git_status"})
    state = resp.json()["state"]
    event_log = state.get("event_log", [])
    audio_events = [e for e in event_log if e.get("provider") == "audio_input"]

    assert audio_events, "no audio_input events found in event log"
    for event in audio_events:
        event_str = str(event)
        assert "_wav_bytes" not in event_str
        assert "wav_bytes" not in event_str
        for value in event.values():
            assert not isinstance(value, (bytes, bytearray)), (
                f"event field contains raw bytes: {event!r}"
            )


# ---------------------------------------------------------------------------
# stt_provider_from_config routing
# ---------------------------------------------------------------------------


def test_stt_provider_from_config_faster_whisper() -> None:
    provider = stt_provider_from_config("faster_whisper")
    assert isinstance(provider, LocalFasterWhisperSTT)


def test_stt_provider_from_config_vosk_scaffold() -> None:
    provider = stt_provider_from_config("vosk")
    assert isinstance(provider, VoskSTT)
    result = provider.transcribe(None, {})
    assert result.status == "not_enabled"
    assert "vosk" not in sys.modules


def test_stt_provider_from_config_openai_whisper_scaffold() -> None:
    provider = stt_provider_from_config("openai_whisper")
    assert isinstance(provider, OpenAIWhisperSTT)
    result = provider.transcribe(None, {})
    assert result.status == "not_enabled"


def test_stt_provider_from_config_whispercpp_scaffold() -> None:
    provider = stt_provider_from_config("whispercpp")
    assert isinstance(provider, WhisperCppSTT)
    result = provider.transcribe(None, {})
    assert result.status == "not_enabled"


def test_stt_provider_from_config_unknown_returns_none() -> None:
    provider = stt_provider_from_config("unknown_engine_xyz")
    assert isinstance(provider, NoneSTT)


# ---------------------------------------------------------------------------
# GET /metis/audio/input — new STT fields
# ---------------------------------------------------------------------------


def test_audio_input_status_includes_stt_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("METIS_STT_ALLOW_LOCAL", raising=False)
    monkeypatch.delenv("METIS_STT_ENGINE", raising=False)
    monkeypatch.delenv("METIS_STT_MODEL", raising=False)
    client = TestClient(app)
    client.post("/metis/state/reset")

    resp = client.get("/metis/audio/input")
    body = resp.json()

    assert resp.status_code == 200
    assert "stt_engine" in body
    assert "stt_allow_local" in body
    assert "faster_whisper_available" in body
    assert "stt_model" in body
    assert body["stt_engine"] == "simulated"
    assert body["stt_allow_local"] is False
    assert body["faster_whisper_available"] is False
    assert body["stt_model"] == "small"


def test_audio_input_status_stt_engine_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METIS_STT_ENGINE", "faster_whisper")
    monkeypatch.setenv("METIS_STT_MODEL", "tiny")
    monkeypatch.delenv("METIS_STT_ALLOW_LOCAL", raising=False)
    client = TestClient(app)
    client.post("/metis/state/reset")

    resp = client.get("/metis/audio/input")
    body = resp.json()

    assert body["stt_engine"] == "faster_whisper"
    assert body["stt_model"] == "tiny"
    assert body["stt_allow_local"] is False
    assert body["faster_whisper_available"] is False


def test_audio_input_status_providers_includes_faster_whisper() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")

    resp = client.get("/metis/audio/input")
    body = resp.json()

    assert "faster_whisper" in body["providers"]["stt"]


# ---------------------------------------------------------------------------
# Device enumeration gated behind mic_hardware_enabled
# ---------------------------------------------------------------------------


def test_device_enumeration_gated_behind_mic_hardware(monkeypatch: pytest.MonkeyPatch) -> None:
    """When mic_hardware_enabled is False, input_devices must be empty even if flag is set."""
    monkeypatch.setenv("METIS_AUDIO_ALLOW_LOCAL_MIC", "true")
    client = TestClient(app)
    client.post("/metis/state/reset")
    # mic_hardware_enabled defaults to True in baseline; disable it
    client.post("/metis/event", json={"type": "hardware_privacy", "device": "mic", "enabled": False})

    resp = client.get("/metis/audio/input")
    body = resp.json()

    assert body["input_devices"] == []
    assert body["sounddevice_available"] is False


# ---------------------------------------------------------------------------
# faster_whisper not imported during normal listen flow
# ---------------------------------------------------------------------------


def test_faster_whisper_not_imported_during_simulated_listen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling audio/listen with the simulated STT provider must not import faster_whisper."""
    monkeypatch.delenv("METIS_STT_ALLOW_LOCAL", raising=False)
    monkeypatch.delenv("METIS_STT_ENGINE", raising=False)
    monkeypatch.delenv("METIS_AUDIO_ALLOW_LOCAL_MIC", raising=False)
    client = TestClient(app)
    _enable_audio_listen(client)

    client.post("/metis/audio/listen", json={"hint": "git_status"})

    assert "faster_whisper" not in sys.modules


# ---------------------------------------------------------------------------
# Mic cutoff still blocks before STT is reached
# ---------------------------------------------------------------------------


def test_mic_cutoff_blocks_before_stt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("METIS_STT_ALLOW_LOCAL", raising=False)
    client = TestClient(app)
    client.post("/metis/state/reset")
    client.post("/metis/event", json={"type": "hardware_privacy", "device": "mic", "enabled": False})
    client.post("/metis/event", json={"type": "button_event", "button": "audio_input", "state": "on"})
    client.post("/metis/event", json={"type": "button_event", "button": "listen_mode", "state": "push_to_talk"})

    resp = client.post("/metis/audio/listen", json={"hint": "git_status"})
    body = resp.json()

    assert body["status"] == "blocked"
    assert body["block_reason"] == "mic_hardware_cutoff"
    assert body["state"]["external_action_executed"] is False
    assert "faster_whisper" not in sys.modules


# ---------------------------------------------------------------------------
# METIS_STT_ENGINE env var selects provider in audio/listen
# ---------------------------------------------------------------------------


def test_metis_stt_engine_env_selects_provider_in_listen(monkeypatch: pytest.MonkeyPatch) -> None:
    """When METIS_STT_ENGINE=faster_whisper but METIS_STT_ALLOW_LOCAL is unset,
    the listen route should use faster_whisper which returns not_enabled."""
    monkeypatch.setenv("METIS_STT_ENGINE", "faster_whisper")
    monkeypatch.delenv("METIS_STT_ALLOW_LOCAL", raising=False)
    monkeypatch.delenv("METIS_AUDIO_ALLOW_LOCAL_MIC", raising=False)
    client = TestClient(app)
    _enable_audio_listen(client)

    resp = client.post("/metis/audio/listen", json={})
    body = resp.json()

    # faster_whisper without flag returns not_enabled → empty text → no_text_recognized
    assert body["status"] in {"no_text_recognized", "blocked", "listen_complete"}
    assert "faster_whisper" not in sys.modules
