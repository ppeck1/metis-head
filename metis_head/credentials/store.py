from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any


class SecretStoreUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ConnectionRecord:
    connection_id: str
    provider: str
    account_id: str
    scopes: tuple[str, ...]
    status: str
    updated_at: str
    access_metadata_version: int = 1
    allowed_calendar_ids: tuple[str, ...] | None = None
    selected_calendar_ids: tuple[str, ...] = ()


class CredentialStore:
    """Persists non-secret connection metadata; tokens stay in the OS keyring."""

    def __init__(self, metadata_path: str | Path, service_name: str = "metis-head") -> None:
        self.metadata_path = Path(metadata_path)
        self.service_name = service_name
        self._lock = RLock()
        self._lock_path = self.metadata_path.with_suffix(self.metadata_path.suffix + ".lock")

    def connect(self, provider: str, account_id: str, scopes: list[str], secret: str) -> ConnectionRecord:
        if not secret:
            raise ValueError("credential secret is required")
        connection_id = f"{provider}:{account_id}"
        with self._transaction():
            records = self._records()
            previous = records.get(connection_id)
            self._set_secret(connection_id, secret)
            record = ConnectionRecord(
                connection_id=connection_id,
                provider=provider,
                account_id=account_id,
                scopes=tuple(sorted(set(scopes))),
                status="connected",
                updated_at=datetime.now(timezone.utc).isoformat(),
                access_metadata_version=previous.access_metadata_version if previous else 1,
                allowed_calendar_ids=previous.allowed_calendar_ids if previous else None,
                selected_calendar_ids=previous.selected_calendar_ids if previous else (),
            )
            records[connection_id] = record
            self._save_records(records)
            return record

    def disconnect(self, connection_id: str) -> None:
        with self._transaction():
            self._delete_secret(connection_id)
            records = self._records()
            records.pop(connection_id, None)
            self._save_records(records)

    def secret(self, connection_id: str) -> str | None:
        keyring = self._keyring()
        return keyring.get_password(self.service_name, connection_id)

    def list_connections(self) -> list[dict[str, Any]]:
        with self._transaction():
            return [asdict(item) for item in self._records().values()]

    def update_google_selection(self, account_id: str, calendar_ids: list[str]) -> ConnectionRecord:
        connection_id = f"google:{account_id.strip()}"
        selected = tuple(dict.fromkeys(item.strip() for item in calendar_ids if isinstance(item, str) and item.strip()))
        if len(selected) > 250:
            raise ValueError("too many selected calendars")
        with self._transaction():
            records = self._records()
            try:
                record = records[connection_id]
            except KeyError as exc:
                raise KeyError(f"unknown connection: {connection_id}") from exc
            allowed = record.allowed_calendar_ids
            if allowed is not None and any(item not in allowed for item in selected):
                raise ValueError("selected calendars must be within the enforced calendar grant")
            updated = replace(
                record,
                selected_calendar_ids=selected,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            records[connection_id] = updated
            self._save_records(records)
            return updated

    def _keyring(self) -> Any:
        try:
            import keyring
        except ImportError as exc:
            raise SecretStoreUnavailable("install the 'google' extra to use the OS credential store") from exc
        return keyring

    def _set_secret(self, connection_id: str, secret: str) -> None:
        try:
            self._keyring().set_password(self.service_name, connection_id, secret)
        except Exception as exc:
            raise SecretStoreUnavailable("OS credential store is unavailable; no plaintext fallback was used") from exc

    def _delete_secret(self, connection_id: str) -> None:
        try:
            self._keyring().delete_password(self.service_name, connection_id)
        except Exception as exc:
            raise SecretStoreUnavailable("OS credential deletion failed; metadata was retained") from exc

    def _records(self) -> dict[str, ConnectionRecord]:
        if not self.metadata_path.exists():
            return {}
        data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        records: dict[str, ConnectionRecord] = {}
        for item in data.get("connections", []):
            values = {
                **item,
                "scopes": tuple(item.get("scopes", [])),
                "allowed_calendar_ids": (
                    tuple(item.get("allowed_calendar_ids", item.get("calendar_ids", [])))
                    if item.get("allowed_calendar_ids", item.get("calendar_ids")) is not None
                    else None
                ),
                "selected_calendar_ids": tuple(item.get("selected_calendar_ids", [])),
            }
            values.pop("calendar_ids", None)
            records[item["connection_id"]] = ConnectionRecord(**values)
        return records

    def _save_records(self, records: dict[str, ConnectionRecord]) -> None:
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.metadata_path.with_suffix(self.metadata_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"connections": [asdict(item) for item in records.values()]}, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.metadata_path)

    @contextmanager
    def _transaction(self):
        with self._lock:
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock_path.open("a+b") as handle:
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                _lock_file(handle)
                try:
                    yield
                finally:
                    _unlock_file(handle)


def _lock_file(handle: Any) -> None:
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock_file(handle: Any) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
