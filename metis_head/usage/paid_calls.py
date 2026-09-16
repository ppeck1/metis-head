from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_UP
from typing import Any, Callable, Mapping, TypeVar

from metis_head.orchestration import CancellationToken

from .accounting import UsageLedger


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("token counts must be non-negative")


@dataclass(frozen=True)
class ModelPrice:
    provider: str
    model: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    pricing_version: str

    def __post_init__(self) -> None:
        if not self.provider or not self.model or not self.pricing_version:
            raise ValueError("provider, model, and pricing version are required")
        if (
            not self.input_usd_per_million.is_finite()
            or not self.output_usd_per_million.is_finite()
            or self.input_usd_per_million < 0
            or self.output_usd_per_million < 0
        ):
            raise ValueError("prices must be finite and non-negative")

    def cost(self, usage: TokenUsage) -> Decimal:
        million = Decimal(1_000_000)
        cost = (
            Decimal(usage.input_tokens) * self.input_usd_per_million
            + Decimal(usage.output_tokens) * self.output_usd_per_million
        ) / million
        # Match the ledger's precision while rounding reservations upward.
        return cost.quantize(Decimal("0.000001"), rounding=ROUND_UP)


class PricingCatalog:
    def __init__(self, prices: Mapping[tuple[str, str], ModelPrice]) -> None:
        self._prices = dict(prices)

    def get(self, provider: str, model: str) -> ModelPrice | None:
        return self._prices.get((provider, model))


@dataclass(frozen=True)
class PaidCallReceipt:
    value: Any
    reservation_id: str
    reserved_usd: Decimal
    actual_usd: Decimal


class PaidCallCancelled(RuntimeError):
    pass


T = TypeVar("T")


class PaidCallExecutor:
    """Reservation-first boundary; no callable is entered until spend is approved."""

    def __init__(self, ledger: UsageLedger, pricing: PricingCatalog) -> None:
        self._ledger = ledger
        self._pricing = pricing

    def execute(
        self,
        *,
        provider: str,
        model: str,
        maximum_usage: TokenUsage,
        cancellation: CancellationToken,
        call: Callable[[], T],
        usage_from_result: Callable[[T], TokenUsage | None],
        estimate_metadata: Mapping[str, Any] | None = None,
    ) -> PaidCallReceipt:
        price = self._pricing.get(provider, model)
        # Passing None deliberately delegates the fail-closed unknown-price check
        # to the persistent ledger before the outbound callable can run.
        reservation = self._ledger.reserve(
            provider=provider,
            model=model,
            estimated_usd=price.cost(maximum_usage) if price else None,
            pricing_version=price.pricing_version if price else None,
            estimate_metadata=dict(estimate_metadata or {}),
        )
        reserved = Decimal(reservation.reserved_usd)
        if cancellation.cancelled:
            self._ledger.release(reservation.reservation_id)
            raise PaidCallCancelled(cancellation.reason or "paid call cancelled before dispatch")

        try:
            value = call()
        except BaseException:
            # Once dispatch begins the provider may have accepted/billed the call.
            # Conservatively keep the full reservation as actual spend.
            self._ledger.reconcile(
                reservation.reservation_id,
                actual_usd=None,
                actual_usage={"accounting": "reserved_after_uncertain_dispatch"},
            )
            raise

        usage = usage_from_result(value)
        actual = price.cost(usage) if price is not None and usage is not None else reserved
        self._ledger.reconcile(
            reservation.reservation_id,
            actual_usd=actual,
            actual_usage={
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "source": "provider_reported",
            }
            if usage is not None
            else {"source": "reservation_fallback"},
        )
        return PaidCallReceipt(value=value, reservation_id=reservation.reservation_id, reserved_usd=reserved, actual_usd=actual)
