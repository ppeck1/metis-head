from __future__ import annotations

import base64
from datetime import UTC, datetime

from metis_head.connectors import (
    CalendarConnector,
    ContactResolution,
    ContactsConnector,
    ConnectorTransportError,
    ErrorCode,
    Freshness,
    GmailConnector,
    ResultStatus,
)
from metis_head.connectors.google_api import GoogleApiTransport


NOW = datetime(2026, 9, 16, 12, tzinfo=UTC)


class CalendarFixture:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def list_events(self, **kwargs):
        self.calls.append(kwargs)
        return self.pages[kwargs["calendar_id"]][kwargs["page_token"]]


def test_calendar_handles_dst_all_day_cancelled_pagination_and_deduplication():
    duplicate = {
        "id": "instance-1",
        "iCalUID": "series@example",
        "recurringEventId": "series-1",
        "originalStartTime": {"dateTime": "2026-11-01T01:30:00-04:00"},
        "summary": "First 1:30",
        "start": {"dateTime": "2026-11-01T01:30:00-04:00"},
        "end": {"dateTime": "2026-11-01T01:45:00-04:00"},
        "htmlLink": "https://calendar.google.com/event?eid=one",
    }
    transport = CalendarFixture(
        {
            "work": {
                None: {"items": [duplicate], "nextPageToken": "p2"},
                "p2": {
                    "items": [
                        duplicate,
                        {
                            "id": "all-day",
                            "summary": "Conference",
                            "start": {"date": "2026-11-02"},
                            "end": {"date": "2026-11-03"},
                        },
                        {"id": "gone", "summary": "Removed", "status": "cancelled"},
                    ]
                },
            }
        }
    )
    connector = CalendarConnector({"personal@example.com": transport}, clock=lambda: NOW)

    result = connector.list_events(
        account_id="personal@example.com",
        calendar_ids=["work"],
        start=datetime(2026, 11, 1, tzinfo=UTC),
        end=datetime(2026, 11, 4, tzinfo=UTC),
        timezone="America/New_York",
    )

    assert result.status is ResultStatus.SUCCESS
    assert len(result.data) == 3
    assert result.data[0].start.utcoffset().total_seconds() == -4 * 3600
    assert result.data[1].all_day is True
    assert result.data[2].cancelled is True
    assert result.provenance.account_id == "personal@example.com"
    assert result.provenance.observed_at == NOW
    assert result.provenance.freshness is Freshness.CURRENT
    assert [call["page_token"] for call in transport.calls] == [None, "p2"]
    assert all(call["single_events"] and call["show_deleted"] for call in transport.calls)


def test_calendar_never_falls_back_to_another_account():
    connector = CalendarConnector({"a": CalendarFixture({})}, clock=lambda: NOW)
    result = connector.list_events(
        account_id="b",
        calendar_ids=["primary"],
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        timezone="UTC",
    )
    assert result.status is ResultStatus.UNAVAILABLE
    assert result.error.code is ErrorCode.ACCOUNT_NOT_CONFIGURED


class GmailFixture:
    def __init__(self):
        self.search_calls = []

    def search_messages(self, **kwargs):
        self.search_calls.append(kwargs)
        if kwargs["page_token"] is None:
            return {"messages": [{"id": "m1", "threadId": "t1"}], "nextPageToken": "p2"}
        return {"messages": [{"id": "m1", "threadId": "t1"}, {"id": "m2", "threadId": "t2"}]}

    def get_message(self, **kwargs):
        encoded = base64.urlsafe_b64encode(b"Fixture body that is longer than ten characters").decode().rstrip("=")
        return {
            "id": kwargs["message_id"],
            "threadId": "t1",
            "internalDate": "1789550400000",
            "snippet": "Fixture",
            "payload": {
                "mimeType": "multipart/alternative",
                "headers": [
                    {"name": "Subject", "value": "Status"},
                    {"name": "From", "value": "A <a@example.com>"},
                    {"name": "To", "value": "b@example.com, c@example.com"},
                ],
                "parts": [{"mimeType": "text/plain", "body": {"data": encoded}}],
            },
        }

    def get_thread(self, **kwargs):
        return {"messages": [self.get_message(account_id=kwargs["account_id"], message_id="m1")]}


def test_gmail_search_and_read_are_bounded_and_sourced():
    transport = GmailFixture()
    connector = GmailConnector({"mail@example.com": transport}, clock=lambda: NOW)
    search = connector.search(account_id="mail@example.com", query="from:a", max_messages=2)
    assert [hit.message_id for hit in search.data] == ["m1", "m2"]
    assert search.truncated is True
    assert search.provenance.source_links[0].startswith("https://mail.google.com/")
    message = connector.read_message(account_id="mail@example.com", message_id="m1", max_body_chars=10)
    assert message.data.subject == "Status"
    assert message.data.body_text == "Fixture bo"
    assert message.data.recipients == ("b@example.com", "c@example.com")
    assert message.truncated is True


def test_safe_transport_error_does_not_return_a_token():
    class Failed(GmailFixture):
        def search_messages(self, **kwargs):
            raise ConnectorTransportError(
                ErrorCode.AUTH_EXPIRED,
                "refresh_token=very-secret-value expired",
            )

    result = GmailConnector({"mail": Failed()}, clock=lambda: NOW).search(account_id="mail", query="hello")
    assert result.status is ResultStatus.UNAVAILABLE
    assert result.error.code is ErrorCode.AUTH_EXPIRED
    assert "very-secret-value" not in result.error.message
    assert "[redacted]" in result.error.message


class ContactsFixture:
    def search_contacts(self, **kwargs):
        return {
            "people": [
                {
                    "resourceName": "people/1",
                    "names": [{"displayName": "Alex Doe"}],
                    "emailAddresses": [{"value": "alex.work@example.com"}],
                    "profileLink": "https://contacts.google.com/person/1",
                },
                {
                    "resourceName": "people/2",
                    "names": [{"displayName": "Alex Doe"}],
                    "emailAddresses": [{"value": "alex.home@example.com"}],
                },
            ]
        }


def test_contact_lookup_reports_ambiguity_instead_of_guessing():
    result = ContactsConnector({"contacts": ContactsFixture()}, clock=lambda: NOW).lookup_email(
        account_id="contacts", query="Alex Doe"
    )
    assert result.status is ResultStatus.SUCCESS
    assert result.data.outcome is ContactResolution.AMBIGUOUS
    assert result.data.email_address is None
    assert len(result.data.contacts) == 2


def test_contact_lookup_resolves_only_a_single_contact_and_email():
    class OneContact(ContactsFixture):
        def search_contacts(self, **kwargs):
            response = super().search_contacts(**kwargs)
            response["people"] = response["people"][:1]
            return response

    result = ContactsConnector({"contacts": OneContact()}, clock=lambda: NOW).lookup_email(
        account_id="contacts", query="Alex Doe"
    )
    assert result.data.outcome is ContactResolution.RESOLVED
    assert result.data.email_address == "alex.work@example.com"


def test_google_people_transport_normalizes_search_results_without_claiming_pagination(monkeypatch):
    captured = {}

    class Call:
        def execute(self):
            return {"results": [{"person": {"resourceName": "people/1", "names": [{"displayName": "Alex"}]}}]}

    class People:
        def people(self):
            return self

        def searchContacts(self, **kwargs):
            captured.update(kwargs)
            return Call()

    transport = GoogleApiTransport("paul@example.test", object())
    monkeypatch.setattr(transport, "_service", lambda api, version: People())
    result = transport.search_contacts(
        account_id="paul@example.test", query="Alex", page_token="ignored", page_size=20
    )
    assert result["people"][0]["resourceName"] == "people/1"
    assert "pageToken" not in captured
