from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Mapping

from .connectors import CalendarConnector, ContactsConnector, GmailConnector, ResultStatus
from .connectors.atlas import AtlasReadConnector
from .connectors.google_access import GoogleReadBroker
from .orchestration import (
    AccessMode,
    AccountGrant,
    AdapterContext,
    AdapterResponse,
    AuthorizationContext,
    CancellationToken,
    Freshness,
    FreshnessStatus,
    LoopLimits,
    Provenance,
    ToolCall,
    ToolExecutor,
    ToolOrchestrator,
    ToolRequest,
    ToolResult,
    ToolResultStatus,
    ToolSpec,
)


CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
CONTACTS_SCOPE = "https://www.googleapis.com/auth/contacts.readonly"


class SingleReadAdapter:
    """Deterministic adapter used to exercise the complete result-aware loop."""

    def __init__(self, call: ToolCall) -> None:
        self._call = call

    def next_step(self, context: AdapterContext) -> AdapterResponse:
        if not context.exchanges:
            return AdapterResponse(tool_calls=(self._call,))
        result = context.exchanges[-1].result
        if result.ok:
            label = "No matching records were found" if result.status is ToolResultStatus.EMPTY else "Read completed"
            source = result.provenance[0].source_label if result.provenance else "configured provider"
            return AdapterResponse(text=f"{label} from {source}. Result: {result.data}")
        return AdapterResponse(text=f"The read did not complete ({result.status.value}): {result.message or result.error_code}.")


def run_google_read(
    *,
    session_id: str,
    turn_id: str,
    tool_name: str,
    arguments: Mapping[str, Any],
    account_id: str,
    granted_scopes: frozenset[str],
    calendar: CalendarConnector,
    gmail: GmailConnector,
    contacts: ContactsConnector,
) -> Any:
    entries = _entries(calendar, gmail, contacts)
    executor = ToolExecutor(entries)
    call = ToolCall("call-1", tool_name, "1", dict(arguments), account_id)
    orchestration = ToolOrchestrator(executor, SingleReadAdapter(call), LoopLimits(max_rounds=2, max_tool_calls=1))
    authorization = AuthorizationContext(accounts={account_id: AccountGrant(account_id, granted_scopes)})
    return orchestration.run(
        session_id=session_id,
        turn_id=turn_id,
        conversation=({"role": "user", "content": "Execute the selected read capability."},),
        authorization=authorization,
        cancellation=CancellationToken(),
        system_instructions="Use only the selected read-only capability and ground the response in its result.",
    )


def run_google_broker_read(
    *,
    session_id: str,
    turn_id: str,
    tool_name: str,
    arguments: Mapping[str, Any],
    account_id: str,
    broker: GoogleReadBroker,
) -> Any:
    """Run the compatibility read endpoint through the production grant broker."""
    entries = google_broker_entries(broker)
    call = ToolCall("call-1", tool_name, "1", dict(arguments), account_id)
    orchestration = ToolOrchestrator(
        ToolExecutor(entries),
        SingleReadAdapter(call),
        LoopLimits(max_rounds=2, max_tool_calls=1),
    )
    account = next((item for item in broker.accounts() if item.account_id == account_id), None)
    scopes = frozenset(account.scopes) if account is not None else frozenset()
    return orchestration.run(
        session_id=session_id,
        turn_id=turn_id,
        conversation=({"role": "user", "content": "Execute the selected read capability."},),
        authorization=AuthorizationContext(accounts={account_id: AccountGrant(account_id, scopes)}),
        cancellation=CancellationToken(),
        system_instructions="Use only the selected read-only capability and ground the response in its result.",
    )


def _entries(calendar: CalendarConnector, gmail: GmailConnector, contacts: ContactsConnector):
    object_schema = lambda properties, required: {"type": "object", "properties": properties, "required": required, "additionalProperties": False}
    calendar_spec = ToolSpec(
        "google.calendar.list", "1", "Read selected calendars in a bounded time range",
        object_schema({
            "calendar_ids": {"type": "array", "items": {"type": "string"}},
            "start": {"type": "string"}, "end": {"type": "string"}, "timezone": {"type": "string"},
        }, ["calendar_ids", "start", "end", "timezone"]),
        AccessMode.READ, frozenset({CALENDAR_SCOPE}), True,
    )
    gmail_spec = ToolSpec(
        "google.gmail.search", "1", "Search a selected Gmail account",
        object_schema({"query": {"type": "string"}, "max_messages": {"type": "integer", "minimum": 1, "maximum": 100}}, ["query"]),
        AccessMode.READ, frozenset({GMAIL_SCOPE}), True,
    )
    contacts_spec = ToolSpec(
        "google.contacts.lookup", "1", "Find an email address in a selected contacts account",
        object_schema({"query": {"type": "string"}}, ["query"]),
        AccessMode.READ, frozenset({CONTACTS_SCOPE}), True,
    )

    def calendar_handler(request: ToolRequest, _cancel: CancellationToken) -> ToolResult:
        try:
            result = calendar.list_events(
                account_id=request.account_id or "", calendar_ids=request.arguments["calendar_ids"],
                start=datetime.fromisoformat(request.arguments["start"].replace("Z", "+00:00")),
                end=datetime.fromisoformat(request.arguments["end"].replace("Z", "+00:00")),
                timezone=request.arguments["timezone"],
            )
        except (ValueError, TypeError) as exc:
            return ToolResult.failure(request.request_id, ToolResultStatus.INVALID, "invalid_datetime", str(exc))
        return _tool_result(request, result)

    def gmail_handler(request: ToolRequest, _cancel: CancellationToken) -> ToolResult:
        return _tool_result(request, gmail.search(account_id=request.account_id or "", query=request.arguments["query"], max_messages=request.arguments.get("max_messages", 25)))

    def contacts_handler(request: ToolRequest, _cancel: CancellationToken) -> ToolResult:
        return _tool_result(request, contacts.lookup_email(account_id=request.account_id or "", query=request.arguments["query"]))

    return {
        calendar_spec.name: (calendar_spec, calendar_handler),
        gmail_spec.name: (gmail_spec, gmail_handler),
        contacts_spec.name: (contacts_spec, contacts_handler),
    }


def google_broker_entries(broker: GoogleReadBroker):
    """Build the complete bounded Google read registry from one trusted broker."""
    object_schema = lambda properties, required: {
        "type": "object", "properties": properties, "required": required, "additionalProperties": False,
    }
    specs = {
        "google.calendar.discover": ToolSpec(
            "google.calendar.discover", "1", "Discover authorized calendars for a selected Google account",
            object_schema({
                "max_calendars": {"type": "integer", "minimum": 1, "maximum": 250},
                "max_pages": {"type": "integer", "minimum": 1, "maximum": 50},
            }, []),
            AccessMode.READ, frozenset({CALENDAR_SCOPE}), True,
        ),
        "google.calendar.list": ToolSpec(
            "google.calendar.list", "1", "Read explicitly selected calendars in a bounded time range",
            object_schema({
                "calendar_ids": {"type": "array", "items": {"type": "string"}},
                "start": {"type": "string"}, "end": {"type": "string"}, "timezone": {"type": "string"},
            }, ["calendar_ids", "start", "end", "timezone"]),
            AccessMode.READ, frozenset({CALENDAR_SCOPE}), True,
        ),
        "google.gmail.search": ToolSpec(
            "google.gmail.search", "1", "Search a selected Gmail account",
            object_schema({"query": {"type": "string"}, "max_messages": {"type": "integer", "minimum": 1, "maximum": 25}}, ["query"]),
            AccessMode.READ, frozenset({GMAIL_SCOPE}), True,
        ),
        "google.gmail.message": ToolSpec(
            "google.gmail.message", "1", "Read one selected Gmail message by stable ID",
            object_schema({"message_id": {"type": "string"}, "max_body_chars": {"type": "integer", "minimum": 1, "maximum": 20000}}, ["message_id"]),
            AccessMode.READ, frozenset({GMAIL_SCOPE}), True,
        ),
        "google.gmail.thread": ToolSpec(
            "google.gmail.thread", "1", "Read one selected Gmail thread by stable ID",
            object_schema({"thread_id": {"type": "string"}, "max_messages": {"type": "integer", "minimum": 1, "maximum": 20}}, ["thread_id"]),
            AccessMode.READ, frozenset({GMAIL_SCOPE}), True,
        ),
        "google.contacts.lookup": ToolSpec(
            "google.contacts.lookup", "1", "Resolve a contact email without choosing ambiguous matches",
            object_schema({"query": {"type": "string"}, "max_contacts": {"type": "integer", "minimum": 1, "maximum": 20}}, ["query"]),
            AccessMode.READ, frozenset({CONTACTS_SCOPE}), True,
        ),
    }

    def handler(request: ToolRequest, _cancel: CancellationToken) -> ToolResult:
        args = request.arguments
        account_id = request.account_id or ""
        try:
            if request.tool_name == "google.calendar.discover":
                result = broker.list_calendars(
                    account_id=account_id,
                    max_calendars=args.get("max_calendars", 100),
                    max_pages=args.get("max_pages", 10),
                )
            elif request.tool_name == "google.calendar.list":
                result = broker.calendar_events(
                    account_id=account_id,
                    calendar_ids=args["calendar_ids"],
                    start=datetime.fromisoformat(args["start"].replace("Z", "+00:00")),
                    end=datetime.fromisoformat(args["end"].replace("Z", "+00:00")),
                    timezone=args["timezone"],
                )
            elif request.tool_name == "google.gmail.search":
                result = broker.gmail_search(account_id=account_id, query=args["query"], max_messages=args.get("max_messages", 25))
            elif request.tool_name == "google.gmail.message":
                result = broker.gmail_message(account_id=account_id, message_id=args["message_id"], max_body_chars=args.get("max_body_chars", 20_000))
            elif request.tool_name == "google.gmail.thread":
                result = broker.gmail_thread(account_id=account_id, thread_id=args["thread_id"], max_messages=args.get("max_messages", 20))
            else:
                result = broker.contact_email(account_id=account_id, query=args["query"], max_contacts=args.get("max_contacts", 20))
        except (ValueError, TypeError, KeyError) as exc:
            return ToolResult.failure(request.request_id, ToolResultStatus.INVALID, "invalid_arguments", str(exc))
        return _tool_result(request, result)

    return {name: (spec, handler) for name, spec in specs.items()}


def atlas_registry_entries(connector: AtlasReadConnector):
    """Production-ready, read-only Atlas registry entries.

    Composition supplies the configured MCP-backed connector; these handlers
    preserve canonical project resolution, MCP normalization, and provenance.
    """
    object_schema = lambda properties, required: {
        "type": "object", "properties": properties, "required": required, "additionalProperties": False,
    }
    argument_schema = object_schema(
        {
            "project": {"type": "string", "minLength": 1, "maxLength": 240},
            "max_projects": {"type": "integer", "minimum": 1, "maximum": 500},
        },
        ["project"],
    )
    specs = {
        "atlas.project.status": ToolSpec(
            "atlas.project.status", "1", "Resolve a named project and read its current Atlas status",
            argument_schema, AccessMode.READ, frozenset(), False,
        ),
        "atlas.project.brief": ToolSpec(
            "atlas.project.brief", "1", "Resolve a named project and read its Atlas brief",
            argument_schema, AccessMode.READ, frozenset(), False,
        ),
        "atlas.project.github_status": ToolSpec(
            "atlas.project.github_status", "1", "Resolve a named project and read its Atlas GitHub evidence",
            argument_schema, AccessMode.READ, frozenset(), False,
        ),
    }

    def handler(request: ToolRequest, _cancel: CancellationToken) -> ToolResult:
        query = request.arguments["project"]
        maximum = request.arguments.get("max_projects", 100)
        if request.tool_name == "atlas.project.status":
            result = connector.project_status(query, max_projects=maximum)
        elif request.tool_name == "atlas.project.brief":
            result = connector.project_brief(query, max_projects=maximum)
        else:
            result = connector.github_status(query, max_projects=maximum)
        return _tool_result(request, result)

    return {name: (spec, handler) for name, spec in specs.items()}


def _tool_result(request: ToolRequest, result: Any) -> ToolResult:
    statuses = {
        ResultStatus.SUCCESS: ToolResultStatus.SUCCESS,
        ResultStatus.EMPTY: ToolResultStatus.EMPTY,
        ResultStatus.UNAVAILABLE: ToolResultStatus.UNAVAILABLE,
        ResultStatus.ERROR: ToolResultStatus.ERROR,
    }
    provenance = result.provenance
    source_uri = provenance.source_links[0] if provenance.source_links else None
    common = {
        "request_id": request.request_id,
        "status": statuses[result.status],
        "provenance": (Provenance(f"{provenance.provider}:{provenance.service}", f"{provenance.provider} {provenance.service}", provenance.account_id, source_uri=source_uri),),
        "freshness": Freshness(FreshnessStatus(provenance.freshness.value), observed_at=provenance.observed_at),
        "truncated": result.truncated,
    }
    if result.ok:
        data = asdict(result.data) if hasattr(result.data, "__dataclass_fields__") else [asdict(item) for item in result.data] if isinstance(result.data, tuple) else result.data
        return ToolResult(data=data, **common)
    return ToolResult(error_code=result.error.code.value if result.error else "provider_error", message=result.error.message if result.error else "provider read failed", **common)
