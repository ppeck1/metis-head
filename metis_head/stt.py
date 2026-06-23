"""Speech-to-text adapter (Phase 0BA / stt_engine.v0.1).

STT providers sit downstream of AudioInputProvider. They receive a CaptureResult
and return a redacted STTResult. The recognized text is held in-memory only and
passed directly to the governed voice-command route; it is never written to
state, the event log, or any response payload.

Provider ladder:
  NoneSTT          — safe unavailable default; no transcription.
  SimulatedSTT     — deterministic hint-to-text map; no model, no network.
  LocalWhisperSTT  — disabled scaffold for Phase 0BC; no whisper import.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


STT_SCHEMA_VERSION = "stt_engine.v0.1"

SIMULATED_TRANSCRIPT_MAP: dict[str, str] = {
    "git_status": "git status",
    "time_now": "what time is it",
    "help": "help",
    "status": "git status",
    "default": "git status",
}


@dataclass
class STTResult:
    """Public (redacted) STT result.

    _recognized_text is set post-construction and is excluded from to_dict().
    It must never be serialised to state or event log.
    """

    provider_id: str
    status: str
    text_len: int
    text_hash: str
    text_redacted: bool = True
    confidence: float = 0.0
    schema_version: str = STT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider_id": self.provider_id,
            "status": self.status,
            "text_len": self.text_len,
            "text_hash": self.text_hash,
            "text_redacted": self.text_redacted,
            "confidence": self.confidence,
        }


def get_recognized_text(result: STTResult) -> str:
    """Return in-memory recognized text from a SimulatedSTT result.

    This accessor is for the audio/listen pipeline only. The returned string
    must be forwarded to the governed voice-command route and must not be
    stored in state, the event log, or any response payload.
    """
    return getattr(result, "_recognized_text", "")


class STTProvider:
    provider_id = "base"
    schema_version = STT_SCHEMA_VERSION

    def health(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "status": "disabled", "schema_version": self.schema_version}

    def transcribe(self, capture: Any, context: Any = None) -> STTResult:
        raise NotImplementedError


class NoneSTT(STTProvider):
    provider_id = "none"

    def health(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "status": "disabled", "schema_version": self.schema_version}

    def transcribe(self, capture: Any, context: Any = None) -> STTResult:
        return STTResult(
            provider_id=self.provider_id,
            status="unavailable",
            text_len=0,
            text_hash="",
            confidence=0.0,
        )


class SimulatedSTT(STTProvider):
    """Deterministic STT: maps a hint key to a canonical recognized phrase.

    The recognized text is attached as _recognized_text (not serialised).
    """

    provider_id = "simulated"

    def health(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "status": "ok", "schema_version": self.schema_version}

    def transcribe(self, capture: Any, context: Any = None) -> STTResult:
        hint = ""
        if isinstance(context, dict):
            hint = str(context.get("hint") or "")
        if not hint:
            hint = "default"

        recognized = SIMULATED_TRANSCRIPT_MAP.get(hint, SIMULATED_TRANSCRIPT_MAP["default"])
        text_hash = hashlib.sha1(recognized.encode("utf-8")).hexdigest()[:16]

        result = STTResult(
            provider_id=self.provider_id,
            status="complete",
            text_len=len(recognized),
            text_hash=text_hash,
            text_redacted=True,
            confidence=0.95,
        )
        result._recognized_text = recognized  # in-memory only; never serialised
        return result


class LocalWhisperSTT(STTProvider):
    """Disabled scaffold for a real local Whisper/Vosk engine (Phase 0BC).

    No whisper or vosk import occurs; returns a governed not-enabled result.
    """

    provider_id = "local_whisper"

    def health(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "status": "disabled",
            "schema_version": self.schema_version,
            "reason": "not_enabled_this_phase",
        }

    def transcribe(self, capture: Any, context: Any = None) -> STTResult:
        return STTResult(
            provider_id=self.provider_id,
            status="not_enabled",
            text_len=0,
            text_hash="",
            confidence=0.0,
        )


def stt_provider_from_config(provider_name: str) -> STTProvider:
    if provider_name == "simulated":
        return SimulatedSTT()
    if provider_name == "local_whisper":
        return LocalWhisperSTT()
    return NoneSTT()
