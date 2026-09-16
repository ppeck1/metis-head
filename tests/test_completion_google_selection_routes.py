from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from metis_head import brain
from metis_head.connectors.google_access import CALENDAR_SCOPE, GoogleReadBroker
from metis_head.credentials import CredentialStore
from metis_head.llm_providers import LLMResult
from metis_head.model_adapters.ollama_local import BoundedUrllibJsonTransport


class CalendarFixture:
    def __init__(self) -> None:
        self.calls = []

    def list_events(self, **kwargs):
        self.calls.append(kwargs)
        return {"items": []}

    def list_calendars(self, **kwargs):
        return {"items": [{"id": "team", "summary": "Team"}, {"id": "private", "summary": "Private"}]}


def _configured_store(tmp_path, monkeypatch):
    store = CredentialStore(tmp_path / "connections.json")
    monkeypatch.setattr(store, "_set_secret", lambda connection_id, secret: None)
    monkeypatch.setattr(store, "_delete_secret", lambda connection_id: None)
    store.connect("google", "work@example.test", [CALENDAR_SCOPE], "fixture")
    store.update_google_selection("work@example.test", ["team"])
    return store


def test_session_create_and_partial_update_enforce_persisted_selection(tmp_path, monkeypatch):
    store = _configured_store(tmp_path, monkeypatch)
    monkeypatch.setattr(brain, "_google_store", lambda: store)

    with TestClient(brain.app) as client:
        allowed = client.post(
            "/metis/sessions",
            json={"client_id": "selected-tab", "context": {"account_id": "work@example.test", "calendar_ids": ["team"]}},
        )
        session_id = allowed.json()["session_id"]
        unselected_create = client.post(
            "/metis/sessions",
            json={"client_id": "bad-tab", "context": {"account_id": "work@example.test", "calendar_ids": ["private"]}},
        )
        calendars_only_bypass = client.post(
            f"/metis/sessions/{session_id}/context",
            json={"calendar_ids": ["private"]},
        )
        client.delete(f"/metis/sessions/{session_id}")

    assert allowed.status_code == 200
    assert unselected_create.status_code == 400
    assert calendars_only_bypass.status_code == 400


def test_session_options_cannot_override_trusted_account_or_calendar(tmp_path, monkeypatch):
    store = _configured_store(tmp_path, monkeypatch)
    fixture = CalendarFixture()
    broker = GoogleReadBroker.from_connection_records(
        [{
            "provider": "google", "status": "connected", "account_id": "work@example.test",
            "scopes": [CALENDAR_SCOPE], "selected_calendar_ids": ["team"],
        }],
        {"work@example.test": fixture},
        clock=lambda: datetime(2026, 9, 16, 12, tzinfo=UTC),
    )
    payloads = []

    class Provider:
        def generate(self, messages, state, options):
            payloads.append(messages)
            return LLMResult("ok", "fixture", "fixture")

    monkeypatch.setattr(brain, "_google_store", lambda: store)
    monkeypatch.setattr(brain, "_google_read_broker", lambda: broker)
    monkeypatch.setattr(brain, "provider_from_config", lambda options: Provider())
    with TestClient(brain.app) as client:
        session_id = client.post(
            "/metis/sessions",
            json={"client_id": "trusted-tab", "context": {"account_id": "work@example.test", "calendar_ids": ["team"]}},
        ).json()["session_id"]
        response = client.post(
            "/metis/chat",
            json={
                "message": "hello", "session_id": session_id,
                "options": {"account_id": "other@example.test", "calendar_ids": ["private"]},
            },
        )

    assert response.status_code == 200
    system = payloads[0][0]["content"]
    assert "Selected account: work@example.test" in system
    assert "Selected calendars: team" in system
    assert "other@example.test" not in system
    assert "private" not in system


def test_production_broker_denies_unselected_calendar_before_transport():
    fixture = CalendarFixture()
    broker = GoogleReadBroker.from_connection_records(
        [{
            "provider": "google", "status": "connected", "account_id": "work@example.test",
            "scopes": [CALENDAR_SCOPE], "selected_calendar_ids": ["team"],
        }],
        {"work@example.test": fixture},
        clock=lambda: datetime(2026, 9, 16, 12, tzinfo=UTC),
    )

    result = broker.calendar_events(
        account_id="work@example.test", calendar_ids=["private"],
        start=datetime(2026, 9, 17, tzinfo=UTC), end=datetime(2026, 9, 18, tzinfo=UTC), timezone="UTC",
    )

    assert result.error.code.value == "permission_denied"
    assert fixture.calls == []


def test_ollama_tool_call_cannot_switch_to_an_unselected_connected_account(tmp_path, monkeypatch):
    store = _configured_store(tmp_path, monkeypatch)
    store.connect("google", "other@example.test", [CALENDAR_SCOPE], "fixture-two")
    store.update_google_selection("other@example.test", ["primary"])
    work = CalendarFixture()
    other = CalendarFixture()
    records = store.list_connections()
    broker = GoogleReadBroker.from_connection_records(
        records,
        {"work@example.test": work, "other@example.test": other},
        clock=lambda: datetime(2026, 9, 16, 12, tzinfo=UTC),
    )
    payloads = []

    def fake_post(self, *, url, payload, timeout_seconds, cancellation):
        payloads.append(payload)
        if len(payloads) == 1:
            calendar_tool = next(item for item in payload["tools"] if "calendar_ids" in item["function"]["parameters"].get("required", []))
            return {"choices": [{"message": {"content": None, "tool_calls": [{
                "id": "wrong-account", "type": "function",
                "function": {
                    "name": calendar_tool["function"]["name"],
                    "arguments": '{"account_id":"other@example.test","calendar_ids":["primary"],"start":"2026-09-17T00:00:00Z","end":"2026-09-18T00:00:00Z","timezone":"UTC"}',
                },
            }]}}]}
        return {"choices": [{"message": {"content": "The requested account was not authorized for this session."}}]}

    monkeypatch.setattr(brain, "_google_store", lambda: store)
    monkeypatch.setattr(brain, "_google_read_broker", lambda: broker)
    monkeypatch.setattr(
        brain,
        "_setup_store",
        lambda: type("SetupFixture", (), {"load": lambda self: {"google_profiles": [
            {"slot_id": "work", "label": "Work", "account_id": "work@example.test", "calendar_ids": ["team"]},
            {"slot_id": "other", "label": "Other", "account_id": "other@example.test", "calendar_ids": ["primary"]},
        ]}})(),
    )
    monkeypatch.setattr(BoundedUrllibJsonTransport, "post_json", fake_post)
    with TestClient(brain.app) as client:
        session_id = client.post(
            "/metis/sessions",
            json={"client_id": "account-bound-tab", "context": {"account_id": "work@example.test", "calendar_ids": ["team"]}},
        ).json()["session_id"]
        response = client.post(
            "/metis/chat",
            json={"message": "read my calendar", "session_id": session_id, "options": {"provider": "ollama", "model": "fixture"}},
        )

    assert response.status_code == 200
    tool_message = next(message for message in payloads[1]["messages"] if message["role"] == "tool")
    assert '"status": "denied"' in tool_message["content"]
    assert "account_not_connected" in tool_message["content"]
    assert work.calls == []
    assert other.calls == []
