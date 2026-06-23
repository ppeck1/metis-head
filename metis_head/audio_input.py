"""Audio input adapter (Phase 0BA / audio_input_adapter.v0.1).

Simulation-first audio-capture layer for the radio form factor. Capture is
fail-closed behind mic_hardware_enabled; no real microphone, no raw PCM, and
no raw audio path ever enter state, the event log, or response payloads.

Provider ladder:
  NoneAudioInput    — safe disabled default, always returns captured=False.
  SimulatedAudioInput — generates a deterministic synthetic WAV in a tempfile,
                        runs it through the shared Piper WAV-analysis helpers,
                        and returns compact audio_levels/audio_spectrum_frames.
  LocalMicAudioInput  — disabled scaffold for Phase 0BB; raises a governed
                        not-enabled result without importing sounddevice.
"""

from __future__ import annotations

import math
import tempfile
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any


AUDIO_INPUT_SCHEMA_VERSION = "audio_input_adapter.v0.1"

_FIXTURE_FREQUENCY: dict[str, float] = {
    "sine_440": 440.0,
    "sine_880": 880.0,
    "sine_220": 220.0,
    "default": 440.0,
}


@dataclass
class CaptureContext:
    hint: str = "default"
    fixture_id: str = "default"
    sample_rate: int = 16000
    duration_ms: int = 1000


@dataclass
class CaptureResult:
    provider_id: str
    status: str
    captured: bool
    audio_duration_ms: int
    audio_levels: list[float]
    audio_spectrum_frames: list[list[float]]
    frame_count: int
    sample_rate: int
    block_reason: str | None = None
    schema_version: str = AUDIO_INPUT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider_id": self.provider_id,
            "status": self.status,
            "captured": self.captured,
            "audio_duration_ms": self.audio_duration_ms,
            "audio_levels": self.audio_levels,
            "frame_count": self.frame_count,
            "sample_rate": self.sample_rate,
            "block_reason": self.block_reason,
        }


class AudioInputProvider:
    provider_id = "base"
    schema_version = AUDIO_INPUT_SCHEMA_VERSION

    def health(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "status": "disabled", "schema_version": self.schema_version}

    def capture(self, context: CaptureContext) -> CaptureResult:
        raise NotImplementedError


class NoneAudioInput(AudioInputProvider):
    provider_id = "none"

    def health(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "status": "disabled", "schema_version": self.schema_version}

    def capture(self, context: CaptureContext) -> CaptureResult:
        return CaptureResult(
            provider_id=self.provider_id,
            status="disabled",
            captured=False,
            audio_duration_ms=0,
            audio_levels=[],
            audio_spectrum_frames=[],
            frame_count=0,
            sample_rate=context.sample_rate,
            block_reason="audio_input_provider_none",
        )


class SimulatedAudioInput(AudioInputProvider):
    """Deterministic simulated capture using the shared Piper WAV-analysis helpers.

    Generates a synthetic sine-wave WAV in a tempfile, analyses it, and returns
    compact audio metadata. No real microphone, no sounddevice import.
    """

    provider_id = "simulated"

    def health(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "status": "ok", "schema_version": self.schema_version}

    def capture(self, context: CaptureContext) -> CaptureResult:
        wav_path = _generate_synthetic_wav(context.fixture_id, context.sample_rate, context.duration_ms)
        try:
            from .voice import _wav_duration_ms, _wav_level_envelope, _wav_spectrum_frames

            audio_levels = _wav_level_envelope(wav_path)
            spectrum_frames = _wav_spectrum_frames(wav_path)
            audio_duration = _wav_duration_ms(wav_path) or context.duration_ms
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except OSError:
                pass
        return CaptureResult(
            provider_id=self.provider_id,
            status="ok",
            captured=True,
            audio_duration_ms=audio_duration,
            audio_levels=audio_levels,
            audio_spectrum_frames=spectrum_frames,
            frame_count=len(spectrum_frames),
            sample_rate=context.sample_rate,
        )


class LocalMicAudioInput(AudioInputProvider):
    """Disabled scaffold for a real device capture (Phase 0BB).

    No sounddevice or PyAudio import occurs in this phase; returns a governed
    not-enabled result unconditionally.
    """

    provider_id = "local_mic"

    def health(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "status": "disabled",
            "schema_version": self.schema_version,
            "reason": "not_enabled_this_phase",
        }

    def capture(self, context: CaptureContext) -> CaptureResult:
        return CaptureResult(
            provider_id=self.provider_id,
            status="not_enabled",
            captured=False,
            audio_duration_ms=0,
            audio_levels=[],
            audio_spectrum_frames=[],
            frame_count=0,
            sample_rate=context.sample_rate,
            block_reason="local_mic_not_enabled_phase_0ba",
        )


def audio_input_provider_from_config(provider_name: str) -> AudioInputProvider:
    if provider_name == "simulated":
        return SimulatedAudioInput()
    if provider_name == "local_mic":
        return LocalMicAudioInput()
    return NoneAudioInput()


def _generate_synthetic_wav(fixture_id: str, sample_rate: int, duration_ms: int) -> Path:
    """Generate a deterministic sine-wave WAV for simulation; no external deps."""
    frequency = _FIXTURE_FREQUENCY.get(fixture_id, 440.0)
    num_samples = int(sample_rate * duration_ms / 1000)
    amplitude = 16384

    pcm = array("h")
    for i in range(num_samples):
        pcm.append(int(amplitude * math.sin(2 * math.pi * frequency * i / sample_rate)))

    with tempfile.NamedTemporaryFile(prefix="metis_sim_audio_", suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)

    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())

    return wav_path
