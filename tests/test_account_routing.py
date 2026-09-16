from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head import brain
from metis_head.account_routing import AccountProfile, resolve_account_labels
from metis_head.audio import PlaybackQueue
from metis_head.conversation import SessionStore
from metis_head.connectors.google_access import GoogleReadBroker
from metis_head.llm_providers import LLMResult


PROFILES = (
    AccountProfile("nursing@example.test", "Professional Nursing", ("nursing-calendar",)),
    AccountProfile("photo@example.test", "Professional Photography", ("photo-calendar",)),
    AccountProfile("personal@example.test", "Personal / Main", ("primary",)),
)


def test_full_labels_unique_aliases_exclusions_and_combined_requests() -> None:
    exact = resolve_account_labels("Check my Professional Nursing calendar", PROFILES)
    unique = resolve_account_labels("Check Nursing calendar", PROFILES)
    ambiguous = resolve_account_labels("Check my Professional calendar", PROFILES)
    excluded = resolve_account_labels("Not Photography, Nursing please", PROFILES, require_selection=True)
    combined = resolve_account_labels("Compare Nursing and Photography calendars", PROFILES)

    assert [item.account_id for item in exact.matched] == ["nursing@example.test"]
    assert [item.account_id for item in unique.matched] == ["nursing@example.test"]
    assert ambiguous.status == "clarification_required"
    assert {item.account_id for item in ambiguous.ambiguous} == {
        "nursing@example.test", "photo@example.test"
    }
    assert [item.account_id for item in excluded.matched] == ["nursing@example.test"]
    assert [item.account_id for item in excluded.excluded] == ["photo@example.test"]
    assert [item.account_id for item in combined.matched] == [
        "nursing@example.test", "photo@example.test"
    ]


class _Connections:
    def list_connections(self):
        return [
            {
                "connection_id": f"connection-{index}",
                "provider": "google",
                "status": "connected",
                "account_id": profile.account_id,
                "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
                "selected_calendar_ids": list(profile.calendar_ids),
            }
            for index, profile in enumerate(PROFILES, 1)
        ]


def _configure_profiles(tmp_path, monkeypatch) -> SessionStore:
    monkeypatch.setenv("METIS_SETUP_FILE", str(tmp_path / "setup.json"))
    sessions = SessionStore()
    monkeypatch.setattr(brain, "SESSIONS", sessions)
    monkeypatch.setattr(brain, "PLAYBACK", PlaybackQueue(sessions.accepts))
    monkeypatch.setattr(brain, "_google_store", lambda: _Connections())
    records = _Connections().list_connections()
    broker = GoogleReadBroker.from_connection_records(
        records, {profile.account_id: object() for profile in PROFILES}
    )
    monkeypatch.setattr(brain, "_google_read_broker", lambda: broker)
    store = brain._setup_store()
    store.update({
        "google_profiles": {
            "profile_1": {
                "label": "Professional Nursing", "account_id": "nursing@example.test",
                "calendar_ids": ["nursing-calendar"], "status": "verified",
            },
            "profile_2": {
                "label": "Professional Photography", "account_id": "photo@example.test",
                "calendar_ids": ["photo-calendar"], "status": "verified",
            },
            "profile_3": {
                "label": "Personal / Main", "account_id": "personal@example.test",
                "calendar_ids": ["primary"], "status": "verified",
            },
        },
        "profile_selection": {
            "mode": "default",
            "default_slot_id": "profile_1",
            "active_slot_ids": ["profile_1"],
        },
    })
    return sessions


def test_typed_clarification_restores_request_without_old_private_history(tmp_path, monkeypatch) -> None:
    sessions = _configure_profiles(tmp_path, monkeypatch)
    model_inputs = []

    class Provider:
        def generate(self, messages, state, options):
            model_inputs.append(messages)
            return LLMResult("fixture answer", "fixture", "fixture")

    monkeypatch.setattr(brain, "provider_from_config", lambda options: Provider())
    with TestClient(brain.app) as client:
        session_id = client.post(
            "/metis/sessions",
            json={
                "client_id": "routing-tab",
                "context": {
                    "account_id": "nursing@example.test",
                    "account_ids": ["nursing@example.test"],
                    "calendar_ids": ["nursing-calendar"],
                    "calendars_by_account": {"nursing@example.test": ["nursing-calendar"]},
                },
            },
        ).json()["session_id"]
        first = client.post("/metis/chat", json={"message": "private preface", "session_id": session_id})
        unclear = client.post(
            "/metis/chat", json={"message": "Check my Professional calendar tomorrow", "session_id": session_id}
        )
        resolved = client.post("/metis/chat", json={"message": "Photography", "session_id": session_id})

    assert first.status_code == 200
    assert unclear.json()["provider"] == "account_router"
    assert unclear.json()["account_resolution"]["status"] == "clarification_required"
    assert resolved.json()["account_resolution"]["status"] == "clarification_resolved"
    assert resolved.json()["account_resolution"]["account_ids"] == ["photo@example.test"]
    final_conversation = model_inputs[-1]
    rendered = "\n".join(item["content"] for item in final_conversation)
    assert "Check my Professional calendar tomorrow" in rendered
    assert "private preface" not in rendered
    assert "fixture answer" not in rendered
    assert "Photography" not in [
        item.text for item in sessions.private_history(session_id) if item.role == "user"
    ]


def test_transcribed_clarification_uses_same_server_resolution_path(tmp_path, monkeypatch) -> None:
    sessions = _configure_profiles(tmp_path, monkeypatch)
    model_inputs = []

    class Provider:
        def generate(self, messages, state, options):
            model_inputs.append(messages)
            return LLMResult("Nursing answer", "fixture", "fixture")

    monkeypatch.setattr(brain, "provider_from_config", lambda options: Provider())
    monkeypatch.setitem(brain.STATE, "mic_hardware_enabled", True)
    with TestClient(brain.app) as client:
        session_id = client.post("/metis/sessions", json={"client_id": "voice-routing-tab"}).json()["session_id"]
        unclear = client.post(
            "/metis/voice/command",
            json={"text": "What is on my calendar tomorrow?", "options": {"session_id": session_id, "voice": {"speak_response": False}}},
        )
        resolved = client.post(
            "/metis/voice/command",
            json={"text": "Nursing", "options": {"session_id": session_id, "voice": {"speak_response": False}}},
        )

    assert unclear.json()["provider"] == "account_router"
    assert resolved.status_code == 200
    assert resolved.json()["account_resolution"]["account_ids"] == ["nursing@example.test"]
    assert "What is on my calendar tomorrow?" in "\n".join(
        item["content"] for item in model_inputs[-1]
    )
    assert sessions.safe_export(session_id)["pending_account_clarification"] is False


def test_removed_profile_is_revoked_before_chat_dispatch(tmp_path, monkeypatch) -> None:
    sessions = _configure_profiles(tmp_path, monkeypatch)
    provider_called = False

    class Provider:
        def generate(self, messages, state, options):
            nonlocal provider_called
            provider_called = True
            return LLMResult("must not run", "fixture", "fixture")

    monkeypatch.setattr(brain, "provider_from_config", lambda options: Provider())
    with TestClient(brain.app) as client:
        session_id = client.post(
            "/metis/sessions",
            json={
                "client_id": "removed-account-tab",
                "context": {
                    "account_id": "nursing@example.test",
                    "account_ids": ["nursing@example.test"],
                    "calendar_ids": ["nursing-calendar"],
                    "calendars_by_account": {"nursing@example.test": ["nursing-calendar"]},
                },
            },
        ).json()["session_id"]
        brain._setup_store().update({
            "google_profiles": {
                "profile_1": {"account_id": None, "calendar_ids": [], "status": "not_connected"}
            },
            "profile_selection": {
                "default_slot_id": "profile_2", "active_slot_ids": ["profile_2"]
            },
        })
        response = client.post(
            "/metis/chat", json={"message": "What is on my calendar?", "session_id": session_id}
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "account_router"
    assert "Professional Nursing" not in response.json()["account_resolution"]["available_labels"]
    assert sessions.snapshot(session_id).context.account_ids == ()
    assert provider_called is False
