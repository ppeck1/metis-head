from decimal import Decimal

import pytest

from metis_head.model_adapters import OpenAICompatibleConfig, OpenAICompatibleToolAdapter, ProviderProtocolError
from metis_head.orchestration import AdapterContext, CancellationToken
from metis_head.usage import ModelPrice, PaidCallExecutor, PricingCatalog, UsageLedger


class RecordingTransport:
    def __init__(self) -> None:
        self.calls = 0

    def post_json(self, **kwargs):
        self.calls += 1
        return {"choices": [{"message": {"content": "unexpected"}}]}


def test_oversized_input_is_rejected_before_reservation_or_transport(tmp_path) -> None:
    transport = RecordingTransport()
    ledger = UsageLedger(tmp_path / "usage.json", "1")
    price = ModelPrice("compatible", "fixture", Decimal("1"), Decimal("1"), "v1")
    provider = OpenAICompatibleToolAdapter(
        OpenAICompatibleConfig(
            provider="compatible",
            model="fixture",
            base_url="https://provider.invalid/v1",
            maximum_input_tokens=10,
        ),
        transport,
        PaidCallExecutor(ledger, PricingCatalog({("compatible", "fixture"): price})),
        CancellationToken(),
    )
    context = AdapterContext(
        system_instructions="bounded",
        conversation=({"role": "user", "content": "x" * 500},),
        tool_specs=(),
        exchanges=(),
        remaining_rounds=1,
    )

    with pytest.raises(ProviderProtocolError, match="heuristic input-token estimate exceeded"):
        provider.next_step(context)

    assert transport.calls == 0
    assert ledger.snapshot()["reservation_count"] == 0
