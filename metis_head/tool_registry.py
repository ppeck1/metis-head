from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha1
import re
from typing import Any


TOOL_REGISTRY_VERSION = "metis_tool_registry.v0.1"
TOOL_RECEIPT_VERSION = "metis_tool_receipt.v0.1"
TOOL_ARGUMENT_VALIDATION_VERSION = "metis_tool_arguments.v0.1"
PERMISSION_MODES = {"disabled", "dry_run", "proposal_only", "approved_read_only"}
SIDE_EFFECT_CLASSES = {"none", "read_only", "local_mutation", "external_mutation"}
RISK_CLASSES = {"low", "medium", "high", "blocked"}
SENSITIVE_ARGUMENT_MARKERS = ("token", "password", "secret", "key", "credential")


class ToolRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class ToolManifest:
    tool_id: str
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_class: str
    side_effect_class: str
    permission_mode: str
    enabled: bool
    source_reference: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TOOL_REGISTRY_VERSION,
            **asdict(self),
            "lifecycle": tool_lifecycle(self),
            "permission_requirements": tool_permission_requirements(self),
        }


def tool_permission_requirements(tool: ToolManifest) -> dict[str, Any]:
    if tool.permission_mode == "approved_read_only":
        gates = ["proposal_queued", "human_review_approved", "lane_scope_match", "redaction_before_display", "audit_receipt"]
        blocked = ["autonomous_execution", "external_mutation", "local_mutation", "shell_execution"]
    elif tool.permission_mode == "dry_run" and tool.side_effect_class == "none":
        gates = ["schema_valid_arguments", "dry_run_receipt"]
        blocked = ["external_action", "mutation", "shell_execution"]
    elif tool.permission_mode == "proposal_only":
        gates = ["proposal_queued", "human_review_recorded"]
        blocked = ["execution_after_review", "external_action", "mutation", "network_io", "shell_execution"]
    else:
        gates = ["disabled"]
        blocked = ["all_execution"]
    if tool.tool_id == "memory.propose":
        blocked = sorted(set(blocked + ["memory_promotion"]))
    if tool.tool_id.startswith("boh."):
        blocked = sorted(set(blocked + ["boh_http_call", "boh_mutation", "operator_token_use"]))
    if tool.tool_id.startswith("fetch."):
        blocked = sorted(set(blocked + ["dns_lookup", "http_request"]))
    if tool.tool_id.startswith("filesystem."):
        gates = gates + ["repo_path_allowlist"] if tool.permission_mode == "approved_read_only" else gates
        blocked = sorted(set(blocked + ["arbitrary_filesystem_access"]))
    if tool.tool_id.startswith("git."):
        gates = gates + ["fixed_no_shell_arguments"] if tool.permission_mode == "approved_read_only" else gates
        blocked = sorted(set(blocked + ["arbitrary_git_command"]))
    return {
        "mode": tool.permission_mode,
        "required_gates": gates,
        "blocked_capabilities": blocked,
        "requires_human_review": tool.permission_mode != "dry_run" or tool.side_effect_class != "none",
        "standing_approval_supported": False,
        "notes": "Metadata only; reducer, proposal review, and execution receipt gates remain authoritative.",
    }


def tool_lifecycle(tool: ToolManifest) -> dict[str, Any]:
    if not tool.enabled or tool.permission_mode == "disabled":
        return {
            "lifecycle_label": "disabled",
            "lifecycle_tags": ["disabled"],
            "operator_summary": "Tool is registered but disabled.",
            "requires_review": True,
            "dry_run_available": False,
            "execution_request_allowed": False,
            "execution_result": "blocked",
        }
    if tool.permission_mode == "dry_run" and tool.side_effect_class == "none":
        return {
            "lifecycle_label": "dry_run_available",
            "lifecycle_tags": ["dry_run_available", "side_effect_free"],
            "operator_summary": "Safe dry-run receipt is available; execute still returns a dry-run receipt, not external action.",
            "requires_review": False,
            "dry_run_available": True,
            "execution_request_allowed": False,
            "execution_result": "dry_run_only_not_executed",
        }
    if tool.permission_mode == "approved_read_only":
        return {
            "lifecycle_label": "approved_read_only",
            "lifecycle_tags": ["proposal_only", "approved_read_only"],
            "operator_summary": "Queues a proposal; after approval, only the scoped read-only lane may return an audit receipt.",
            "requires_review": True,
            "dry_run_available": False,
            "execution_request_allowed": True,
            "execution_result": "executed_read_only",
        }
    tags = ["proposal_only", "blocked_after_review"]
    if tool.tool_id.endswith("_proposed"):
        tags.append("future_only")
    return {
        "lifecycle_label": "proposal_only",
        "lifecycle_tags": tags,
        "operator_summary": "Queues a proposal for review; execution requests remain blocked after approval in this phase.",
        "requires_review": True,
        "dry_run_available": False,
        "execution_request_allowed": False,
        "execution_result": "blocked_after_review",
    }


TOOLS: dict[str, ToolManifest] = {
    "time.now": ToolManifest(
        tool_id="time.now",
        name="Current Time",
        description="Return a safe current-time shaped result. Pattern donor: MCP Time reference server.",
        input_schema={"type": "object", "properties": {"timezone": {"type": "string"}, "now": {"type": "string"}}, "additionalProperties": False},
        output_schema={"type": "object", "properties": {"iso_time": {"type": "string"}, "timezone": {"type": "string"}}},
        risk_class="low",
        side_effect_class="none",
        permission_mode="dry_run",
        enabled=True,
        source_reference="modelcontextprotocol/servers:time",
    ),
    "text.summarize": ToolManifest(
        tool_id="text.summarize",
        name="Text Summarize",
        description="Return a deterministic local summary-shaped result without calling external models.",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}, "max_words": {"type": "integer"}}, "required": ["text"], "additionalProperties": False},
        output_schema={"type": "object", "properties": {"summary": {"type": "string"}, "word_count": {"type": "integer"}}},
        risk_class="low",
        side_effect_class="none",
        permission_mode="dry_run",
        enabled=True,
        source_reference="metis-native:text",
    ),
    "math.calculate": ToolManifest(
        tool_id="math.calculate",
        name="Math Calculate",
        description="Perform a narrow arithmetic dry run from explicit operator and operands. No eval.",
        input_schema={"type": "object", "properties": {"operation": {"type": "string"}, "a": {"type": "number"}, "b": {"type": "number"}}, "required": ["operation", "a", "b"], "additionalProperties": False},
        output_schema={"type": "object", "properties": {"result": {"type": "number"}, "operation": {"type": "string"}}},
        risk_class="low",
        side_effect_class="none",
        permission_mode="dry_run",
        enabled=True,
        source_reference="anthropic-tools:manual-math-pattern",
    ),
    "thinking.plan_outline": ToolManifest(
        tool_id="thinking.plan_outline",
        name="Visible Plan Outline",
        description="Return a short visible planning outline from an explicit task. No hidden reasoning or autonomous execution.",
        input_schema={"type": "object", "properties": {"task": {"type": "string"}, "max_steps": {"type": "integer"}}, "required": ["task"], "additionalProperties": False},
        output_schema={"type": "object", "properties": {"task": {"type": "string"}, "steps": {"type": "array"}, "execution_allowed": {"type": "boolean"}}},
        risk_class="low",
        side_effect_class="none",
        permission_mode="dry_run",
        enabled=True,
        source_reference="modelcontextprotocol/servers:sequentialthinking",
    ),
    "filesystem.read_proposed": ToolManifest(
        tool_id="filesystem.read_proposed",
        name="Filesystem Read Proposal",
        description="Queue a proposal for a future governed file read; Phase 0T does not read files.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False},
        output_schema={"type": "object", "properties": {"proposal_only": {"type": "boolean"}}},
        risk_class="medium",
        side_effect_class="read_only",
        permission_mode="proposal_only",
        enabled=True,
        source_reference="modelcontextprotocol/servers:filesystem",
    ),
    "filesystem.read": ToolManifest(
        tool_id="filesystem.read",
        name="Filesystem Read",
        description="Approved read-only current-repo file preview with path, extension, and size gates.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False},
        output_schema={"type": "object", "properties": {"path": {"type": "string"}, "byte_count": {"type": "integer"}, "preview_lines": {"type": "array"}}},
        risk_class="medium",
        side_effect_class="read_only",
        permission_mode="approved_read_only",
        enabled=True,
        source_reference="modelcontextprotocol/servers:filesystem",
    ),
    "git.status_proposed": ToolManifest(
        tool_id="git.status_proposed",
        name="Git Status Proposal",
        description="Queue a proposal for a future governed git status check; Phase 0T does not run git.",
        input_schema={"type": "object", "properties": {"repository": {"type": "string"}}, "additionalProperties": False},
        output_schema={"type": "object", "properties": {"proposal_only": {"type": "boolean"}}},
        risk_class="medium",
        side_effect_class="read_only",
        permission_mode="proposal_only",
        enabled=True,
        source_reference="modelcontextprotocol/servers:git",
    ),
    "git.status": ToolManifest(
        tool_id="git.status",
        name="Git Status",
        description="Approved read-only git status lane using fixed no-shell arguments and redacted/truncated output.",
        input_schema={"type": "object", "properties": {"repository": {"type": "string"}}, "additionalProperties": False},
        output_schema={"type": "object", "properties": {"branch": {"type": "string"}, "changed_count": {"type": "integer"}, "status_preview": {"type": "array"}}},
        risk_class="medium",
        side_effect_class="read_only",
        permission_mode="approved_read_only",
        enabled=True,
        source_reference="modelcontextprotocol/servers:git",
    ),
    "fetch.url_proposed": ToolManifest(
        tool_id="fetch.url_proposed",
        name="Fetch URL Proposal",
        description="Queue a proposal for future governed URL fetch; Phase 0K does not perform network calls.",
        input_schema={"type": "object", "properties": {"url": {"type": "string"}, "method": {"type": "string"}}, "required": ["url"], "additionalProperties": False},
        output_schema={"type": "object", "properties": {"proposal_only": {"type": "boolean"}}},
        risk_class="high",
        side_effect_class="read_only",
        permission_mode="proposal_only",
        enabled=True,
        source_reference="modelcontextprotocol/servers:fetch",
    ),
    "boh.retrieve_proposed": ToolManifest(
        tool_id="boh.retrieve_proposed",
        name="BOH Retrieve Proposal",
        description="Queue a proposal for future BOH retrieval-as-tool; Phase 0E does not call BOH through the tool registry.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}, "mode": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"], "additionalProperties": False},
        output_schema={"type": "object", "properties": {"proposal_only": {"type": "boolean"}}},
        risk_class="medium",
        side_effect_class="read_only",
        permission_mode="proposal_only",
        enabled=True,
        source_reference="metis-native:boh-retrieval-contract",
    ),
    "memory.propose": ToolManifest(
        tool_id="memory.propose",
        name="Memory Proposal",
        description="Queue a memory proposal for review; no memory promotion happens in Phase 0T.",
        input_schema={"type": "object", "properties": {"memory_id": {"type": "string"}, "summary": {"type": "string"}}, "required": ["memory_id"], "additionalProperties": False},
        output_schema={"type": "object", "properties": {"proposal_only": {"type": "boolean"}}},
        risk_class="medium",
        side_effect_class="local_mutation",
        permission_mode="proposal_only",
        enabled=True,
        source_reference="modelcontextprotocol/servers:memory",
    ),
}


def list_tools() -> dict[str, Any]:
    return {"tool_registry_version": TOOL_REGISTRY_VERSION, "tools": [tool.to_dict() for tool in TOOLS.values()]}


def get_tool(tool_id: str) -> ToolManifest:
    try:
        return TOOLS[tool_id]
    except KeyError as exc:
        raise ToolRegistryError(f"unknown tool: {tool_id}") from exc


def sanitize_arguments(arguments: Any) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        return {}
    sanitized: dict[str, Any] = {}
    for key, value in arguments.items():
        if _is_sensitive_argument(str(key)):
            sanitized[str(key)] = "***"
        elif isinstance(value, str):
            sanitized[str(key)] = value[:240]
        elif isinstance(value, (int, float, bool)) or value is None:
            sanitized[str(key)] = value
        else:
            sanitized[str(key)] = str(value)[:240]
    return sanitized


def validate_tool_arguments(tool_id: str, arguments: Any) -> dict[str, Any]:
    tool = get_tool(tool_id)
    schema = tool.input_schema
    if schema.get("type") != "object":
        raise ToolRegistryError(f"unsupported input schema for tool: {tool_id}")
    if not isinstance(arguments, dict):
        raise ToolRegistryError(f"arguments must be an object for tool: {tool_id}")
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    required = set(schema.get("required", []))
    missing = sorted(name for name in required if name not in arguments)
    if missing:
        raise ToolRegistryError(f"missing required argument(s) for {tool_id}: {', '.join(missing)}")
    warnings: list[str] = []
    allowed: dict[str, Any] = {}
    for key, value in arguments.items():
        key = str(key)
        if key not in properties:
            if schema.get("additionalProperties", True) is False:
                if _is_sensitive_argument(key):
                    warnings.append(f"dropped_sensitive_argument:{key}")
                    continue
                raise ToolRegistryError(f"unexpected argument for {tool_id}: {key}")
            allowed[key] = value
            continue
        expected = properties[key].get("type") if isinstance(properties[key], dict) else None
        if expected and not _matches_schema_type(value, str(expected)):
            raise ToolRegistryError(f"invalid argument type for {tool_id}.{key}: expected {expected}")
        allowed[key] = value
    return {
        "schema_version": TOOL_ARGUMENT_VALIDATION_VERSION,
        "valid": True,
        "arguments": sanitize_arguments(allowed),
        "warnings": warnings,
    }


def _matches_schema_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def _is_sensitive_argument(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SENSITIVE_ARGUMENT_MARKERS)


def tool_policy(tool: ToolManifest, *, agent_mode: bool) -> dict[str, Any]:
    reasons = [f"tool risk={tool.risk_class}", f"side_effect={tool.side_effect_class}", f"permission={tool.permission_mode}"]
    if agent_mode:
        reasons.append("Agent Mode can prepare tool proposals only")
    return {
        "requires_approval": agent_mode or tool.permission_mode != "dry_run" or tool.side_effect_class != "none",
        "default_decision": "queue_for_review" if tool.permission_mode in {"proposal_only", "approved_read_only"} or agent_mode else "dry_run_only",
        "reasons": reasons,
    }


def build_tool_proposal_event(tool_id: str, arguments: Any, state: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
    tool = get_tool(tool_id)
    validation = validate_tool_arguments(tool_id, arguments)
    sanitized = validation["arguments"]
    policy = tool_policy(tool, agent_mode=state.get("interaction_mode") == "agent")
    intent = reason or f"tool proposal: {tool_id}"
    return {
        "type": "user_intent",
        "intent": intent,
        "action_class": _action_class_for_tool(tool),
        "policy": policy,
        "tool_id": tool_id,
        "tool_arguments": sanitized,
        "risk_class": tool.risk_class,
        "side_effect_class": tool.side_effect_class,
        "dry_run_available": tool.permission_mode == "dry_run",
        "argument_validation": {"schema_version": validation["schema_version"], "valid": True, "warnings": validation["warnings"]},
    }


def _action_class_for_tool(tool: ToolManifest) -> str:
    if tool.tool_id == "memory.propose":
        return "propose_memory"
    if tool.side_effect_class == "external_mutation":
        return "external_action"
    if tool.side_effect_class in {"read_only", "local_mutation"}:
        return "modify_local"
    return "observe"


def dry_run_tool(tool_id: str, arguments: Any) -> dict[str, Any]:
    tool = get_tool(tool_id)
    validation = validate_tool_arguments(tool_id, arguments)
    sanitized = validation["arguments"]
    if not tool.enabled:
        raise ToolRegistryError(f"tool disabled: {tool_id}")
    if tool.permission_mode != "dry_run" or tool.side_effect_class != "none":
        raise ToolRegistryError(f"tool requires proposal: {tool_id}")
    output = _dry_run_output(tool_id, sanitized)
    return {
        "tool_receipt_version": TOOL_RECEIPT_VERSION,
        "tool_id": tool_id,
        "status": "dry_run_complete",
        "execution_allowed": False,
        "arguments": sanitized,
        "argument_validation": {"schema_version": validation["schema_version"], "valid": True, "warnings": validation["warnings"]},
        "result": output,
        "result_hash": sha1(repr(output).encode("utf-8")).hexdigest()[:16],
    }


def execute_tool(tool_id: str, arguments: Any, state: dict[str, Any]) -> dict[str, Any]:
    tool = get_tool(tool_id)
    validate_tool_arguments(tool_id, arguments)
    if tool.permission_mode == "dry_run" and tool.side_effect_class == "none" and state.get("interaction_mode") != "agent":
        receipt = dry_run_tool(tool_id, arguments)
        return {**receipt, "status": "dry_run_complete_not_executed", "blocked_reason": "Phase 0T execute returns dry-run receipts only"}
    return {
        "tool_receipt_version": TOOL_RECEIPT_VERSION,
        "tool_id": tool_id,
        "status": "blocked_pending_review",
        "execution_allowed": False,
        "blocked_reason": "Phase 0T does not execute side-effectful or Agent Mode tools",
        "proposal_required": True,
    }


def _dry_run_output(tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if tool_id == "time.now":
        iso_time = str(arguments.get("now") or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
        return {"iso_time": iso_time, "timezone": str(arguments.get("timezone") or "UTC")}
    if tool_id == "text.summarize":
        text = str(arguments.get("text") or "")
        max_words = int(arguments.get("max_words") or 24)
        words = text.split()
        return {"summary": " ".join(words[: max(1, min(80, max_words))]), "word_count": len(words)}
    if tool_id == "math.calculate":
        operation = str(arguments.get("operation") or "").lower()
        a = float(arguments.get("a", 0))
        b = float(arguments.get("b", 0))
        if operation in {"add", "+"}:
            result = a + b
        elif operation in {"subtract", "-"}:
            result = a - b
        elif operation in {"multiply", "*"}:
            result = a * b
        elif operation in {"divide", "/"}:
            if b == 0:
                raise ToolRegistryError("division by zero")
            result = a / b
        else:
            raise ToolRegistryError(f"unsupported math operation: {operation}")
        return {"operation": operation, "result": result}
    if tool_id == "thinking.plan_outline":
        task = str(arguments.get("task") or "").strip()
        if not task:
            raise ToolRegistryError("task is required")
        max_steps = max(1, min(6, int(arguments.get("max_steps") or 4)))
        verbs = ["Clarify the goal", "Identify constraints", "Draft the smallest safe change", "Verify the result", "Record the outcome", "Queue follow-up review"]
        return {"task": task[:240], "steps": verbs[:max_steps], "execution_allowed": False}
    raise ToolRegistryError(f"no dry-run implementation for: {tool_id}")


def route_tool_request(message: str) -> dict[str, Any] | None:
    text = message.strip()
    lowered = text.lower()
    if not text:
        return None
    math_route = _route_math(text)
    if math_route:
        return math_route
    if any(phrase in lowered for phrase in ("what time", "current time", "time is it")):
        return {"tool_id": "time.now", "arguments": {}, "reason": "chat requested current time"}
    if lowered.startswith("summarize:") or lowered.startswith("summarise:"):
        return {"tool_id": "text.summarize", "arguments": {"text": text.split(":", 1)[1].strip()}, "reason": "chat requested summarization"}
    if lowered.startswith("plan:") or lowered.startswith("outline plan:"):
        return {"tool_id": "thinking.plan_outline", "arguments": {"task": text.split(":", 1)[1].strip()}, "reason": "chat requested visible plan outline"}
    if lowered.startswith("fetch url ") or lowered.startswith("fetch "):
        url = text.split(" ", 2)[2].strip() if lowered.startswith("fetch url ") else text.split(" ", 1)[1].strip()
        return {"tool_id": "fetch.url_proposed", "arguments": {"url": url, "method": "GET"}, "reason": "chat requested URL fetch proposal"}
    if lowered.startswith("search boh ") or lowered.startswith("retrieve boh ") or lowered.startswith("search library "):
        query = text.split(" ", 2)[2].strip()
        return {"tool_id": "boh.retrieve_proposed", "arguments": {"query": query, "mode": "exploration", "limit": 5}, "reason": "chat requested BOH retrieval proposal"}
    if "git status" in lowered:
        return {"tool_id": "git.status", "arguments": {"repository": "."}, "reason": "chat requested git status"}
    if lowered.startswith("read file ") or lowered.startswith("open file "):
        path = text.split(" ", 2)[2].strip()
        return {"tool_id": "filesystem.read", "arguments": {"path": path}, "reason": "chat requested file read"}
    if lowered.startswith("remember "):
        summary = text[len("remember ") :].strip()
        memory_id = f"chat_memory_{sha1(summary.encode('utf-8')).hexdigest()[:8]}"
        return {"tool_id": "memory.propose", "arguments": {"memory_id": memory_id, "summary": summary}, "reason": "chat requested memory proposal"}
    return None


def _route_math(text: str) -> dict[str, Any] | None:
    patterns = [
        (r"(?:calculate|what is|what's)\s+(-?\d+(?:\.\d+)?)\s*([\+\-\*/])\s*(-?\d+(?:\.\d+)?)", None),
        (r"(?:add)\s+(-?\d+(?:\.\d+)?)\s+(?:and|to)\s+(-?\d+(?:\.\d+)?)", "add"),
        (r"(?:multiply)\s+(-?\d+(?:\.\d+)?)\s+(?:and|by)\s+(-?\d+(?:\.\d+)?)", "multiply"),
    ]
    for pattern, named_operation in patterns:
        match = re.search(pattern, text.lower())
        if not match:
            continue
        if named_operation:
            a, b = match.groups()
            operation = named_operation
        else:
            a, symbol, b = match.groups()
            operation = {"+": "add", "-": "subtract", "*": "multiply", "/": "divide"}[symbol]
        return {"tool_id": "math.calculate", "arguments": {"operation": operation, "a": float(a), "b": float(b)}, "reason": "chat requested calculation"}
    return None
