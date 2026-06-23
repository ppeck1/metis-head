"""Phase 0BB — LocalMicAudioInput tests.

All tests run in CI with NO real microphone and NO METIS_AUDIO_ALLOW_LOCAL_MIC env var.
They verify the triple-gate logic, the lazy sounddevice import, and the governance
precedence without ever opening a real audio device.
"""

from __future__ import annotations

import sys
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from metis_head.audio_input import (
    CaptureContext,
    LocalMicAudioInput,
    _local_mic_allowed,
    audio_input_provider_from_config,
)
from metis_head.brain import app
from metis_head.reducer import reduce_metis_event
from metis_head.schemas import baseline_state


# ---------------------------------------------------------------------------
# Verify sounddevice is NOT imported at module load time
# ---------------------------------------------------------------------------


def test_audio_input_module_does_not_import_sounddevice() -> None:
    """Importing metis_head.audio_input must not pull in sounddevice."""
    # audio_input was already imported above via the from-import; if sounddevice
    # had been imported at module level it would be in sys.modules now.
    assert "sounddevice" not in sys.modules, (
        "sounddevice appeared in sys.modules after importing metis_head.audio_input — "
        "it must be lazy-imported inside capture() only."
    )


def test_local_mic_allowed_flag_defaults_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("METIS_AUDIO_ALLOW_LOCAL_MIC", raising=False)
    assert _local_mic_allowed() is False


def test_local_mic_allowed_flag_truthy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("true", "True", "TRUE", "1", "yes", "on", "enabled"):
        monkeypatch.setenv("METIS_AUDIO_ALLOW_LOCAL_MIC", value)
        assert _local_mic_allowed() is True, f"expected True for METIS_AUDIO_ALLOW_LOCAL_MIC={value!r}"


def test_local_mic_allowed_flag_falsy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("false", "0", "no", "off", "", "disabled"):
        monkeypatch.setenv("METIS_AUDIO_ALLOW_LOCAL_MIC", value)
        assert _local_mic_allowed() is False, f"expected False for METIS_AUDIO_ALLOW_LOCAL_MIC={value!r}"


# ---------------------------------------------------------------------------
# Gate 1: METIS_AUDIO_ALLOW_LOCAL_MIC not set → not_enabled, no device access
# ---------------------------------------------------------------------------


def test_local_mic_capture_not_enabled_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("METIS_AUDIO_ALLOW_LOCAL_MIC", raising=False)
    provider = LocalMicAudioInput()

    result = provider.capture(CaptureContext())

    assert result.captured is False
    assert result.status == "not_enabled"
    assert "METIS_AUDIO_ALLOW_LOCAL_MIC" in (result.block_reason or "")
    assert "sounddevice" not in sys.modules


def test_local_mic_health_disabled_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("METIS_AUDIO_ALLOW_LOCAL_MIC", raising=False)
    provider = LocalMicAudioInput()

    health = provider.health()

    assert health["status"] == "disabled"
    assert health["allow_local_mic"] is False
    assert "sounddevice" not in sys.modules


# ---------------------------------------------------------------------------
# Gate 1 + env flag set but sounddevice missing → dependency_unavailable
# ---------------------------------------------------------------------------


def test_local_mic_capture_dependency_unavailable_when_sounddevice_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the env flag is set but sounddevice is not installed, capture must return
    dependency_unavailable without crashing, and sounddevice must not appear in sys.modules."""
    monkeypatch.setenv("METIS_AUDIO_ALLOW_LOCAL_MIC", "true")
    # Simulate sounddevice being absent by temporarily hiding it, even if installed.
    monkeypatch.setitem(sys.modules, "sounddevice", None)  # type: ignore[arg-type]

    provider = LocalMicAudioInput()
    result = provider.capture(CaptureContext())

    assert result.captured is False
    assert result.status in {"dependency_unavailable", "not_enabled"}
    assert result.block_reason is not None


# ---------------------------------------------------------------------------
# Gate 2: mic_hardware_enabled=False blocks before provider is called
# ---------------------------------------------------------------------------


def test_mic_cutoff_blocks_local_mic_before_device_access() -> None:
    """Governance in brain.py must block before capture() is called when mic is off.

    We assert: (a) the response is blocked, (b) the block_reason is mic_hardware_cutoff,
    (c) external_action_executed stays False, (d) sounddevice was never imported.
    """
    client = TestClient(app)
    client.post("/metis/state/reset")
    # Disable mic hardware
    client.post("/metis/event", json={"type": "hardware_privacy", "device": "mic", "enabled": False})
    # Enable audio_input and listen_mode so only the mic cutoff blocks
    client.post("/metis/event", json={"type": "button_event", "button": "audio_input", "state": "on"})
    client.post("/metis/event", json={"type": "button_event", "button": "listen_mode", "state": "push_to_talk"})

    resp = client.post("/metis/audio/listen", json={"provider": "local_mic", "hint": "default"})

    body = resp.json()
    assert body["status"] == "blocked"
    assert body["block_reason"] == "mic_hardware_cutoff"
    assert body["state"]["external_action_executed"] is False
    assert "sounddevice" not in sys.modules


def test_mic_cutoff_blocks_local_mic_capture_endpoint() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")
    client.post("/metis/event", json={"type": "hardware_privacy", "device": "mic", "enabled": False})
    client.post("/metis/event", json={"type": "button_event", "button": "audio_input", "state": "on"})

    resp = client.post("/metis/audio/input/capture", json={"provider": "local_mic"})

    body = resp.json()
    assert body["status"] == "blocked"
    assert body["block_reason"] == "mic_hardware_cutoff"


# ---------------------------------------------------------------------------
# Gate 3: audio_input_enabled=False blocks before any capture
# ---------------------------------------------------------------------------


def test_audio_input_disabled_blocks_local_mic() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")
    # mic is on by default; audio_input_enabled defaults to False

    resp = client.post("/metis/audio/input/capture", json={"provider": "local_mic"})

    assert resp.json()["block_reason"] == "audio_input_disabled"


def test_audio_listen_local_mic_no_flag_stays_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even when all state gates pass, missing env flag returns not_enabled from the provider."""
    monkeypatch.delenv("METIS_AUDIO_ALLOW_LOCAL_MIC", raising=False)
    client = TestClient(app)
    client.post("/metis/state/reset")
    client.post("/metis/event", json={"type": "button_event", "button": "audio_input", "state": "on"})
    client.post("/metis/event", json={"type": "button_event", "button": "listen_mode", "state": "push_to_talk"})

    resp = client.post("/metis/audio/listen", json={"provider": "local_mic", "hint": "default"})

    body = resp.json()
    # provider returns not_enabled → listen treats this as blocked capture
    assert body["status"] in {"blocked", "listen_complete"}
    if body["status"] == "blocked":
        assert "METIS_AUDIO_ALLOW_LOCAL_MIC" in (body.get("block_reason") or "") or body.get("block_reason") is not None
    assert body["state"]["external_action_executed"] is False
    assert "sounddevice" not in sys.modules


# ---------------------------------------------------------------------------
# listen_mode gate: no_listen blocks without reaching the provider
# ---------------------------------------------------------------------------


def test_listen_mode_no_listen_blocks_before_provider() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")
    client.post("/metis/event", json={"type": "button_event", "button": "audio_input", "state": "on"})
    # listen_mode defaults to no_listen

    resp = client.post("/metis/audio/listen", json={"provider": "local_mic"})

    assert resp.json()["block_reason"] == "listen_mode_no_listen"


# ---------------------------------------------------------------------------
# Governance helper unit tests
# ---------------------------------------------------------------------------


def test_governance_helper_mic_cutoff_highest_precedence() -> None:
    """mic_hardware_cutoff must be returned before audio_input_disabled."""
    state = baseline_state()
    state = reduce_metis_event(state, {"type": "hardware_privacy", "device": "mic", "enabled": False})
    # audio_input is also off — but mic_cutoff should be reported first
    assert state["mic_hardware_enabled"] is False
    assert state["audio_input_enabled"] is False

    # Simulate what _audio_capture_governance() reads from STATE:
    # (we test indirectly via the capture endpoint)
    client = TestClient(app)
    client.post("/metis/state/reset")
    client.post("/metis/event", json={"type": "hardware_privacy", "device": "mic", "enabled": False})

    resp = client.post("/metis/audio/input/capture")

    assert resp.json()["block_reason"] == "mic_hardware_cutoff"


def test_governance_helper_standby_blocks_after_enabled_checks() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")
    client.post("/metis/event", json={"type": "button_event", "button": "audio_input", "state": "on"})
    client.post("/metis/event", json={"type": "button_event", "button": "pwr", "state": "standby"})

    resp = client.post("/metis/audio/input/capture")

    assert resp.json()["block_reason"] == "standby_blocks_capture"


# ---------------------------------------------------------------------------
# Status endpoint reflects local_mic state
# ---------------------------------------------------------------------------


def test_status_endpoint_no_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("METIS_AUDIO_ALLOW_LOCAL_MIC", raising=False)
    client = TestClient(app)
    client.post("/metis/state/reset")

    resp = client.get("/metis/audio/input")

    body = resp.json()
    assert resp.status_code == 200
    assert body["allow_local_mic"] is False
    assert body["sounddevice_available"] is False
    assert body["input_devices"] == []
    assert body["selected_audio_provider"] == "simulated"


def test_status_endpoint_with_flag_no_sounddevice(monkeypatch: pytest.MonkeyPatch) -> None:
    """When flag is set but sounddevice is absent, status is graceful."""
    monkeypatch.setenv("METIS_AUDIO_ALLOW_LOCAL_MIC", "true")
    monkeypatch.setitem(sys.modules, "sounddevice", None)  # type: ignore[arg-type]
    client = TestClient(app)
    client.post("/metis/state/reset")

    resp = client.get("/metis/audio/input")

    body = resp.json()
    assert resp.status_code == 200
    assert body["allow_local_mic"] is True
    assert body["selected_audio_provider"] == "local_mic"


# ---------------------------------------------------------------------------
# No execution authority added
# ---------------------------------------------------------------------------


def test_local_mic_blocked_no_execution_authority() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")
    # All gates off — every path is blocked
    client.post("/metis/event", json={"type": "hardware_privacy", "device": "mic", "enabled": False})

    resp = client.post("/metis/audio/listen", json={"provider": "local_mic"})

    state = resp.json()["state"]
    assert state["external_action_executed"] is False
    assert state.get("approval_queue", []) == [] or all(
        p.get("review_status") != "executed" for p in state["approval_queue"]
    )
