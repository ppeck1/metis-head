from __future__ import annotations

from pathlib import Path
from hashlib import sha1
import subprocess
from typing import Any


class ReadOnlyToolError(ValueError):
    pass


ALLOWED_TEXT_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
MAX_FILE_PREVIEW_BYTES = 32_768


def execute_filesystem_read(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments if isinstance(arguments, dict) else {}
    path = _allowed_file(args.get("path"))
    data = path.read_bytes()
    if len(data) > MAX_FILE_PREVIEW_BYTES:
        raise ReadOnlyToolError("file exceeds Phase 0F preview size limit")
    text = data.decode("utf-8", errors="replace")
    lines = [_redact_line(line)[:160] for line in text.splitlines()[:12]]
    return {
        "path": str(path),
        "extension": path.suffix.lower(),
        "byte_count": len(data),
        "line_count": len(text.splitlines()),
        "content_hash": sha1(data).hexdigest()[:16],
        "preview_lines": lines,
    }


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


def _allowed_file(raw_path: Any) -> Path:
    if not raw_path:
        raise ReadOnlyToolError("path is required")
    path = Path(str(raw_path)).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    resolved = path.resolve()
    allowed_root = Path.cwd().resolve()
    if allowed_root not in (resolved, *resolved.parents):
        raise ReadOnlyToolError("path is outside the Phase 0F allowlist")
    if not resolved.is_file():
        raise ReadOnlyToolError("path is not a file")
    if resolved.suffix.lower() not in ALLOWED_TEXT_EXTENSIONS:
        raise ReadOnlyToolError("file extension is outside the Phase 0F allowlist")
    return resolved


def _redact_line(line: str) -> str:
    lowered = line.lower()
    if any(marker in lowered for marker in ("token", "password", "secret", "credential", "api_key", "apikey")):
        return "[redacted]"
    return line
