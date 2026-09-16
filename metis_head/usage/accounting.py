from __future__ import annotations

import json
import os
import threading
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


class PricingUnknown(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


class LedgerConfigurationError(RuntimeError):
    pass


@dataclass
class Reservation:
    reservation_id: str
    provider: str
    model: str
    reserved_usd: str
    pricing_version: str
    created_at: str
    status: str = "reserved"
    actual_usd: str | None = None
    actual_usage: dict[str, Any] | None = None
    estimate_metadata: dict[str, Any] | None = None


class UsageLedger:
    """Persistent, transactionally locked application-level paid-call ceiling.

    Every read/modify/write operation takes a lock on a stable sidecar file and
    reloads the ledger while holding that lock. The sidecar is important:
    locking the JSON file itself would not survive the atomic ``os.replace``
    used for durable writes. This coordinates independent ``UsageLedger``
    instances and processes, including on Windows.
    """

    def __init__(self, path: str | Path, budget_usd: str | Decimal | None = None) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.budget_usd = self._money(budget_usd) if budget_usd is not None else None
        self._records: list[Reservation] = []
        with self._transaction():
            if not self.path.exists():
                self._save_unlocked()

    @staticmethod
    def _money(value: str | Decimal | int | float) -> Decimal:
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("invalid monetary amount") from exc
        if not amount.is_finite() or amount < 0:
            raise ValueError("monetary amount must be finite and non-negative")
        return amount.quantize(Decimal("0.000001"))

    @property
    def committed_usd(self) -> Decimal:
        with self._transaction():
            return self._committed_usd()

    def _committed_usd(self) -> Decimal:
        total = Decimal("0")
        for item in self._records:
            if item.status == "reserved":
                total += Decimal(item.reserved_usd)
            elif item.status == "reconciled":
                total += Decimal(item.actual_usd or item.reserved_usd)
        return total

    def reserve(
        self,
        *,
        provider: str,
        model: str,
        estimated_usd: str | Decimal | None,
        pricing_version: str | None,
        estimate_metadata: dict[str, Any] | None = None,
    ) -> Reservation:
        with self._transaction():
            if estimated_usd is None or not pricing_version:
                raise PricingUnknown("paid call blocked: price or pricing configuration version is unknown")
            if self.budget_usd is None:
                raise BudgetExceeded("paid call blocked until METIS_PAID_BUDGET_USD is deliberately configured")
            amount = self._money(estimated_usd)
            if self._committed_usd() + amount > self.budget_usd:
                raise BudgetExceeded("paid call blocked: application budget would be exceeded")
            item = Reservation(
                reservation_id=f"usage_{uuid.uuid4().hex}",
                provider=provider,
                model=model,
                reserved_usd=str(amount),
                pricing_version=pricing_version,
                created_at=datetime.now(timezone.utc).isoformat(),
                estimate_metadata=dict(estimate_metadata or {}),
            )
            self._records.append(item)
            self._save_unlocked()
            return item

    def reconcile(
        self,
        reservation_id: str,
        *,
        actual_usd: str | Decimal | None,
        actual_usage: dict[str, Any] | None = None,
    ) -> Reservation:
        with self._transaction():
            item = self._find(reservation_id)
            if item.status != "reserved":
                return item
            item.actual_usd = str(self._money(actual_usd)) if actual_usd is not None else item.reserved_usd
            item.actual_usage = dict(actual_usage or {})
            item.status = "reconciled"
            self._save_unlocked()
            return item

    def release(self, reservation_id: str) -> Reservation:
        with self._transaction():
            item = self._find(reservation_id)
            if item.status == "reserved":
                item.status = "released"
                self._save_unlocked()
            return item

    def snapshot(self) -> dict[str, Any]:
        with self._transaction():
            return {
                "schema_version": "metis_usage.v1",
                "budget_configured": self.budget_usd is not None,
                "budget_usd": str(self.budget_usd) if self.budget_usd is not None else None,
                "committed_usd": str(self._committed_usd().quantize(Decimal("0.000001"))),
                "reservation_count": len(self._records),
                "records": [asdict(item) for item in self._records[-100:]],
            }

    def _find(self, reservation_id: str) -> Reservation:
        for item in self._records:
            if item.reservation_id == reservation_id:
                return item
        raise KeyError(reservation_id)

    def _load_unlocked(self) -> None:
        if not self.path.exists():
            self._records = []
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        stored_budget = payload.get("budget_usd")
        if "budget_usd" in payload:
            configured = str(self.budget_usd) if self.budget_usd is not None else None
            if stored_budget != configured:
                raise LedgerConfigurationError(
                    "usage ledger budget does not match this process; use one shared cumulative budget"
                )
        self._records = [Reservation(**item) for item in payload.get("records", [])]

    def _save_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(
            f"{self.path.name}.tmp.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}"
        )
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(
                    {
                        "schema_version": "metis_usage.v1",
                        "budget_usd": str(self.budget_usd) if self.budget_usd is not None else None,
                        "records": [asdict(item) for item in self._records],
                    },
                    handle,
                    indent=2,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    @contextmanager
    def _transaction(self):
        """Hold the process/thread transaction lock and refresh disk state."""

        with self._lock:
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock_path.open("a+b") as handle:
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                _lock_file(handle)
                try:
                    self._load_unlocked()
                    yield
                finally:
                    _unlock_file(handle)


def _lock_file(handle: Any) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock_file(handle: Any) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
