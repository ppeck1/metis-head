from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .contracts import ConnectorError, ConnectorResult, ErrorCode, Freshness, Provenance, ResultStatus, utc_now
from .mcp_contracts import normalize_mcp_read_result


AtlasTransport = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]


class ProjectResolution(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class ProjectIdentity:
    project_id: str
    name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectStatus:
    resolution: ProjectResolution
    project: ProjectIdentity | None
    candidates: tuple[ProjectIdentity, ...]
    status: str | None
    summary: str | None
    observed_at: datetime
    freshness: Freshness
    source_links: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectEvidence:
    resolution: ProjectResolution
    project: ProjectIdentity | None
    candidates: tuple[ProjectIdentity, ...]
    capability: str
    title: str | None
    summary: str | None
    state: str | None
    observed_at: datetime
    freshness: Freshness
    source_links: tuple[str, ...]


class AtlasReadConnector:
    """Read-only Atlas adapter that resolves a stable project ID before status."""

    def __init__(self, transport: AtlasTransport, *, clock=utc_now, stale_after_seconds: int = 86_400) -> None:
        self._transport = transport
        self._clock = clock
        self._stale_after_seconds = stale_after_seconds

    def project_status(self, query: str, *, max_projects: int = 100) -> ConnectorResult[ProjectStatus]:
        now = self._clock()
        if not isinstance(query, str) or not query.strip() or not 1 <= max_projects <= 500:
            return self._error(now, ErrorCode.INVALID_REQUEST, "project query or bound is invalid")
        try:
            listing = self._call("list_projects", {"limit": max_projects})
            projects = _projects(listing)
            matches = _resolve(projects, query)
            if len(matches) != 1:
                resolution = ProjectResolution.NOT_FOUND if not matches else ProjectResolution.AMBIGUOUS
                data = ProjectStatus(resolution, None, tuple(matches), None, None, now, Freshness.UNKNOWN, ())
                return ConnectorResult(ResultStatus.EMPTY if not matches else ResultStatus.SUCCESS, data, Provenance("atlas", "projects", "configured", observed_at=now))
            project = matches[0]
            raw = self._call("get_project_status", {"project_id": project.project_id})
            payload = _payload(raw)
            observed = _observed_at(payload) or now
            freshness = _freshness(payload, now, observed, self._stale_after_seconds)
            links = _source_links(payload)
            data = ProjectStatus(
                ProjectResolution.RESOLVED, project, (project,),
                _optional_text(payload.get("status") or payload.get("state")),
                _optional_text(payload.get("summary") or payload.get("description")),
                observed, freshness, links,
            )
            return ConnectorResult(
                ResultStatus.SUCCESS, data,
                Provenance("atlas", "projects", "configured", resource_ids=(project.project_id,), source_links=links, observed_at=observed, freshness=freshness),
            )
        except _AtlasReportedError:
            return self._error(now, ErrorCode.UNAVAILABLE, "Atlas reported a tool error")
        except Exception:
            return self._error(now, ErrorCode.UNAVAILABLE, "Atlas read failed")

    def project_brief(self, query: str, *, max_projects: int = 100) -> ConnectorResult[ProjectEvidence]:
        return self._project_evidence(query, "get_project_brief", "brief", max_projects=max_projects)

    def github_status(self, query: str, *, max_projects: int = 100) -> ConnectorResult[ProjectEvidence]:
        return self._project_evidence(query, "get_github_remote_status", "github", max_projects=max_projects)

    def _project_evidence(
        self, query: str, tool_name: str, capability: str, *, max_projects: int
    ) -> ConnectorResult[ProjectEvidence]:
        now = self._clock()
        if not isinstance(query, str) or not query.strip() or not 1 <= max_projects <= 500:
            return self._error(now, ErrorCode.INVALID_REQUEST, "project query or bound is invalid")
        try:
            matches = _resolve(_projects(self._call("list_projects", {"limit": max_projects})), query)
            if len(matches) != 1:
                resolution = ProjectResolution.NOT_FOUND if not matches else ProjectResolution.AMBIGUOUS
                data = ProjectEvidence(resolution, None, tuple(matches), capability, None, None, None, now, Freshness.UNKNOWN, ())
                return ConnectorResult(
                    ResultStatus.EMPTY if not matches else ResultStatus.SUCCESS,
                    data,
                    Provenance("atlas", "projects", "configured", observed_at=now),
                )
            project = matches[0]
            payload = _payload(self._call(tool_name, {"project_id": project.project_id}))
            observed = _observed_at(payload) or now
            freshness = _freshness(payload, now, observed, self._stale_after_seconds)
            links = _source_links(payload)
            data = ProjectEvidence(
                ProjectResolution.RESOLVED,
                project,
                (project,),
                capability,
                _optional_text(payload.get("title") or payload.get("name")),
                _optional_text(payload.get("summary") or payload.get("brief") or payload.get("description")),
                _optional_text(payload.get("status") or payload.get("state")),
                observed,
                freshness,
                links,
            )
            return ConnectorResult(
                ResultStatus.SUCCESS,
                data,
                Provenance("atlas", "projects", "configured", resource_ids=(project.project_id,), source_links=links, observed_at=observed, freshness=freshness),
            )
        except _AtlasReportedError:
            return self._error(now, ErrorCode.UNAVAILABLE, "Atlas reported a tool error")
        except Exception:
            return self._error(now, ErrorCode.UNAVAILABLE, "Atlas read failed")

    def _call(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        result = self._transport(tool_name, dict(arguments))
        if not isinstance(result, Mapping):
            raise ValueError("Atlas result must be an object")
        if result.get("status") in {"read_error", "disabled", "blocked", "not_configured"}:
            raise _AtlasReportedError
        # call_mcp_tool wraps the protocol result; direct MCP test transports do not.
        candidate = result.get("result") if result.get("attempted") is True else result
        normalized = normalize_mcp_read_result(candidate)
        if not normalized.completed:
            raise _AtlasReportedError
        return normalized.payload

    @staticmethod
    def _error(now: datetime, code: ErrorCode, message: str):
        return ConnectorResult(
            ResultStatus.UNAVAILABLE if code is ErrorCode.UNAVAILABLE else ResultStatus.ERROR,
            None,
            Provenance("atlas", "projects", "configured", observed_at=now, freshness=Freshness.UNKNOWN),
            error=ConnectorError(code, message, retryable=code is ErrorCode.UNAVAILABLE),
        )


class _AtlasReportedError(Exception):
    pass


def _projects(result: Mapping[str, Any]) -> list[ProjectIdentity]:
    payload = _payload(result)
    raw_items = payload.get("projects", payload.get("items", payload.get("results", ())))
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
        return []
    projects: list[ProjectIdentity] = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        project_id = _optional_text(item.get("project_id") or item.get("id"))
        name = _optional_text(item.get("name") or item.get("title") or item.get("project_name"))
        if not project_id or not name:
            continue
        aliases = item.get("aliases", ())
        projects.append(ProjectIdentity(project_id, name, tuple(str(alias) for alias in aliases) if isinstance(aliases, Sequence) and not isinstance(aliases, (str, bytes)) else ()))
    return projects


def _resolve(projects: Sequence[ProjectIdentity], query: str) -> list[ProjectIdentity]:
    needle = _normalized(query)
    if not needle:
        return []
    scored: list[tuple[int, ProjectIdentity]] = []
    for project in projects:
        identities = (project.project_id, project.name, *project.aliases)
        score = 0
        for identity in identities:
            candidate = _normalized(identity)
            if not candidate:
                continue
            if needle == candidate:
                score = max(score, 3)
            elif f" {candidate} " in f" {needle} ":
                score = max(score, 2)
        if score:
            scored.append((score, project))
    if not scored:
        return []
    best = max(score for score, _ in scored)
    return [project for score, project in scored if score == best]


def _payload(result: Mapping[str, Any]) -> Mapping[str, Any]:
    current = result
    for _ in range(4):
        structured = current.get("structuredContent")
        if isinstance(structured, Mapping):
            current = structured
            continue
        nested = current.get("result")
        if isinstance(nested, Mapping):
            current = nested
            continue
        break
    return current


def _normalized(value: str) -> str:
    return " ".join("".join(character if character.isalnum() else " " for character in value.casefold()).split())


def _observed_at(payload: Mapping[str, Any]) -> datetime | None:
    raw = payload.get("observed_at") or payload.get("updated_at")
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _freshness(payload: Mapping[str, Any], now: datetime, observed: datetime, stale_after: int) -> Freshness:
    explicit = str(payload.get("freshness") or "").casefold()
    if explicit in {item.value for item in Freshness}:
        return Freshness(explicit)
    if payload.get("stale") is True:
        return Freshness.STALE
    if not (payload.get("observed_at") or payload.get("updated_at")):
        return Freshness.UNKNOWN
    return Freshness.STALE if (now - observed).total_seconds() > stale_after else Freshness.CURRENT


def _source_links(payload: Mapping[str, Any]) -> tuple[str, ...]:
    values = [payload.get(key) for key in ("source_url", "html_url", "repository_url")]
    nested = payload.get("source_links", ())
    if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes)):
        values.extend(nested)
    return tuple(dict.fromkeys(value for value in values if isinstance(value, str) and value.startswith(("https://", "http://"))))


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None and str(value) else None
