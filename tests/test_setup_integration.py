from __future__ import annotations

from fastapi.testclient import TestClient
from datetime import UTC, datetime

from metis_head import brain
from metis_head.audio import AUDIO_ARTIFACTS, PlaybackQueue
from metis_head.conversation import SessionStore, TurnStage
from metis_head.voice import VoiceResult
from metis_head.connectors import GoogleReadBroker
from metis_head.connectors.google_access import CALENDAR_SCOPE
from metis_head.connectors.contracts import ErrorCode, ResultStatus


class _Connections:
    def list_connections(self):
        return [
            {
                "provider": "google",
                "status": "connected",
                "account_id": account,
                "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
                "selected_calendar_ids": ["primary"],
            }
            for account in ("personal@example.test", "nursing@example.test", "photo@example.test", "shop@example.test")
        ]


def _fresh_runtime(monkeypatch):
    sessions = SessionStore()
    monkeypatch.setattr(brain, "SESSIONS", sessions)
    monkeypatch.setattr(brain, "PLAYBACK", PlaybackQueue(sessions.accepts))
    return sessions


def test_preview_requires_owned_session_and_queues_for_same_browser(monkeypatch):
    sessions = _fresh_runtime(monkeypatch)
    artifact_id = AUDIO_ARTIFACTS.put(b"RIFFpreview-WAVE")
    real_speak_text = brain.speak_text

    def synthesize(text, state, options):
        result = real_speak_text(text, state, {"voice": {"enabled": True, "provider": "mock"}})
        next(event for event in result.events if event["status"] == "speaking")["audio_ref"] = (
            f"/metis/voice/audio/{artifact_id}"
        )
        return result

    monkeypatch.setattr(brain, "speak_text", synthesize)
    with TestClient(brain.app) as client:
        missing = client.post("/metis/voice/preview", json={"provider": "piper"})
        session = client.post("/metis/sessions", json={"client_id": "preview-tab"}).json()
        preview = client.post(
            "/metis/voice/preview",
            json={"session_id": session["session_id"], "provider": "piper"},
        )
        command = client.get("/metis/playback/next", params={"client_id": "preview-tab"}).json()["command"]

    assert missing.status_code == 400
    assert preview.status_code == 200
    assert preview.json()["metadata"]["playback_id"] == command["playback_id"]
    assert command["session_id"] == session["session_id"]
    assert sessions.snapshot(session["session_id"]).turns[-1].stage is TurnStage.PLAYBACK_QUEUED


def test_four_account_session_authorizes_exact_selected_set(monkeypatch):
    sessions = _fresh_runtime(monkeypatch)
    monkeypatch.setattr(brain, "_google_store", lambda: _Connections())
    context = {
        "account_ids": ["personal@example.test", "photo@example.test"],
        "calendars_by_account": {
            "personal@example.test": ["primary"],
            "photo@example.test": ["primary"],
        },
    }
    with TestClient(brain.app) as client:
        response = client.post("/metis/sessions", json={"client_id": "two-profile-tab", "context": context})
    assert response.status_code == 200
    stored = sessions.snapshot(response.json()["session_id"]).context
    assert stored.account_ids == ("personal@example.test", "photo@example.test")
    assert "nursing@example.test" not in stored.account_ids
    assert dict(stored.calendars_by_account) == {
        "personal@example.test": ("primary",),
        "photo@example.test": ("primary",),
    }


def test_account_supplied_calendar_map_cannot_expand_authorized_set(monkeypatch):
    _fresh_runtime(monkeypatch)
    monkeypatch.setattr(brain, "_google_store", lambda: _Connections())
    with TestClient(brain.app) as client:
        response = client.post(
            "/metis/sessions",
            json={
                "client_id": "blocked-expansion",
                "context": {
                    "account_ids": ["personal@example.test"],
                    "calendars_by_account": {"shop@example.test": ["primary"]},
                },
            },
        )
    assert response.status_code == 400
    assert "selected Google account" in response.json()["detail"]


def test_primary_account_cannot_expand_explicit_account_set(monkeypatch):
    _fresh_runtime(monkeypatch)
    monkeypatch.setattr(brain, "_google_store", lambda: _Connections())
    with TestClient(brain.app) as client:
        response = client.post(
            "/metis/sessions",
            json={
                "client_id": "blocked-primary-expansion",
                "context": {
                    "account_id": "personal@example.test",
                    "account_ids": ["photo@example.test"],
                    "calendars_by_account": {"photo@example.test": ["primary"]},
                },
            },
        )
    assert response.status_code == 400
    assert "primary account" in response.json()["detail"]


def test_session_scoped_broker_rejects_broader_persisted_calendar():
    broker = GoogleReadBroker.from_connection_records(
        [{
            "provider": "google", "status": "connected", "account_id": "personal@example.test",
            "scopes": [CALENDAR_SCOPE], "selected_calendar_ids": ["primary", "private"],
        }],
        {"personal@example.test": object()},
    )
    scoped = broker.restrict_to(["personal@example.test"], {"personal@example.test": ["primary"]})
    result = scoped.calendar_events(
        account_id="personal@example.test",
        calendar_ids=["private"],
        start=datetime(2026, 9, 17, tzinfo=UTC),
        end=datetime(2026, 9, 18, tzinfo=UTC),
        timezone="UTC",
    )
    assert result.status is ResultStatus.UNAVAILABLE
    assert result.error and result.error.code is ErrorCode.PERMISSION_DENIED


def test_setup_api_rejects_unavailable_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("METIS_SETUP_FILE", str(tmp_path / "setup.json"))
    with TestClient(brain.app) as client:
        current = client.get("/metis/setup").json()["setup"]
        response = client.patch(
            "/metis/setup",
            json={"patch": {"provider": {"choice": "openai_api"}}, "expected_revision": current["revision"]},
        )
    assert response.status_code == 400
    assert "not available" in response.json()["detail"]


def test_setup_page_and_build_contract_are_served(tmp_path, monkeypatch):
    monkeypatch.setenv("METIS_SETUP_FILE", str(tmp_path / "setup.json"))
    monkeypatch.setattr(brain, "_google_store", lambda: _Connections())
    with TestClient(brain.app) as client:
        page = client.get("/setup")
        status = client.get("/metis/setup")
        build = client.get("/metis/build")
    assert page.status_code == 200 and "Setup / Connections" in page.text
    assert status.status_code == 200
    assert status.json()["setup"]["google_profiles"] == []
    assert status.json()["providers"]["providers"][1]["selectable"] is False
    assert build.json()["schema"] == "metis.build.v1"


def test_profile_labels_route_exact_account_or_require_clarification(tmp_path, monkeypatch):
    monkeypatch.setenv("METIS_SETUP_FILE", str(tmp_path / "setup.json"))
    monkeypatch.setattr(brain, "_google_store", lambda: _Connections())
    profiles = [
        {
            "slot_id": slot, "label": label, "account_id": account,
            "calendar_ids": ["primary"], "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
            "status": "verified", "last_verification": None,
        }
        for slot, label, account in (
            ("profile_1", "Personal / Main", "personal@example.test"),
            ("profile_2", "Nursing", "nursing@example.test"),
            ("profile_3", "Photography", "photo@example.test"),
            ("profile_4", "Sinternet Cult", "shop@example.test"),
        )
    ]
    with TestClient(brain.app) as client:
        current = client.get("/metis/setup").json()["setup"]
        saved = client.patch(
            "/metis/setup",
            json={"patch": {
                "google_profiles": profiles,
                "profile_selection": {
                    "mode": "default", "default_slot_id": "profile_1", "active_slot_ids": ["profile_1"],
                },
            }, "expected_revision": current["revision"]},
        )
        matched = client.post(
            "/metis/setup/resolve-profile", json={"message": "What is on my Nursing calendar?"}
        )
        unclear = client.post(
            "/metis/setup/resolve-profile", json={"message": "What is on my calendar?"}
        )
        default_context = client.get("/metis/setup/conversation-context")

    assert saved.status_code == 200
    assert matched.json()["status"] == "matched"
    assert matched.json()["account_ids"] == ["nursing@example.test"]
    assert matched.json()["matched_labels"] == ["Nursing"]
    assert unclear.json()["status"] == "clarification_required"
    assert unclear.json()["account_ids"] == []
    assert default_context.json()["account_ids"] == []
    assert set(default_context.json()["labels"].values()) == {
        "Personal / Main", "Nursing", "Photography", "Sinternet Cult"
    }
