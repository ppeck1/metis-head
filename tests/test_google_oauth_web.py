from __future__ import annotations

import pytest

from metis_head.google_oauth_web import GoogleOAuthWebError, GoogleOAuthWebManager


class Credentials:
    granted_scopes = ("https://www.googleapis.com/auth/gmail.readonly",)

    def to_json(self):
        return '{"refresh_token":"not-exported-by-public-contract"}'


class Flow:
    credentials = Credentials()
    redirect_uri = None

    def authorization_url(self, **kwargs):
        return "https://accounts.google.com/o/oauth2/auth?state=state-1", "state-1"

    def fetch_token(self, **kwargs):
        self.authorization_response = kwargs["authorization_response"]


class GmailBuild:
    def users(self): return self
    def getProfile(self, **kwargs): return self
    def execute(self): return {"emailAddress": "verified@example.test"}


class Store:
    def __init__(self, existing=()): self.existing = tuple(existing); self.saved = []
    def list_connections(self): return [{"provider": "google", "account_id": item} for item in self.existing]
    def connect(self, provider, account_id, scopes, secret): self.saved.append((provider, account_id, scopes, secret))


def test_web_oauth_binds_verified_identity_and_is_single_use():
    manager = GoogleOAuthWebManager()
    flow = Flow()
    started = manager.start(
        {"installed": {"client_id": "fixture"}},
        redirect_uri="http://127.0.0.1:8787/metis/connectors/google/oauth/callback",
        flow_factory=lambda config, scopes: flow,
    )
    store = Store()
    result = manager.complete(
        state=started["state"],
        authorization_response="http://127.0.0.1/callback?code=fixture&state=state-1",
        store=store,
        build_factory=lambda *args, **kwargs: GmailBuild(),
    )
    assert result["account_id"] == "verified@example.test"
    assert result["duplicate_identity"] is False
    assert store.saved[0][:3] == ("google", "verified@example.test", list(Credentials.granted_scopes))
    with pytest.raises(GoogleOAuthWebError, match="expired|already"):
        manager.complete(state=started["state"], authorization_response="replay", store=store)


def test_web_oauth_rejects_invalid_client_config_and_expired_state():
    manager = GoogleOAuthWebManager(ttl_seconds=1, clock=lambda: 5)
    with pytest.raises(GoogleOAuthWebError, match="installed or web"):
        manager.start({}, redirect_uri="http://127.0.0.1/callback", flow_factory=lambda *_: Flow())
