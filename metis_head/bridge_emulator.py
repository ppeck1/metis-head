from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable
from urllib import error, request

from .bridge import BRIDGE_SCHEMA_VERSION, button_event, control_change, hardware_privacy, heartbeat
from .reducer import replay_events
from .schemas import baseline_state, validate_event


BRIDGE_EMULATOR_VERSION = "metis_bridge_emulator.v0.1"
DEFAULT_BRAIN_URL = "http://127.0.0.1:8787"


class BridgeEmulatorError(RuntimeError):
    pass


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_event(event)
    normalized.setdefault("bridge_schema", BRIDGE_SCHEMA_VERSION)
    normalized.setdefault("emulator_version", BRIDGE_EMULATOR_VERSION)
    return normalized


def emulator_control(control: str, value: float, raw: int | None = None, timestamp_ms: int = 0) -> dict[str, Any]:
    return normalize_event(control_change(control, value, raw=raw, timestamp_ms=timestamp_ms))


def emulator_button(button: str, state: str | bool, timestamp_ms: int = 0) -> dict[str, Any]:
    return normalize_event(button_event(button, state, timestamp_ms=timestamp_ms))


def emulator_privacy(device: str, enabled: bool, timestamp_ms: int = 0) -> dict[str, Any]:
    return normalize_event(hardware_privacy(device, enabled, timestamp_ms=timestamp_ms))


def emulator_heartbeat(bridge_id: str = "sim-bridge-001", uptime_ms: int = 0, firmware: str = "sim.0.1") -> dict[str, Any]:
    return normalize_event(heartbeat(bridge_id=bridge_id, uptime_ms=uptime_ms, firmware=firmware))


def parse_jsonl_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise BridgeEmulatorError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise BridgeEmulatorError(f"line {line_number}: event must be a JSON object")
        try:
            events.append(normalize_event(parsed))
        except ValueError as exc:
            raise BridgeEmulatorError(f"line {line_number}: {exc}") from exc
    return events


def events_to_jsonl(events: Iterable[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(normalize_event(event), sort_keys=True) for event in events)


def replay_jsonl_locally(text: str) -> dict[str, Any]:
    return replay_events(baseline_state(), parse_jsonl_events(text))


def post_event(base_url: str, event: dict[str, Any], timeout: int = 5) -> dict[str, Any]:
    normalized = normalize_event(event)
    url = f"{base_url.rstrip('/')}/metis/event"
    data = json.dumps(normalized).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return _decode_response(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise BridgeEmulatorError(f"POST {url} failed with HTTP {exc.code}: {detail}") from exc
    except (error.URLError, OSError, TimeoutError) as exc:
        raise BridgeEmulatorError(f"POST {url} failed: {exc}") from exc


def post_events(base_url: str, events: Iterable[dict[str, Any]], timeout: int = 5) -> list[dict[str, Any]]:
    return [post_event(base_url, event, timeout=timeout) for event in events]


def _decode_response(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BridgeEmulatorError("mock Brain returned non-JSON response") from exc
    if not isinstance(parsed, dict):
        raise BridgeEmulatorError("mock Brain returned a non-object response")
    return parsed


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on", "enabled"}:
        return True
    if lowered in {"0", "false", "no", "off", "disabled"}:
        return False
    raise argparse.ArgumentTypeError(f"expected boolean value, got {value!r}")


def _emit_or_post(event: dict[str, Any], post_url: str | None) -> dict[str, Any]:
    if post_url:
        return post_event(post_url, event)
    return event


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Metis Head bridge emulator")
    parser.add_argument("--post", metavar="BASE_URL", help=f"post event(s) to a mock Brain, default route base like {DEFAULT_BRAIN_URL}")
    subcommands = parser.add_subparsers(dest="command", required=True)

    control = subcommands.add_parser("control", help="emit a control_change event")
    control.add_argument("control", choices=["volume", "conversation_depth", "initiative"])
    control.add_argument("value", type=float)
    control.add_argument("--raw", type=int)
    control.add_argument("--timestamp-ms", type=int, default=0)

    button = subcommands.add_parser("button", help="emit a button_event")
    button.add_argument("button", choices=["pwr", "loud", "afc", "am_fm"])
    button.add_argument("state")
    button.add_argument("--timestamp-ms", type=int, default=0)

    privacy = subcommands.add_parser("privacy", help="emit a hardware_privacy event")
    privacy.add_argument("device", choices=["mic", "camera"])
    privacy.add_argument("enabled", type=_parse_bool)
    privacy.add_argument("--timestamp-ms", type=int, default=0)

    beat = subcommands.add_parser("heartbeat", help="emit a heartbeat event")
    beat.add_argument("--bridge-id", default="sim-bridge-001")
    beat.add_argument("--uptime-ms", type=int, default=0)
    beat.add_argument("--firmware", default="sim.0.1")

    replay = subcommands.add_parser("replay", help="replay JSONL bridge events")
    replay.add_argument("path", type=Path)
    replay.add_argument("--local-final-state", action="store_true", help="print local reducer final state instead of event responses")
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "control":
            result = _emit_or_post(emulator_control(args.control, args.value, raw=args.raw, timestamp_ms=args.timestamp_ms), args.post)
        elif args.command == "button":
            result = _emit_or_post(emulator_button(args.button, args.state, timestamp_ms=args.timestamp_ms), args.post)
        elif args.command == "privacy":
            result = _emit_or_post(emulator_privacy(args.device, args.enabled, timestamp_ms=args.timestamp_ms), args.post)
        elif args.command == "heartbeat":
            result = _emit_or_post(emulator_heartbeat(args.bridge_id, args.uptime_ms, args.firmware), args.post)
        elif args.command == "replay":
            text = args.path.read_text(encoding="utf-8")
            events = parse_jsonl_events(text)
            if args.local_final_state or not args.post:
                result = replay_events(baseline_state(), events)
            else:
                result = {"responses": post_events(args.post, events), "event_count": len(events)}
        else:
            parser.error("unknown command")
            return 2
    except BridgeEmulatorError as exc:
        parser.exit(1, f"{exc}\n")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
