from __future__ import annotations

from itertools import count

import pytest

from metis_head.audio import PlaybackAck, PlaybackCommandKind, PlaybackQueue, PlaybackState
from metis_head.conversation import SessionContext, SessionStore, TurnOrigin, TurnStage, TurnToken


def _ids(prefix: str = "id"):
    values = count(1)
    return lambda: f"{prefix}-{next(values)}"


def test_unknown_turn_cancellation_does_not_invalidate_live_work() -> None:
    store = SessionStore(id_factory=_ids())
    session = store.create_session("tab")
    token = store.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="keep working")
    with pytest.raises(KeyError, match="unknown turn"):
        store.cancel(session.session_id, turn_id="not-this-turn")
    assert store.accepts(token)


def test_more_than_32_sequential_closed_sessions_do_not_exhaust_capacity() -> None:
    store = SessionStore(max_sessions=4, id_factory=_ids())
    for index in range(40):
        session = store.create_session(f"tab-{index}")
        store.close_session(session.session_id)
    assert store.create_session("current-tab").active


def test_all_active_sessions_still_enforce_capacity_bound() -> None:
    store = SessionStore(max_sessions=2, id_factory=_ids())
    store.create_session("one")
    store.create_session("two")
    with pytest.raises(RuntimeError, match="capacity"):
        store.create_session("three")


def test_playback_cancel_blocks_late_audio_for_cancelled_generation() -> None:
    store = SessionStore(id_factory=_ids("session"))
    session = store.create_session("browser")
    token = store.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="answer")
    playback = PlaybackQueue(store.accepts, id_factory=_ids("audio"))
    assert playback.enqueue(client_id="browser", token=token, audio_ref="/audio/first", content_type="audio/wav")
    playback.cancel_session(session.session_id, through_generation=token.generation)
    assert playback.enqueue(client_id="browser", token=token, audio_ref="/audio/late", content_type="audio/wav") is None


@pytest.mark.parametrize("invalid", ["", "   ", "x" * 12_001])
def test_invalid_message_does_not_mutate_session_or_block_next_turn(invalid: str) -> None:
    store = SessionStore(id_factory=_ids())
    session = store.create_session("tab")
    with pytest.raises(ValueError):
        store.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text=invalid)
    snapshot = store.snapshot(session.session_id)
    assert snapshot.turns == ()
    assert snapshot.history_count == 0
    assert store.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="valid")


def test_terminalize_supports_text_preserving_no_artifact_and_failure_paths() -> None:
    store = SessionStore(id_factory=_ids())
    session = store.create_session("tab")
    no_artifact = store.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="speak")
    assert store.commit_assistant_text(no_artifact, "text survives")
    assert store.transition(no_artifact, TurnStage.SYNTHESIZING)
    assert store.terminalize(no_artifact, TurnStage.COMPLETED, failure_code="speech_unavailable")
    assert store.snapshot(session.session_id).turns[-1].failure_code == "speech_unavailable"

    failed = store.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="provider")
    assert store.terminalize(failed, TurnStage.FAILED, failure_code="provider_error")
    assert store.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="next")


def test_context_updates_are_atomic_bounded_and_backwards_compatible() -> None:
    store = SessionStore(id_factory=_ids())
    session = store.create_session(
        "tab",
        context=SessionContext(account_id="account", project_id="project", timezone="America/New_York"),
    )
    updated = store.update_context(session.session_id, calendar_ids=["primary", "primary", "work"])
    assert updated.context == SessionContext(
        account_id="account",
        project_id="project",
        timezone="America/New_York",
        calendar_ids=("primary", "work"),
    )
    cleared = store.update_context(session.session_id, project_id=None, timezone="UTC")
    assert cleared.context.project_id is None
    assert cleared.context.account_id == "account"
    assert cleared.context.calendar_ids == ("primary", "work")


def test_pre_start_failure_and_duplicate_ack_are_accepted_and_release_queue() -> None:
    store = SessionStore(id_factory=_ids("session"))
    session = store.create_session("browser")
    first = store.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="first")
    playback = PlaybackQueue(store.accepts, id_factory=_ids("audio"))
    item = playback.enqueue(client_id="browser", token=first, audio_ref="/one", content_type="audio/wav")
    assert item is not None
    assert playback.next_command("browser").playback_id == item.playback_id
    failed = PlaybackAck(item.playback_id, "browser", PlaybackState.FAILED, "autoplay_rejected")
    assert playback.acknowledge(failed)
    assert playback.acknowledge(failed)
    assert playback.get(item.playback_id).failure_code == "autoplay_rejected"


def test_duplicate_lifecycle_acknowledgements_are_idempotent_without_reopening_turn() -> None:
    store = SessionStore(id_factory=_ids())
    session = store.create_session("browser")
    token = store.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="answer")
    assert store.transition(token, TurnStage.COMPLETED)
    assert store.transition(token, TurnStage.COMPLETED)
    assert not store.transition(token, TurnStage.FAILED, failure_code="late_failure")
    assert store.snapshot(session.session_id).turns[-1].stage is TurnStage.COMPLETED


def test_stop_command_can_be_drained_before_next_play() -> None:
    store = SessionStore(id_factory=_ids("session"))
    session = store.create_session("browser")
    old = store.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="old")
    playback = PlaybackQueue(store.accepts, id_factory=_ids("audio"))
    old_item = playback.enqueue(client_id="browser", token=old, audio_ref="/old", content_type="audio/wav")
    assert old_item is not None
    assert playback.next_command("browser").kind is PlaybackCommandKind.PLAY
    store.cancel(session.session_id)
    playback.cancel_session(session.session_id, through_generation=old.generation)

    new = store.begin_turn(session.session_id, origin=TurnOrigin.TEXT, user_text="new")
    new_item = playback.enqueue(client_id="browser", token=new, audio_ref="/new", content_type="audio/wav")
    assert new_item is not None
    assert playback.next_command("browser").kind is PlaybackCommandKind.STOP
    command = playback.next_command("browser")
    assert command is not None and command.kind is PlaybackCommandKind.PLAY
    assert command.playback_id == new_item.playback_id


def test_playback_terminal_items_and_tombstones_are_bounded() -> None:
    current_tokens = set()
    playback = PlaybackQueue(
        lambda token: token in current_tokens,
        max_terminal_items=2,
        max_session_tombstones=2,
        id_factory=_ids("audio"),
    )
    identifiers = []
    for index in range(5):
        token = TurnToken(f"s-{index}", f"t-{index}", 0)
        current_tokens.add(token)
        item = playback.enqueue(client_id="browser", token=token, audio_ref=f"/{index}", content_type="audio/wav")
        assert item is not None
        identifiers.append(item.playback_id)
        playback.cancel_session(token.session_id, through_generation=0)
    with pytest.raises(KeyError):
        playback.get(identifiers[0])
    assert playback.get(identifiers[-1]).state is PlaybackState.CANCELLED

    # The oldest session tombstone was evicted, while the most recent still
    # rejects a late artifact from its cancelled generation.
    assert playback.enqueue(
        client_id="browser", token=TurnToken("s-0", "fresh", 0), audio_ref="/evicted", content_type="audio/wav"
    ) is None  # token predicate still rejects an unknown turn
    assert playback.enqueue(
        client_id="browser", token=TurnToken("s-4", "t-4", 0), audio_ref="/late", content_type="audio/wav"
    ) is None
