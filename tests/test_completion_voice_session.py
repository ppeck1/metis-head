from __future__ import annotations

from itertools import count

import pytest

from metis_head.audio import PlaybackAck, PlaybackCommandKind, PlaybackQueue, PlaybackState
from metis_head.conversation import SessionContext, SessionStore, TurnOrigin, TurnStage


def _ids(prefix: str = "id"):
    values = count(1)
    return lambda: f"{prefix}-{next(values)}"


def test_voice_transcript_is_private_bounded_and_export_is_redacted() -> None:
    store = SessionStore(max_history_messages=2, id_factory=_ids())
    session = store.create_session("browser-tab", context=SessionContext(account_id="personal", project_id="metis"))
    first = store.begin_turn(session.session_id, origin=TurnOrigin.VOICE)
    assert store.transition(first, TurnStage.TRANSCRIBING)
    assert store.set_transcript(first, "Tomorrow is my dentist appointment")
    assert store.transition(first, TurnStage.THINKING)
    assert store.commit_assistant_text(first, "I will keep that in this conversation.")
    assert store.transition(first, TurnStage.COMPLETED)

    second = store.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="What time was it?")
    history = store.private_history(session.session_id)
    assert [message.text for message in history] == ["I will keep that in this conversation.", "What time was it?"]
    exported = store.safe_export(session.session_id)
    assert "dentist" not in repr(exported)
    assert "personal" not in repr(exported)
    assert all(item["text"] == "[REDACTED]" for item in exported["history"])
    assert store.accepts(second)


def test_sessions_are_isolated_and_have_unique_turns() -> None:
    store = SessionStore(id_factory=_ids())
    left = store.create_session("left-tab")
    right = store.create_session("right-tab")
    left_turn = store.begin_turn(left.session_id, origin=TurnOrigin.TEXT, user_text="left secret")
    right_turn = store.begin_turn(right.session_id, origin=TurnOrigin.TEXT, user_text="right secret")

    assert left.session_id != right.session_id
    assert left_turn.turn_id != right_turn.turn_id
    assert [item.text for item in store.private_history(left.session_id)] == ["left secret"]
    assert [item.text for item in store.private_history(right.session_id)] == ["right secret"]


def test_cancellation_generation_rejects_late_results_and_allows_next_turn() -> None:
    store = SessionStore(id_factory=_ids())
    session = store.create_session("tab")
    old = store.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="slow request")

    assert store.cancel(session.session_id, turn_id=old.turn_id) == old.generation + 1
    assert not store.commit_assistant_text(old, "late answer")
    assert not store.transition(old, TurnStage.COMPLETED)
    assert "late answer" not in [item.text for item in store.private_history(session.session_id)]

    current = store.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="new request")
    assert current.generation == old.generation + 1
    assert store.commit_assistant_text(current, "current answer")


def test_invalid_lifecycle_transition_fails_loudly() -> None:
    store = SessionStore(id_factory=_ids())
    session = store.create_session("tab")
    turn = store.begin_turn(session.session_id, origin=TurnOrigin.VOICE)
    with pytest.raises(ValueError, match="invalid turn transition"):
        store.transition(turn, TurnStage.PLAYING)


def test_playback_requires_correct_client_ack_and_real_completion() -> None:
    store = SessionStore(id_factory=_ids("session"))
    session = store.create_session("selected-browser")
    token = store.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="speak")
    assert store.transition(token, TurnStage.SYNTHESIZING)
    playback = PlaybackQueue(store.accepts, id_factory=_ids("audio"))
    item = playback.enqueue(client_id="selected-browser", token=token, audio_ref="/audio/one", content_type="audio/wav")
    assert item is not None

    command = playback.next_command("selected-browser")
    assert command is not None and command.kind == PlaybackCommandKind.PLAY
    assert not playback.acknowledge(PlaybackAck(item.playback_id, "other-browser", PlaybackState.STARTED))
    assert playback.acknowledge(PlaybackAck(item.playback_id, "selected-browser", PlaybackState.STARTED))
    assert playback.get(item.playback_id).state == PlaybackState.STARTED
    assert playback.acknowledge(PlaybackAck(item.playback_id, "selected-browser", PlaybackState.COMPLETED))
    assert playback.get(item.playback_id).state == PlaybackState.COMPLETED


def test_cancel_stops_active_and_queued_playback_and_rejects_stale_audio() -> None:
    store = SessionStore(id_factory=_ids("session"))
    session = store.create_session("browser")
    token = store.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="long answer")
    playback = PlaybackQueue(store.accepts, id_factory=_ids("audio"))
    active = playback.enqueue(client_id="browser", token=token, audio_ref="/audio/active", content_type="audio/wav")
    queued = playback.enqueue(client_id="browser", token=token, audio_ref="/audio/queued", content_type="audio/wav")
    assert active is not None and queued is not None
    assert playback.next_command("browser").playback_id == active.playback_id
    assert playback.acknowledge(PlaybackAck(active.playback_id, "browser", PlaybackState.STARTED))

    store.cancel(session.session_id)
    assert set(playback.cancel_session(session.session_id)) == {active.playback_id, queued.playback_id}
    stop = playback.next_command("browser")
    assert stop is not None and stop.kind == PlaybackCommandKind.STOP and stop.playback_id == active.playback_id
    assert not playback.acknowledge(PlaybackAck(active.playback_id, "browser", PlaybackState.COMPLETED))
    assert playback.next_command("browser") is None
    assert playback.enqueue(client_id="browser", token=token, audio_ref="/audio/late", content_type="audio/wav") is None


def test_close_clears_private_history_and_invalidates_tokens() -> None:
    store = SessionStore(id_factory=_ids())
    session = store.create_session("tab")
    token = store.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="do not retain")
    store.close_session(session.session_id)

    assert store.private_history(session.session_id) == ()
    assert not store.accepts(token)
    assert store.safe_export(session.session_id)["active"] is False
