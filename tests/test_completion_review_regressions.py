from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha1
from threading import Event

from fastapi.testclient import TestClient

from metis_head import brain
from metis_head.boh_retrieval import BOHRetrievalResult
from metis_head.llm_providers import LLMResult
from metis_head.model_adapters.ollama_local import BoundedUrllibJsonTransport
from metis_head.connectors.google_access import GoogleReadBroker
from metis_head.stt import STTResult


def _enable_browser_ptt(client: TestClient) -> None:
    client.post("/metis/state/reset")
    client.post("/metis/event", json={"type": "button_event", "button": "audio_input", "state": "on"})
    client.post("/metis/event", json={"type": "button_event", "button": "listen_mode", "state": "push_to_talk"})


def test_cancel_during_stt_cannot_create_a_replacement_turn(monkeypatch) -> None:
    started = Event()
    release = Event()
    provider_calls: list[object] = []

    class SlowSTT:
        def transcribe(self, capture, context):
            started.set()
            assert release.wait(5)
            text = "private delayed transcript"
            result = STTResult("slow-fixture", "complete", len(text), sha1(text.encode()).hexdigest(), confidence=1.0)
            result._recognized_text = text
            return result

    monkeypatch.setattr(brain, "stt_provider_from_config", lambda name: SlowSTT())
    monkeypatch.setattr(brain, "provider_from_config", lambda options: provider_calls.append(options))

    with TestClient(brain.app) as client:
        _enable_browser_ptt(client)
        session_id = client.post("/metis/sessions", json={"client_id": "slow-stt-tab"}).json()["session_id"]
        client.post("/metis/audio/ptt", json={"action": "press"})
        options = '{"session_id":"%s","provider":"mock","voice":{"speak_response":false}}' % session_id
        wav = b"RIFF" + (b"\x00" * 4) + b"WAVE" + (b"\x00" * 32)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                client.post,
                "/metis/audio/browser_ptt",
                files={"audio": ("utterance.wav", wav, "audio/wav")},
                data={"stt_provider": "slow", "stt_hint": "", "options_json": options},
            )
            assert started.wait(5)
            cancelled = client.post(f"/metis/sessions/{session_id}/cancel")
            release.set()
            response = future.result(timeout=5)

        snapshot = client.get(f"/metis/sessions/{session_id}").json()
    assert cancelled.status_code == 200
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert provider_calls == []
    assert len(snapshot["turns"]) == 1
    assert snapshot["turns"][0]["stage"] == "cancelled"
    assert snapshot["history"] == []


def test_cancel_during_boh_retrieval_stops_before_model_dispatch(monkeypatch) -> None:
    started = Event()
    release = Event()
    provider_calls = []
    monkeypatch.setenv("METIS_BOH_ENABLED", "true")
    monkeypatch.setenv("METIS_BOH_RETRIEVAL_TOKEN", "fixture-token")

    def delayed_retrieval(config, query):
        started.set()
        assert release.wait(5)
        return BOHRetrievalResult(enabled=True, attempted=True, ok=True, source_state="sourced", count=1, context_packs=[])

    class Provider:
        def generate(self, messages, state, options):
            provider_calls.append(messages)
            return LLMResult("must not dispatch", "fixture", "fixture")

    monkeypatch.setattr(brain, "retrieve_boh_context", delayed_retrieval)
    monkeypatch.setattr(brain, "provider_from_config", lambda options: Provider())
    with TestClient(brain.app) as client:
        client.post("/metis/state/reset")
        client.post("/metis/event", json={"type": "button_event", "button": "afc", "state": True})
        session_id = client.post("/metis/sessions", json={"client_id": "slow-boh-tab"}).json()["session_id"]
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(client.post, "/metis/chat", json={"message": "look this up", "session_id": session_id})
            assert started.wait(5)
            cancelled = client.post(f"/metis/sessions/{session_id}/cancel")
            release.set()
            response = future.result(timeout=5)

    assert cancelled.status_code == 200
    assert response.status_code == 409
    assert provider_calls == []


def test_cancel_before_coordinator_registration_stops_ollama_dispatch(monkeypatch) -> None:
    started = Event()
    release = Event()
    provider_calls = []
    original_builder = brain._build_personal_coordinator
    monkeypatch.setattr(brain, "_google_read_broker", lambda: GoogleReadBroker({}, {}))

    def delayed_builder(options, broker=None, *, selected_account_id=None):
        started.set()
        assert release.wait(5)
        return original_builder(options, broker, selected_account_id=selected_account_id)

    def fake_post(self, *, url, payload, timeout_seconds, cancellation):
        provider_calls.append(payload)
        return {"choices": [{"message": {"content": "must not dispatch"}}]}

    monkeypatch.setattr(brain, "_build_personal_coordinator", delayed_builder)
    monkeypatch.setattr(BoundedUrllibJsonTransport, "post_json", fake_post)
    with TestClient(brain.app) as client:
        client.post("/metis/state/reset")
        session_id = client.post("/metis/sessions", json={"client_id": "registration-race-tab"}).json()["session_id"]
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                client.post,
                "/metis/chat",
                json={"message": "hello", "session_id": session_id, "options": {"provider": "ollama", "model": "fixture"}},
            )
            assert started.wait(5)
            cancelled = client.post(f"/metis/sessions/{session_id}/cancel")
            release.set()
            response = future.result(timeout=5)

    assert cancelled.status_code == 200
    assert response.status_code == 502
    assert provider_calls == []


def test_invalid_and_unexpected_provider_failures_leave_session_reusable(monkeypatch) -> None:
    class SometimesFails:
        calls = 0

        def generate(self, messages, state, options):
            self.calls += 1
            if self.calls == 1:
                raise ValueError("synthetic provider bug")
            return LLMResult("Recovered response.", "fixture", "fixture")

    provider = SometimesFails()
    monkeypatch.setattr(brain, "provider_from_config", lambda options: provider)
    with TestClient(brain.app) as client:
        session_id = client.post("/metis/sessions", json={"client_id": "recovery-tab"}).json()["session_id"]
        invalid = client.post("/metis/chat", json={"message": "x" * 12_001, "session_id": session_id})
        failed = client.post("/metis/chat", json={"message": "first valid", "session_id": session_id})
        recovered = client.post("/metis/chat", json={"message": "second valid", "session_id": session_id})

    assert invalid.status_code == 400
    assert failed.status_code == 502
    assert recovered.status_code == 200
    assert recovered.json()["message"] == "Recovered response."


def test_mock_speech_without_artifact_completes_and_next_turn_works(monkeypatch) -> None:
    class Provider:
        def generate(self, messages, state, options):
            return LLMResult("Text survives speech handling.", "fixture", "fixture")

    monkeypatch.setattr(brain, "provider_from_config", lambda options: Provider())
    with TestClient(brain.app) as client:
        session_id = client.post("/metis/sessions", json={"client_id": "mock-speech-tab"}).json()["session_id"]
        first = client.post(
            "/metis/chat",
            json={"message": "speak", "session_id": session_id, "options": {"voice": {"speak_response": True, "provider": "mock"}}},
        )
        second = client.post("/metis/chat", json={"message": "continue", "session_id": session_id})

    assert first.status_code == 200, first.text
    assert first.json()["message"] == "Text survives speech handling."
    assert second.status_code == 200


def test_ollama_sourced_label_requires_boh_evidence_in_actual_model_payload(monkeypatch) -> None:
    sentinel = "BOH-SENTINEL-UNTRUSTED-9234"
    payloads: list[dict] = []
    monkeypatch.setenv("METIS_BOH_ENABLED", "true")
    monkeypatch.setenv("METIS_BOH_RETRIEVAL_TOKEN", "fixture-token")
    monkeypatch.setattr(
        brain,
        "retrieve_boh_context",
        lambda config, query: BOHRetrievalResult(
            enabled=True,
            attempted=True,
            ok=True,
            source_state="sourced",
            count=1,
            context_packs=[{"id": "fixture", "citation": "boh://fixture", "text": sentinel}],
        ),
    )

    def fake_post(self, *, url, payload, timeout_seconds, cancellation):
        payloads.append(payload)
        return {"choices": [{"message": {"content": "Evidence-aware answer."}}]}

    monkeypatch.setattr(BoundedUrllibJsonTransport, "post_json", fake_post)
    with TestClient(brain.app) as client:
        client.post("/metis/state/reset")
        client.post("/metis/event", json={"type": "button_event", "button": "afc", "state": True})
        session_id = client.post("/metis/sessions", json={"client_id": "boh-context-tab"}).json()["session_id"]
        response = client.post(
            "/metis/chat",
            json={"message": "Use BOH", "session_id": session_id, "options": {"provider": "ollama", "model": "fixture"}},
        )

    assert response.status_code == 200, response.text
    assert response.json()["source_state"] == "sourced"
    assert "Source label: sourced context delivered" in response.json()["message"]
    assert "not independent verification" in response.json()["message"]
    assert response.json()["metadata"]["boh_evidence_delivery"] == "delivered"
    assert response.json()["metadata"]["answer_attribution"] == "unverified"
    joined = "\n".join(str(message.get("content") or "") for message in payloads[0]["messages"])
    assert sentinel in joined
    assert "UNTRUSTED BOH EVIDENCE" in joined
