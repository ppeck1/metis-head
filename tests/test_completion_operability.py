from __future__ import annotations

import json

import pytest

from metis_head.credentials.store import CredentialStore, SecretStoreUnavailable
from metis_head.usage.accounting import BudgetExceeded, PricingUnknown, UsageLedger


def test_usage_fails_closed_without_budget_or_pricing(tmp_path):
    ledger = UsageLedger(tmp_path / "usage.json")
    with pytest.raises(PricingUnknown):
        ledger.reserve(provider="cloud", model="m", estimated_usd=None, pricing_version=None)
    with pytest.raises(BudgetExceeded):
        ledger.reserve(provider="cloud", model="m", estimated_usd="0.01", pricing_version="v1")


def test_usage_reserves_reconciles_and_survives_restart(tmp_path):
    path = tmp_path / "usage.json"
    ledger = UsageLedger(path, "0.05")
    first = ledger.reserve(provider="cloud", model="m", estimated_usd="0.02", pricing_version="v1")
    ledger.reconcile(first.reservation_id, actual_usd="0.012", actual_usage={"input_tokens": 12})
    restarted = UsageLedger(path, "0.05")
    assert restarted.snapshot()["committed_usd"] == "0.012000"
    with pytest.raises(BudgetExceeded):
        restarted.reserve(provider="cloud", model="m", estimated_usd="0.04", pricing_version="v1")


def test_connection_metadata_contains_no_secret(tmp_path, monkeypatch):
    class FakeKeyring:
        values = {}
        def set_password(self, service, key, value): self.values[(service, key)] = value
        def get_password(self, service, key): return self.values.get((service, key))
        def delete_password(self, service, key): self.values.pop((service, key), None)

    store = CredentialStore(tmp_path / "connections.json")
    monkeypatch.setattr(store, "_keyring", lambda: FakeKeyring())
    record = store.connect("google", "paul@example.test", ["calendar.readonly"], "top-secret")
    assert store.secret(record.connection_id) == "top-secret"
    assert "top-secret" not in (tmp_path / "connections.json").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "connections.json").read_text())["connections"][0]["status"] == "connected"


def test_credential_store_has_no_plaintext_fallback(tmp_path, monkeypatch):
    store = CredentialStore(tmp_path / "connections.json")
    monkeypatch.setattr(store, "_keyring", lambda: (_ for _ in ()).throw(SecretStoreUnavailable("no keyring")))
    with pytest.raises(SecretStoreUnavailable):
        store.connect("google", "account", ["scope"], "secret")
    assert not (tmp_path / "connections.json").exists()


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "-0.01"])
def test_usage_rejects_non_finite_or_negative_budget(tmp_path, value):
    with pytest.raises(ValueError, match="finite and non-negative"):
        UsageLedger(tmp_path / "usage.json", value)
