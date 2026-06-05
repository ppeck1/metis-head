from __future__ import annotations

from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def ensure_export_has_git_checkout() -> None:
    if (ROOT / ".git").exists():
        return
    subprocess.run(["git", "init"], cwd=ROOT, capture_output=True, text=True, check=True)


@pytest.fixture(autouse=True)
def configure_metis_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METIS_REPO_ROOT", str(ROOT))
