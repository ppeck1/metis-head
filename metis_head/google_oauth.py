from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .connectors.google_api import GOOGLE_READ_SCOPES
from .credentials import CredentialStore
from .runtime_paths import connections_path


GMAIL_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
CALENDAR_READ_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


def default_connections_path() -> Path:
    return connections_path()


def _granted_scopes(credentials: Any) -> tuple[str, ...]:
    scopes = getattr(credentials, "granted_scopes", None) or getattr(credentials, "scopes", None) or ()
    return tuple(sorted({str(scope) for scope in scopes if scope}))


def _connected_account_id(credentials: Any, build: Callable[..., Any], scopes: tuple[str, ...]) -> str:
    if GMAIL_READ_SCOPE in scopes:
        profile = build("gmail", "v1", credentials=credentials, cache_discovery=False).users().getProfile(userId="me").execute()
        account_id = str(profile.get("emailAddress") or "").strip()
        if account_id:
            return account_id
    if CALENDAR_READ_SCOPE in scopes:
        calendar = build("calendar", "v3", credentials=credentials, cache_discovery=False).calendars().get(calendarId="primary").execute()
        account_id = str(calendar.get("id") or "").strip()
        if account_id:
            return account_id
    id_token = getattr(credentials, "id_token", None)
    if isinstance(id_token, dict):
        account_id = str(id_token.get("email") or "").strip()
        if account_id:
            return account_id
    raise RuntimeError("Google did not return the connected account identity for the granted read scopes")


def connect_google_account(client_secrets: str | Path, metadata_path: str | Path) -> str:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("install the Google extra first: pip install -e '.[google]'") from exc
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), GOOGLE_READ_SCOPES)
    credentials = flow.run_local_server(port=0, authorization_prompt_message="Open this URL to connect Google read-only access: {url}")
    granted_scopes = _granted_scopes(credentials)
    account_id = _connected_account_id(credentials, build, granted_scopes)
    store = CredentialStore(metadata_path)
    store.connect("google", account_id, list(granted_scopes), credentials.to_json())
    return account_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect one Google account to Metis using read-only OAuth scopes.")
    parser.add_argument("--client-secrets", required=True)
    parser.add_argument("--metadata", default=str(default_connections_path()))
    args = parser.parse_args()
    account_id = connect_google_account(args.client_secrets, args.metadata)
    print(f"Connected Google account: {account_id}")


if __name__ == "__main__":
    main()
