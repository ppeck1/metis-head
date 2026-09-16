from datetime import UTC, datetime, timedelta

from metis_head.connectors import CalendarConnector, ContactsConnector, GmailConnector
from metis_head.personal_orchestration import CALENDAR_SCOPE, run_google_read


class CalendarFixture:
    def list_events(self, **kwargs):
        return {"items": [{"id": "event-1", "summary": "Dentist", "start": {"dateTime": "2026-09-17T10:00:00-04:00"}, "end": {"dateTime": "2026-09-17T11:00:00-04:00"}, "htmlLink": "https://calendar.google.com/event?eid=event-1"}]}


def test_real_result_round_trip_is_grounded_and_authorized():
    account = "paul@example.test"
    outcome = run_google_read(
        session_id="s1", turn_id="t1", tool_name="google.calendar.list",
        arguments={"calendar_ids": ["primary"], "start": "2026-09-17T00:00:00-04:00", "end": "2026-09-18T00:00:00-04:00", "timezone": "America/New_York"},
        account_id=account, granted_scopes=frozenset({CALENDAR_SCOPE}),
        calendar=CalendarConnector({account: CalendarFixture()}), gmail=GmailConnector({}), contacts=ContactsConnector({}),
    )
    assert outcome.stop_reason == "completed"
    assert len(outcome.exchanges) == 1
    assert outcome.exchanges[0].result.ok
    assert "Dentist" in outcome.text
    assert "google calendar" in outcome.text
