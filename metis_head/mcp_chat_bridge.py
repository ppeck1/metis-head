from __future__ import annotations

import hashlib
import json
import os
import re
from time import perf_counter
from typing import Any, Callable

from .control_center import build_control_center_status
from .connectors.mcp_contracts import mcp_config_identity
from .mcp_access import call_configured_mcp_tool, mcp_status


MCP_CHAT_BRIDGE_VERSION = "metis_mcp_chat_bridge.v0.1"
SERVER_LABELS = {"boh": "BOH MCP", "project_atlas": "Project Atlas MCP"}

CallMCPTool = Callable[..., dict[str, Any]]
_CACHE_TTL_SECONDS = 10.0
_CACHE_MAX_ITEMS = 16
_CACHE: dict[str, dict[str, Any]] = {}


def route_mcp_chat_read(
    message: str,
    state: dict[str, Any],
    *,
    env: dict[str, str] | None = None,
    call_tool: CallMCPTool | None = None,
) -> dict[str, Any] | None:
    intents = _classify_intents(message)
    if not intents:
        return None

    env = env or os.environ
    call_tool = call_tool or call_configured_mcp_tool
    control = build_control_center_status(state, mcp_status(env))
    results = [
        _route_single_mcp_chat_read(intent, control=control, env=env, call_tool=call_tool)
        for intent in intents
    ]
    if len(results) == 1:
        return results[0]
    return _combined_bridge_result(results)


def _route_single_mcp_chat_read(
    intent: dict[str, Any],
    *,
    control: dict[str, Any],
    env: dict[str, str],
    call_tool: CallMCPTool,
) -> dict[str, Any]:
    server_id = intent["server_id"]
    server_status = control["mcp"]["servers"][server_id]

    if intent["action"] == "write_proposal":
        return _blocked_result(
            intent,
            "mcp_write_is_proposal_only",
            (
                f"{SERVER_LABELS[server_id]} write requests remain proposal-only. "
                "No MCP write/apply action was performed; direct apply remains blocked."
            ),
            read_status=server_status.get("read_status", "unknown"),
        )

    read_status = server_status.get("read_status", "unknown")
    if read_status != "usable":
        return _blocked_result(
            intent,
            f"mcp_read_{read_status}",
            (
                f"{SERVER_LABELS[server_id]} read is not usable right now: {read_status}. "
                "Check the Tool Control Center read mode and server-side MCP configuration."
            ),
            read_status=read_status,
        )

    started = perf_counter()
    cache_key = _cache_key(server_id, intent["tool_name"], intent["arguments"], env)
    mcp = _cached_mcp_result(cache_key, started)
    cache_hit = mcp is not None
    if mcp is None:
        mcp = _call_mcp(call_tool, server_id, intent["tool_name"], intent["arguments"], env)
        _remember_mcp_result(cache_key, mcp, started)
    elapsed_ms = max(0, round((perf_counter() - started) * 1000))
    status = str(mcp.get("status") or "unknown")
    if status == "read_only_complete":
        source_state = "sourced"
        message_text = _render_success(intent, mcp, elapsed_ms, cache_hit)
    else:
        source_state = "degraded"
        reason = mcp.get("blocked_reason") or mcp.get("error") or status
        message_text = (
            f"{SERVER_LABELS[server_id]} read was attempted but did not complete: {reason}. "
            "No unsupported answer was generated."
        )

    return _bridge_result(
        intent,
        message_text,
        status=status,
        source_state=source_state,
        elapsed_ms=elapsed_ms,
        result_hash=mcp.get("result_hash"),
        blocked_reason=mcp.get("blocked_reason"),
        read_status=read_status,
        cache_hit=cache_hit,
    )

def clear_mcp_chat_cache() -> None:
    _CACHE.clear()


def _call_mcp(
    call_tool: CallMCPTool,
    server_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    env: dict[str, str],
) -> dict[str, Any]:
    return call_tool(server_id, tool_name, arguments, env=env)


def _classify_intent(message: str) -> dict[str, Any] | None:
    intents = _classify_intents(message)
    return intents[0] if intents else None


def _classify_intents(message: str) -> list[dict[str, Any]]:
    normalized = _normalize(message)
    if not normalized:
        return []
    server_ids = _servers_from_text(normalized)
    if not server_ids:
        return []
    if not _mentions_read_or_mcp(normalized):
        return []
    intents = []
    for server_id in server_ids:
        if _is_write_request(normalized):
            intents.append(
                {
                    "schema_version": MCP_CHAT_BRIDGE_VERSION,
                    "server_id": server_id,
                    "tool_name": "proposal_required",
                    "arguments": {},
                    "action": "write_proposal",
                    "intent_summary": _summary(message),
                }
            )
        else:
            tool_name, arguments = _read_tool_and_arguments(server_id, message, normalized)
            intents.append(
                {
                    "schema_version": MCP_CHAT_BRIDGE_VERSION,
                    "server_id": server_id,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "action": "read",
                    "intent_summary": _summary(message),
                }
            )
    return intents

def _server_from_text(normalized: str) -> str | None:
    server_ids = _servers_from_text(normalized)
    return server_ids[0] if server_ids else None


def _servers_from_text(normalized: str) -> list[str]:
    if "mcp" not in normalized:
        return []
    server_ids = []
    if "boh" in normalized or "bag of holding" in normalized:
        server_ids.append("boh")
    if "project atlas" in normalized or "atlas" in normalized:
        server_ids.append("project_atlas")
    return server_ids

def _mentions_read_or_mcp(normalized: str) -> bool:
    terms = (
        "mcp",
        "read",
        "retrieve",
        "search",
        "find",
        "show",
        "list",
        "status",
        "access",
        "can you",
        "check",
        "random",
        "occupation",
        "trade card",
    )
    return any(term in normalized for term in terms)


def _is_write_request(normalized: str) -> bool:
    write_terms = (
        "write",
        "update",
        "change",
        "create",
        "delete",
        "apply",
        "promote",
        "push",
        "record",
        "refresh",
        "mutate",
        "modify",
    )
    if "read" in normalized and not any(term in normalized for term in ("write", "apply", "promote", "delete", "push")):
        return False
    return any(term in normalized for term in write_terms)


def _read_tool_and_arguments(server_id: str, message: str, normalized: str) -> tuple[str, dict[str, Any]]:
    if server_id == "project_atlas":
        return "list_projects", {"limit": 5}
    if _is_boh_access_probe(normalized):
        return "get_current_state", {}
    return "retrieve_context", {"query": _boh_query(message), "limit": 3}


def _is_boh_access_probe(normalized: str) -> bool:
    content_terms = ("trade card", "occupation", "search", "find", "retrieve", "context", "random")
    return ("access" in normalized or "status" in normalized or "check" in normalized) and not any(
        term in normalized for term in content_terms
    )


def _boh_query(message: str) -> str:
    query = re.sub(r"\b(boh|mcp|bag of holding)\b", " ", message, flags=re.IGNORECASE)
    query = re.sub(r"\b(please|can you|could you|check access to|read me|read|retrieve|search|find)\b", " ", query, flags=re.IGNORECASE)
    query = re.sub(r"[^A-Za-z0-9._\-\s]+", " ", query)
    query = re.sub(r"\s+", " ", query).strip()
    query = re.sub(r"^the\s+", "", query, flags=re.IGNORECASE)
    return query or message.strip()


def _render_success(intent: dict[str, Any], mcp: dict[str, Any], elapsed_ms: int, cache_hit: bool) -> str:
    server_id = intent["server_id"]
    tool_name = intent["tool_name"]
    result_hash = mcp.get("result_hash") or "none"
    if server_id == "boh":
        detail = _render_boh_detail(mcp.get("result"))
    else:
        detail = _render_atlas_detail(mcp.get("result"))
    cache_note = ", cache hit" if cache_hit else ""
    return (
        f"{SERVER_LABELS[server_id]} read complete via `{tool_name}` ({elapsed_ms} ms{cache_note}). "
        f"{detail}\n\nSource label: sourced; MCP result hash: `{result_hash}`."
    )


def _render_boh_detail(result: Any) -> str:
    packs = _context_packs(result)
    if packs:
        pack = packs[0]
        title = _clean_text(str(pack.get("title") or pack.get("doc_id") or "untitled BOH result"), limit=120)
        snippet = _clean_text(str(pack.get("snippet") or ""), limit=320)
        if snippet:
            return f"One BOH result: {title}. Snippet: {snippet}"
        return f"One BOH result: {title}."
    text = _first_text(result)
    if text:
        return f"Result preview: {_clean_text(text, limit=360)}"
    return "The MCP read returned no displayable BOH text."


def _render_atlas_detail(result: Any) -> str:
    projects = _project_items(result)
    if projects:
        rendered = []
        for project in projects[:5]:
            name = project.get("name") or project.get("title") or project.get("project_name") or project.get("id") or project.get("project_id") or "unknown"
            status = project.get("status") or project.get("state")
            rendered.append(_clean_text(f"{name}{f' ({status})' if status else ''}", limit=100))
        return f"Projects: {', '.join(rendered)}."
    text = _first_text(result)
    if text:
        return f"Result preview: {_clean_text(text, limit=360)}"
    return "The MCP read returned no displayable Project Atlas text."


def _context_packs(result: Any) -> list[dict[str, Any]]:
    for payload in _parsed_payloads(result):
        packs = payload.get("context_packs") if isinstance(payload, dict) else None
        if isinstance(packs, list):
            return [pack for pack in packs if isinstance(pack, dict)]
    recovered = []
    for text in _texts(result):
        pack = _recover_pack_from_text(text)
        if pack:
            recovered.append(pack)
    return recovered


def _recover_pack_from_text(text: str) -> dict[str, Any] | None:
    title = _regex_json_string(text, "title")
    snippet = _regex_json_string(text, "snippet")
    doc_id = _regex_json_string(text, "doc_id")
    if not title and not snippet and not doc_id:
        return None
    return {"title": title, "snippet": snippet, "doc_id": doc_id}


def _regex_json_string(text: str, key: str) -> str:
    match = re.search(rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"', text)
    if not match:
        return ""
    raw = match.group(1)
    try:
        return str(json.loads(f'"{raw}"'))
    except json.JSONDecodeError:
        return raw.replace(r"\n", " ").replace(r"\"", '"')


def _project_items(result: Any) -> list[dict[str, Any]]:
    for payload in _parsed_payloads(result):
        if not isinstance(payload, dict):
            continue
        candidates = [payload]
        nested = payload.get("result")
        if isinstance(nested, dict):
            candidates.append(nested)
        for candidate in candidates:
            for key in ("projects", "items", "results"):
                items = candidate.get(key)
                if isinstance(items, list):
                    return [item for item in items if isinstance(item, dict)]
    return []


def _parsed_payloads(result: Any) -> list[Any]:
    payloads: list[Any] = []
    if isinstance(result, dict):
        payloads.append(result)
    for text in _texts(result):
        try:
            payloads.append(json.loads(text))
        except json.JSONDecodeError:
            continue
    return payloads


def _first_text(result: Any) -> str:
    texts = _texts(result)
    return texts[0] if texts else ""


def _texts(result: Any) -> list[str]:
    texts: list[str] = []
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    texts.append(item["text"])
        if isinstance(result.get("text"), str):
            texts.append(result["text"])
    elif isinstance(result, str):
        texts.append(result)
    return texts


def _blocked_result(intent: dict[str, Any], reason: str, message: str, *, read_status: str) -> dict[str, Any]:
    return _bridge_result(
        intent,
        message,
        status="blocked",
        source_state="unsourced",
        elapsed_ms=0,
        result_hash=None,
        blocked_reason=reason,
        read_status=read_status,
        cache_hit=False,
    )


def _bridge_result(
    intent: dict[str, Any],
    message: str,
    *,
    status: str,
    source_state: str,
    elapsed_ms: int,
    result_hash: Any,
    blocked_reason: Any,
    read_status: str,
    cache_hit: bool,
) -> dict[str, Any]:
    event = {
        "type": "mcp_chat_read",
        "status": status,
        "server_id": intent["server_id"],
        "tool_name": intent["tool_name"],
        "intent_summary": intent.get("intent_summary", ""),
        "read_status": read_status,
        "elapsed_ms": elapsed_ms,
        "result_hash": result_hash,
        "blocked_reason": blocked_reason,
        "cache_hit": cache_hit,
        "schema_version": "metis_event.v0.1",
    }
    metadata = {
        "schema_version": MCP_CHAT_BRIDGE_VERSION,
        "server_id": intent["server_id"],
        "tool_name": intent["tool_name"],
        "status": status,
        "read_status": read_status,
        "elapsed_ms": elapsed_ms,
        "result_hash": result_hash,
        "blocked_reason": blocked_reason,
        "cache_hit": cache_hit,
        "llm_summarization_used": False,
        "write_apply_allowed": False,
    }
    return {
        "message": message,
        "provider": "mcp_chat_bridge",
        "model": MCP_CHAT_BRIDGE_VERSION,
        "source_state": source_state,
        "event": event,
        "events": [event],
        "metadata": metadata,
    }


def _combined_bridge_result(results: list[dict[str, Any]]) -> dict[str, Any]:
    reads = [dict(result["metadata"]) for result in results]
    all_complete = all(read.get("status") == "read_only_complete" for read in reads)
    any_complete = any(read.get("status") == "read_only_complete" for read in reads)
    source_state = "sourced" if all_complete else "degraded" if any_complete else "unsourced"
    status = "multi_read_complete" if all_complete else "multi_read_partial" if any_complete else "blocked"
    detail = "\n\n".join(_strip_source_label(result["message"]) for result in results)
    hash_parts = [
        f"{SERVER_LABELS.get(str(read.get('server_id')), str(read.get('server_id')))}: `{read.get('result_hash')}`"
        for read in reads
        if read.get("result_hash")
    ]
    hash_summary = "; ".join(hash_parts) if hash_parts else "none"
    message = f"Combined MCP read complete.\n\n{detail}\n\nSource label: {source_state}; MCP result hashes: {hash_summary}."
    events: list[dict[str, Any]] = []
    for result in results:
        result_events = result.get("events") or [result["event"]]
        events.extend(event for event in result_events if isinstance(event, dict))
    metadata = {
        "schema_version": MCP_CHAT_BRIDGE_VERSION,
        "status": status,
        "server_ids": [read.get("server_id") for read in reads],
        "reads": reads,
        "elapsed_ms": sum(int(read.get("elapsed_ms") or 0) for read in reads),
        "cache_hit": all(bool(read.get("cache_hit")) for read in reads),
        "llm_summarization_used": False,
        "write_apply_allowed": False,
    }
    return {
        "message": message,
        "provider": "mcp_chat_bridge",
        "model": MCP_CHAT_BRIDGE_VERSION,
        "source_state": source_state,
        "event": events[0],
        "events": events,
        "metadata": metadata,
    }


def _strip_source_label(message: str) -> str:
    return message.split("\n\nSource label:", 1)[0]

def _normalize(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"[^a-z0-9.\s_-]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _summary(value: str) -> str:
    return _clean_text(value, limit=160)


def _clean_text(value: str, *, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    if len(cleaned) > limit:
        return f"{cleaned[:limit].rstrip()}..."
    return cleaned


def _cache_key(server_id: str, tool_name: str, arguments: dict[str, Any], env: dict[str, str]) -> str:
    config = {
        "server_id": server_id,
        "tool_name": tool_name,
        "arguments": arguments,
        "connection_identity": mcp_config_identity(server_id, env),
    }
    body = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(body.encode("utf-8")).hexdigest()


def _env_prefix(server_id: str) -> str:
    return "METIS_MCP_BOH" if server_id == "boh" else "METIS_MCP_ATLAS"


def _hash_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def _cached_mcp_result(cache_key: str, now: float) -> dict[str, Any] | None:
    item = _CACHE.get(cache_key)
    if not item:
        return None
    if now - float(item.get("stored_at", 0.0)) > _CACHE_TTL_SECONDS:
        _CACHE.pop(cache_key, None)
        return None
    result = item.get("result")
    return dict(result) if isinstance(result, dict) else None


def _remember_mcp_result(cache_key: str, result: dict[str, Any], now: float) -> None:
    if result.get("status") != "read_only_complete":
        return
    if len(_CACHE) >= _CACHE_MAX_ITEMS:
        oldest = min(_CACHE.items(), key=lambda item: float(item[1].get("stored_at", 0.0)))[0]
        _CACHE.pop(oldest, None)
    _CACHE[cache_key] = {"stored_at": now, "result": dict(result)}
