from __future__ import annotations

from pathlib import Path
import subprocess


def test_dynamic_setup_connections_render_and_remove_in_node() -> None:
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        ["node", str(root / "tests" / "node_setup_connections.cjs")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "setup connections ok" in completed.stdout
