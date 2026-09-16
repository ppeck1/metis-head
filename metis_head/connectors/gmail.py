from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import quote

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


class GmailTransport(Protocol):
    def search_messages(self, *, account_id: str, query: str, page_token: str | None, page_size: int) -> Mapping[str, Any]: ...
    def get_message(self, *, account_id: str, message_id: str) -> Mapping[str, Any]: ...
    def get_thread(self, *, account_id: str, thread_id: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class GmailSearchHit:
    message_id: str
    thread_id: str
    account_id: str
    source_link: str


@dataclass(frozen=True, slots=True)
class GmailMessage:
    message_id: str
    thread_id: str
    account_id: str
    subject: str
    sender: str
    recipients: tuple[str, ...]
    sent_at: datetime | None
    snippet: str
    body_text: str
    source_link: str


class GmailConnector:
    def __init__(self, transports: Mapping[str, GmailTransport], *, clock: Clock = utc_now) -> None:
        self._transports = dict(transports)
        self._clock = clock

    def search(
        self,
        *,
        account_id: str,
        query: str,
        max_messages: int = 25,
        max_pages: int = 5,
    ) -> ConnectorResult[tuple[GmailSearchHit, ...]]:
        observed_at = self._clock()
        try:
            transport = select_transport(self._transports, account_id)
            if not isinstance(query, str) or not query.strip():
                raise ValueError("query is required")
            if not 1 <= max_messages <= 100:
                raise ValueError("max_messages must be between 1 and 100")
            if not 1 <= max_pages <= 20:
                raise ValueError("max_pages must be between 1 and 20")
        except ValueError as exc:
            return self._failure(account_id, observed_at, ErrorCode.INVALID_REQUEST, safe_message(exc))
        except LookupError:
            return self._failure(account_id, observed_at, ErrorCode.ACCOUNT_NOT_CONFIGURED, "account is not configured")

        hits: list[GmailSearchHit] = []
        seen: set[str] = set()
        token: str | None = None
        truncated = False
        try:
            for _ in range(max_pages):
                response = transport.search_messages(
                    account_id=account_id,
                    query=query.strip(),
                    page_token=token,
                    page_size=min(100, max_messages),
                )
                raw_messages = response.get("messages", ())
                if not isinstance(raw_messages, Sequence) or isinstance(raw_messages, (str, bytes)):
                    raise ValueError("gmail messages must be a list")
                for raw in raw_messages:
                    if not isinstance(raw, Mapping):
                        continue
                    message_id = _required_string(raw.get("id"), "message id")
                    if message_id in seen:
                        continue
                    thread_id = _required_string(raw.get("threadId") or message_id, "thread id")
                    seen.add(message_id)
                    hits.append(GmailSearchHit(message_id, thread_id, account_id, _gmail_link(account_id, thread_id)))
                    if len(hits) >= max_messages:
                        truncated = True
                        break
                token = _string_or_none(response.get("nextPageToken"))
                if truncated or not token:
                    break
            else:
                truncated = bool(token)
        except Exception as exc:
            return self._transport_failure(account_id, observed_at, exc)

        links = tuple(hit.source_link for hit in hits)
        return ConnectorResult(
            ResultStatus.SUCCESS if hits else ResultStatus.EMPTY,
            tuple(hits),
            Provenance("google", "gmail", account_id, source_links=links, observed_at=observed_at, freshness=Freshness.CURRENT),
            truncated=truncated,
            next_page_token=token if truncated else None,
        )

    def read_message(
        self, *, account_id: str, message_id: str, max_body_chars: int = 20_000
    ) -> ConnectorResult[GmailMessage]:
        observed_at = self._clock()
        try:
            transport = select_transport(self._transports, account_id)
            if not isinstance(message_id, str) or not message_id.strip():
                raise ValueError("message_id is required")
            if not 1 <= max_body_chars <= 100_000:
                raise ValueError("max_body_chars must be between 1 and 100000")
        except ValueError as exc:
            return self._failure(account_id, observed_at, ErrorCode.INVALID_REQUEST, safe_message(exc))
        except LookupError:
            return self._failure(account_id, observed_at, ErrorCode.ACCOUNT_NOT_CONFIGURED, "account is not configured")
        try:
            raw = transport.get_message(account_id=account_id, message_id=message_id)
            message, was_truncated = _normalize_message(raw, account_id, max_body_chars)
        except Exception as exc:
            return self._transport_failure(account_id, observed_at, exc)
        return ConnectorResult(
            ResultStatus.SUCCESS,
            message,
            Provenance(
                "google", "gmail", account_id, resource_ids=(message.message_id,),
                source_links=(message.source_link,), observed_at=observed_at, freshness=Freshness.CURRENT,
            ),
            truncated=was_truncated,
        )

    def read_thread(
        self, *, account_id: str, thread_id: str, max_messages: int = 20, max_body_chars: int = 20_000
    ) -> ConnectorResult[tuple[GmailMessage, ...]]:
        observed_at = self._clock()
        try:
            transport = select_transport(self._transports, account_id)
            if not isinstance(thread_id, str) or not thread_id.strip():
                raise ValueError("thread_id is required")
            if not 1 <= max_messages <= 100 or not 1 <= max_body_chars <= 100_000:
                raise ValueError("thread bounds are invalid")
        except ValueError as exc:
            return self._failure(account_id, observed_at, ErrorCode.INVALID_REQUEST, safe_message(exc))
        except LookupError:
            return self._failure(account_id, observed_at, ErrorCode.ACCOUNT_NOT_CONFIGURED, "account is not configured")
        try:
            raw = transport.get_thread(account_id=account_id, thread_id=thread_id)
            raw_messages = raw.get("messages", ())
            if not isinstance(raw_messages, Sequence) or isinstance(raw_messages, (str, bytes)):
                raise ValueError("gmail thread messages must be a list")
            truncated = len(raw_messages) > max_messages
            messages: list[GmailMessage] = []
            for item in raw_messages[:max_messages]:
                if not isinstance(item, Mapping):
                    continue
                message, body_truncated = _normalize_message(item, account_id, max_body_chars)
                messages.append(message)
                truncated = truncated or body_truncated
        except Exception as exc:
            return self._transport_failure(account_id, observed_at, exc)
        link = _gmail_link(account_id, thread_id)
        return ConnectorResult(
            ResultStatus.SUCCESS if messages else ResultStatus.EMPTY,
            tuple(messages),
            Provenance("google", "gmail", account_id, resource_ids=(thread_id,), source_links=(link,), observed_at=observed_at, freshness=Freshness.CURRENT),
            truncated=truncated,
        )

    @staticmethod
    def _failure(account_id: str, observed_at: datetime, code: ErrorCode, message: str):
        return failed_result(provider="google", service="gmail", account_id=account_id, observed_at=observed_at, error=ConnectorError(code, message))

    @staticmethod
    def _transport_failure(account_id: str, observed_at: datetime, exc: Exception):
        error = ConnectorError(ErrorCode.MALFORMED_RESPONSE, "gmail response was malformed") if isinstance(exc, (ValueError, TypeError, KeyError)) else error_from_exception(exc)
        return failed_result(provider="google", service="gmail", account_id=account_id, observed_at=observed_at, error=error)


def _normalize_message(raw: Mapping[str, Any], account_id: str, max_body_chars: int) -> tuple[GmailMessage, bool]:
    message_id = _required_string(raw.get("id"), "message id")
    thread_id = _required_string(raw.get("threadId") or message_id, "thread id")
    headers = _headers(raw.get("payload"))
    body = _extract_body(raw.get("payload"))
    was_truncated = len(body) > max_body_chars
    body = body[:max_body_chars]
    return GmailMessage(
        message_id=message_id,
        thread_id=thread_id,
        account_id=account_id,
        subject=headers.get("subject", "(no subject)"),
        sender=headers.get("from", ""),
        recipients=tuple(item.strip() for item in headers.get("to", "").split(",") if item.strip()),
        sent_at=_sent_at(raw, headers),
        snippet=str(raw.get("snippet") or "")[:500],
        body_text=body,
        source_link=_gmail_link(account_id, thread_id),
    ), was_truncated


def _headers(payload: object) -> dict[str, str]:
    if not isinstance(payload, Mapping):
        return {}
    raw_headers = payload.get("headers", ())
    if not isinstance(raw_headers, Sequence) or isinstance(raw_headers, (str, bytes)):
        return {}
    result: dict[str, str] = {}
    for item in raw_headers:
        if isinstance(item, Mapping) and isinstance(item.get("name"), str):
            result[item["name"].casefold()] = str(item.get("value") or "")
    return result


def _extract_body(payload: object) -> str:
    if not isinstance(payload, Mapping):
        return ""
    plain: list[str] = []
    html: list[str] = []

    def visit(part: Mapping[str, Any]) -> None:
        mime = str(part.get("mimeType") or "").casefold()
        body = part.get("body")
        data = body.get("data") if isinstance(body, Mapping) else None
        if isinstance(data, str):
            decoded = _decode_base64url(data)
            if mime == "text/plain":
                plain.append(decoded)
            elif mime == "text/html":
                html.append(decoded)
        parts = part.get("parts", ())
        if isinstance(parts, Sequence) and not isinstance(parts, (str, bytes)):
            for child in parts:
                if isinstance(child, Mapping):
                    visit(child)

    visit(payload)
    if plain:
        return "\n".join(plain).strip()
    if html:
        parser = _TextExtractor()
        parser.feed("\n".join(html))
        return parser.text.strip()
    return ""


def _decode_base64url(value: str) -> str:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    @property
    def text(self) -> str:
        return " ".join(part.strip() for part in self._parts if part.strip())


def _sent_at(raw: Mapping[str, Any], headers: Mapping[str, str]) -> datetime | None:
    internal = raw.get("internalDate")
    if internal is not None:
        try:
            return datetime.fromtimestamp(int(str(internal)) / 1000, tz=UTC)
        except (ValueError, OverflowError):
            pass
    return None


def _gmail_link(account_id: str, thread_id: str) -> str:
    return f"https://mail.google.com/mail/u/{quote(account_id, safe='')}/#all/{quote(thread_id, safe='')}"


def _required_string(raw: object, label: str) -> str:
    value = _string_or_none(raw)
    if not value:
        raise ValueError(f"{label} is required")
    return value


def _string_or_none(raw: object) -> str | None:
    return raw if isinstance(raw, str) and raw else None
