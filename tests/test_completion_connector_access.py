from __future__ import annotations

from datetime import UTC, datetime

from metis_head.connectors.atlas import AtlasReadConnector, ProjectResolution
from metis_head.connectors.contracts import ErrorCode, Freshness, ResultStatus
from metis_head.connectors.google_access import (
    CALENDAR_SCOPE,
    CONTACTS_SCOPE,
    GMAIL_SCOPE,
    GoogleReadBroker,
    GoogleReadGrant,
)


NOW = datetime(2026, 9, 16, 12, tzinfo=UTC)


class GoogleFixture:
    def __init__(self):
        self.calls = []

    def list_calendars(self, **kwargs):
        self.calls.append(("list_calendars", kwargs))
        return {
            "items": [
                {"id": "visible", "summary": "Visible", "primary": True, "timeZone": "America/New_York"},
                {"id": "blocked", "summary": "Blocked"},
            ]
        }

    def list_events(self, **kwargs):
        self.calls.append(("list_events", kwargs))
        return {"items": []}

    def search_messages(self, **kwargs):
        self.calls.append(("search_messages", kwargs))
        return {"messages": [{"id": "m1", "threadId": "t1"}]}

    def get_message(self, **kwargs):
        self.calls.append(("get_message", kwargs))
        return {"id": kwargs["message_id"], "threadId": "t1", "payload": {"headers": []}}

    def get_thread(self, **kwargs):
        self.calls.append(("get_thread", kwargs))
        return {"messages": []}

    def search_contacts(self, **kwargs):
        self.calls.append(("search_contacts", kwargs))
        return {"people": []}


def test_google_broker_discovers_only_connected_accounts_and_granted_calendars():
    fixture = GoogleFixture()
    broker = GoogleReadBroker.from_connection_records(
        [
            {"provider": "google", "account_id": "work", "status": "connected", "scopes": [CALENDAR_SCOPE], "calendar_ids": ["visible"]},
            {"provider": "google", "account_id": "old", "status": "disconnected", "scopes": [CALENDAR_SCOPE]},
        ],
        {"work": fixture, "old": fixture},
        clock=lambda: NOW,
    )
    assert [item.account_id for item in broker.accounts()] == ["work"]
    result = broker.list_calendars(account_id="work")
    assert [item.calendar_id for item in result.data] == ["visible"]
    assert result.provenance.account_id == "work"


def test_google_broker_blocks_ungranted_scope_and_resource_before_transport():
    fixture = GoogleFixture()
    broker = GoogleReadBroker(
        {"work": fixture},
        {"work": GoogleReadGrant("work", frozenset({CALENDAR_SCOPE}), frozenset({"visible"}))},
        clock=lambda: NOW,
    )
    gmail = broker.gmail_search(account_id="work", query="invoice")
    blocked_calendar = broker.calendar_events(
        account_id="work", calendar_ids=["blocked"],
        start=datetime(2026, 9, 16, tzinfo=UTC), end=datetime(2026, 9, 17, tzinfo=UTC), timezone="UTC",
    )
    assert gmail.error.code is ErrorCode.PERMISSION_DENIED
    assert blocked_calendar.error.code is ErrorCode.PERMISSION_DENIED
    assert fixture.calls == []


def test_google_broker_keeps_gmail_search_message_thread_and_contacts_separate():
    fixture = GoogleFixture()
    scopes = frozenset({GMAIL_SCOPE, CONTACTS_SCOPE})
    broker = GoogleReadBroker({"personal": fixture}, {"personal": GoogleReadGrant("personal", scopes)}, clock=lambda: NOW)
    assert broker.gmail_search(account_id="personal", query="from:alex").status is ResultStatus.SUCCESS
    assert broker.gmail_message(account_id="personal", message_id="m1").status is ResultStatus.SUCCESS
    assert broker.gmail_thread(account_id="personal", thread_id="t1").status is ResultStatus.EMPTY
    assert broker.contact_email(account_id="personal", query="Alex").data.outcome.value == "not_found"
    assert [call[0] for call in fixture.calls] == ["search_messages", "get_message", "get_thread", "search_contacts"]


def test_atlas_resolves_stable_identity_then_reports_stale_sourced_status():
    calls = []

    def transport(tool_name, arguments):
        calls.append((tool_name, arguments))
        if tool_name == "list_projects":
            return {"structuredContent": {"projects": [{"id": "p-1", "name": "Metis Head", "aliases": ["metis"]}]}}
        return {
            "structuredContent": {
                "status": "active",
                "summary": "Fixture status",
                "observed_at": "2026-09-14T12:00:00Z",
                "source_url": "https://example.test/projects/p-1",
            }
        }

    result = AtlasReadConnector(transport, clock=lambda: NOW, stale_after_seconds=3600).project_status("metis")
    assert result.data.resolution is ProjectResolution.RESOLVED
    assert result.data.project.project_id == "p-1"
    assert result.data.freshness is Freshness.STALE
    assert result.provenance.source_links == ("https://example.test/projects/p-1",)
    assert calls == [("list_projects", {"limit": 100}), ("get_project_status", {"project_id": "p-1"})]


def test_atlas_does_not_guess_ambiguous_project_or_accept_is_error():
    def ambiguous(tool_name, arguments):
        return {"projects": [{"id": "1", "name": "One", "aliases": ["same"]}, {"id": "2", "name": "Two", "aliases": ["same"]}]}

    result = AtlasReadConnector(ambiguous, clock=lambda: NOW).project_status("same")
    assert result.data.resolution is ProjectResolution.AMBIGUOUS

    failed = AtlasReadConnector(lambda tool, args: {"isError": True, "content": [{"text": "failed"}]}, clock=lambda: NOW).project_status("Metis")
    assert failed.status is ResultStatus.UNAVAILABLE
    assert failed.data is None
