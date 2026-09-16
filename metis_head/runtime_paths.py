"""Shared writable per-user runtime path resolution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


def state_root(env: Mapping[str, str] | None = None) -> Path:
    values = os.environ if env is None else env
    explicit = str(values.get("METIS_STATE_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    if os.name == "nt":
        base = values.get("LOCALAPPDATA") or values.get("APPDATA")
        if base:
            return (Path(base) / "MetisHead").resolve()
    xdg = values.get("XDG_STATE_HOME")
    if xdg:
        return (Path(xdg) / "metis-head").expanduser().resolve()
    return (Path.home() / ".local" / "state" / "metis-head").resolve()


def connections_path(env: Mapping[str, str] | None = None) -> Path:
    values = os.environ if env is None else env
    explicit = str(values.get("METIS_CONNECTIONS_FILE") or "").strip()
    return Path(explicit).expanduser().resolve() if explicit else state_root(values) / "connections.json"


def usage_path(env: Mapping[str, str] | None = None) -> Path:
    values = os.environ if env is None else env
    explicit = str(values.get("METIS_USAGE_FILE") or "").strip()
    return Path(explicit).expanduser().resolve() if explicit else state_root(values) / "usage.json"
