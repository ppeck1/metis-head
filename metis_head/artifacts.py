from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ARTIFACT_SCHEMA_VERSION = "metis_artifact.v0.1"
ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts"
SUPPORTED_ARTIFACT_TYPES = {"export", "manifest"}


class ArtifactError(ValueError):
    pass


def artifact_dir() -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    return ARTIFACT_DIR


def save_artifact(payload: dict[str, Any], artifact_type: str, label: str | None = None) -> dict[str, Any]:
    if artifact_type not in SUPPORTED_ARTIFACT_TYPES:
        raise ArtifactError(f"unsupported artifact type: {artifact_type}")
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    stem = _safe_stem(label or artifact_type)
    filename = f"{timestamp.replace(':', '').replace('-', '')}_{artifact_type}_{stem}.json"
    path = artifact_dir() / filename
    envelope = {
        "artifact_schema": ARTIFACT_SCHEMA_VERSION,
        "artifact_type": artifact_type,
        "label": label or artifact_type,
        "created_at": timestamp,
        "payload": payload,
    }
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True), encoding="utf-8")
    return _artifact_record(path, envelope)


def list_artifacts() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(artifact_dir().glob("*.json"), reverse=True):
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(envelope, dict) and envelope.get("artifact_schema") == ARTIFACT_SCHEMA_VERSION:
            records.append(_artifact_record(path, envelope))
    return records


def read_artifact(filename: str) -> dict[str, Any]:
    if Path(filename).name != filename or not filename.endswith(".json"):
        raise ArtifactError("artifact filename must be a JSON file name, not a path")
    path = artifact_dir() / filename
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArtifactError(f"artifact not found: {filename}") from exc
    except json.JSONDecodeError as exc:
        raise ArtifactError(f"artifact is not valid JSON: {filename}") from exc
    if not isinstance(envelope, dict) or envelope.get("artifact_schema") != ARTIFACT_SCHEMA_VERSION:
        raise ArtifactError(f"artifact has unsupported schema: {filename}")
    return envelope


def _artifact_record(path: Path, envelope: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_schema": ARTIFACT_SCHEMA_VERSION,
        "filename": path.name,
        "artifact_type": envelope.get("artifact_type"),
        "label": envelope.get("label"),
        "created_at": envelope.get("created_at"),
        "size_bytes": path.stat().st_size,
    }


def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value.strip()).strip("._")
    return (stem or "artifact")[:64]
