from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Protocol, Sequence

from .calendar import CalendarConnector, CalendarEvent
from .contacts import ContactLookup, ContactsConnector
from .contracts import (
    ConnectorError,
    ConnectorResult,
    ConnectorTransportError,
    ErrorCode,
    Freshness,
    Provenance,
    ResultStatus,
    error_from_exception,
    utc_now,
)
from .gmail import GmailConnector, GmailMessage, GmailSearchHit
from .google_metadata import GoogleAccountPolicy


CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
CONTACTS_SCOPE = "https://www.googleapis.com/auth/contacts.readonly"


class GoogleDiscoveryTransport(Protocol):
    def list_calendars(
        self, *, account_id: str, page_token: str | None, page_size: int
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class GoogleReadGrant:
    account_id: str
    scopes: frozenset[str]
    calendar_ids: frozenset[str] | None = None

    def allows(self, scope: str, calendar_id: str | None = None) -> bool:
        if scope not in self.scopes:
            return False
        return calendar_id is None or self.calendar_ids is None or calendar_id in self.calendar_ids


@dataclass(frozen=True, slots=True)
class GoogleAccount:
    account_id: str
    scopes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GoogleRestoredAccount:
    account_id: str
    scopes: tuple[str, ...]
    status: str
    error_code: ErrorCode | None = None


@dataclass(frozen=True, slots=True)
class GoogleBrokerRestoration:
    broker: "GoogleReadBroker"
    accounts: tuple[GoogleRestoredAccount, ...]


@dataclass(frozen=True, slots=True)
class GoogleCalendar:
    calendar_id: str
    account_id: str
    name: str
    primary: bool
    selected: bool
    access_role: str
    timezone: str | None


class GoogleReadBroker:
    """Trusted selection boundary above the service-specific read adapters."""

    def __init__(
        self,
        transports: Mapping[str, Any],
        grants: Mapping[str, GoogleReadGrant],
        *,
        clock=utc_now,
    ) -> None:
        self._transports = dict(transports)
        self._grants = dict(grants)
        self._clock = clock
        self._calendar = CalendarConnector(self._transports, clock=clock)
        self._gmail = GmailConnector(self._transports, clock=clock)
        self._contacts = ContactsConnector(self._transports, clock=clock)
        self._selections: dict[str, tuple[str, ...]] = {}
        self._enforce_selections = False

    @classmethod
    def from_connection_records(
        cls, records: Sequence[Mapping[str, Any]], transports: Mapping[str, Any], *, clock=utc_now
    ) -> "GoogleReadBroker":
        grants: dict[str, GoogleReadGrant] = {}
        selections: dict[str, tuple[str, ...]] = {}
        for record in records:
            if record.get("provider") != "google" or record.get("status") != "connected":
                continue
            account_id = str(record.get("account_id") or "").strip()
            if not account_id or account_id not in transports:
                continue
            try:
                policy = GoogleAccountPolicy.from_record(record)
            except (TypeError, ValueError):
                continue
            grants[account_id] = GoogleReadGrant(account_id, policy.granted_scopes, policy.allowed_calendar_ids)
            selections[account_id] = policy.selected_calendar_ids
        broker = cls({key: transports[key] for key in grants}, grants, clock=clock)
        broker._selections = selections
        broker._enforce_selections = True
        return broker

    @classmethod
    def restore_from_credential_store(
        cls,
        store: Any,
        *,
        transport_factory: Callable[[str, Any], Any] | None = None,
        clock=utc_now,
    ) -> GoogleBrokerRestoration:
        """Restore actual token grants and report reconnect-required accounts."""
        if transport_factory is None:
            from .google_api import GoogleApiTransport

            transport_factory = GoogleApiTransport
        transports: dict[str, Any] = {}
        grants: dict[str, GoogleReadGrant] = {}
        selections: dict[str, tuple[str, ...]] = {}
        states: list[GoogleRestoredAccount] = []
        for record in store.list_connections():
            if record.get("provider") != "google" or record.get("status") != "connected":
                continue
            account_id = str(record.get("account_id") or "").strip()
            if not account_id:
                continue
            transport = transport_factory(account_id, store)
            try:
                scopes = tuple(transport.granted_scopes())
            except ConnectorTransportError as exc:
                status = "reconnect_required" if exc.code is ErrorCode.AUTH_EXPIRED else "unavailable"
                states.append(GoogleRestoredAccount(account_id, (), status, exc.code))
                continue
            allowed = record.get("allowed_calendar_ids", record.get("calendar_ids"))
            calendar_ids = (
                frozenset(str(item) for item in allowed if isinstance(item, str) and item)
                if isinstance(allowed, (list, tuple, set, frozenset))
                else None
            )
            transports[account_id] = transport
            grants[account_id] = GoogleReadGrant(account_id, frozenset(scopes), calendar_ids)
            selections[account_id] = tuple(
                str(item)
                for item in record.get("selected_calendar_ids", ())
                if isinstance(item, str) and item
            )
            states.append(GoogleRestoredAccount(account_id, scopes, "connected"))
        broker = cls(transports, grants, clock=clock)
        broker._selections = selections
        broker._enforce_selections = True
        return GoogleBrokerRestoration(broker, tuple(states))

    def accounts(self) -> tuple[GoogleAccount, ...]:
        return tuple(
            GoogleAccount(account_id, tuple(sorted(grant.scopes)))
            for account_id, grant in sorted(self._grants.items())
            if account_id in self._transports
        )

    def selected_calendar_ids(self, account_id: str) -> tuple[str, ...]:
        return self._selections.get(account_id, ())

    def restrict_to(
        self,
        account_ids: Sequence[str],
        calendars_by_account: Mapping[str, Sequence[str]],
    ) -> "GoogleReadBroker":
        """Return an enforcement clone limited to one conversation's exact grants."""
        allowed = frozenset(account_ids)
        broker = GoogleReadBroker(
            {key: value for key, value in self._transports.items() if key in allowed},
            {key: value for key, value in self._grants.items() if key in allowed},
            clock=self._clock,
        )
        broker._selections = {
            account_id: tuple(
                dict.fromkeys(str(item) for item in calendars_by_account.get(account_id, ()) if str(item))
            )
            for account_id in allowed
        }
        broker._enforce_selections = True
        return broker

    def restrict_to(
        self,
        account_ids: Sequence[str],
        calendars_by_account: Mapping[str, Sequence[str]],
    ) -> "GoogleReadBroker":
        """Return an enforcement clone limited to one conversation's exact grants."""
        allowed = frozenset(account_ids)
        broker = GoogleReadBroker(
            {key: value for key, value in self._transports.items() if key in allowed},
            {key: value for key, value in self._grants.items() if key in allowed},
            clock=self._clock,
        )
        broker._selections = {
            account_id: tuple(dict.fromkeys(str(item) for item in calendars_by_account.get(account_id, ()) if str(item)))
            for account_id in allowed
        }
        broker._enforce_selections = True
        return broker

    def list_calendars(
        self, *, account_id: str, max_calendars: int = 100, max_pages: int = 10
    ) -> ConnectorResult[tuple[GoogleCalendar, ...]]:
        observed_at = self._clock()
        denied = self._authorize(account_id, CALENDAR_SCOPE, observed_at, "calendar")
        if denied:
            return denied
        if not 1 <= max_calendars <= 250 or not 1 <= max_pages <= 50:
            return self._error(account_id, observed_at, "calendar", ErrorCode.INVALID_REQUEST, "calendar discovery bounds are invalid")
        transport = self._transports[account_id]
        token: str | None = None
        calendars: list[GoogleCalendar] = []
        seen: set[str] = set()
        truncated = False
        try:
            for _ in range(max_pages):
                response = transport.list_calendars(
                    account_id=account_id,
                    page_token=token,
                    page_size=min(250, max_calendars - len(calendars)),
                )
                items = response.get("items", ())
                if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
                    raise ValueError
                for raw in items:
                    if not isinstance(raw, Mapping) or not isinstance(raw.get("id"), str):
                        continue
                    calendar_id = raw["id"]
                    grant = self._grants[account_id]
                    if calendar_id in seen or not grant.allows(CALENDAR_SCOPE, calendar_id):
                        continue
                    seen.add(calendar_id)
                    calendars.append(
                        GoogleCalendar(
                            calendar_id=calendar_id,
                            account_id=account_id,
                            name=str(raw.get("summaryOverride") or raw.get("summary") or calendar_id),
                            primary=bool(raw.get("primary", False)),
                            selected=(calendar_id in self._selections.get(account_id, ()))
                            if self._enforce_selections
                            else bool(raw.get("selected", False)),
                            access_role=str(raw.get("accessRole") or "unknown"),
                            timezone=str(raw["timeZone"]) if raw.get("timeZone") else None,
                        )
                    )
                    if len(calendars) >= max_calendars:
                        truncated = True
                        break
                token = response.get("nextPageToken") if isinstance(response.get("nextPageToken"), str) else None
                if truncated or not token:
                    break
            else:
                truncated = bool(token)
        except Exception as exc:
            error = error_from_exception(exc)
            return ConnectorResult(
                ResultStatus.UNAVAILABLE if error.code is not ErrorCode.INVALID_REQUEST else ResultStatus.ERROR,
                None,
                Provenance("google", "calendar", account_id, observed_at=observed_at, freshness=Freshness.UNKNOWN),
                error=error,
            )
        return ConnectorResult(
            ResultStatus.SUCCESS if calendars else ResultStatus.EMPTY,
            tuple(calendars),
            Provenance("google", "calendar", account_id, resource_ids=tuple(item.calendar_id for item in calendars), observed_at=observed_at, freshness=Freshness.CURRENT),
            truncated=truncated,
            next_page_token=token if truncated else None,
        )

    def calendar_events(
        self,
        *,
        account_id: str,
        calendar_ids: Sequence[str],
        start: datetime,
        end: datetime,
        timezone: str,
        max_events: int = 100,
    ) -> ConnectorResult[tuple[CalendarEvent, ...]]:
        observed_at = self._clock()
        selected = frozenset(self._selections.get(account_id, ()))
        if self._enforce_selections and any(calendar_id not in selected for calendar_id in calendar_ids):
            return self._error(
                account_id,
                observed_at,
                "calendar",
                ErrorCode.PERMISSION_DENIED,
                "requested calendar is not selected for this account",
            )
        for calendar_id in calendar_ids:
            denied = self._authorize(account_id, CALENDAR_SCOPE, observed_at, "calendar", calendar_id)
            if denied:
                return denied
        return self._calendar.list_events(
            account_id=account_id, calendar_ids=calendar_ids, start=start, end=end,
            timezone=timezone, max_events=max_events,
        )

    def gmail_search(self, *, account_id: str, query: str, max_messages: int = 25) -> ConnectorResult[tuple[GmailSearchHit, ...]]:
        denied = self._authorize(account_id, GMAIL_SCOPE, self._clock(), "gmail")
        return denied or self._gmail.search(account_id=account_id, query=query, max_messages=max_messages)

    def gmail_message(self, *, account_id: str, message_id: str, max_body_chars: int = 20_000) -> ConnectorResult[GmailMessage]:
        denied = self._authorize(account_id, GMAIL_SCOPE, self._clock(), "gmail")
        return denied or self._gmail.read_message(account_id=account_id, message_id=message_id, max_body_chars=max_body_chars)

    def gmail_thread(self, *, account_id: str, thread_id: str, max_messages: int = 20) -> ConnectorResult[tuple[GmailMessage, ...]]:
        denied = self._authorize(account_id, GMAIL_SCOPE, self._clock(), "gmail")
        return denied or self._gmail.read_thread(account_id=account_id, thread_id=thread_id, max_messages=max_messages)

    def contact_email(self, *, account_id: str, query: str, max_contacts: int = 20) -> ConnectorResult[ContactLookup]:
        denied = self._authorize(account_id, CONTACTS_SCOPE, self._clock(), "contacts")
        return denied or self._contacts.lookup_email(account_id=account_id, query=query, max_contacts=max_contacts)

    def _authorize(self, account_id: str, scope: str, observed_at: datetime, service: str, resource_id: str | None = None):
        if account_id not in self._transports or account_id not in self._grants:
            return self._error(account_id, observed_at, service, ErrorCode.ACCOUNT_NOT_CONFIGURED, "account is not configured")
        grant = self._grants[account_id]
        if grant.account_id != account_id or not grant.allows(scope, resource_id):
            return self._error(account_id, observed_at, service, ErrorCode.PERMISSION_DENIED, "requested scope or resource is not granted")
        return None

    @staticmethod
    def _error(account_id: str, observed_at: datetime, service: str, code: ErrorCode, message: str):
        status = ResultStatus.UNAVAILABLE if code in {ErrorCode.ACCOUNT_NOT_CONFIGURED, ErrorCode.PERMISSION_DENIED, ErrorCode.UNAVAILABLE} else ResultStatus.ERROR
        return ConnectorResult(
            status, None, Provenance("google", service, account_id, observed_at=observed_at, freshness=Freshness.UNKNOWN),
            error=ConnectorError(code, message),
        )
