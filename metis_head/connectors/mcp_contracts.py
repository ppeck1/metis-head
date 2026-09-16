from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Any, Mapping

from .contracts import Freshness


@dataclass(frozen=True, slots=True)
class MCPReadOutcome:
    completed: bool
    status: str
    blocked_reason: str | None
    payload: Mapping[str, Any]


def normalize_mcp_read_result(result: object) -> MCPReadOutcome:
    """Interpret MCP CallToolResult without treating isError as success."""
    if not isinstance(result, Mapping):
        return MCPReadOutcome(False, "read_error", "mcp_result_not_an_object", {})
    payload = dict(result)
    if payload.get("isError") is True:
        return MCPReadOutcome(False, "read_error", "mcp_tool_reported_error", payload)
    return MCPReadOutcome(True, "read_only_complete", None, payload)


def mcp_config_identity(server_id: str, env: Mapping[str, str]) -> str:
    """Opaque identity for cache partitioning; contains no command or secret text."""
    prefix = "METIS_MCP_BOH" if server_id == "boh" else "METIS_MCP_ATLAS"
    material = {
        "server_id": server_id,
        "command": env.get(f"{prefix}_COMMAND", ""),
        "cwd": env.get(f"{prefix}_CWD", ""),
        "args": env.get(f"{prefix}_ARGS_JSON", ""),
        "child_env": env.get(f"{prefix}_ENV_JSON", ""),
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()[:24]


def evidence_freshness(
    payload: Mapping[str, Any], *, now: datetime, stale_after_seconds: int = 86_400
) -> tuple[datetime | None, Freshness]:
    raw = payload.get("observed_at") or payload.get("updated_at")
    explicit = str(payload.get("freshness") or "").casefold()
    observed: datetime | None = None
    if isinstance(raw, str):
        try:
            observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = None
        except ValueError:
            observed = None
    if explicit in {member.value for member in Freshness}:
        return observed, Freshness(explicit)
    if payload.get("stale") is True:
        return observed, Freshness.STALE
    if observed is None:
        return None, Freshness.UNKNOWN
    state = Freshness.STALE if (now - observed).total_seconds() > stale_after_seconds else Freshness.CURRENT
    return observed, state
