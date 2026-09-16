"""Versioned, non-secret persistence for the Metis setup wizard.

This module deliberately stores preferences and connection *metadata* only. OAuth
credentials, API keys, transcripts, and message content belong elsewhere.
"""

from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from threading import RLock
from typing import Any, Mapping
from urllib.parse import urlparse

from .runtime_paths import state_root


SCHEMA_VERSION = 1
WIZARD_VERSION = "1"
PROFILE_SLOT_IDS = tuple(f"profile_{number}" for number in range(1, 5))

_PROVIDER_CHOICES = {"ollama", "openai_api", "codex_app_server"}
_STATUS_VALUES = {"not_configured", "not_connected", "unverified", "verified", "error", "unavailable"}
_VOICE_OUTPUTS = {"browser", "system"}
_VOICE_ENGINES = {"piper", "browser"}
_SELECTION_MODES = {"default", "explicit"}
_SENSITIVE_KEY = re.compile(r"(?:api[_-]?key|authorization|credential|oauth|password|secret|token|transcript)", re.I)
_SENSITIVE_VALUE = re.compile(r"(?:\bBearer\s+[A-Za-z0-9._~+/-]+=*|\bsk-[A-Za-z0-9_-]{12,}|BEGIN [A-Z ]*PRIVATE KEY)", re.I)


class SetupStateError(ValueError):
    """Raised when setup state is invalid, corrupt, or concurrently changed."""


def default_setup_path(env: Mapping[str, str] | None = None) -> Path:
    values = os.environ if env is None else env
    explicit = str(values.get("METIS_SETUP_FILE") or "").strip()
    return Path(explicit).expanduser().resolve() if explicit else state_root(values) / "setup.json"


def _default_state() -> dict[str, Any]:
    labels = ("Personal / Main", "Nursing", "Photography", "Sinternet Cult")
    profiles = [
        {
            "slot_id": slot_id,
            "label": labels[index - 1],
            "account_id": None,
            "calendar_ids": [],
            "scopes": [],
            "status": "not_connected",
            "last_verification": None,
        }
        for index, slot_id in enumerate(PROFILE_SLOT_IDS, start=1)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": 0,
        "wizard": {"completed": False, "completed_version": None},
        "provider": {
            "choice": "ollama",
            "model": None,
            "base_url": "http://127.0.0.1:11434",
            "status": "unverified",
            "last_verification": None,
        },
        "voice": {
            "enabled": True,
            "output": "browser",
            "engine": "piper",
            "voice_id": "piper-local",
            "volume": 0.8,
            "rate": 1.0,
            "last_verification": None,
        },
        "google_profiles": profiles,
        "profile_selection": {
            "mode": "default",
            "default_slot_id": "profile_1",
            "active_slot_ids": ["profile_1"],
        },
    }


def _plain_json(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError) as exc:
        raise SetupStateError("setup state must contain JSON-compatible values") from exc


def _assert_keys(value: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise SetupStateError(f"unsupported {context} field(s): {', '.join(sorted(unknown))}")


def _assert_no_sensitive_material(value: Any, path: str = "setup") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _SENSITIVE_KEY.search(str(key)):
                raise SetupStateError(f"sensitive field is not permitted in setup state: {path}.{key}")
            _assert_no_sensitive_material(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_sensitive_material(child, f"{path}[{index}]")
    elif isinstance(value, str) and _SENSITIVE_VALUE.search(value):
        raise SetupStateError(f"secret-like value is not permitted in setup state: {path}")


def _text(value: Any, field: str, *, optional: bool = False, maximum: int = 200) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise SetupStateError(f"{field} must be a string")
    result = value.strip()
    if not result and not optional:
        raise SetupStateError(f"{field} cannot be empty")
    if len(result) > maximum:
        raise SetupStateError(f"{field} is too long")
    return result or None


def _string_list(value: Any, field: str, *, maximum_items: int = 100) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum_items:
        raise SetupStateError(f"{field} must be a list with at most {maximum_items} entries")
    result: list[str] = []
    for item in value:
        text = _text(item, field, maximum=500)
        if text not in result:
            result.append(text)
    return result


def _verification(value: Any, field: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise SetupStateError(f"{field} must be an object or null")
    allowed = {"timestamp", "device", "provider", "model", "status", "error_code"}
    _assert_keys(value, allowed, field)
    result: dict[str, Any] = {}
    for key in ("device", "provider", "model", "error_code"):
        result[key] = _text(value.get(key), f"{field}.{key}", optional=True)
    status = value.get("status")
    if status not in _STATUS_VALUES:
        raise SetupStateError(f"{field}.status is invalid")
    result["status"] = status
    timestamp = _text(value.get("timestamp"), f"{field}.timestamp")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SetupStateError(f"{field}.timestamp must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise SetupStateError(f"{field}.timestamp must include a timezone")
    result["timestamp"] = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return result


def _validate(state: Mapping[str, Any]) -> dict[str, Any]:
    _assert_keys(
        state,
        {"schema_version", "revision", "wizard", "provider", "voice", "google_profiles", "profile_selection"},
        "top-level",
    )
    if state.get("schema_version") != SCHEMA_VERSION:
        raise SetupStateError(f"unsupported setup schema version: {state.get('schema_version')!r}")
    revision = state.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise SetupStateError("revision must be a non-negative integer")

    wizard = state.get("wizard")
    if not isinstance(wizard, Mapping):
        raise SetupStateError("wizard must be an object")
    _assert_keys(wizard, {"completed", "completed_version"}, "wizard")
    completed = wizard.get("completed")
    if not isinstance(completed, bool):
        raise SetupStateError("wizard.completed must be a boolean")
    completed_version = _text(wizard.get("completed_version"), "wizard.completed_version", optional=True, maximum=30)
    if completed and completed_version is None:
        raise SetupStateError("wizard.completed_version is required when the wizard is completed")

    provider = state.get("provider")
    if not isinstance(provider, Mapping):
        raise SetupStateError("provider must be an object")
    _assert_keys(provider, {"choice", "model", "base_url", "status", "last_verification"}, "provider")
    if provider.get("choice") not in _PROVIDER_CHOICES:
        raise SetupStateError("provider.choice is invalid")
    if provider.get("status") not in _STATUS_VALUES:
        raise SetupStateError("provider.status is invalid")
    base_url = _text(provider.get("base_url"), "provider.base_url", optional=True, maximum=500)
    if base_url and urlparse(base_url).scheme not in {"http", "https"}:
        raise SetupStateError("provider.base_url must use http or https")

    voice = state.get("voice")
    if not isinstance(voice, Mapping):
        raise SetupStateError("voice must be an object")
    _assert_keys(voice, {"enabled", "output", "engine", "voice_id", "volume", "rate", "last_verification"}, "voice")
    if not isinstance(voice.get("enabled"), bool):
        raise SetupStateError("voice.enabled must be a boolean")
    if voice.get("output") not in _VOICE_OUTPUTS or voice.get("engine") not in _VOICE_ENGINES:
        raise SetupStateError("voice output or engine is invalid")
    volume = voice.get("volume")
    rate = voice.get("rate")
    if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not 0 <= volume <= 1:
        raise SetupStateError("voice.volume must be between 0 and 1")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not 0.5 <= rate <= 2:
        raise SetupStateError("voice.rate must be between 0.5 and 2")

    profiles = state.get("google_profiles")
    if not isinstance(profiles, list) or len(profiles) != 4:
        raise SetupStateError("google_profiles must contain exactly four slots")
    validated_profiles: list[dict[str, Any]] = []
    for index, profile in enumerate(profiles):
        if not isinstance(profile, Mapping):
            raise SetupStateError("each Google profile must be an object")
        _assert_keys(profile, {"slot_id", "label", "account_id", "calendar_ids", "scopes", "status", "last_verification"}, "Google profile")
        slot_id = profile.get("slot_id")
        if slot_id != PROFILE_SLOT_IDS[index]:
            raise SetupStateError("Google profile slots must be unique and in canonical order")
        status = profile.get("status")
        if status not in _STATUS_VALUES:
            raise SetupStateError(f"{slot_id}.status is invalid")
        validated_profiles.append(
            {
                "slot_id": slot_id,
                "label": _text(profile.get("label"), f"{slot_id}.label", maximum=80),
                "account_id": _text(profile.get("account_id"), f"{slot_id}.account_id", optional=True, maximum=320),
                "calendar_ids": _string_list(profile.get("calendar_ids"), f"{slot_id}.calendar_ids"),
                "scopes": _string_list(profile.get("scopes"), f"{slot_id}.scopes", maximum_items=20),
                "status": status,
                "last_verification": _verification(profile.get("last_verification"), f"{slot_id}.last_verification"),
            }
        )

    selection = state.get("profile_selection")
    if not isinstance(selection, Mapping):
        raise SetupStateError("profile_selection must be an object")
    _assert_keys(selection, {"mode", "default_slot_id", "active_slot_ids"}, "profile_selection")
    mode = selection.get("mode")
    default_slot_id = selection.get("default_slot_id")
    active_slot_ids = _string_list(selection.get("active_slot_ids"), "profile_selection.active_slot_ids", maximum_items=4)
    if mode not in _SELECTION_MODES or default_slot_id not in PROFILE_SLOT_IDS:
        raise SetupStateError("profile selection mode or default slot is invalid")
    if not active_slot_ids or any(slot_id not in PROFILE_SLOT_IDS for slot_id in active_slot_ids):
        raise SetupStateError("profile_selection.active_slot_ids must select one to four known slots")
    if mode == "default" and active_slot_ids != [default_slot_id]:
        raise SetupStateError("default selection mode must activate only the default slot")

    normalized = {
        "schema_version": SCHEMA_VERSION,
        "revision": revision,
        "wizard": {"completed": completed, "completed_version": completed_version},
        "provider": {
            "choice": provider["choice"],
            "model": _text(provider.get("model"), "provider.model", optional=True),
            "base_url": base_url,
            "status": provider["status"],
            "last_verification": _verification(provider.get("last_verification"), "provider.last_verification"),
        },
        "voice": {
            "enabled": voice["enabled"],
            "output": voice["output"],
            "engine": voice["engine"],
            "voice_id": _text(voice.get("voice_id"), "voice.voice_id", optional=True),
            "volume": float(volume),
            "rate": float(rate),
            "last_verification": _verification(voice.get("last_verification"), "voice.last_verification"),
        },
        "google_profiles": validated_profiles,
        "profile_selection": {
            "mode": mode,
            "default_slot_id": default_slot_id,
            "active_slot_ids": active_slot_ids,
        },
    }
    _assert_no_sensitive_material(normalized)
    return normalized


class SetupStateStore:
    """Thread-safe JSON store with validated partial updates and atomic writes."""

    def __init__(self, path: str | Path | None = None, *, env: Mapping[str, str] | None = None) -> None:
        self.path = Path(path).expanduser().resolve() if path is not None else default_setup_path(env)
        self._lock = RLock()
        self._lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                initial = _validate(_default_state())
                self._write(initial)
                return deepcopy(initial)
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise SetupStateError(f"unable to read valid setup state from {self.path}") from exc
            if not isinstance(raw, Mapping):
                raise SetupStateError("setup state root must be an object")
            return deepcopy(_validate(raw))

    def public_view(self, *, include_account_ids: bool = False) -> dict[str, Any]:
        state = self.load()
        if not include_account_ids:
            for profile in state["google_profiles"]:
                profile["connected"] = bool(profile["account_id"])
                profile["account_id"] = None
        return state

    def update(self, patch: Mapping[str, Any], *, expected_revision: int | None = None) -> dict[str, Any]:
        if not isinstance(patch, Mapping):
            raise SetupStateError("setup update must be an object")
        _assert_keys(patch, {"wizard", "provider", "voice", "google_profiles", "profile_selection"}, "update")
        _assert_no_sensitive_material(patch, "update")
        with self._lock:
            with self._process_lock():
                current = self.load()
                if expected_revision is not None and current["revision"] != expected_revision:
                    raise SetupStateError("setup state revision changed; reload before updating")
                candidate = deepcopy(current)
                for section in ("wizard", "provider", "voice", "profile_selection"):
                    if section in patch:
                        value = patch[section]
                        if not isinstance(value, Mapping):
                            raise SetupStateError(f"{section} update must be an object")
                        candidate[section].update(_plain_json(value))
                if "google_profiles" in patch:
                    updates = patch["google_profiles"]
                    if not isinstance(updates, Mapping):
                        raise SetupStateError("google_profiles update must map slot IDs to fields")
                    unknown_slots = set(updates) - set(PROFILE_SLOT_IDS)
                    if unknown_slots:
                        raise SetupStateError(f"unknown Google profile slot(s): {', '.join(sorted(unknown_slots))}")
                    by_slot = {profile["slot_id"]: profile for profile in candidate["google_profiles"]}
                    for slot_id, value in updates.items():
                        if not isinstance(value, Mapping):
                            raise SetupStateError(f"{slot_id} update must be an object")
                        if "slot_id" in value and value["slot_id"] != slot_id:
                            raise SetupStateError("Google profile slot_id cannot be changed")
                        by_slot[slot_id].update(_plain_json(value))
                candidate["revision"] = current["revision"] + 1
                validated = _validate(candidate)
                self._write(validated)
                return deepcopy(validated)

    @contextmanager
    def _process_lock(self):
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _write(self, state: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(state, handle, indent=2, sort_keys=True, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise


__all__ = [
    "PROFILE_SLOT_IDS",
    "SCHEMA_VERSION",
    "WIZARD_VERSION",
    "SetupStateError",
    "SetupStateStore",
    "default_setup_path",
]
