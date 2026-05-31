from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

import metis_head.boh_link as boh_link
import metis_head.boh_retrieval as boh_retrieval
from metis_head.boh_link import (
    LINK_AUTH_FAILED,
    LINK_CONNECTED,
    LINK_DEGRADED,
    LINK_DISABLED,
    LINK_DISCONNECTED,
    BOHLinkConfig,
    BOHLinkState,
    link_config_from_env,
    probe_boh_once,
)
from metis_head.brain import app

SECRET_TOKEN = "super-secret-readonly-token"


def _config(*, enabled: bool = True, token: str = SECRET_TOKEN) -> BOHLinkConfig:
    return BOHLinkConfig(
        enabled=enabled,
        base_url="http://127.0.0.1:8000",
        token=token,
        mode="exploration",
        limit=5,
        poll_seconds=15,
        probe_query="__metis_connection_probe__",
    )


def _resp(status: int | None, body: dict[str, Any] | None = None, network_error: str | None = None) -> boh_link._Resp:
    return boh_link._Resp(status=status, body=body, network_error=network_error)


def _route(responses: dict[str, boh_link._Resp]):
    def fake_request(url: str, method: str, payload, headers, timeout) -> boh_link._Resp:
        for fragment, resp in responses.items():
            if url.endswith(fragment):
                return resp
        raise AssertionError(f"unexpected url: {url}")

    return fake_request


def test_link_config_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("METIS_BOH_BACKGROUND_ENABLED", raising=False)
    config = link_config_from_env(env={})
    assert config.enabled is False


def test_background_disabled_yields_disabled_state(monkeypatch) -> None:
    state = BOHLinkState()
    probe_boh_once(_config(enabled=False), state)
    assert state.state == LINK_DISABLED
    assert state.enabled is False


def test_missing_token_is_auth_failed(monkeypatch) -> None:
    state = BOHLinkState()
    probe_boh_once(_config(token=""), state)
    assert state.state == LINK_AUTH_FAILED


def test_healthy_health_status_and_probe_yields_connected(monkeypatch) -> None:
    monkeypatch.setattr(
        boh_link,
        "_request",
        _route(
            {
                "/api/health": _resp(200, {"status": "ok"}),
                "/api/retrieve/status": _resp(200, {"configured": True, "read_only": True}),
                "/api/retrieve": _resp(200, {"count": 1, "context_packs": [{"doc_id": "d1"}]}),
            }
        ),
    )
    state = BOHLinkState()
    probe_boh_once(_config(), state)
    assert state.state == LINK_CONNECTED
    assert state.last_probe_count == 1
    assert state.last_connected_at is not None
    assert state.last_error is None
    assert state.retrieval_status == {"configured": True, "read_only": True}


def test_connection_refused_yields_disconnected(monkeypatch) -> None:
    monkeypatch.setattr(
        boh_link,
        "_request",
        _route({"/api/health": _resp(None, None, network_error="Connection refused")}),
    )
    state = BOHLinkState()
    probe_boh_once(_config(), state)
    assert state.state == LINK_DISCONNECTED
    assert state.last_error


def test_auth_rejection_on_probe_yields_auth_failed(monkeypatch) -> None:
    monkeypatch.setattr(
        boh_link,
        "_request",
        _route(
            {
                "/api/health": _resp(200, {"status": "ok"}),
                "/api/retrieve/status": _resp(200, {"configured": True}),
                "/api/retrieve": _resp(403),
            }
        ),
    )
    state = BOHLinkState()
    probe_boh_once(_config(), state)
    assert state.state == LINK_AUTH_FAILED


def test_auth_rejection_on_retrieve_status_yields_auth_failed(monkeypatch) -> None:
    monkeypatch.setattr(
        boh_link,
        "_request",
        _route(
            {
                "/api/health": _resp(200, {"status": "ok"}),
                "/api/retrieve/status": _resp(401),
            }
        ),
    )
    state = BOHLinkState()
    probe_boh_once(_config(), state)
    assert state.state == LINK_AUTH_FAILED
    assert "401" in state.last_error


def test_health_ok_but_probe_network_error_yields_degraded(monkeypatch) -> None:
    monkeypatch.setattr(
        boh_link,
        "_request",
        _route(
            {
                "/api/health": _resp(200, {"status": "ok"}),
                "/api/retrieve/status": _resp(200, {"configured": True}),
                "/api/retrieve": _resp(None, None, network_error="timed out"),
            }
        ),
    )
    state = BOHLinkState()
    probe_boh_once(_config(), state)
    assert state.state == LINK_DEGRADED


def test_transition_emitted_once_not_repeatedly(monkeypatch) -> None:
    monkeypatch.setattr(
        boh_link,
        "_request",
        _route(
            {
                "/api/health": _resp(200, {"status": "ok"}),
                "/api/retrieve/status": _resp(200, {}),
                "/api/retrieve": _resp(200, {"count": 2}),
            }
        ),
    )
    state = BOHLinkState()
    probe_boh_once(_config(), state)
    probe_boh_once(_config(), state)
    probe_boh_once(_config(), state)
    connected_events = [e for e in state.transition_events if e["to"] == LINK_CONNECTED]
    assert len(connected_events) == 1


def test_status_endpoint_returns_safe_state_without_token(monkeypatch) -> None:
    state = BOHLinkState(
        enabled=True,
        state=LINK_CONNECTED,
        base_url="http://127.0.0.1:8000",
        last_probe_count=3,
    )
    monkeypatch.setattr(boh_link, "_LINK_STATE", state)
    client = TestClient(app)
    response = client.get("/metis/boh/status")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == LINK_CONNECTED
    assert body["last_probe_count"] == 3
    assert "token" not in body
    # No secret should ever be serialized through the status endpoint.
    assert SECRET_TOKEN not in json.dumps(body)


def test_to_dict_never_includes_token_field() -> None:
    state = BOHLinkState(enabled=True, state=LINK_CONNECTED)
    payload = state.to_dict()
    assert "token" not in payload
    assert "Authorization" not in json.dumps(payload)


def test_probe_scrubs_token_from_network_error(monkeypatch) -> None:
    monkeypatch.setattr(
        boh_link,
        "_request",
        _route(
            {
                "/api/health": _resp(200, {"status": "ok"}),
                "/api/retrieve/status": _resp(200, {}),
                "/api/retrieve": _resp(None, None, network_error=f"failed with {SECRET_TOKEN}"),
            }
        ),
    )
    state = BOHLinkState()
    probe_boh_once(_config(), state)
    assert SECRET_TOKEN not in json.dumps(state.to_dict())


def test_probe_scrubs_token_from_surfaced_payloads(monkeypatch) -> None:
    monkeypatch.setattr(
        boh_link,
        "_request",
        _route(
            {
                "/api/health": _resp(200, {"echo": SECRET_TOKEN}),
                "/api/retrieve/status": _resp(200, {"nested": {"echo": SECRET_TOKEN}}),
                "/api/retrieve": _resp(200, {"count": 1}),
            }
        ),
    )
    state = BOHLinkState()
    probe_boh_once(_config(), state)
    serialized = json.dumps(state.to_dict())
    assert SECRET_TOKEN not in serialized
    assert "***" in serialized


def test_chat_auth_failed_skips_live_retrieval(monkeypatch) -> None:
    monkeypatch.setenv("METIS_LLM_PROVIDER", "mock")
    monkeypatch.setenv("METIS_BOH_ENABLED", "true")
    monkeypatch.setenv("METIS_BOH_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("METIS_BOH_RETRIEVAL_TOKEN", SECRET_TOKEN)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("live retrieval must be skipped when background link is auth_failed")

    monkeypatch.setattr(boh_retrieval, "_post_json", fail_if_called)
    monkeypatch.setattr(
        boh_link,
        "_LINK_STATE",
        BOHLinkState(enabled=True, state=LINK_AUTH_FAILED, base_url="http://127.0.0.1:8000"),
    )
    client = TestClient(app)
    client.post("/metis/state/reset")
    client.post("/metis/event", json={"type": "button_event", "button": "afc", "state": True})
    response = client.post("/metis/chat", json={"message": "What do we know?"})
    assert response.status_code == 200
    body = response.json()
    assert body["source_state"] == "degraded"
    assert "degraded" in body["message"].lower()
    assert body["retrieval"]["attempted"] is False
