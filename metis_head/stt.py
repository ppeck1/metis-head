"""Speech-to-text adapter (Phase 0BC / stt_engine.v0.1).

STT providers sit downstream of AudioInputProvider. They receive a CaptureResult
(which carries in-memory WAV bytes on _wav_bytes) and return a redacted STTResult.
The recognized text is held in-memory only and passed directly to the governed
voice-command route; it is never written to state, the event log, or any response.

Provider ladder:
  NoneSTT              — safe unavailable default; no transcription.
  SimulatedSTT         — deterministic hint-to-text map; no model, no network.
  LocalFasterWhisperSTT— real CTranslate2/faster-whisper engine; gated behind
                         METIS_STT_ALLOW_LOCAL=true + lazy import.
  LocalWhisperSTT      — deprecated scaffold; returns not_enabled.
  VoskSTT              — disabled scaffold; no vosk import.
  OpenAIWhisperSTT     — disabled scaffold; no openai-whisper import.
  WhisperCppSTT        — disabled scaffold; no whisper.cpp import.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
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
    """Return in-memory recognized text.

    This accessor is for the audio/listen pipeline only. The returned string
    must be forwarded to the governed voice-command route and must not be
    stored in state, the event log, or any response payload.
    """
    return getattr(result, "_recognized_text", "")


def _local_stt_allowed() -> bool:
    """True only when METIS_STT_ALLOW_LOCAL is explicitly set to a truthy value."""
    return os.environ.get("METIS_STT_ALLOW_LOCAL", "").strip().lower() in {
        "1", "true", "yes", "on", "enabled",
    }


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


class LocalFasterWhisperSTT(STTProvider):
    """Real local STT using faster-whisper (CTranslate2; no PyTorch).

    Gated behind METIS_STT_ALLOW_LOCAL=true. faster_whisper is lazy-imported
    inside transcribe() only — never at module load. If the package is absent
    or the model cannot be loaded, a governed result is returned (never a crash).

    Audio is received as WAV bytes on capture._wav_bytes, written to a tempfile,
    transcribed, and the tempfile is deleted — raw audio never persists.

    Env vars:
      METIS_STT_ALLOW_LOCAL  — must be truthy to enable (default: disabled)
      METIS_STT_MODEL        — model size (default: small)
      METIS_STT_MODEL_DIR    — local model directory; absent → download_root default
    """

    provider_id = "faster_whisper"

    def health(self) -> dict[str, Any]:
        if not _local_stt_allowed():
            return {
                "provider_id": self.provider_id,
                "status": "disabled",
                "schema_version": self.schema_version,
                "allow_local": False,
                "reason": "METIS_STT_ALLOW_LOCAL_not_set",
            }
        faster_whisper_ok = False
        try:
            import faster_whisper  # noqa: PLC0415 – intentional lazy import
            faster_whisper_ok = True
        except ImportError:
            pass
        return {
            "provider_id": self.provider_id,
            "status": "ok" if faster_whisper_ok else "dependency_unavailable",
            "schema_version": self.schema_version,
            "allow_local": True,
            "faster_whisper_available": faster_whisper_ok,
            "model": os.environ.get("METIS_STT_MODEL", "small"),
        }

    def transcribe(self, capture: Any, context: Any = None) -> STTResult:
        if not _local_stt_allowed():
            return STTResult(
                provider_id=self.provider_id,
                status="not_enabled",
                text_len=0,
                text_hash="",
                confidence=0.0,
            )

        try:
            from faster_whisper import WhisperModel  # noqa: PLC0415
        except ImportError:
            return STTResult(
                provider_id=self.provider_id,
                status="dependency_unavailable",
                text_len=0,
                text_hash="",
                confidence=0.0,
            )

        wav_bytes: bytes | None = getattr(capture, "_wav_bytes", None) if capture is not None else None
        if not wav_bytes:
            return STTResult(
                provider_id=self.provider_id,
                status="no_audio",
                text_len=0,
                text_hash="",
                confidence=0.0,
            )

        model_size = os.environ.get("METIS_STT_MODEL", "small")
        model_dir = os.environ.get("METIS_STT_MODEL_DIR")

        try:
            kwargs: dict[str, Any] = {}
            if model_dir:
                kwargs["download_root"] = model_dir
            model = WhisperModel(model_size, device="cpu", compute_type="int8", **kwargs)
        except Exception:
            return STTResult(
                provider_id=self.provider_id,
                status="model_unavailable",
                text_len=0,
                text_hash="",
                confidence=0.0,
            )

        wav_path_str: str | None = None
        recognized = ""
        confidence = 0.0
        try:
            with tempfile.NamedTemporaryFile(prefix="metis_stt_audio_", suffix=".wav", delete=False) as tmp:
                tmp.write(wav_bytes)
                wav_path_str = tmp.name
            segments, info = model.transcribe(wav_path_str, beam_size=5)
            recognized = " ".join(seg.text.strip() for seg in segments).strip()
            confidence = float(getattr(info, "language_probability", 0.0))
        except Exception:
            recognized = ""
            confidence = 0.0
        finally:
            if wav_path_str is not None:
                try:
                    os.unlink(wav_path_str)
                except OSError:
                    pass

        text_hash = hashlib.sha1(recognized.encode("utf-8")).hexdigest()[:16] if recognized else ""
        result = STTResult(
            provider_id=self.provider_id,
            status="complete" if recognized else "no_text",
            text_len=len(recognized),
            text_hash=text_hash,
            text_redacted=True,
            confidence=confidence,
        )
        result._recognized_text = recognized  # in-memory only; never serialised
        return result


class LocalWhisperSTT(STTProvider):
    """Deprecated scaffold; superseded by LocalFasterWhisperSTT."""

    provider_id = "local_whisper"

    def health(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "status": "disabled",
            "schema_version": self.schema_version,
            "reason": "superseded_by_faster_whisper",
        }

    def transcribe(self, capture: Any, context: Any = None) -> STTResult:
        return STTResult(
            provider_id=self.provider_id,
            status="not_enabled",
            text_len=0,
            text_hash="",
            confidence=0.0,
        )


class VoskSTT(STTProvider):
    """Disabled scaffold; no vosk import."""

    provider_id = "vosk"

    def transcribe(self, capture: Any, context: Any = None) -> STTResult:
        return STTResult(
            provider_id=self.provider_id,
            status="not_enabled",
            text_len=0,
            text_hash="",
            confidence=0.0,
        )


class OpenAIWhisperSTT(STTProvider):
    """Disabled scaffold; no openai-whisper import."""

    provider_id = "openai_whisper"

    def transcribe(self, capture: Any, context: Any = None) -> STTResult:
        return STTResult(
            provider_id=self.provider_id,
            status="not_enabled",
            text_len=0,
            text_hash="",
            confidence=0.0,
        )


class WhisperCppSTT(STTProvider):
    """Disabled scaffold; no whisper.cpp import."""

    provider_id = "whispercpp"

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
    if provider_name == "faster_whisper":
        return LocalFasterWhisperSTT()
    if provider_name == "local_whisper":
        return LocalWhisperSTT()
    if provider_name == "vosk":
        return VoskSTT()
    if provider_name == "openai_whisper":
        return OpenAIWhisperSTT()
    if provider_name == "whispercpp":
        return WhisperCppSTT()
    return NoneSTT()
