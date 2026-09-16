from __future__ import annotations

from metis_head.google_oauth import CALENDAR_READ_SCOPE, _connected_account_id, _granted_scopes


class _Credentials:
    granted_scopes = (CALENDAR_READ_SCOPE,)
    scopes = ("requested-but-not-granted",)
    id_token = None


class _Call:
    def execute(self):
        return {"id": "calendar-only@example.test"}


class _CalendarService:
    def calendars(self):
        return self

    def get(self, **kwargs):
        assert kwargs == {"calendarId": "primary"}
        return _Call()


def test_calendar_only_grant_resolves_identity_without_gmail() -> None:
    calls: list[tuple[str, str]] = []

    def build(api, version, **kwargs):
        calls.append((api, version))
        return _CalendarService()

    credentials = _Credentials()
    scopes = _granted_scopes(credentials)
    assert scopes == (CALENDAR_READ_SCOPE,)
    assert _connected_account_id(credentials, build, scopes) == "calendar-only@example.test"
    assert calls == [("calendar", "v3")]
