"""Sanitized source identity for local runtime/evidence attribution."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


def build_info(root: Path | None = None) -> dict[str, object]:
    repository = (root or Path(__file__).resolve().parents[1]).resolve()
    explicit = os.environ.get("METIS_BUILD_ID", "").strip()
    revision = explicit or _git(repository, "rev-parse", "HEAD") or "unknown"
    branch = _git(repository, "branch", "--show-current") or "unknown"
    dirty = bool(_git(repository, "status", "--porcelain"))
    short = revision[:12] if revision != "unknown" else revision
    return {
        "schema": "metis.build.v1",
        "build_id": f"{short}{'+working' if dirty else ''}",
        "revision": revision,
        "branch": branch,
        "working_tree_modified": dirty,
    }


def _git(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments], cwd=root, capture_output=True, text=True, timeout=2, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


__all__ = ["build_info"]
