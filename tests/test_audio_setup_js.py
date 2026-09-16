from __future__ import annotations

from pathlib import Path
import subprocess


def test_audio_setup_controller_in_node() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["node", str(root / "tests" / "node_audio_setup.cjs")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "audio setup controller tests passed" in result.stdout
