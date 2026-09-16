from decimal import Decimal
import re

from metis_head.model_adapters import OpenAICompatibleConfig, OpenAICompatibleToolAdapter
from metis_head.orchestration import AccessMode, AdapterContext, CancellationToken, ToolSpec
from metis_head.usage import ModelPrice, PaidCallExecutor, PricingCatalog, UsageLedger


class WireTransport:
    def __init__(self) -> None:
        self.payload = None

    def post_json(self, **kwargs):
        self.payload = kwargs["payload"]
        wire_name = self.payload["tools"][0]["function"]["name"]
        return {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {"id": "call-1", "function": {"name": wire_name, "arguments": "{}"}}
                        ]
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        }


def test_dotted_metis_tool_name_round_trips_through_portable_wire_name(tmp_path) -> None:
    transport = WireTransport()
    ledger = UsageLedger(tmp_path / "usage.json", "1")
    price = ModelPrice("compatible", "fixture", Decimal("1"), Decimal("1"), "v1")
    adapter = OpenAICompatibleToolAdapter(
        OpenAICompatibleConfig(provider="compatible", model="fixture", base_url="https://provider.invalid/v1"),
        transport,
        PaidCallExecutor(ledger, PricingCatalog({("compatible", "fixture"): price})),
        CancellationToken(),
    )
    spec = ToolSpec(
        name="google.calendar.list",
        version="1",
        description="fixture",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        access=AccessMode.READ,
    )
    result = adapter.next_step(AdapterContext("safe", (), (spec,), (), 1))

    wire_name = transport.payload["tools"][0]["function"]["name"]
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", wire_name)
    assert wire_name != spec.name
    assert result.tool_calls[0].tool_name == spec.name
    assert result.tool_calls[0].call_id == "call-1"
