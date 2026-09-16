from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


GOOGLE_ACCESS_METADATA_VERSION = 1


@dataclass(frozen=True, slots=True)
class GoogleAccountPolicy:
    """Versioned non-secret grants and interface preferences for one account.

    ``allowed_calendar_ids`` is an enforcement boundary.  A selection is only a
    preference and is required to be a subset of that boundary when one exists.
    """

    account_id: str
    granted_scopes: frozenset[str]
    allowed_calendar_ids: frozenset[str] | None = None
    selected_calendar_ids: tuple[str, ...] = ()
    version: int = GOOGLE_ACCESS_METADATA_VERSION

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "GoogleAccountPolicy":
        account_id = str(record.get("account_id") or "").strip()
        if not account_id:
            raise ValueError("Google account metadata requires account_id")
        version = int(record.get("access_metadata_version", GOOGLE_ACCESS_METADATA_VERSION))
        if version != GOOGLE_ACCESS_METADATA_VERSION:
            raise ValueError("unsupported Google access metadata version")
        scopes = frozenset(_strings(record.get("scopes", ())))
        raw_allowed = record.get("allowed_calendar_ids", record.get("calendar_ids"))
        allowed = frozenset(_strings(raw_allowed)) if _is_sequence(raw_allowed) else None
        selected = tuple(dict.fromkeys(_strings(record.get("selected_calendar_ids", ()))))
        if allowed is not None and any(item not in allowed for item in selected):
            raise ValueError("selected calendars must be within the enforced calendar grant")
        return cls(account_id, scopes, allowed, selected, version)

    def overlay(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "access_metadata_version": self.version,
            "selected_calendar_ids": list(self.selected_calendar_ids),
        }
        if self.allowed_calendar_ids is not None:
            value["allowed_calendar_ids"] = sorted(self.allowed_calendar_ids)
        return value


def _is_sequence(value: object) -> bool:
    return isinstance(value, (list, tuple, set, frozenset))


def _strings(value: object) -> tuple[str, ...]:
    if not _is_sequence(value):
        return ()
    return tuple(str(item).strip() for item in value if isinstance(item, str) and item.strip())
