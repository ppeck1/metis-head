from __future__ import annotations

from dataclasses import dataclass, field

from .schemas import SUPPORTED_ADAPTER_SCHEMAS


@dataclass(frozen=True)
class AdapterStatus:
    adapter_id: str
    enabled: bool
    health: str
    capabilities: list[str]
    schema_version: str
    schema_supported: bool


@dataclass
class AdapterBase:
    adapter_id: str
    role: str
    schema_version: str
    capabilities: list[str] = field(default_factory=list)
    enabled: bool = False
    health: str = "disabled"

    def health_check(self) -> AdapterStatus:
        schema_supported = self.schema_version in SUPPORTED_ADAPTER_SCHEMAS
        enabled = self.enabled and self.health == "ok" and schema_supported
        health = self.health if schema_supported else "schema_mismatch"
        return AdapterStatus(
            adapter_id=self.adapter_id,
            enabled=enabled,
            health=health,
            capabilities=list(self.capabilities),
            schema_version=self.schema_version,
            schema_supported=schema_supported,
        )

    def capability_check(self, capability: str) -> bool:
        status = self.health_check()
        return status.enabled and capability in status.capabilities

    def schema_version_check(self) -> bool:
        return self.schema_version in SUPPORTED_ADAPTER_SCHEMAS
