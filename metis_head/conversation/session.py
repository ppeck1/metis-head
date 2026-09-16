"""In-memory session and turn lifecycle for private conversational context.

Raw utterances intentionally live here rather than in the event/audit state.  The
store is process-local, bounded, and has no persistence hooks.  Callers should use
``safe_export`` for diagnostics and never serialize ``private_history``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Callable, Deque, Iterable, Mapping
from uuid import uuid4


Clock = Callable[[], datetime]
IdFactory = Callable[[], str]
_UNSET = object()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TurnOrigin(StrEnum):
    TEXT = "text"
    VOICE = "voice"


class TurnStage(StrEnum):
    CAPTURING = "capturing"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SYNTHESIZING = "synthesizing"
    PLAYBACK_QUEUED = "playback_queued"
    PLAYING = "playing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


TERMINAL_STAGES = frozenset({TurnStage.COMPLETED, TurnStage.CANCELLED, TurnStage.FAILED})

_TRANSITIONS: dict[TurnStage, frozenset[TurnStage]] = {
    TurnStage.CAPTURING: frozenset({TurnStage.TRANSCRIBING, TurnStage.THINKING, TurnStage.CANCELLED, TurnStage.FAILED}),
    TurnStage.TRANSCRIBING: frozenset({TurnStage.THINKING, TurnStage.CANCELLED, TurnStage.FAILED}),
    TurnStage.THINKING: frozenset({TurnStage.SYNTHESIZING, TurnStage.COMPLETED, TurnStage.CANCELLED, TurnStage.FAILED}),
    # Synthesis may intentionally produce no artifact (muted output, a text-only
    # provider, or a recoverable speech failure after text was committed).
    TurnStage.SYNTHESIZING: frozenset(
        {TurnStage.PLAYBACK_QUEUED, TurnStage.COMPLETED, TurnStage.CANCELLED, TurnStage.FAILED}
    ),
    TurnStage.PLAYBACK_QUEUED: frozenset({TurnStage.PLAYING, TurnStage.CANCELLED, TurnStage.FAILED}),
    TurnStage.PLAYING: frozenset({TurnStage.COMPLETED, TurnStage.CANCELLED, TurnStage.FAILED}),
    TurnStage.COMPLETED: frozenset(),
    TurnStage.CANCELLED: frozenset(),
    TurnStage.FAILED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class TurnToken:
    """Capability-like identity required when committing asynchronous work."""

    session_id: str
    turn_id: str
    generation: int


@dataclass(frozen=True, slots=True)
class SessionContext:
    account_id: str | None = None
    project_id: str | None = None
    timezone: str | None = None
    calendar_ids: tuple[str, ...] = ()
    account_ids: tuple[str, ...] = ()
    calendars_by_account: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    role: str
    text: str
    turn_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TurnSnapshot:
    turn_id: str
    generation: int
    origin: TurnOrigin
    stage: TurnStage
    created_at: datetime
    updated_at: datetime
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    session_id: str
    client_id: str
    generation: int
    active: bool
    context: SessionContext
    turns: tuple[TurnSnapshot, ...]
    history_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class _Session:
    session_id: str
    client_id: str
    generation: int
    active: bool
    context: SessionContext
    turns: Deque[TurnSnapshot]
    history: Deque[ConversationMessage]
    pending_account_request: str | None
    created_at: datetime
    updated_at: datetime


class SessionStore:
    """Thread-safe, process-private, bounded session storage.

    Session IDs are never inferred from client IDs.  A client must present the
    assigned session ID, which prevents accidental cross-tab state sharing.
    """

    def __init__(
        self,
        *,
        max_sessions: int = 32,
        max_turns: int = 32,
        max_history_messages: int = 24,
        max_message_chars: int = 12_000,
        clock: Clock = _utc_now,
        id_factory: IdFactory | None = None,
    ) -> None:
        if min(max_sessions, max_turns, max_history_messages, max_message_chars) < 1:
            raise ValueError("session bounds must be positive")
        self._max_sessions = max_sessions
        self._max_turns = max_turns
        self._max_history_messages = max_history_messages
        self._max_message_chars = max_message_chars
        self._clock = clock
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._sessions: dict[str, _Session] = {}
        self._lock = RLock()

    def create_session(self, client_id: str, *, context: SessionContext | None = None) -> SessionSnapshot:
        client_id = client_id.strip()
        if not client_id:
            raise ValueError("client_id is required")
        with self._lock:
            if len(self._sessions) >= self._max_sessions:
                self._evict_oldest_closed()
            now = self._clock()
            session_id = self._new_unique_id(self._sessions)
            session = _Session(
                session_id=session_id,
                client_id=client_id,
                generation=0,
                active=True,
                context=self._normalize_context(context or SessionContext()),
                turns=deque(maxlen=self._max_turns),
                history=deque(maxlen=self._max_history_messages),
                pending_account_request=None,
                created_at=now,
                updated_at=now,
            )
            self._sessions[session_id] = session
            return self._snapshot(session)

    def begin_turn(
        self,
        session_id: str,
        *,
        origin: TurnOrigin,
        user_text: str | None = None,
        initial_stage: TurnStage | None = None,
    ) -> TurnToken:
        # Validate caller-controlled content before mutating the session.  An
        # invalid message must not leave an active turn behind.
        clean_user_text = self._clean_message(user_text) if user_text is not None else None
        stage = initial_stage or (
            TurnStage.CAPTURING if origin == TurnOrigin.VOICE and clean_user_text is None else TurnStage.THINKING
        )
        if stage in TERMINAL_STAGES:
            raise ValueError("a turn cannot begin in a terminal stage")
        with self._lock:
            session = self._require_active(session_id)
            if any(turn.stage not in TERMINAL_STAGES for turn in session.turns):
                raise RuntimeError("session already has an active turn")
            now = self._clock()
            turn_id = self._new_unique_id({turn.turn_id: turn for turn in session.turns})
            turn = TurnSnapshot(turn_id, session.generation, origin, stage, now, now)
            session.turns.append(turn)
            session.updated_at = now
            if clean_user_text is not None:
                self._append_clean_message(session, "user", clean_user_text, turn_id, now)
            return TurnToken(session_id, turn_id, session.generation)

    def update_context(
        self,
        session_id: str,
        *,
        account_id: str | None | object = _UNSET,
        project_id: str | None | object = _UNSET,
        timezone: str | None | object = _UNSET,
        calendar_ids: Iterable[str] | None = None,
        account_ids: Iterable[str] | None = None,
        calendars_by_account: Mapping[str, Iterable[str]] | None = None,
        clear_history: bool = False,
    ) -> SessionSnapshot:
        """Atomically replace selectable context for an active session.

        Omitted scalar values and ``calendar_ids`` preserve prior selections;
        explicit ``None`` clears a scalar and an empty iterable clears calendars.
        """
        with self._lock:
            session = self._require_active(session_id)
            candidate = SessionContext(
                account_id=session.context.account_id if account_id is _UNSET else account_id,  # type: ignore[arg-type]
                project_id=session.context.project_id if project_id is _UNSET else project_id,  # type: ignore[arg-type]
                timezone=session.context.timezone if timezone is _UNSET else timezone,  # type: ignore[arg-type]
                calendar_ids=session.context.calendar_ids if calendar_ids is None else tuple(calendar_ids),
                account_ids=session.context.account_ids if account_ids is None else tuple(account_ids),
                calendars_by_account=(
                    session.context.calendars_by_account
                    if calendars_by_account is None
                    else tuple((key, tuple(values)) for key, values in calendars_by_account.items())
                ),
            )
            session.context = self._normalize_context(candidate)
            if clear_history:
                session.history.clear()
            session.updated_at = self._clock()
            return self._snapshot(session)

    def set_pending_account_request(self, session_id: str, text: str) -> None:
        """Retain one unresolved request only in process-private session memory."""
        clean = self._clean_message(text)
        with self._lock:
            session = self._require_active(session_id)
            session.pending_account_request = clean
            session.updated_at = self._clock()

    def pending_account_request(self, session_id: str) -> str | None:
        with self._lock:
            return self._require_active(session_id).pending_account_request

    def clear_pending_account_request(self, session_id: str) -> None:
        with self._lock:
            session = self._require_active(session_id)
            session.pending_account_request = None
            session.updated_at = self._clock()

    def transition(self, token: TurnToken, stage: TurnStage, *, failure_code: str | None = None) -> bool:
        """Advance a current turn; return False for cancelled/stale late work."""
        with self._lock:
            session = self._sessions.get(token.session_id)
            if not self._accepts_locked(session, token):
                # A matching terminal acknowledgement may be retried after the
                # originating token stopped accepting new work.  Repeating the
                # exact recorded terminal outcome is idempotent; it does not
                # reopen the turn or accept a different late result.
                if session is not None:
                    try:
                        _, recorded = self._find_turn(session, token.turn_id)
                    except KeyError:
                        recorded = None
                    if (
                        recorded is not None
                        and recorded.generation == token.generation
                        and recorded.stage == stage
                        and stage in TERMINAL_STAGES
                    ):
                        return True
                return False
            index, current = self._find_turn(session, token.turn_id)
            if current.stage == stage:
                return True
            if stage not in _TRANSITIONS[current.stage]:
                raise ValueError(f"invalid turn transition: {current.stage} -> {stage}")
            now = self._clock()
            session.turns[index] = replace(current, stage=stage, updated_at=now, failure_code=failure_code)
            session.updated_at = now
            return True

    def terminalize(
        self,
        token: TurnToken,
        stage: TurnStage,
        *,
        failure_code: str | None = None,
    ) -> bool:
        """Finish current work through one explicitly legal outcome.

        Completion remains stage-sensitive through ``_TRANSITIONS``.  Failure
        is legal from every nonterminal stage.  Cancellation also invalidates
        the generation, preventing late asynchronous work from committing.
        """
        if stage not in TERMINAL_STAGES:
            raise ValueError("terminal outcome is required")
        if stage is TurnStage.CANCELLED:
            with self._lock:
                session = self._sessions.get(token.session_id)
                if not self._accepts_locked(session, token):
                    return False
                self.cancel(token.session_id, turn_id=token.turn_id)
                return True
        return self.transition(token, stage, failure_code=failure_code)

    def set_transcript(self, token: TurnToken, text: str) -> bool:
        """Store a spoken transcript privately without adding it to safe exports."""
        with self._lock:
            session = self._sessions.get(token.session_id)
            if not self._accepts_locked(session, token):
                return False
            now = self._clock()
            self._append_message(session, "user", text, token.turn_id, now)
            session.updated_at = now
            return True

    def commit_assistant_text(self, token: TurnToken, text: str) -> bool:
        """Commit model output only while the originating generation is current."""
        with self._lock:
            session = self._sessions.get(token.session_id)
            if not self._accepts_locked(session, token):
                return False
            now = self._clock()
            self._append_message(session, "assistant", text, token.turn_id, now)
            session.updated_at = now
            return True

    def cancel(self, session_id: str, *, turn_id: str | None = None) -> int:
        """Invalidate all outstanding tokens and cancel the active matching turn."""
        with self._lock:
            session = self._require(session_id)
            if turn_id is not None:
                _, target = self._find_turn(session, turn_id)
                if target.stage in TERMINAL_STAGES:
                    return session.generation
            now = self._clock()
            session.generation += 1
            for index, turn in enumerate(session.turns):
                if turn.stage not in TERMINAL_STAGES and (turn_id is None or turn.turn_id == turn_id):
                    session.turns[index] = replace(turn, stage=TurnStage.CANCELLED, updated_at=now)
            session.updated_at = now
            return session.generation

    def close_session(self, session_id: str) -> None:
        with self._lock:
            session = self._require(session_id)
            self.cancel(session_id)
            session.active = False
            session.history.clear()
            session.pending_account_request = None
            session.updated_at = self._clock()

    def accepts(self, token: TurnToken) -> bool:
        with self._lock:
            return self._accepts_locked(self._sessions.get(token.session_id), token)

    def private_history(self, session_id: str) -> tuple[ConversationMessage, ...]:
        with self._lock:
            return tuple(self._require(session_id).history)

    def snapshot(self, session_id: str) -> SessionSnapshot:
        with self._lock:
            return self._snapshot(self._require(session_id))

    def safe_export(self, session_id: str) -> dict[str, object]:
        """Return diagnostics containing metadata only, never transcript content."""
        snapshot = self.snapshot(session_id)
        return {
            "schema": "metis.session.safe-export.v1",
            "session_id": snapshot.session_id,
            "client_id": snapshot.client_id,
            "generation": snapshot.generation,
            "active": snapshot.active,
            "context": {
                "account_selected": snapshot.context.account_id is not None,
                "selected_account_count": len(snapshot.context.account_ids),
                "project_selected": snapshot.context.project_id is not None,
            },
            "history": [
                {"role": item.role, "turn_id": item.turn_id, "text": "[REDACTED]", "character_count": len(item.text)}
                for item in self.private_history(session_id)
            ],
            "pending_account_clarification": snapshot.active and self.pending_account_request(session_id) is not None,
            "turns": [
                {
                    "turn_id": turn.turn_id,
                    "generation": turn.generation,
                    "origin": turn.origin.value,
                    "stage": turn.stage.value,
                    "failure_code": turn.failure_code,
                }
                for turn in snapshot.turns
            ],
        }

    def _append_message(self, session: _Session, role: str, text: str, turn_id: str, now: datetime) -> None:
        if role not in {"user", "assistant", "tool"}:
            raise ValueError("unsupported conversation role")
        clean = self._clean_message(text)
        self._append_clean_message(session, role, clean, turn_id, now)

    def _clean_message(self, text: str) -> str:
        if not isinstance(text, str):
            raise ValueError("message text is required")
        clean = text.strip()
        if not clean:
            raise ValueError("message text is required")
        if len(clean) > self._max_message_chars:
            raise ValueError("message exceeds private history limit")
        return clean

    @staticmethod
    def _append_clean_message(session: _Session, role: str, clean: str, turn_id: str, now: datetime) -> None:
        session.history.append(ConversationMessage(role, clean, turn_id, now))

    @staticmethod
    def _normalize_context(context: SessionContext) -> SessionContext:
        def scalar(value: str | None, label: str) -> str | None:
            if value is None:
                return None
            if not isinstance(value, str):
                raise ValueError(f"{label} must be text")
            clean = value.strip()
            if not clean:
                return None
            if len(clean) > 512:
                raise ValueError(f"{label} is too long")
            return clean

        calendars: list[str] = []
        for value in context.calendar_ids:
            clean = scalar(value, "calendar_id")
            if clean is not None and clean not in calendars:
                calendars.append(clean)
            if len(calendars) > 32:
                raise ValueError("too many selected calendars")
        accounts: list[str] = []
        for value in context.account_ids:
            clean = scalar(value, "account_id")
            if clean is not None and clean not in accounts:
                accounts.append(clean)
            if len(accounts) > 8:
                raise ValueError("too many selected accounts")
        primary = scalar(context.account_id, "account_id")
        if accounts and primary and primary not in accounts:
            raise ValueError("primary account must be within selected accounts")
        calendar_map: list[tuple[str, tuple[str, ...]]] = []
        for raw_account, raw_calendars in context.calendars_by_account:
            clean_account = scalar(raw_account, "account_id")
            if clean_account is None or clean_account not in accounts:
                raise ValueError("calendar account must be within selected accounts")
            clean_calendars: list[str] = []
            for value in raw_calendars:
                clean = scalar(value, "calendar_id")
                if clean is not None and clean not in clean_calendars:
                    clean_calendars.append(clean)
                if len(clean_calendars) > 32:
                    raise ValueError("too many selected calendars")
            calendar_map.append((clean_account, tuple(clean_calendars)))
        if accounts and primary and calendars and not any(item[0] == primary for item in calendar_map):
            calendar_map.append((primary, tuple(calendars)))
        return SessionContext(
            account_id=primary,
            project_id=scalar(context.project_id, "project_id"),
            timezone=scalar(context.timezone, "timezone"),
            calendar_ids=tuple(calendars),
            account_ids=tuple(accounts),
            calendars_by_account=tuple(calendar_map),
        )

    def _accepts_locked(self, session: _Session | None, token: TurnToken) -> bool:
        if session is None or not session.active or session.generation != token.generation:
            return False
        try:
            _, turn = self._find_turn(session, token.turn_id)
        except KeyError:
            return False
        return turn.generation == token.generation and turn.stage not in TERMINAL_STAGES

    @staticmethod
    def _find_turn(session: _Session, turn_id: str) -> tuple[int, TurnSnapshot]:
        for index, turn in enumerate(session.turns):
            if turn.turn_id == turn_id:
                return index, turn
        raise KeyError(f"unknown turn: {turn_id}")

    def _require(self, session_id: str) -> _Session:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"unknown session: {session_id}") from exc

    def _require_active(self, session_id: str) -> _Session:
        session = self._require(session_id)
        if not session.active:
            raise RuntimeError("session is closed")
        return session

    def _new_unique_id(self, existing: Mapping[str, object]) -> str:
        for _ in range(8):
            candidate = self._id_factory()
            if candidate and candidate not in existing:
                return candidate
        raise RuntimeError("could not allocate a unique identifier")

    def _evict_oldest_closed(self) -> None:
        closed = [session for session in self._sessions.values() if not session.active]
        if not closed:
            raise RuntimeError("session capacity reached; close an active session")
        oldest = min(closed, key=lambda session: session.updated_at)
        del self._sessions[oldest.session_id]

    @staticmethod
    def _snapshot(session: _Session) -> SessionSnapshot:
        return SessionSnapshot(
            session.session_id,
            session.client_id,
            session.generation,
            session.active,
            session.context,
            tuple(session.turns),
            len(session.history),
            session.created_at,
            session.updated_at,
        )
