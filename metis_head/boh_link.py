from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib import error, request

from .boh_retrieval import BOH_RETRIEVAL_HEADER, _as_bool, boh_config_from_env

# Phase 0C: lightweight, read-only background awareness of the BOH link.
# This module NEVER mutates BOH, never holds or sends BOH's operator token,
# and never copies the BOH corpus into Metis. It only tracks connection
# health and a tiny probe result so the dashboard can surface link state.

# Background link states. These are link-health states, distinct from the
# per-message source_state labels (sourced/unsourced/degraded) the brain owns.
LINK_DISABLED = "disabled"
LINK_CONNECTING = "connecting"
LINK_CONNECTED = "connected"
LINK_DEGRADED = "degraded"
LINK_DISCONNECTED = "disconnected"
LINK_AUTH_FAILED = "auth_failed"

DEFAULT_POLL_SECONDS = 15
DEFAULT_PROBE_QUERY = "__metis_connection_probe__"
AUTH_FAILED_MIN_BACKOFF = 60
MAX_TRANSITION_EVENTS = 20
_PROBE_TIMEOUT = 8


@dataclass
class _Resp:
    status: int | None
    body: dict[str, Any] | None
    network_error: str | None = None


def _request(url: str, method: str, payload: dict[str, Any] | None, headers: dict[str, str], timeout: int) -> _Resp:
    """Read-only HTTP request that distinguishes auth (401/403) from network failures.

    llm_providers' helpers collapse HTTP status codes into error strings, which
    makes it impossible to tell an auth failure from a connection refusal. The
    background link manager needs that distinction to choose auth_failed vs.
    disconnected, so it uses this dedicated request helper.
    """
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    all_headers = {"Content-Type": "application/json", **headers}
    req = request.Request(url, data=data, headers=all_headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return _Resp(status=response.status, body=_safe_json(raw))
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return _Resp(status=exc.code, body=_safe_json(raw))
    except (error.URLError, OSError, TimeoutError) as exc:
        return _Resp(status=None, body=None, network_error=str(exc))


def _safe_json(raw: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _scrub(text: str | None, token: str) -> str | None:
    if not text:
        return text
    if token and token in text:
        return text.replace(token, "***")
    return text


@dataclass(frozen=True)
class BOHLinkConfig:
    enabled: bool
    base_url: str
    token: str
    mode: str
    limit: int
    poll_seconds: int
    probe_query: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "base_url": self.base_url,
            "mode": self.mode,
            "limit": self.limit,
            "poll_seconds": self.poll_seconds,
            "token_configured": bool(self.token),
        }


@dataclass
class BOHLinkState:
    enabled: bool = False
    state: str = LINK_DISABLED
    base_url: str = ""
    last_checked_at: float | None = None
    last_connected_at: float | None = None
    last_error: str | None = None
    health: dict[str, Any] | None = None
    retrieval_status: dict[str, Any] | None = None
    last_probe_count: int | None = None
    transition_events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        # Token must never appear here. Only health/retrieval_status snapshots
        # from BOH's secret-free endpoints are surfaced.
        return {
            "enabled": self.enabled,
            "state": self.state,
            "base_url": self.base_url,
            "last_checked_at": self.last_checked_at,
            "last_connected_at": self.last_connected_at,
            "last_error": self.last_error,
            "health": self.health,
            "retrieval_status": self.retrieval_status,
            "last_probe_count": self.last_probe_count,
            "transition_events": list(self.transition_events),
        }


def link_config_from_env(env: dict[str, str] | None = None, options: dict[str, Any] | None = None) -> BOHLinkConfig:
    env = env or os.environ
    base = boh_config_from_env(env=env, options=options)
    enabled = _as_bool(env.get("METIS_BOH_BACKGROUND_ENABLED", "false"))
    try:
        poll_seconds = int(env.get("METIS_BOH_POLL_SECONDS", str(DEFAULT_POLL_SECONDS)))
    except (TypeError, ValueError):
        poll_seconds = DEFAULT_POLL_SECONDS
    poll_seconds = max(5, min(3600, poll_seconds))
    probe_query = str(env.get("METIS_BOH_PROBE_QUERY", DEFAULT_PROBE_QUERY)) or DEFAULT_PROBE_QUERY
    return BOHLinkConfig(
        enabled=enabled,
        base_url=base.base_url,
        token=base.token,
        mode=base.mode,
        limit=base.limit,
        poll_seconds=poll_seconds,
        probe_query=probe_query,
    )


def _set_state(state: BOHLinkState, new_state: str) -> None:
    """Record a transition only when the link state actually changes."""
    if state.state == new_state:
        return
    state.transition_events.append({"from": state.state, "to": new_state, "at": time.time()})
    if len(state.transition_events) > MAX_TRANSITION_EVENTS:
        del state.transition_events[: len(state.transition_events) - MAX_TRANSITION_EVENTS]
    state.state = new_state


def probe_boh_once(config: BOHLinkConfig, state: BOHLinkState) -> BOHLinkState:
    """Run a single read-only health/status/probe cycle and update state.

    Pure with respect to I/O isolation: callers (and tests) provide the state to
    mutate, and all network access goes through the module-level ``_request`` so
    it can be monkeypatched without threads or sockets.
    """
    state.enabled = config.enabled
    state.base_url = config.base_url
    state.last_checked_at = time.time()

    if not config.enabled:
        state.last_error = None
        _set_state(state, LINK_DISABLED)
        return state

    if not config.token:
        state.last_error = "METIS_BOH_RETRIEVAL_TOKEN is required when background link is enabled"
        _set_state(state, LINK_AUTH_FAILED)
        return state

    health = _request(f"{config.base_url}/api/health", "GET", None, {}, _PROBE_TIMEOUT)
    if health.network_error is not None:
        state.last_error = _scrub(health.network_error, config.token)
        state.health = None
        _set_state(state, LINK_DISCONNECTED)
        return state
    if health.status in (401, 403):
        state.last_error = f"BOH health returned {health.status}"
        state.health = None
        _set_state(state, LINK_AUTH_FAILED)
        return state
    state.health = health.body
    if health.status is None or health.status >= 500:
        state.last_error = f"BOH health returned status {health.status}"
        _set_state(state, LINK_DEGRADED)
        return state

    status = _request(f"{config.base_url}/api/retrieve/status", "GET", None, {}, _PROBE_TIMEOUT)
    if status.status not in (401, 403) and status.network_error is None and status.body is not None:
        state.retrieval_status = status.body

    probe = _request(
        f"{config.base_url}/api/retrieve",
        "POST",
        {"query": config.probe_query, "mode": config.mode, "limit": 1},
        {BOH_RETRIEVAL_HEADER: config.token},
        _PROBE_TIMEOUT,
    )
    if probe.status in (401, 403):
        state.last_error = f"BOH retrieval probe returned {probe.status}"
        _set_state(state, LINK_AUTH_FAILED)
        return state
    if probe.network_error is not None:
        state.last_error = _scrub(probe.network_error, config.token)
        _set_state(state, LINK_DEGRADED)
        return state
    if probe.status is None or probe.status >= 400:
        state.last_error = f"BOH retrieval probe returned status {probe.status}"
        _set_state(state, LINK_DEGRADED)
        return state

    count = probe.body.get("count") if isinstance(probe.body, dict) else None
    if not isinstance(count, int):
        packs = probe.body.get("context_packs") if isinstance(probe.body, dict) else None
        count = len(packs) if isinstance(packs, list) else 0
    state.last_probe_count = count
    state.last_error = None
    state.last_connected_at = time.time()
    _set_state(state, LINK_CONNECTED)
    return state


class BOHLinkManager:
    """Daemon-thread poller. Uses threading (not asyncio) because the BOH HTTP
    helpers are blocking urllib calls."""

    def __init__(self, config: BOHLinkConfig, state: BOHLinkState) -> None:
        self.config = config
        self.state = state
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        _set_state(self.state, LINK_CONNECTING)
        self.state.enabled = True
        self._thread = threading.Thread(target=self._run, name="boh-link-manager", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                probe_boh_once(self.config, self.state)
            except Exception as exc:  # never let the poller thread die
                self.state.last_error = _scrub(str(exc), self.config.token)
                _set_state(self.state, LINK_DEGRADED)
            wait = self.config.poll_seconds
            if self.state.state == LINK_AUTH_FAILED:
                wait = max(wait, AUTH_FAILED_MIN_BACKOFF)
            self._stop.wait(wait)


# Module globals. The link state exists at import time as a disabled state so
# GET /metis/boh/status works even when FastAPI startup never fires (existing
# tests build TestClient(app) without the context-manager form).
_LINK_STATE = BOHLinkState()
_LINK_MANAGER: BOHLinkManager | None = None


def get_link_state() -> BOHLinkState:
    return _LINK_STATE


def start_background_link(env: dict[str, str] | None = None) -> BOHLinkState:
    global _LINK_MANAGER
    config = link_config_from_env(env=env)
    _LINK_STATE.enabled = config.enabled
    _LINK_STATE.base_url = config.base_url
    if not config.enabled:
        _set_state(_LINK_STATE, LINK_DISABLED)
        return _LINK_STATE
    if _LINK_MANAGER is not None:
        return _LINK_STATE
    _LINK_MANAGER = BOHLinkManager(config, _LINK_STATE)
    _LINK_MANAGER.start()
    return _LINK_STATE


def stop_background_link() -> None:
    global _LINK_MANAGER
    if _LINK_MANAGER is not None:
        _LINK_MANAGER.stop()
        _LINK_MANAGER = None
