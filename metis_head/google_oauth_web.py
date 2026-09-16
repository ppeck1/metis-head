"""Bounded in-browser Google OAuth coordinator for the local setup wizard."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
import time
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlparse

from .connectors.google_api import GOOGLE_READ_SCOPES
from .google_oauth import _connected_account_id, _granted_scopes


@dataclass(slots=True)
class _Pending:
    flow: Any
    expires_at: float
    redirect_uri: str


class GoogleOAuthWebError(ValueError):
    pass


class GoogleOAuthWebManager:
    def __init__(self, *, ttl_seconds: int = 600, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._pending: dict[str, _Pending] = {}
        self._lock = RLock()

    def start(
        self,
        client_config: Mapping[str, Any],
        *,
        redirect_uri: str,
        flow_factory: Callable[[Mapping[str, Any], tuple[str, ...]], Any] | None = None,
    ) -> dict[str, str]:
        if not isinstance(client_config, Mapping) or not ({"installed", "web"} & set(client_config)):
            raise GoogleOAuthWebError("Google OAuth client JSON must contain an installed or web client")
        if flow_factory is None:
            try:
                from google_auth_oauthlib.flow import Flow
            except ImportError as exc:
                raise GoogleOAuthWebError("install the Google extra before connecting an account") from exc
            flow_factory = lambda config, scopes: Flow.from_client_config(config, scopes=scopes)
        flow = flow_factory(client_config, GOOGLE_READ_SCOPES)
        flow.redirect_uri = redirect_uri
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        if not state or not str(authorization_url).startswith("https://accounts.google.com/"):
            raise GoogleOAuthWebError("Google OAuth did not return a valid authorization request")
        with self._lock:
            self._discard_expired()
            self._pending[str(state)] = _Pending(flow, self._clock() + self._ttl, redirect_uri)
        return {"authorization_url": str(authorization_url), "state": str(state)}

    def complete(
        self,
        *,
        state: str,
        authorization_response: str,
        store: Any,
        build_factory: Callable[..., Any] | None = None,
    ) -> dict[str, Any]:
        requested_state = str(state or "")
        with self._lock:
            self._discard_expired()
            pending = self._pending.pop(requested_state, None)
        if pending is None:
            raise GoogleOAuthWebError("Google connection request expired or has already been used")
        callback = urlparse(authorization_response)
        expected = urlparse(pending.redirect_uri)
        if (
            callback.scheme != expected.scheme
            or callback.hostname != expected.hostname
            or callback.port != expected.port
            or callback.path != expected.path
            or callback.hostname not in {"127.0.0.1", "localhost", "::1"}
        ):
            raise GoogleOAuthWebError("Google connection callback did not match the loopback request")
        query = parse_qs(callback.query, keep_blank_values=True)
        returned_state = query.get("state", [""])[0]
        if returned_state != requested_state:
            raise GoogleOAuthWebError("Google connection callback state did not match")
        if query.get("error"):
            detail = query.get("error_description", query["error"])[0]
            raise GoogleOAuthWebError(f"Google connection was denied: {detail}")
        code = query.get("code", [""])[0]
        if not code:
            raise GoogleOAuthWebError("Google connection callback did not include an authorization code")
        try:
            # Supplying the code directly is the supported installed-app loopback
            # path. Passing an http:// authorization_response asks oauthlib to
            # treat the callback as a general web redirect and rejects it as an
            # insecure transport, even though Google permits loopback redirects.
            # Token exchange still goes to Google's HTTPS token endpoint.
            pending.flow.fetch_token(code=code)
        except Exception as exc:
            raise GoogleOAuthWebError("Google token exchange failed; retry the connection") from exc
        credentials = pending.flow.credentials
        scopes = _granted_scopes(credentials)
        if build_factory is None:
            try:
                from googleapiclient.discovery import build
            except ImportError as exc:
                raise GoogleOAuthWebError("install the Google extra before connecting an account") from exc
            build_factory = build
        account_id = _connected_account_id(credentials, build_factory, scopes)
        existing = {
            str(item.get("account_id"))
            for item in store.list_connections()
            if item.get("provider") == "google"
        }
        store.connect("google", account_id, list(scopes), credentials.to_json())
        return {
            "account_id": account_id,
            "scopes": list(scopes),
            "duplicate_identity": account_id in existing,
        }

    def _discard_expired(self) -> None:
        now = self._clock()
        self._pending = {key: value for key, value in self._pending.items() if value.expires_at > now}


__all__ = ["GoogleOAuthWebError", "GoogleOAuthWebManager"]
