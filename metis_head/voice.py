from __future__ import annotations

import os
import hashlib
import re
import shutil
import subprocess
import sysconfig
import tempfile
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any


VOICE_SCHEMA_VERSION = "metis_voice.v0.1"
VOICE_OPTIONS_VERSION = "metis_voice_options.v0.1"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PIPER_VOICE_DIR = REPO_ROOT / "models" / "piper" / "en_US" / "hfc_female" / "medium"
DEFAULT_PIPER_MODEL = DEFAULT_PIPER_VOICE_DIR / "en_US-hfc_female-medium.onnx"
DEFAULT_PIPER_CONFIG = DEFAULT_PIPER_VOICE_DIR / "en_US-hfc_female-medium.onnx.json"

VOICE_OPTION_CATALOG: list[dict[str, Any]] = [
    {
        "option_id": "metis-counsel-mock",
        "provider": "mock",
        "status": "available",
        "privacy_class": "local_no_audio",
        "description": "Deterministic no-audio voice event provider used for tests and safe boot.",
        "requires_network": False,
        "requires_install": False,
        "current_default": True,
        "notes": "This is the voice Metis has now: a governed TTS harness, not audible speech.",
    },
    {
        "option_id": "windows-system-tts",
        "provider": "system",
        "status": "gated",
        "privacy_class": "local_os_audio",
        "description": "Windows/system TTS provider shape for local audible speech.",
        "requires_network": False,
        "requires_install": False,
        "current_default": False,
        "notes": "Explicitly disabled until METIS_VOICE_ALLOW_SYSTEM_TTS=true and a real synthesis implementation is approved.",
    },
    {
        "option_id": "piper-local",
        "provider": "piper",
        "status": "candidate",
        "privacy_class": "local_model_audio",
        "description": "Future local neural TTS candidate for offline voice output.",
        "requires_network": False,
        "requires_install": True,
        "current_default": False,
        "notes": "Needs provider bakeoff and installation path before runtime support.",
    },
    {
        "option_id": "openai-tts",
        "provider": "openai",
        "status": "candidate",
        "privacy_class": "cloud_audio_external",
        "description": "Future cloud TTS candidate with external transmission.",
        "requires_network": True,
        "requires_install": False,
        "current_default": False,
        "notes": "Would require explicit cloud/privacy labeling and operator approval before use.",
    },
]


class VoiceProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class VoiceConfig:
    enabled: bool
    provider: str
    voice_id: str
    rate: float
    volume: float
    allow_system_tts: bool = False
    allow_piper: bool = False
    piper_exe: str | None = None
    piper_model: str | None = None
    piper_config: str | None = None
    piper_playback: bool = True
    piper_playback_strategy: str = "soundplayer"
    piper_playback_mode: str = "async"
    normalize_text: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "voice_schema": VOICE_SCHEMA_VERSION,
            "enabled": self.enabled,
            "provider": self.provider,
            "voice_id": self.voice_id,
            "rate": self.rate,
            "volume": self.volume,
            "allow_system_tts": self.allow_system_tts,
            "allow_piper": self.allow_piper,
            "piper_configured": bool(self.piper_exe and self.piper_model),
            "piper_playback_strategy": self.piper_playback_strategy,
            "piper_playback_mode": self.piper_playback_mode,
            "normalize_text": self.normalize_text,
            "providers": ["mock", "system", "piper"],
        }


@dataclass
class VoiceResult:
    ok: bool
    spoken: bool
    provider: str
    voice_id: str
    blocked_reason: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "voice_schema": VOICE_SCHEMA_VERSION,
            "ok": self.ok,
            "spoken": self.spoken,
            "provider": self.provider,
            "voice_id": self.voice_id,
            "blocked_reason": self.blocked_reason,
            "events": self.events,
            "event_count": len(self.events),
            "metadata": self.metadata,
        }


class BaseVoiceProvider:
    provider_id = "base"

    def speak(self, text: str, config: VoiceConfig) -> list[dict[str, Any]]:
        raise NotImplementedError


class MockVoiceProvider(BaseVoiceProvider):
    provider_id = "mock"

    def speak(self, text: str, config: VoiceConfig) -> list[dict[str, Any]]:
        metadata = _text_metadata(text)
        base = {
            **metadata,
            "provider": "tts",
            "voice_provider": self.provider_id,
            "voice_id": config.voice_id,
            "voice_schema": VOICE_SCHEMA_VERSION,
            "volume": config.volume,
            "rate": config.rate,
        }
        return [
            {
                "type": "provider_event",
                **base,
                "status": "queued",
            },
            {
                "type": "provider_event",
                **base,
                "status": "synthesizing",
            },
            {
                "type": "provider_event",
                **base,
                "status": "speaking",
            },
            {
                "type": "provider_event",
                **base,
                "status": "complete",
            },
        ]


class FailedVoiceProvider(BaseVoiceProvider):
    provider_id = "failed"

    def speak(self, text: str, config: VoiceConfig) -> list[dict[str, Any]]:
        return [
            {
                "type": "provider_event",
                "provider": "tts",
                "status": "failure",
                "failure_id": "tts_failure",
                "reason": "voice provider failure",
                **_text_metadata(text),
                "voice_provider": self.provider_id,
                "voice_id": config.voice_id,
                "voice_schema": VOICE_SCHEMA_VERSION,
            }
        ]


class SystemVoiceProvider(MockVoiceProvider):
    provider_id = "system"

    def speak(self, text: str, config: VoiceConfig) -> list[dict[str, Any]]:
        if not config.allow_system_tts:
            raise VoiceProviderError("system TTS is present but disabled; set METIS_VOICE_ALLOW_SYSTEM_TTS=true to allow real OS speech")
        # Phase 0V keeps real OS speech behind this explicit gate. The emitted
        # events are the contract; a later provider can add actual synthesis.
        events = super().speak(text, config)
        for event in events:
            event["voice_provider"] = self.provider_id
            event["system_tts_allowed"] = True
        return events


class PiperVoiceProvider(BaseVoiceProvider):
    provider_id = "piper"

    def speak(self, text: str, config: VoiceConfig) -> list[dict[str, Any]]:
        spoken_text = normalize_spoken_text(text) if config.normalize_text else text
        if not config.allow_piper:
            raise VoiceProviderError("Piper TTS is disabled; set METIS_VOICE_ALLOW_PIPER=true to allow local speech")
        if not config.piper_exe:
            raise VoiceProviderError("Piper TTS executable is not configured; set METIS_PIPER_EXE")
        if not config.piper_model:
            raise VoiceProviderError("Piper TTS model is not configured; set METIS_PIPER_MODEL")
        piper_exe = Path(config.piper_exe)
        piper_model = Path(config.piper_model)
        if not piper_exe.exists():
            raise VoiceProviderError(f"Piper TTS executable not found: {piper_exe}")
        if not piper_model.exists():
            raise VoiceProviderError(f"Piper TTS model not found: {piper_model}")

        metadata = _text_metadata(spoken_text)
        base = {
            **metadata,
            "type": "provider_event",
            "provider": "tts",
            "voice_provider": self.provider_id,
            "voice_id": config.voice_id,
            "voice_schema": VOICE_SCHEMA_VERSION,
            "volume": config.volume,
            "rate": config.rate,
            "playback": bool(config.piper_playback),
            "playback_strategy": config.piper_playback_strategy,
            "playback_mode": config.piper_playback_mode,
            "normalized_text": config.normalize_text,
            "source_text_len": len(text),
            "source_text_hash": _text_hash(text),
            "audio_visualization_hint_ms": _audio_visualization_hint_ms(spoken_text),
        }
        events = [
            {**base, "status": "queued"},
            {**base, "status": "synthesizing"},
        ]
        with tempfile.NamedTemporaryFile(prefix="metis_piper_", suffix=".wav", delete=False) as wav_file:
            wav_path = Path(wav_file.name)
        cleanup_wav = True
        try:
            command = [str(piper_exe), "--model", str(piper_model), "--output-file", str(wav_path), "--volume", str(config.volume)]
            if config.piper_config:
                command.extend(["--config", str(config.piper_config)])
            subprocess.run(
                command,
                input=spoken_text,
                text=True,
                capture_output=True,
                timeout=_piper_timeout_seconds(spoken_text),
                check=True,
            )
            events.append({**base, "status": "speaking", "audio_file": "local_temp_wav"})
            if config.piper_playback:
                if config.piper_playback_mode == "async":
                    cleanup_wav = False
                    _play_wav_file_async(wav_path, config.piper_playback_strategy)
                else:
                    _play_wav_file(wav_path, config.piper_playback_strategy)
            events.append({**base, "status": "complete", "audio_file": "local_temp_wav"})
        except subprocess.TimeoutExpired as exc:
            raise VoiceProviderError("Piper TTS timed out") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            detail = f"Piper TTS failed: {stderr}" if stderr else "Piper TTS failed"
            raise VoiceProviderError(detail) from exc
        finally:
            if cleanup_wav:
                try:
                    wav_path.unlink(missing_ok=True)
                except OSError:
                    pass
        return events


def voice_config_from_env(env: dict[str, str] | None = None, options: dict[str, Any] | None = None, state: dict[str, Any] | None = None) -> VoiceConfig:
    env = env or os.environ
    options = options or {}
    voice_options = options.get("voice") if isinstance(options.get("voice"), dict) else options
    enabled = _as_bool(voice_options.get("enabled", env.get("METIS_VOICE_ENABLED", "false")))
    provider = str(voice_options.get("provider") or env.get("METIS_VOICE_PROVIDER", "mock")).lower()
    voice_id = str(voice_options.get("voice_id") or env.get("METIS_VOICE_ID", "metis-counsel-mock"))
    rate = _clamp_float(voice_options.get("rate", env.get("METIS_VOICE_RATE", "1.0")), 0.5, 2.0, 1.0)
    state_volume = state.get("volume_level") if isinstance(state, dict) else None
    volume_default = state_volume if state_volume is not None else env.get("METIS_VOICE_VOLUME", "0.6")
    volume = _clamp_float(voice_options.get("volume", volume_default), 0.0, 1.0, 0.6)
    allow_system_tts = _as_bool(voice_options.get("allow_system_tts", env.get("METIS_VOICE_ALLOW_SYSTEM_TTS", "false")))
    allow_piper = _as_bool(voice_options.get("allow_piper", env.get("METIS_VOICE_ALLOW_PIPER", "false")))
    piper_exe = _optional_str(voice_options.get("piper_exe", env.get("METIS_PIPER_EXE"))) or _default_piper_exe()
    piper_model = _optional_str(voice_options.get("piper_model", env.get("METIS_PIPER_MODEL"))) or _default_piper_model()
    piper_config = _optional_str(voice_options.get("piper_config", env.get("METIS_PIPER_CONFIG"))) or _default_piper_config()
    piper_playback = _as_bool(voice_options.get("piper_playback", env.get("METIS_PIPER_PLAYBACK", "true")))
    piper_playback_strategy = _playback_strategy(voice_options.get("piper_playback_strategy", env.get("METIS_PIPER_PLAYBACK_STRATEGY", "soundplayer")))
    piper_playback_mode = _playback_mode(voice_options.get("piper_playback_mode", env.get("METIS_PIPER_PLAYBACK_MODE", "async")))
    normalize_text = _as_bool(voice_options.get("normalize_text", env.get("METIS_VOICE_NORMALIZE_TEXT", "true")))
    if provider not in {"mock", "system", "piper", "failed"}:
        provider = "mock"
    return VoiceConfig(
        enabled=enabled,
        provider=provider,
        voice_id=voice_id,
        rate=rate,
        volume=volume,
        allow_system_tts=allow_system_tts,
        allow_piper=allow_piper,
        piper_exe=piper_exe,
        piper_model=piper_model,
        piper_config=piper_config,
        piper_playback=piper_playback,
        piper_playback_strategy=piper_playback_strategy,
        piper_playback_mode=piper_playback_mode,
        normalize_text=normalize_text,
    )


def voice_provider_from_config(config: VoiceConfig) -> BaseVoiceProvider:
    if config.provider == "mock":
        return MockVoiceProvider()
    if config.provider == "system":
        return SystemVoiceProvider()
    if config.provider == "piper":
        return PiperVoiceProvider()
    if config.provider == "failed":
        return FailedVoiceProvider()
    raise VoiceProviderError(f"unsupported voice provider: {config.provider}")


def speak_text(text: str, state: dict[str, Any], options: dict[str, Any] | None = None) -> VoiceResult:
    config = voice_config_from_env(options=options, state=state)
    if not config.enabled:
        return VoiceResult(ok=True, spoken=False, provider=config.provider, voice_id=config.voice_id, blocked_reason="voice output disabled")
    if state.get("output_muted"):
        return VoiceResult(
            ok=True,
            spoken=False,
            provider=config.provider,
            voice_id=config.voice_id,
            blocked_reason="output muted",
            events=[
                {
                    "type": "provider_event",
                    "provider": "tts",
                    "status": "muted",
                    "reason": "output muted",
                    **_text_metadata(text),
                    "voice_provider": config.provider,
                    "voice_id": config.voice_id,
                    "voice_schema": VOICE_SCHEMA_VERSION,
                }
            ],
        )
    if state.get("power_state") != "awake":
        return VoiceResult(
            ok=True,
            spoken=False,
            provider=config.provider,
            voice_id=config.voice_id,
            blocked_reason="standby blocks voice output",
            events=[
                {
                    "type": "provider_event",
                    "provider": "tts",
                    "status": "muted",
                    "reason": "standby blocks voice output",
                    **_text_metadata(text),
                    "voice_provider": config.provider,
                    "voice_id": config.voice_id,
                    "voice_schema": VOICE_SCHEMA_VERSION,
                }
            ],
        )
    if not text.strip():
        return VoiceResult(ok=False, spoken=False, provider=config.provider, voice_id=config.voice_id, blocked_reason="text is required")
    try:
        events = voice_provider_from_config(config).speak(text, config)
    except VoiceProviderError as exc:
        return VoiceResult(
            ok=False,
            spoken=False,
            provider=config.provider,
            voice_id=config.voice_id,
            blocked_reason=str(exc),
            events=[
                {
                    "type": "provider_event",
                    "provider": "tts",
                    "status": "failure",
                    "failure_id": "tts_failure",
                    "reason": str(exc),
                    "voice_provider": config.provider,
                    "voice_id": config.voice_id,
                    "voice_schema": VOICE_SCHEMA_VERSION,
                }
            ],
        )
    spoken = any(event.get("provider") == "tts" and event.get("status") == "speaking" for event in events)
    failed = any(event.get("provider") == "tts" and event.get("status") == "failure" for event in events)
    return VoiceResult(
        ok=not failed,
        spoken=spoken,
        provider=config.provider,
        voice_id=config.voice_id,
        blocked_reason="voice provider failure" if failed else None,
        events=events,
        metadata={"rate": config.rate, "volume": config.volume},
    )


def stop_voice(state: dict[str, Any], options: dict[str, Any] | None = None) -> VoiceResult:
    config = voice_config_from_env(options=options, state=state)
    return VoiceResult(
        ok=True,
        spoken=False,
        provider=config.provider,
        voice_id=config.voice_id,
        blocked_reason="cancelled",
        events=[
            {
                "type": "provider_event",
                "provider": "tts",
                "status": "cancelled",
                "voice_provider": config.provider,
                "voice_id": config.voice_id,
                "voice_schema": VOICE_SCHEMA_VERSION,
            }
        ],
    )


def voice_profile(state: dict[str, Any], options: dict[str, Any] | None = None) -> dict[str, Any]:
    config = voice_config_from_env(options=options, state=state)
    return {
        **config.to_public_dict(),
        "output_muted": bool(state.get("output_muted")),
        "volume_level": state.get("volume_level"),
        "audio_state": state.get("audio_state"),
        "can_speak_now": bool(config.enabled and not state.get("output_muted")),
        "boundary": "TTS output only; does not imply microphone capture, listening, or privacy state changes.",
    }


def voice_options(state: dict[str, Any]) -> dict[str, Any]:
    profile = voice_profile(state)
    config = voice_config_from_env(state=state)
    options = _voice_option_catalog_for_config(config)
    return {
        "voice_options_version": VOICE_OPTIONS_VERSION,
        "selected_provider": profile["provider"],
        "selected_voice_id": profile["voice_id"],
        "current_voice_is_audible": profile["provider"] in {"piper", "system"} and profile["can_speak_now"],
        "boundary": profile["boundary"],
        "piper": {
            "exe": config.piper_exe,
            "model": config.piper_model,
            "config": config.piper_config,
            "playback": config.piper_playback,
            "playback_strategy": config.piper_playback_strategy,
            "playback_mode": config.piper_playback_mode,
            "configured": bool(config.piper_exe and config.piper_model),
        },
        "options": options,
    }


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return bool(value)


def _clamp_float(value: Any, low: float, high: float, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


def _text_metadata(text: str) -> dict[str, Any]:
    return {"text_len": len(text), "text_hash": _text_hash(text), "text_redacted": True}


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def normalize_spoken_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"```.*?```", " ", normalized, flags=re.DOTALL)
    normalized = re.sub(r"`([^`]+)`", r"\1", normalized)
    normalized = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", normalized)
    normalized = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", normalized)
    lines: list[str] = []
    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        if not line:
            lines.append("")
            continue
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"^>\s*", "", line)
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        line = re.sub(r"^\|?(.*?)\|?$", r"\1", line) if "|" in line else line
        line = line.replace("|", ", ")
        lines.append(line)
    normalized = "\n".join(lines)
    replacements = {
        "**": "",
        "__": "",
        "*": "",
        "_": " ",
        "~~": "",
        "#": "",
        ">": "",
        "•": "",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    normalized = re.sub(r"\s+[-–—]\s+", ". ", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"\s+([.,;:!?])", r"\1", normalized)
    normalized = re.sub(r"([.!?]){2,}", r"\1", normalized)
    normalized = normalized.strip()
    return normalized or "No spoken content."


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _voice_option_catalog_for_config(config: VoiceConfig) -> list[dict[str, Any]]:
    catalog = []
    piper_ready = bool(config.piper_exe and config.piper_model)
    for item in VOICE_OPTION_CATALOG:
        option = dict(item)
        if option["option_id"] == "piper-local" and piper_ready:
            option["status"] = "available"
            option["current_default"] = config.provider == "piper"
            option["notes"] = "Configured through METIS_PIPER_EXE and METIS_PIPER_MODEL; selecting it in the UI opts in to local playback."
        elif option["option_id"] == "metis-counsel-mock":
            option["current_default"] = config.provider == "mock"
        elif option["option_id"] == "windows-system-tts":
            option["current_default"] = config.provider == "system"
        catalog.append(option)
    return catalog


def _default_piper_exe() -> str | None:
    discovered = shutil.which("piper") or shutil.which("piper.exe")
    if discovered:
        return discovered
    scripts = sysconfig.get_path("scripts")
    if scripts:
        candidate = Path(scripts) / "piper.exe"
        if candidate.exists():
            return str(candidate)
    return None


def _default_piper_model() -> str | None:
    return str(DEFAULT_PIPER_MODEL) if DEFAULT_PIPER_MODEL.exists() else None


def _default_piper_config() -> str | None:
    return str(DEFAULT_PIPER_CONFIG) if DEFAULT_PIPER_CONFIG.exists() else None


def _playback_strategy(value: Any) -> str:
    strategy = str(value or "soundplayer").strip().lower()
    if strategy not in {"soundplayer", "winsound"}:
        return "soundplayer"
    return strategy


def _playback_mode(value: Any) -> str:
    mode = str(value or "async").strip().lower()
    if mode not in {"async", "sync"}:
        return "async"
    return mode


def _piper_timeout_seconds(text: str) -> int:
    return max(90, min(240, 60 + (len(text) // 10)))


def _audio_visualization_hint_ms(text: str) -> int:
    return max(2200, min(30000, 900 + (len(text) * 70)))


def _play_wav_file_async(wav_path: Path, strategy: str = "soundplayer") -> None:
    thread = threading.Thread(target=_play_wav_file_and_cleanup, args=(wav_path, strategy), daemon=True)
    thread.start()


def _play_wav_file_and_cleanup(wav_path: Path, strategy: str) -> None:
    try:
        _play_wav_file(wav_path, strategy)
    finally:
        try:
            wav_path.unlink(missing_ok=True)
        except OSError:
            pass


def _play_wav_file(wav_path: Path, strategy: str = "soundplayer") -> None:
    if strategy == "winsound":
        _play_wav_with_winsound(wav_path)
        return
    _play_wav_with_soundplayer(wav_path)


def _play_wav_with_soundplayer(wav_path: Path) -> None:
    env = dict(os.environ)
    env["METIS_PIPER_WAV"] = str(wav_path)
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "(New-Object Media.SoundPlayer $env:METIS_PIPER_WAV).PlaySync()",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=True,
    )


def _play_wav_with_winsound(wav_path: Path) -> None:
    try:
        import winsound
    except ImportError as exc:
        raise VoiceProviderError("local WAV playback is only implemented on Windows in this phase") from exc
    winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
