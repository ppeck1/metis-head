from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Mapping

from metis_head.credentials import CredentialStore, SecretStoreUnavailable

from .contracts import ConnectorTransportError, ErrorCode


GOOGLE_READ_SCOPES = (
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/contacts.readonly",
)


class GoogleApiTransport:
    """Lazy official-client transport for one explicitly connected account."""

    def __init__(
        self,
        account_id: str,
        credential_store: CredentialStore,
        *,
        credentials_loader: Callable[[Mapping[str, Any]], Any] | None = None,
        service_builder: Callable[..., Any] | None = None,
        request_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.account_id = account_id
        self._store = credential_store
        self._services: dict[str, Any] = {}
        self._credentials_loader = credentials_loader
        self._service_builder = service_builder
        self._request_factory = request_factory

    def list_calendars(
        self, *, account_id: str, page_token: str | None, page_size: int
    ) -> Mapping[str, Any]:
        """Return one bounded CalendarList page through the official client surface."""
        self._assert_account(account_id)
        if not 1 <= page_size <= 250:
            raise ConnectorTransportError(ErrorCode.INVALID_REQUEST, "calendar page size must be between 1 and 250")
        if page_token is not None and (not isinstance(page_token, str) or len(page_token) > 2048):
            raise ConnectorTransportError(ErrorCode.INVALID_REQUEST, "calendar page token is invalid")
        call = self._service("calendar", "v3").calendarList().list(
            pageToken=page_token,
            maxResults=page_size,
            showDeleted=False,
            showHidden=False,
        )
        return self._execute(call)

    def granted_scopes(self) -> tuple[str, ...]:
        """Restore the token's actual grants, refreshing and persisting when needed."""
        return _actual_scopes(self._credentials())

    def list_events(self, *, account_id: str, calendar_id: str, time_min: datetime, time_max: datetime, page_token: str | None, page_size: int, single_events: bool, show_deleted: bool) -> Mapping[str, Any]:
        self._assert_account(account_id)
        call = self._service("calendar", "v3").events().list(
            calendarId=calendar_id,
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            pageToken=page_token,
            maxResults=page_size,
            singleEvents=single_events,
            showDeleted=show_deleted,
            orderBy="startTime" if single_events else None,
        )
        return self._execute(call)

    def search_messages(self, *, account_id: str, query: str, page_token: str | None, page_size: int) -> Mapping[str, Any]:
        self._assert_account(account_id)
        return self._execute(self._service("gmail", "v1").users().messages().list(userId="me", q=query, pageToken=page_token, maxResults=page_size))

    def get_message(self, *, account_id: str, message_id: str) -> Mapping[str, Any]:
        self._assert_account(account_id)
        return self._execute(self._service("gmail", "v1").users().messages().get(userId="me", id=message_id, format="full"))

    def get_thread(self, *, account_id: str, thread_id: str) -> Mapping[str, Any]:
        self._assert_account(account_id)
        return self._execute(self._service("gmail", "v1").users().threads().get(userId="me", id=thread_id, format="full"))

    def search_contacts(self, *, account_id: str, query: str, page_token: str | None, page_size: int) -> Mapping[str, Any]:
        self._assert_account(account_id)
        response = self._execute(
            self._service("people", "v1").people().searchContacts(
                query=query,
                readMask="names,emailAddresses",
                pageSize=page_size,
            )
        )
        # People searchContacts returns [{person: ...}] rather than the
        # connections-list shape used by the provider-neutral connector.
        results = response.get("results", ())
        people = [item["person"] for item in results if isinstance(item, Mapping) and isinstance(item.get("person"), Mapping)]
        return {"people": people}

    def _assert_account(self, account_id: str) -> None:
        if account_id != self.account_id:
            raise ConnectorTransportError(ErrorCode.PERMISSION_DENIED, "selected account does not match connector account")

    def _service(self, api: str, version: str) -> Any:
        key = f"{api}:{version}"
        if key in self._services:
            return self._services[key]
        credentials = self._credentials()
        builder = self._service_builder
        if builder is None:
            try:
                from googleapiclient.discovery import build
            except ImportError as exc:
                raise ConnectorTransportError(ErrorCode.UNAVAILABLE, "Google client dependencies are not installed") from exc
            builder = build
        try:
            service = builder(api, version, credentials=credentials, cache_discovery=False)
        except Exception as exc:
            raise ConnectorTransportError(ErrorCode.UNAVAILABLE, "Google client could not be initialized") from exc
        self._services[key] = service
        return service

    def _credentials(self) -> Any:
        try:
            raw = self._store.secret(f"google:{self.account_id}")
        except SecretStoreUnavailable as exc:
            raise ConnectorTransportError(
                ErrorCode.UNAVAILABLE, "OS credential store is unavailable", retryable=True
            ) from exc
        if not raw:
            raise ConnectorTransportError(ErrorCode.AUTH_EXPIRED, "Google connection is missing or disconnected")
        try:
            info = json.loads(raw)
            if not isinstance(info, Mapping):
                raise ValueError
            loader = self._credentials_loader
            if loader is None:
                from google.oauth2.credentials import Credentials

                # Restored token scopes are authoritative; do not replace them
                # with the application's requested superset.
                loader = Credentials.from_authorized_user_info
            credentials = loader(info)
            if bool(getattr(credentials, "expired", False)):
                if not getattr(credentials, "refresh_token", None):
                    raise ConnectorTransportError(
                        ErrorCode.AUTH_EXPIRED, "Google authorization expired; reconnect the account"
                    )
                request_factory = self._request_factory
                if request_factory is None:
                    from google.auth.transport.requests import Request

                    request_factory = Request
                credentials.refresh(request_factory())
                scopes = _actual_scopes(credentials)
                self._store.connect("google", self.account_id, list(scopes), credentials.to_json())
            return credentials
        except ConnectorTransportError:
            raise
        except Exception as exc:
            if _is_refresh_error(exc):
                raise ConnectorTransportError(
                    ErrorCode.AUTH_EXPIRED, "Google authorization was revoked or expired; reconnect the account"
                ) from exc
            raise ConnectorTransportError(ErrorCode.AUTH_EXPIRED, "Google credentials could not be loaded") from exc

    @staticmethod
    def _execute(call: Any) -> Mapping[str, Any]:
        try:
            response = call.execute()
        except Exception as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status in {401} or _is_refresh_error(exc):
                raise ConnectorTransportError(ErrorCode.AUTH_EXPIRED, "Google authorization expired; reconnect the account") from exc
            if status in {403}:
                raise ConnectorTransportError(ErrorCode.PERMISSION_DENIED, "Google denied the requested read scope") from exc
            if status in {429}:
                raise ConnectorTransportError(ErrorCode.RATE_LIMITED, "Google rate limit reached", retryable=True) from exc
            if status and int(status) >= 500:
                raise ConnectorTransportError(ErrorCode.UNAVAILABLE, "Google service is temporarily unavailable", retryable=True) from exc
            raise ConnectorTransportError(ErrorCode.UNAVAILABLE, "Google request failed", retryable=True) from exc
        return response if isinstance(response, Mapping) else {}


def _actual_scopes(credentials: Any) -> tuple[str, ...]:
    scopes = getattr(credentials, "granted_scopes", None) or getattr(credentials, "scopes", None) or ()
    return tuple(sorted({str(scope) for scope in scopes if isinstance(scope, str) and scope}))


def _is_refresh_error(exc: Exception) -> bool:
    return type(exc).__name__ == "RefreshError" and type(exc).__module__.startswith("google.auth")


def transports_from_connections(store: CredentialStore) -> dict[str, GoogleApiTransport]:
    transports: dict[str, GoogleApiTransport] = {}
    for item in store.list_connections():
        if item.get("provider") == "google" and item.get("status") == "connected":
            account_id = str(item["account_id"])
            transports[account_id] = GoogleApiTransport(account_id, store)
    return transports
