from __future__ import annotations

from hashlib import sha1
import re
from typing import Any

from .tool_governance import evaluate_tool_request
from .tool_registry import ToolRegistryError, get_tool, validate_tool_arguments


TOOL_TASK_PLAN_VERSION = "metis_tool_task_plan.v0.1"


def plan_tool_task(task: str, state: dict[str, Any]) -> dict[str, Any]:
    task = str(task or "").strip()
    if not task:
        raise ValueError("task is required")
    steps = _candidate_steps(task)
    planned_steps = [_plan_step(index, step, state) for index, step in enumerate(steps)]
    return {
        "schema_version": TOOL_TASK_PLAN_VERSION,
        "plan_id": _stable_plan_id(task, planned_steps),
        "task": task[:500],
        "status": "reviewable_plan",
        "execution_allowed": False,
        "autonomous_execution_allowed": False,
        "step_count": len(planned_steps),
        "steps": planned_steps,
        "summary": {
            "dry_run_available_count": sum(1 for step in planned_steps if step["status"] == "dry_run_available"),
            "proposal_required_count": sum(1 for step in planned_steps if step["status"] == "proposal_required"),
            "future_or_blocked_count": sum(1 for step in planned_steps if step["status"] in {"future_only_blocked", "blocked_no_tool"}),
        },
        "boundary": "Task plans are reviewable only; no tools are run, queued, approved, or executed by this endpoint.",
    }


def _candidate_steps(task: str) -> list[dict[str, Any]]:
    lowered = task.lower()
    steps: list[dict[str, Any]] = []
    if "git status" in lowered or ("status" in lowered and "repo" in lowered):
        steps.append({"tool_id": "git.status", "arguments": {"repository": "."}, "reason": "inspect repository status"})
    path = _extract_file_path(task)
    if path:
        steps.append({"tool_id": "filesystem.read", "arguments": {"path": path}, "reason": "read requested file"})
    if "summarize" in lowered or "summarise" in lowered:
        if path:
            steps.append({"tool_id": "text.summarize", "arguments": {"text": "<requires approved filesystem.read output>"}, "reason": "summarize after approved read"})
        else:
            text = task.split(":", 1)[1].strip() if ":" in task else task
            steps.append({"tool_id": "text.summarize", "arguments": {"text": text}, "reason": "summarize provided text"})
    if "fetch " in lowered or "http://" in lowered or "https://" in lowered:
        steps.append({"tool_id": "fetch.url_proposed", "arguments": {"url": _extract_url(task) or "<url_required>"}, "reason": "future URL fetch proposal"})
    if "boh" in lowered or "library" in lowered or "vault" in lowered:
        steps.append({"tool_id": "boh.retrieve_proposed", "arguments": {"query": task[:240], "mode": "exploration", "limit": 5}, "reason": "future BOH retrieval proposal"})
    if any(word in lowered for word in ("write", "edit", "modify", "delete", "commit", "push", "create file")):
        steps.append({"tool_id": None, "arguments": {}, "reason": "mutation/external action remains future-only", "blocked_capability": "mutation_or_external_action"})
    if not steps:
        steps.append({"tool_id": "thinking.plan_outline", "arguments": {"task": task, "max_steps": 4}, "reason": "prepare a visible governed plan"})
    return steps


def _plan_step(index: int, step: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    tool_id = step.get("tool_id")
    if not tool_id:
        return {
            "step_id": f"step_{index + 1:02d}",
            "tool_id": None,
            "reason": step["reason"],
            "arguments": {},
            "status": "blocked_no_tool",
            "execution_allowed": False,
            "future_out_of_scope": True,
            "blocked_capabilities": [step.get("blocked_capability", "unsupported_tool")],
        }
    try:
        tool = get_tool(str(tool_id))
        validation = validate_tool_arguments(str(tool_id), step.get("arguments") or {})
        gate = evaluate_tool_request(str(tool_id), validation["arguments"], state, "dry_run")
    except (ToolRegistryError, ValueError) as exc:
        return {
            "step_id": f"step_{index + 1:02d}",
            "tool_id": tool_id,
            "reason": step["reason"],
            "arguments": step.get("arguments") or {},
            "status": "blocked_invalid_arguments",
            "execution_allowed": False,
            "error": str(exc),
        }
    future_only = "future_only" in tool.to_dict()["lifecycle"].get("lifecycle_tags", [])
    status = "future_only_blocked" if future_only else "proposal_required" if gate["proposal_required"] else "dry_run_available"
    return {
        "step_id": f"step_{index + 1:02d}",
        "tool_id": tool_id,
        "reason": step["reason"],
        "arguments": validation["arguments"],
        "status": status,
        "permission_mode": tool.permission_mode,
        "side_effect_class": tool.side_effect_class,
        "risk_class": tool.risk_class,
        "review_required": gate["review_required"],
        "execution_allowed": False,
        "future_out_of_scope": future_only,
        "required_gates": gate["required_gates"],
        "blocked_capabilities": gate["blocked_capabilities"],
    }


def _extract_file_path(task: str) -> str | None:
    match = re.search(r"(?:read|open|summarize|summarise)\s+(?:file\s+)?([A-Za-z0-9_./\\:-]+\.[A-Za-z0-9]+)", task, re.IGNORECASE)
    return match.group(1) if match else None


def _extract_url(task: str) -> str | None:
    match = re.search(r"https?://\S+", task)
    return match.group(0).rstrip(".,;") if match else None


def _stable_plan_id(task: str, steps: list[dict[str, Any]]) -> str:
    digest = sha1(f"{task}:{[(step.get('tool_id'), step.get('status')) for step in steps]}".encode("utf-8")).hexdigest()[:10]
    return f"tool_plan_{digest}"
