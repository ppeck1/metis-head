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
        self.code = kwargs["code"]


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
        authorization_response="http://127.0.0.1:8787/metis/connectors/google/oauth/callback?code=fixture&state=state-1",
        store=store,
        build_factory=lambda *args, **kwargs: GmailBuild(),
    )
    assert result["account_id"] == "verified@example.test"
    assert flow.code == "fixture"
    assert result["duplicate_identity"] is False
    assert store.saved[0][:3] == ("google", "verified@example.test", list(Credentials.granted_scopes))
    with pytest.raises(GoogleOAuthWebError, match="expired|already"):
        manager.complete(state=started["state"], authorization_response="replay", store=store)


def test_web_oauth_rejects_invalid_client_config_and_expired_state():
    now = [5.0]
    manager = GoogleOAuthWebManager(ttl_seconds=1, clock=lambda: now[0])
    with pytest.raises(GoogleOAuthWebError, match="installed or web"):
        manager.start({}, redirect_uri="http://127.0.0.1/callback", flow_factory=lambda *_: Flow())
    started = manager.start(
        {"installed": {"client_id": "fixture"}},
        redirect_uri="http://127.0.0.1/callback",
        flow_factory=lambda *_: Flow(),
    )
    now[0] = 6.0
    with pytest.raises(GoogleOAuthWebError, match="expired|already"):
        manager.complete(
            state=started["state"],
            authorization_response="http://127.0.0.1/callback?code=x&state=state-1",
            store=Store(),
        )


@pytest.mark.parametrize(
    ("callback", "message"),
    [
        ("http://127.0.0.1:8787/metis/connectors/google/oauth/callback?state=state-1", "authorization code"),
        ("http://127.0.0.1:8787/metis/connectors/google/oauth/callback?error=access_denied&state=state-1", "denied"),
        ("http://127.0.0.1:8787/metis/connectors/google/oauth/callback?code=x&state=other", "state"),
        ("http://localhost:8787/metis/connectors/google/oauth/callback?code=x&state=state-1", "loopback"),
    ],
)
def test_web_oauth_rejects_invalid_callback_once(callback, message):
    manager = GoogleOAuthWebManager()
    started = manager.start(
        {"installed": {"client_id": "fixture"}},
        redirect_uri="http://127.0.0.1:8787/metis/connectors/google/oauth/callback",
        flow_factory=lambda *_: Flow(),
    )
    with pytest.raises(GoogleOAuthWebError, match=message):
        manager.complete(state=started["state"], authorization_response=callback, store=Store())
    with pytest.raises(GoogleOAuthWebError, match="expired|already"):
        manager.complete(state=started["state"], authorization_response=callback, store=Store())


def test_real_google_flow_uses_code_for_loopback_without_disabling_https(monkeypatch):
    from google_auth_oauthlib.flow import Flow as RealFlow

    config = {"installed": {
        "client_id": "fixture.apps.googleusercontent.com",
        "client_secret": "fixture-secret",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://127.0.0.1"],
    }}
    manager = GoogleOAuthWebManager()
    captured = {}

    def factory(client_config, scopes):
        flow = RealFlow.from_client_config(client_config, scopes=scopes, state="real-state")

        def exchange(token_url, **kwargs):
            captured.update({"token_url": token_url, **kwargs})
            flow.oauth2session.token = {
                "access_token": "fixture-token", "token_type": "Bearer",
                    "scope": list(scopes), "expires_at": 2_000_000_000,
            }
            return flow.oauth2session.token

        monkeypatch.setattr(flow.oauth2session, "fetch_token", exchange)
        return flow

    started = manager.start(config, redirect_uri="http://127.0.0.1:8787/callback", flow_factory=factory)
    result = manager.complete(
        state=started["state"],
        authorization_response=f"http://127.0.0.1:8787/callback?code=fixture-code&state={started['state']}",
        store=Store(),
        build_factory=lambda *args, **kwargs: GmailBuild(),
    )

    assert result["account_id"] == "verified@example.test"
    assert captured["code"] == "fixture-code"
    assert captured["token_url"] == "https://oauth2.googleapis.com/token"
