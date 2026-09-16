from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .contracts import AccessMode, ToolRequest, ToolSpec


class AuthorizationError(PermissionError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class AccountGrant:
    account_id: str
    scopes: frozenset[str]
    resources: frozenset[str] = field(default_factory=lambda: frozenset({"*"}))


@dataclass(frozen=True)
class AuthorizationContext:
    accounts: Mapping[str, AccountGrant]
    allow_write: bool = False

    def authorize(self, spec: ToolSpec, request: ToolRequest) -> None:
        if request.tool_name != spec.name or request.tool_version != spec.version:
            raise AuthorizationError("tool_identity_mismatch", "tool name or version does not match its registered specification")
        if spec.access is AccessMode.WRITE and not self.allow_write:
            raise AuthorizationError("write_not_granted", "write tools are not enabled for this request")
        if spec.account_required and not request.account_id:
            raise AuthorizationError("account_required", "an explicitly selected account is required")

        if request.account_id is None:
            if spec.required_scopes:
                raise AuthorizationError("account_required", "scoped tool requires an account grant")
            return

        grant = self.accounts.get(request.account_id)
        if grant is None:
            raise AuthorizationError("account_not_connected", "the selected account is not connected")
        if request.granted_scopes != grant.scopes:
            raise AuthorizationError("untrusted_scope_claim", "request capability scopes must come from the trusted account grant")
        missing = spec.required_scopes - grant.scopes
        if missing:
            raise AuthorizationError("scope_not_granted", f"missing required scope(s): {', '.join(sorted(missing))}")

        if spec.resource_argument:
            resource = request.arguments.get(spec.resource_argument)
            if not isinstance(resource, str) or not resource:
                raise AuthorizationError("resource_required", f"resource argument {spec.resource_argument!r} is required")
            if "*" not in grant.resources and resource not in grant.resources:
                raise AuthorizationError("resource_not_granted", "the selected resource is outside the account grant")
