from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from metis_head.connectors.atlas import AtlasReadConnector
from metis_head.connectors.contracts import ConnectorTransportError, ErrorCode, Freshness
from metis_head.connectors.google_access import CALENDAR_SCOPE, GoogleReadBroker, GoogleReadGrant
from metis_head.connectors.google_api import GoogleApiTransport
from metis_head.connectors.google_metadata import GoogleAccountPolicy
from metis_head.credentials import CredentialStore, SecretStoreUnavailable
from metis_head.orchestration import AuthorizationContext, CancellationToken, ToolExecutor, ToolRequest
from metis_head.personal_orchestration import atlas_registry_entries, google_broker_entries, run_google_broker_read


NOW = datetime(2026, 9, 16, 12, tzinfo=UTC)


class Store:
    def __init__(self, secret: str = "{}", records=()):
        self.value = secret
        self.records = list(records)
        self.saved = []

    def secret(self, connection_id):
        return self.value

    def connect(self, provider, account_id, scopes, secret):
        self.saved.append((provider, account_id, scopes, secret))

    def list_connections(self):
        return list(self.records)


class Call:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class CalendarList:
    def __init__(self, pages, calls):
        self.pages = pages
        self.calls = calls

    def list(self, **kwargs):
        self.calls.append(kwargs)
        return Call(self.pages[kwargs.get("pageToken")])


class CalendarService:
    def __init__(self, pages, calls):
        self.resource = CalendarList(pages, calls)

    def calendarList(self):
        return self.resource


class Credentials:
    def __init__(self, *, expired=False, refresh_error=None):
        self.expired = expired
        self.refresh_token = "refresh" if expired else None
        self.granted_scopes = (CALENDAR_SCOPE,)
        self.scopes = (CALENDAR_SCOPE, "not-authoritative")
        self.refresh_error = refresh_error

    def refresh(self, request):
        if self.refresh_error:
            raise self.refresh_error
        self.expired = False

    def to_json(self):
        return json.dumps({"scopes": list(self.granted_scopes), "token": "redacted-fixture"})


def _transport(pages, *, credentials=None, store=None):
    calls = []
    service = CalendarService(pages, calls)
    credential = credentials or Credentials()
    actual_store = store or Store()
    transport = GoogleApiTransport(
        "work@example.test",
        actual_store,
        credentials_loader=lambda info: credential,
        service_builder=lambda *args, **kwargs: service,
        request_factory=lambda: object(),
    )
    return transport, calls, actual_store


def test_real_google_transport_surface_and_broker_bound_paginated_discovery():
    transport, calls, _ = _transport(
        {
            None: {"items": [{"id": "one", "summary": "One"}], "nextPageToken": "p2"},
            "p2": {"items": [{"id": "two", "summary": "Two"}], "nextPageToken": "p3"},
            "p3": {"items": [{"id": "three", "summary": "Three"}]},
        }
    )
    broker = GoogleReadBroker(
        {"work@example.test": transport},
        {"work@example.test": GoogleReadGrant("work@example.test", frozenset({CALENDAR_SCOPE}))},
        clock=lambda: NOW,
    )

    result = broker.list_calendars(account_id="work@example.test", max_calendars=2, max_pages=10)

    assert [item.calendar_id for item in result.data] == ["one", "two"]
    assert result.truncated is True
    assert result.next_page_token == "p3"
    assert calls == [
        {"pageToken": None, "maxResults": 2, "showDeleted": False, "showHidden": False},
        {"pageToken": "p2", "maxResults": 1, "showDeleted": False, "showHidden": False},
    ]


def test_refresh_persists_rotated_token_with_actual_granted_scopes():
    credentials = Credentials(expired=True)
    transport, _, store = _transport({None: {"items": []}}, credentials=credentials)

    assert transport.granted_scopes() == (CALENDAR_SCOPE,)
    assert store.saved[0][:3] == ("google", "work@example.test", [CALENDAR_SCOPE])


def test_credential_refresh_preserves_persistent_calendar_selection(tmp_path, monkeypatch):
    store = CredentialStore(tmp_path / "connections.json")
    monkeypatch.setattr(store, "_set_secret", lambda connection_id, secret: None)
    store.connect("google", "work@example.test", [CALENDAR_SCOPE], "first")
    store.update_google_selection("work@example.test", ["team"])

    refreshed = store.connect("google", "work@example.test", [CALENDAR_SCOPE], "rotated")

    assert refreshed.selected_calendar_ids == ("team",)
    assert store.list_connections()[0]["selected_calendar_ids"] == ("team",)


def test_restore_maps_revoked_auth_to_reconnect_required():
    RefreshError = type("RefreshError", (Exception,), {"__module__": "google.auth.exceptions"})
    store = Store(records=[{"provider": "google", "status": "connected", "account_id": "work@example.test"}])

    def factory(account_id, selected_store):
        return _transport({None: {}}, credentials=Credentials(expired=True, refresh_error=RefreshError()), store=selected_store)[0]

    restored = GoogleReadBroker.restore_from_credential_store(store, transport_factory=factory, clock=lambda: NOW)
    assert restored.broker.accounts() == ()
    assert restored.accounts[0].status == "reconnect_required"
    assert restored.accounts[0].error_code is ErrorCode.AUTH_EXPIRED


def test_restore_maps_missing_keyring_to_unavailable_without_false_reconnect():
    class MissingStore(Store):
        def secret(self, connection_id):
            raise SecretStoreUnavailable("fixture keyring unavailable")

    store = MissingStore(records=[{"provider": "google", "status": "connected", "account_id": "work@example.test"}])
    restored = GoogleReadBroker.restore_from_credential_store(store, clock=lambda: NOW)
    assert restored.broker.accounts() == ()
    assert restored.accounts[0].status == "unavailable"
    assert restored.accounts[0].error_code is ErrorCode.UNAVAILABLE


def test_restore_keeps_persisted_selection_for_real_discovery():
    store = Store(records=[{
        "provider": "google", "status": "connected", "account_id": "work@example.test",
        "selected_calendar_ids": ["team"],
    }])

    def factory(account_id, selected_store):
        return _transport({None: {"items": [{"id": "team", "summary": "Team"}]}}, store=selected_store)[0]

    restored = GoogleReadBroker.restore_from_credential_store(store, transport_factory=factory, clock=lambda: NOW)
    calendars = restored.broker.list_calendars(account_id="work@example.test")
    assert calendars.data[0].selected is True


def test_empty_persisted_selection_grants_no_calendar_even_if_google_marks_one_selected():
    transport, _, _ = _transport({
        None: {"items": [{"id": "primary", "summary": "Primary", "selected": True}]}
    })
    broker = GoogleReadBroker.from_connection_records(
        [{
            "provider": "google", "status": "connected", "account_id": "work@example.test",
            "scopes": [CALENDAR_SCOPE], "selected_calendar_ids": [],
        }],
        {"work@example.test": transport},
        clock=lambda: NOW,
    )

    discovered = broker.list_calendars(account_id="work@example.test")
    events = broker.calendar_events(
        account_id="work@example.test", calendar_ids=["primary"],
        start=NOW, end=datetime(2026, 9, 17, 12, tzinfo=UTC), timezone="UTC",
    )

    assert discovered.data[0].selected is False
    assert events.error and events.error.code is ErrorCode.PERMISSION_DENIED


def test_versioned_selection_never_broadens_enforced_calendar_grant():
    policy = GoogleAccountPolicy.from_record(
        {
            "account_id": "work@example.test",
            "scopes": [CALENDAR_SCOPE],
            "allowed_calendar_ids": ["team"],
            "selected_calendar_ids": ["team"],
        }
    )
    assert policy.allowed_calendar_ids == frozenset({"team"})
    assert policy.selected_calendar_ids == ("team",)
    with pytest.raises(ValueError, match="within the enforced"):
        GoogleAccountPolicy.from_record(
            {"account_id": "work@example.test", "allowed_calendar_ids": ["team"], "selected_calendar_ids": ["private"]}
        )


def test_google_discovery_is_registered_and_still_enforces_broker_grants():
    transport, _, _ = _transport({None: {"items": [{"id": "team"}, {"id": "private"}]}})
    broker = GoogleReadBroker(
        {"work@example.test": transport},
        {"work@example.test": GoogleReadGrant("work@example.test", frozenset({CALENDAR_SCOPE}), frozenset({"team"}))},
        clock=lambda: NOW,
    )
    executor = ToolExecutor(google_broker_entries(broker))
    from metis_head.orchestration import AccountGrant

    authorization = AuthorizationContext(
        accounts={"work@example.test": AccountGrant("work@example.test", frozenset({CALENDAR_SCOPE}))}
    )
    result = executor.execute(
        ToolRequest("r1", "s1", "t1", "google.calendar.discover", "1", {}, "work@example.test", frozenset({CALENDAR_SCOPE})),
        authorization,
        CancellationToken(),
    )
    assert result.ok
    assert [item["calendar_id"] for item in result.data] == ["team"]


def test_compatibility_orchestration_cannot_bypass_broker_calendar_grant():
    transport, calls, _ = _transport({None: {"items": []}})
    broker = GoogleReadBroker(
        {"work@example.test": transport},
        {"work@example.test": GoogleReadGrant("work@example.test", frozenset({CALENDAR_SCOPE}), frozenset({"team"}))},
        clock=lambda: NOW,
    )
    outcome = run_google_broker_read(
        session_id="session", turn_id="turn", tool_name="google.calendar.list",
        arguments={
            "calendar_ids": ["private"], "start": "2026-09-17T00:00:00Z",
            "end": "2026-09-18T00:00:00Z", "timezone": "UTC",
        },
        account_id="work@example.test", broker=broker,
    )
    assert outcome.exchanges[0].result.error_code == "permission_denied"
    assert calls == []


def test_atlas_registry_resolves_natural_name_then_reads_mcp_status_with_provenance():
    calls = []

    def mcp(tool_name, arguments):
        calls.append((tool_name, arguments))
        if tool_name == "list_projects":
            return {
                "status": "read_only_complete",
                "attempted": True,
                "result": {"structuredContent": {"projects": [{"id": "metis-1", "name": "Metis Head", "aliases": ["metis"]}]}},
            }
        return {
            "status": "read_only_complete",
            "attempted": True,
            "result": {
                "structuredContent": {
                    "status": "active",
                    "summary": "Production fixture status",
                    "observed_at": "2026-09-16T11:30:00Z",
                    "source_url": "https://atlas.example.test/projects/metis-1",
                }
            },
        }

    executor = ToolExecutor(atlas_registry_entries(AtlasReadConnector(mcp, clock=lambda: NOW)))
    result = executor.execute(
        ToolRequest(
            "r-atlas", "s1", "t1", "atlas.project.status", "1",
            {"project": "Check my Metis project status"},
        ),
        AuthorizationContext(accounts={}),
        CancellationToken(),
    )
    assert result.ok
    assert result.data["project"]["project_id"] == "metis-1"
    assert result.freshness.status.value == Freshness.CURRENT.value
    assert result.provenance[0].source_uri == "https://atlas.example.test/projects/metis-1"
    assert calls == [("list_projects", {"limit": 100}), ("get_project_status", {"project_id": "metis-1"})]


def test_atlas_registry_normalizes_is_error_without_throwing():
    connector = AtlasReadConnector(lambda tool, args: {"isError": True, "content": [{"type": "text", "text": "failed"}]}, clock=lambda: NOW)
    executor = ToolExecutor(atlas_registry_entries(connector))
    result = executor.execute(
        ToolRequest("r-atlas", "s1", "t1", "atlas.project.status", "1", {"project": "Metis"}),
        AuthorizationContext(accounts={}),
        CancellationToken(),
    )
    assert result.status.value == "unavailable"
    assert result.error_code == ErrorCode.UNAVAILABLE.value
