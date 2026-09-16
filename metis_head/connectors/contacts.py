from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence

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
    safe_message,
    select_transport,
    utc_now,
)


class ContactsTransport(Protocol):
    def search_contacts(self, *, account_id: str, query: str, page_token: str | None, page_size: int) -> Mapping[str, Any]: ...


class ContactResolution(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class Contact:
    resource_name: str
    account_id: str
    display_name: str
    email_addresses: tuple[str, ...]
    source_link: str | None


@dataclass(frozen=True, slots=True)
class ContactLookup:
    outcome: ContactResolution
    query: str
    contacts: tuple[Contact, ...]

    @property
    def email_address(self) -> str | None:
        if self.outcome is ContactResolution.RESOLVED and len(self.contacts) == 1 and len(self.contacts[0].email_addresses) == 1:
            return self.contacts[0].email_addresses[0]
        return None


class ContactsConnector:
    def __init__(self, transports: Mapping[str, ContactsTransport], *, clock: Clock = utc_now) -> None:
        self._transports = dict(transports)
        self._clock = clock

    def lookup_email(
        self,
        *,
        account_id: str,
        query: str,
        max_contacts: int = 20,
        max_pages: int = 5,
    ) -> ConnectorResult[ContactLookup]:
        observed_at = self._clock()
        try:
            transport = select_transport(self._transports, account_id)
            if not isinstance(query, str) or not query.strip():
                raise ValueError("query is required")
            if not 1 <= max_contacts <= 100 or not 1 <= max_pages <= 20:
                raise ValueError("contact bounds are invalid")
        except ValueError as exc:
            return self._failure(account_id, observed_at, ErrorCode.INVALID_REQUEST, safe_message(exc))
        except LookupError:
            return self._failure(account_id, observed_at, ErrorCode.ACCOUNT_NOT_CONFIGURED, "account is not configured")

        contacts: list[Contact] = []
        seen: set[str] = set()
        token: str | None = None
        truncated = False
        try:
            for _ in range(max_pages):
                response = transport.search_contacts(
                    account_id=account_id,
                    query=query.strip(),
                    page_token=token,
                    page_size=min(100, max_contacts),
                )
                raw_people = response.get("people", response.get("connections", ()))
                if not isinstance(raw_people, Sequence) or isinstance(raw_people, (str, bytes)):
                    raise ValueError("contacts response people must be a list")
                for raw in raw_people:
                    if not isinstance(raw, Mapping):
                        continue
                    contact = _normalize_contact(raw, account_id)
                    if contact.resource_name in seen or not contact.email_addresses:
                        continue
                    seen.add(contact.resource_name)
                    contacts.append(contact)
                    if len(contacts) >= max_contacts:
                        truncated = True
                        break
                token = _string_or_none(response.get("nextPageToken"))
                if truncated or not token:
                    break
            else:
                truncated = bool(token)
        except Exception as exc:
            error = ConnectorError(ErrorCode.MALFORMED_RESPONSE, "contacts response was malformed") if isinstance(exc, (ValueError, TypeError, KeyError)) else error_from_exception(exc)
            return failed_result(provider="google", service="contacts", account_id=account_id, observed_at=observed_at, error=error)  # type: ignore[return-value]

        exact = tuple(contact for contact in contacts if _matches_exact(contact, query))
        candidates = exact or tuple(contacts)
        if not candidates:
            outcome = ContactResolution.NOT_FOUND
        elif len(candidates) == 1 and len(candidates[0].email_addresses) == 1:
            outcome = ContactResolution.RESOLVED
        else:
            outcome = ContactResolution.AMBIGUOUS
        lookup = ContactLookup(outcome, query.strip(), candidates)
        links = tuple(item.source_link for item in candidates if item.source_link)
        return ConnectorResult(
            ResultStatus.EMPTY if outcome is ContactResolution.NOT_FOUND else ResultStatus.SUCCESS,
            lookup,
            Provenance("google", "contacts", account_id, resource_ids=tuple(item.resource_name for item in candidates), source_links=links, observed_at=observed_at, freshness=Freshness.CURRENT),
            truncated=truncated,
            next_page_token=token if truncated else None,
        )

    @staticmethod
    def _failure(account_id: str, observed_at: datetime, code: ErrorCode, message: str):
        return failed_result(provider="google", service="contacts", account_id=account_id, observed_at=observed_at, error=ConnectorError(code, message))


def _normalize_contact(raw: Mapping[str, Any], account_id: str) -> Contact:
    resource_name = _string_or_none(raw.get("resourceName"))
    if not resource_name:
        raise ValueError("contact resourceName is required")
    names = raw.get("names", ())
    display_name = ""
    if isinstance(names, Sequence) and not isinstance(names, (str, bytes)):
        for name in names:
            if isinstance(name, Mapping) and name.get("displayName"):
                display_name = str(name["displayName"])
                break
    emails: list[str] = []
    raw_emails = raw.get("emailAddresses", ())
    if isinstance(raw_emails, Sequence) and not isinstance(raw_emails, (str, bytes)):
        for email in raw_emails:
            value = email.get("value") if isinstance(email, Mapping) else None
            if isinstance(value, str) and value.strip() and value.casefold() not in {item.casefold() for item in emails}:
                emails.append(value.strip())
    return Contact(
        resource_name=resource_name,
        account_id=account_id,
        display_name=display_name or "(unnamed contact)",
        email_addresses=tuple(emails),
        source_link=_string_or_none(raw.get("profileLink") or raw.get("url")),
    )


def _matches_exact(contact: Contact, query: str) -> bool:
    needle = query.strip().casefold()
    return contact.display_name.casefold() == needle or any(address.casefold() == needle for address in contact.email_addresses)


def _string_or_none(raw: object) -> str | None:
    return raw if isinstance(raw, str) and raw else None
