from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any


class ReadOnlyToolError(ValueError):
    pass


def execute_git_status(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments if isinstance(arguments, dict) else {}
    repo = _allowed_repository(args.get("repository"))
    result = subprocess.run(
        ["git", "-C", str(repo), "status", "--short", "--branch"],
        capture_output=True,
        text=True,
        timeout=5,
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        raise ReadOnlyToolError("git status failed")
    lines = [line[:160] for line in result.stdout.splitlines()[:24]]
    branch = lines[0] if lines else "## unknown"
    changes = [line for line in lines[1:] if line.strip()]
    return {
        "repository": str(repo),
        "branch": branch,
        "changed_count": len(changes),
        "line_count": len(lines),
        "status_preview": changes[:12],
    }


def _allowed_repository(raw_repository: Any) -> Path:
    repo = Path(str(raw_repository or ".")).expanduser().resolve()
    allowed = Path.cwd().resolve()
    if repo != allowed:
        raise ReadOnlyToolError("repository is outside the Phase 0G allowlist")
    if not (repo / ".git").exists():
        raise ReadOnlyToolError("repository is not a git checkout")
    return repo
