from fastapi.testclient import TestClient

from metis_head import brain
from metis_head.audio import AUDIO_ARTIFACTS, AudioArtifactStore
from metis_head.conversation import TurnOrigin, TurnStage


def test_audio_artifacts_are_bounded_and_single_use():
    store = AudioArtifactStore(max_items=2, max_total_bytes=8, ttl_seconds=300)
    first = store.put(b"1111")
    second = store.put(b"2222")
    third = store.put(b"3333")
    assert store.consume(first) is None
    assert store.consume(second).data == b"2222"
    assert store.consume(second) is None
    assert store.consume(third).content_type == "audio/wav"


def test_client_audio_endpoint_is_no_store_and_single_use():
    artifact_id = AUDIO_ARTIFACTS.put(b"RIFFfixture-WAVE")
    with TestClient(brain.app) as client:
        response = client.get(f"/metis/voice/audio/{artifact_id}")
        second = client.get(f"/metis/voice/audio/{artifact_id}")
    assert response.status_code == 200
    assert response.content == b"RIFFfixture-WAVE"
    assert response.headers["cache-control"] == "no-store"
    assert second.status_code == 404


def test_owned_audio_and_playback_ack_complete_the_turn():
    session = brain.SESSIONS.create_session("audio-tab")
    token = brain.SESSIONS.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="speak")
    brain.SESSIONS.transition(token, TurnStage.SYNTHESIZING)
    artifact_id = AUDIO_ARTIFACTS.put(b"RIFF-owned-WAVE")
    assert AUDIO_ARTIFACTS.bind(
        artifact_id,
        session_id=token.session_id,
        turn_id=token.turn_id,
        generation=token.generation,
    )
    audio_ref = f"/metis/voice/audio/{artifact_id}?session_id={token.session_id}"
    item = brain.PLAYBACK.enqueue(client_id="audio-tab", token=token, audio_ref=audio_ref, content_type="audio/wav")
    assert item is not None
    brain.SESSIONS.transition(token, TurnStage.PLAYBACK_QUEUED)

    with TestClient(brain.app) as client:
        assert client.get(f"/metis/voice/audio/{artifact_id}").status_code == 404
        command = client.get("/metis/playback/next", params={"client_id": "audio-tab"}).json()["command"]
        assert command["audio_ref"] == audio_ref
        started = client.post("/metis/playback/ack", json={"playback_id": item.playback_id, "client_id": "audio-tab", "state": "started"})
        completed = client.post("/metis/playback/ack", json={"playback_id": item.playback_id, "client_id": "audio-tab", "state": "completed"})
        completed_again = client.post("/metis/playback/ack", json={"playback_id": item.playback_id, "client_id": "audio-tab", "state": "completed"})
        owned = client.get(f"/metis/voice/audio/{artifact_id}", params={"session_id": token.session_id})

    assert started.status_code == 200
    assert completed.status_code == 200
    assert completed_again.status_code == 200
    assert owned.status_code == 200
    assert brain.SESSIONS.snapshot(token.session_id).turns[-1].stage is TurnStage.COMPLETED


def test_pre_start_playback_failure_terminalizes_and_next_turn_is_usable():
    session = brain.SESSIONS.create_session("reject-tab")
    token = brain.SESSIONS.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="speak")
    brain.SESSIONS.transition(token, TurnStage.SYNTHESIZING)
    item = brain.PLAYBACK.enqueue(
        client_id="reject-tab", token=token, audio_ref="/metis/voice/audio/fixture", content_type="audio/wav"
    )
    assert item is not None
    brain.SESSIONS.transition(token, TurnStage.PLAYBACK_QUEUED)

    with TestClient(brain.app) as client:
        command = client.get("/metis/playback/next", params={"client_id": "reject-tab"}).json()["command"]
        failed = client.post(
            "/metis/playback/ack",
            json={
                "playback_id": command["playback_id"],
                "client_id": "reject-tab",
                "state": "failed",
                "failure_code": "audio_play_rejected",
            },
        )

    assert failed.status_code == 200
    assert brain.SESSIONS.snapshot(token.session_id).turns[-1].stage is TurnStage.FAILED
    assert brain.SESSIONS.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="next")
