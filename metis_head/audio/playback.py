"""Bounded, acknowledgement-driven client playback delivery.

This module does not play audio on the server.  It produces PLAY/STOP commands
for the session's selected client and validates acknowledgements from that client.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Callable, Deque
from uuid import uuid4

from metis_head.conversation import TurnToken


class PlaybackState(StrEnum):
    QUEUED = "queued"
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlaybackCommandKind(StrEnum):
    PLAY = "play"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class PlaybackItem:
    playback_id: str
    client_id: str
    token: TurnToken
    audio_ref: str
    content_type: str
    state: PlaybackState
    created_at: datetime
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class PlaybackCommand:
    kind: PlaybackCommandKind
    playback_id: str
    token: TurnToken
    audio_ref: str | None = None
    content_type: str | None = None


@dataclass(frozen=True, slots=True)
class PlaybackAck:
    playback_id: str
    client_id: str
    state: PlaybackState
    failure_code: str | None = None


class PlaybackQueue:
    """Per-client playback queues with explicit cancellation and stale guards."""

    def __init__(
        self,
        token_is_current: Callable[[TurnToken], bool],
        *,
        max_queued_per_client: int = 4,
        max_terminal_items: int = 128,
        max_commands_per_client: int = 8,
        max_session_tombstones: int = 128,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        if min(max_queued_per_client, max_terminal_items, max_commands_per_client, max_session_tombstones) < 1:
            raise ValueError("playback bounds must be positive")
        self._token_is_current = token_is_current
        self._max_queued = max_queued_per_client
        self._max_terminal = max_terminal_items
        self._max_commands = max_commands_per_client
        self._max_tombstones = max_session_tombstones
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._items: dict[str, PlaybackItem] = {}
        self._queued: dict[str, Deque[str]] = {}
        self._active: dict[str, str] = {}
        self._commands: dict[str, Deque[PlaybackCommand]] = {}
        self._cancelled_through: OrderedDict[str, int] = OrderedDict()
        self._terminal_ids: Deque[str] = deque()
        self._lock = RLock()

    def enqueue(self, *, client_id: str, token: TurnToken, audio_ref: str, content_type: str) -> PlaybackItem | None:
        """Return None rather than enqueue audio produced by stale work."""
        if not self._token_is_current(token):
            return None
        if not client_id.strip() or not audio_ref.strip() or not content_type.startswith("audio/"):
            raise ValueError("client_id, audio_ref, and an audio content type are required")
        with self._lock:
            if not self._token_is_current(token):
                return None
            if token.generation <= self._cancelled_through.get(token.session_id, -1):
                return None
            queue = self._queued.setdefault(client_id, deque())
            if len(queue) >= self._max_queued:
                raise RuntimeError("client playback queue is full")
            playback_id = self._unique_id()
            item = PlaybackItem(
                playback_id,
                client_id,
                token,
                audio_ref,
                content_type,
                PlaybackState.QUEUED,
                datetime.now(timezone.utc),
            )
            self._items[playback_id] = item
            queue.append(playback_id)
            return item

    def next_command(self, client_id: str) -> PlaybackCommand | None:
        """Return a pending STOP first, otherwise one current PLAY command."""
        with self._lock:
            commands = self._commands.setdefault(client_id, deque())
            if commands:
                return commands.popleft()
            if client_id in self._active:
                return None
            queue = self._queued.setdefault(client_id, deque())
            while queue:
                playback_id = queue.popleft()
                item = self._items[playback_id]
                if item.state != PlaybackState.QUEUED:
                    continue
                if not self._token_is_current(item.token):
                    self._set_terminal_locked(item, PlaybackState.CANCELLED)
                    continue
                self._active[client_id] = playback_id
                return PlaybackCommand(
                    PlaybackCommandKind.PLAY,
                    item.playback_id,
                    item.token,
                    item.audio_ref,
                    item.content_type,
                )
            return None

    def acknowledge(self, ack: PlaybackAck) -> bool:
        """Accept only acknowledgements from the assigned client and valid state."""
        with self._lock:
            item = self._items.get(ack.playback_id)
            if item is None or item.client_id != ack.client_id:
                return False
            active_id = self._active.get(ack.client_id)
            if item.state in {PlaybackState.COMPLETED, PlaybackState.FAILED, PlaybackState.CANCELLED}:
                # Network retries and duplicate browser events are harmless when
                # they repeat the terminal result already recorded.
                return ack.state is item.state
            if ack.state == PlaybackState.STARTED:
                if item.state == PlaybackState.STARTED and active_id == ack.playback_id:
                    return True
                if active_id != ack.playback_id or item.state != PlaybackState.QUEUED or not self._token_is_current(item.token):
                    return False
                self._items[ack.playback_id] = replace(item, state=PlaybackState.STARTED)
                return True
            if ack.state in {PlaybackState.COMPLETED, PlaybackState.FAILED}:
                allowed_states = {PlaybackState.STARTED}
                if ack.state is PlaybackState.FAILED:
                    # Audio.play() rejection/decode failure happens before a
                    # STARTED acknowledgement and still must release the queue.
                    allowed_states.add(PlaybackState.QUEUED)
                if active_id != ack.playback_id or item.state not in allowed_states:
                    return False
                self._set_terminal_locked(item, ack.state, failure_code=ack.failure_code)
                self._active.pop(ack.client_id, None)
                return True
            if ack.state is PlaybackState.CANCELLED:
                if active_id != ack.playback_id or item.state not in {PlaybackState.QUEUED, PlaybackState.STARTED}:
                    return False
                self._set_terminal_locked(item, PlaybackState.CANCELLED, failure_code=ack.failure_code)
                self._active.pop(ack.client_id, None)
                return True
            return False

    def cancel_session(self, session_id: str, *, through_generation: int | None = None) -> tuple[str, ...]:
        """Cancel queued/active audio and issue STOP for active client playback."""
        cancelled: list[str] = []
        with self._lock:
            generations = [item.token.generation for item in self._items.values() if item.token.session_id == session_id]
            inferred = max(generations, default=-1)
            floor = inferred if through_generation is None else through_generation
            self._remember_tombstone_locked(session_id, floor)
            affected_clients: set[str] = set()
            for playback_id, item in tuple(self._items.items()):
                if item.token.session_id != session_id or item.state in {
                    PlaybackState.COMPLETED,
                    PlaybackState.FAILED,
                    PlaybackState.CANCELLED,
                }:
                    continue
                self._set_terminal_locked(item, PlaybackState.CANCELLED)
                cancelled.append(playback_id)
                affected_clients.add(item.client_id)
                if self._active.get(item.client_id) == playback_id:
                    del self._active[item.client_id]
                    self._append_command_locked(
                        item.client_id,
                        PlaybackCommand(PlaybackCommandKind.STOP, playback_id, item.token)
                    )
            for client_id in affected_clients:
                queue = self._queued.get(client_id)
                if queue is not None:
                    self._queued[client_id] = deque(
                        item_id for item_id in queue if item_id in self._items and self._items[item_id].state is PlaybackState.QUEUED
                    )
            return tuple(cancelled)

    def get(self, playback_id: str) -> PlaybackItem:
        with self._lock:
            try:
                return self._items[playback_id]
            except KeyError as exc:
                raise KeyError(f"unknown playback: {playback_id}") from exc

    def pending_count(self, client_id: str) -> int:
        with self._lock:
            return sum(
                self._items[item_id].state == PlaybackState.QUEUED
                for item_id in self._queued.get(client_id, ())
            )

    def _unique_id(self) -> str:
        for _ in range(8):
            value = self._id_factory()
            if value and value not in self._items:
                return value
        raise RuntimeError("could not allocate a unique playback identifier")

    def _set_terminal_locked(
        self,
        item: PlaybackItem,
        state: PlaybackState,
        *,
        failure_code: str | None = None,
    ) -> None:
        bounded_code = failure_code[:256] if failure_code else None
        self._items[item.playback_id] = replace(item, state=state, failure_code=bounded_code)
        self._terminal_ids.append(item.playback_id)
        while len(self._terminal_ids) > self._max_terminal:
            expired = self._terminal_ids.popleft()
            expired_item = self._items.get(expired)
            if expired_item is not None and expired_item.state in {
                PlaybackState.COMPLETED,
                PlaybackState.FAILED,
                PlaybackState.CANCELLED,
            }:
                self._items.pop(expired, None)

    def _append_command_locked(self, client_id: str, command: PlaybackCommand) -> None:
        commands = self._commands.setdefault(client_id, deque())
        if any(existing.kind is command.kind and existing.playback_id == command.playback_id for existing in commands):
            return
        commands.append(command)
        while len(commands) > self._max_commands:
            commands.popleft()

    def _remember_tombstone_locked(self, session_id: str, generation: int) -> None:
        current = self._cancelled_through.get(session_id, -1)
        self._cancelled_through[session_id] = max(current, generation)
        self._cancelled_through.move_to_end(session_id)
        while len(self._cancelled_through) > self._max_tombstones:
            self._cancelled_through.popitem(last=False)
