"""Deterministic, server-authoritative Google account label routing.

The resolver intentionally has no access to credentials or conversation state.
Callers supply the currently connected profiles and must validate the returned
account IDs before granting a session access to connectors.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping


_ACCOUNT_TERMS = frozenset({"calendar", "calendars", "contact", "contacts", "gmail", "inbox", "schedule"})
_MAIL_TERMS = frozenset({"email", "emails", "mail", "message", "messages"})
_READ_TERMS = frozenset({"any", "check", "find", "latest", "list", "new", "read", "recent", "search", "show", "what"})
_WRITE_TERMS = frozenset({"add", "compose", "create", "delete", "draft", "forward", "remove", "reply", "send", "update"})
_EXCLUSION = re.compile(r"\b(?:not|except|excluding|exclude|without)\b[^,;.]*$", re.IGNORECASE)
_CANCEL = re.compile(r"^\s*(?:cancel|never\s+mind|nevermind|forget\s+it|none)\s*[.!]?\s*$", re.IGNORECASE)


def normalize_label(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _routing_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9,;.]+", " ", value.casefold())).strip()


@dataclass(frozen=True, slots=True)
class AccountProfile:
    account_id: str
    label: str
    calendar_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AccountResolution:
    status: str
    matched: tuple[AccountProfile, ...] = ()
    excluded: tuple[AccountProfile, ...] = ()
    ambiguous: tuple[AccountProfile, ...] = ()
    explicit_match: bool = False
    account_request: bool = False
    cancelled: bool = False

    @property
    def requires_clarification(self) -> bool:
        return self.status == "clarification_required"


def profiles_from_setup(items: Iterable[Mapping[str, object]]) -> tuple[AccountProfile, ...]:
    profiles: list[AccountProfile] = []
    seen: set[str] = set()
    for item in items:
        account_id = str(item.get("account_id") or "").strip()
        label = str(item.get("label") or "").strip()
        if not account_id or not label or account_id in seen:
            continue
        raw_calendars = item.get("calendar_ids")
        calendars = tuple(
            str(value).strip()
            for value in (raw_calendars if isinstance(raw_calendars, (list, tuple)) else ())
            if str(value).strip()
        )
        profiles.append(AccountProfile(account_id, label, calendars))
        seen.add(account_id)
    return tuple(profiles)


def is_account_request(message: str) -> bool:
    words = set(re.findall(r"[a-z0-9]+", message.casefold()))
    if _WRITE_TERMS.intersection(words):
        return False
    return bool(_ACCOUNT_TERMS.intersection(words)) or bool(
        _MAIL_TERMS.intersection(words) and _READ_TERMS.intersection(words)
    )


def resolve_account_labels(
    message: str,
    profiles: Iterable[AccountProfile],
    *,
    require_selection: bool | None = None,
) -> AccountResolution:
    """Resolve full labels and aliases that identify exactly one profile.

    Full labels win over aliases, so a shared word inside ``Professional
    Nursing`` cannot also select ``Professional Photography``. A shared alias
    used on its own is ambiguous. Exclusion scopes never contribute authority.
    """

    clean_message = message.strip()
    available = tuple(profiles)
    if _CANCEL.fullmatch(clean_message):
        return AccountResolution("cancelled", cancelled=True)
    normalized_message = _routing_text(clean_message)
    account_request = is_account_request(clean_message) if require_selection is None else require_selection
    if not available:
        return AccountResolution("no_profiles", account_request=account_request)

    label_words = {profile: tuple(normalize_label(profile.label).split()) for profile in available}
    alias_owners: dict[str, set[AccountProfile]] = {}
    for profile, words in label_words.items():
        # Slash-separated names are deliberate aliases (for example
        # ``Personal / Main``); individual words are accepted only when unique.
        candidates = {word for word in words if len(word) >= 3}
        for component in re.split(r"\s*/\s*", profile.label):
            alias = normalize_label(component)
            if alias and alias != normalize_label(profile.label):
                candidates.add(alias)
        for alias in candidates:
            alias_owners.setdefault(alias, set()).add(profile)

    occupied: list[tuple[int, int]] = []
    mentions: list[tuple[int, int, tuple[AccountProfile, ...]]] = []
    # Work against normalized text so punctuation cannot make matching broader.
    for profile in sorted(available, key=lambda item: len(normalize_label(item.label)), reverse=True):
        label = normalize_label(profile.label)
        if not label:
            continue
        for match in re.finditer(rf"(?<![a-z0-9]){re.escape(label)}(?![a-z0-9])", normalized_message):
            span = match.span()
            if not any(_overlap(span, prior) for prior in occupied):
                mentions.append((*span, (profile,)))
                occupied.append(span)

    for alias, owners in sorted(alias_owners.items(), key=lambda item: len(item[0]), reverse=True):
        for match in re.finditer(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", normalized_message):
            span = match.span()
            if any(_overlap(span, prior) for prior in occupied):
                continue
            mentions.append((*span, tuple(sorted(owners, key=lambda item: item.label.casefold()))))
            occupied.append(span)

    selected: list[AccountProfile] = []
    excluded: list[AccountProfile] = []
    ambiguous: list[AccountProfile] = []
    for start, _end, owners in sorted(mentions):
        is_excluded = bool(_EXCLUSION.search(normalized_message[:start]))
        target = excluded if is_excluded else (selected if len(owners) == 1 else ambiguous)
        for owner in owners:
            if owner not in target:
                target.append(owner)

    excluded_ids = {profile.account_id for profile in excluded}
    selected = [profile for profile in selected if profile.account_id not in excluded_ids]
    ambiguous = [profile for profile in ambiguous if profile.account_id not in excluded_ids]
    if ambiguous:
        candidates = _ordered_union(selected, ambiguous)
        return AccountResolution(
            "clarification_required",
            excluded=tuple(excluded),
            ambiguous=tuple(candidates),
            explicit_match=bool(mentions),
            account_request=True,
        )
    if selected:
        return AccountResolution(
            "matched",
            matched=tuple(selected),
            excluded=tuple(excluded),
            explicit_match=True,
            account_request=True,
        )
    if account_request:
        remaining = tuple(profile for profile in available if profile.account_id not in excluded_ids)
        if len(remaining) == 1:
            return AccountResolution(
                "sole_profile",
                matched=remaining,
                excluded=tuple(excluded),
                account_request=True,
            )
        return AccountResolution(
            "clarification_required",
            excluded=tuple(excluded),
            ambiguous=remaining,
            account_request=True,
        )
    return AccountResolution("not_account_request", excluded=tuple(excluded), account_request=False)


def _overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _ordered_union(*groups: Iterable[AccountProfile]) -> list[AccountProfile]:
    result: list[AccountProfile] = []
    seen: set[str] = set()
    for group in groups:
        for profile in group:
            if profile.account_id not in seen:
                result.append(profile)
                seen.add(profile.account_id)
    return result
