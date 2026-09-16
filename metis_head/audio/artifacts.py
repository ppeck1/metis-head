from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioArtifact:
    artifact_id: str
    content_type: str
    data: bytes
    created_at: float
    session_id: str | None = None
    turn_id: str | None = None
    generation: int | None = None


class AudioArtifactStore:
    """Short-lived bounded memory store; audio is never written to durable state."""

    def __init__(self, *, max_items: int = 8, max_total_bytes: int = 24_000_000, ttl_seconds: int = 300) -> None:
        self.max_items = max_items
        self.max_total_bytes = max_total_bytes
        self.ttl_seconds = ttl_seconds
        self._items: OrderedDict[str, AudioArtifact] = OrderedDict()
        self._lock = threading.RLock()

    def put(self, data: bytes, content_type: str = "audio/wav") -> str:
        if not data or len(data) > self.max_total_bytes:
            raise ValueError("audio artifact is empty or exceeds the store bound")
        with self._lock:
            self._prune()
            artifact_id = secrets.token_urlsafe(24)
            self._items[artifact_id] = AudioArtifact(artifact_id, content_type, bytes(data), time.monotonic())
            while len(self._items) > self.max_items or self._total_bytes() > self.max_total_bytes:
                self._items.popitem(last=False)
            return artifact_id

    def bind(self, artifact_id: str, *, session_id: str, turn_id: str, generation: int) -> bool:
        with self._lock:
            self._prune()
            artifact = self._items.get(artifact_id)
            if artifact is None:
                return False
            self._items[artifact_id] = AudioArtifact(
                artifact.artifact_id,
                artifact.content_type,
                artifact.data,
                artifact.created_at,
                session_id,
                turn_id,
                generation,
            )
            return True

    def consume(self, artifact_id: str, *, session_id: str | None = None) -> AudioArtifact | None:
        with self._lock:
            self._prune()
            artifact = self._items.get(artifact_id)
            if artifact is None:
                return None
            if artifact.session_id is not None and artifact.session_id != session_id:
                return None
            return self._items.pop(artifact_id)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def _prune(self) -> None:
        cutoff = time.monotonic() - self.ttl_seconds
        for key in [key for key, item in self._items.items() if item.created_at < cutoff]:
            self._items.pop(key, None)

    def _total_bytes(self) -> int:
        return sum(len(item.data) for item in self._items.values())


AUDIO_ARTIFACTS = AudioArtifactStore()
