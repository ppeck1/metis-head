from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Mapping, Protocol, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .contracts import (
    Clock,
    ConnectorError,
    ConnectorResult,
    ErrorCode,
    Freshness,
    Provenance,
    ResultStatus,
    error_from_exception,
    failed_result,
    require_aware,
    safe_message,
    select_transport,
    utc_now,
)


class CalendarTransport(Protocol):
    def list_events(
        self,
        *,
        account_id: str,
        calendar_id: str,
        time_min: datetime,
        time_max: datetime,
        page_token: str | None,
        page_size: int,
        single_events: bool,
        show_deleted: bool,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    event_id: str
    calendar_id: str
    account_id: str
    title: str
    start: datetime | date | None
    end: datetime | date | None
    all_day: bool
    status: str
    cancelled: bool
    recurring_event_id: str | None
    original_start: datetime | date | None
    source_link: str | None
    updated_at: datetime | None


class CalendarConnector:
    def __init__(self, transports: Mapping[str, CalendarTransport], *, clock: Clock = utc_now) -> None:
        self._transports = dict(transports)
        self._clock = clock

    def list_events(
        self,
        *,
        account_id: str,
        calendar_ids: Sequence[str],
        start: datetime,
        end: datetime,
        timezone: str,
        max_events: int = 100,
        max_pages_per_calendar: int = 10,
    ) -> ConnectorResult[tuple[CalendarEvent, ...]]:
        observed_at = self._clock()
        try:
            transport = select_transport(self._transports, account_id)
            zone = ZoneInfo(timezone)
            require_aware(start, "start")
            require_aware(end, "end")
            if end <= start:
                raise ValueError("end must be after start")
            calendars = tuple(dict.fromkeys(item for item in calendar_ids if isinstance(item, str) and item.strip()))
            if not calendars:
                raise ValueError("at least one calendar_id is required")
            if not 1 <= max_events <= 500:
                raise ValueError("max_events must be between 1 and 500")
            if not 1 <= max_pages_per_calendar <= 50:
                raise ValueError("max_pages_per_calendar must be between 1 and 50")
        except (ValueError, ZoneInfoNotFoundError) as exc:
            return self._failure(account_id, observed_at, ErrorCode.INVALID_REQUEST, safe_message(exc))
        except LookupError:
            return self._failure(account_id, observed_at, ErrorCode.ACCOUNT_NOT_CONFIGURED, "account is not configured")

        events: list[CalendarEvent] = []
        seen: set[tuple[str, str, str]] = set()
        links: list[str] = []
        truncated = False
        continuation: str | None = None
        try:
            for calendar_id in calendars:
                token: str | None = None
                for _ in range(max_pages_per_calendar):
                    response = transport.list_events(
                        account_id=account_id,
                        calendar_id=calendar_id,
                        time_min=start,
                        time_max=end,
                        page_token=token,
                        page_size=min(250, max_events),
                        single_events=True,
                        show_deleted=True,
                    )
                    raw_items = response.get("items", ())
                    if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
                        raise ValueError("calendar response items must be a list")
                    for raw in raw_items:
                        if not isinstance(raw, Mapping):
                            continue
                        event = _normalize_event(raw, account_id, calendar_id, zone)
                        key = _dedupe_key(event)
                        if key in seen:
                            continue
                        seen.add(key)
                        events.append(event)
                        if event.source_link and event.source_link not in links:
                            links.append(event.source_link)
                        if len(events) >= max_events:
                            continuation = _string_or_none(response.get("nextPageToken"))
                            truncated = True
                            break
                    if truncated:
                        break
                    token = _string_or_none(response.get("nextPageToken"))
                    if not token:
                        break
                else:
                    truncated = bool(token)
                    continuation = token
                if truncated:
                    break
        except Exception as exc:
            error = ConnectorError(ErrorCode.MALFORMED_RESPONSE, "calendar response was malformed") if isinstance(exc, (ValueError, TypeError)) else error_from_exception(exc)
            return failed_result(provider="google", service="calendar", account_id=account_id, observed_at=observed_at, error=error)  # type: ignore[return-value]

        events.sort(key=_sort_key)
        provenance = Provenance(
            provider="google",
            service="calendar",
            account_id=account_id,
            resource_ids=calendars,
            source_links=tuple(links),
            observed_at=observed_at,
            freshness=Freshness.CURRENT,
        )
        return ConnectorResult(
            status=ResultStatus.SUCCESS if events else ResultStatus.EMPTY,
            data=tuple(events),
            provenance=provenance,
            truncated=truncated,
            next_page_token=continuation,
        )

    @staticmethod
    def _failure(account_id: str, observed_at: datetime, code: ErrorCode, message: str) -> ConnectorResult[tuple[CalendarEvent, ...]]:
        return failed_result(
            provider="google", service="calendar", account_id=account_id, observed_at=observed_at,
            error=ConnectorError(code, message),
        )  # type: ignore[return-value]


def _normalize_event(raw: Mapping[str, Any], account_id: str, calendar_id: str, zone: ZoneInfo) -> CalendarEvent:
    event_id = _required_string(raw.get("id"), "event id")
    status = str(raw.get("status") or "confirmed")
    start, all_day = _parse_event_time(raw.get("start"), zone)
    end, end_all_day = _parse_event_time(raw.get("end"), zone)
    if all_day != end_all_day and start is not None and end is not None:
        raise ValueError("event start/end types differ")
    original_start, _ = _parse_event_time(raw.get("originalStartTime"), zone)
    return CalendarEvent(
        event_id=event_id,
        calendar_id=calendar_id,
        account_id=account_id,
        title=str(raw.get("summary") or "(untitled)"),
        start=start,
        end=end,
        all_day=all_day,
        status=status,
        cancelled=status.casefold() == "cancelled",
        recurring_event_id=_string_or_none(raw.get("recurringEventId")),
        original_start=original_start,
        source_link=_string_or_none(raw.get("htmlLink")),
        updated_at=_parse_datetime(raw.get("updated"), zone),
    )


def _parse_event_time(raw: object, fallback_zone: ZoneInfo) -> tuple[datetime | date | None, bool]:
    if raw is None:
        return None, False
    if not isinstance(raw, Mapping):
        raise ValueError("event time must be an object")
    if raw.get("date"):
        return date.fromisoformat(str(raw["date"])), True
    if raw.get("dateTime"):
        named_zone = raw.get("timeZone")
        zone = ZoneInfo(str(named_zone)) if named_zone else fallback_zone
        return _parse_datetime(raw["dateTime"], zone), False
    return None, False


def _parse_datetime(raw: object, fallback_zone: ZoneInfo) -> datetime | None:
    if not raw:
        return None
    value = str(raw)
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=fallback_zone)
    return parsed.astimezone(fallback_zone)


def _dedupe_key(event: CalendarEvent) -> tuple[str, str, str]:
    occurrence = event.original_start or event.start
    return event.calendar_id, event.recurring_event_id or event.event_id, occurrence.isoformat() if occurrence else event.event_id


def _sort_key(event: CalendarEvent) -> tuple[str, str]:
    value = event.start
    if isinstance(value, datetime):
        marker = value.isoformat()
    elif isinstance(value, date):
        marker = datetime.combine(value, time.min).isoformat()
    else:
        marker = "9999"
    return marker, event.title.casefold()


def _required_string(raw: object, label: str) -> str:
    value = _string_or_none(raw)
    if not value:
        raise ValueError(f"{label} is required")
    return value


def _string_or_none(raw: object) -> str | None:
    return raw if isinstance(raw, str) and raw else None
