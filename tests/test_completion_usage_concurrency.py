from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

import pytest

from metis_head.usage import BudgetExceeded, LedgerConfigurationError, UsageLedger


def test_independent_instances_cannot_oversubscribe_one_budget(tmp_path: Path) -> None:
    path = tmp_path / "shared-usage.json"
    ledgers = [UsageLedger(path, "0.10"), UsageLedger(path, "0.10")]
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    outcome_lock = threading.Lock()

    def reserve(ledger: UsageLedger) -> None:
        barrier.wait()
        try:
            ledger.reserve(
                provider="fixture",
                model="shared",
                estimated_usd="0.08",
                pricing_version="fixture-v1",
            )
            result = "reserved"
        except BudgetExceeded:
            result = "blocked"
        with outcome_lock:
            outcomes.append(result)

    threads = [threading.Thread(target=reserve, args=(ledger,)) for ledger in ledgers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(outcomes) == ["blocked", "reserved"]
    snapshot = UsageLedger(path, "0.10").snapshot()
    assert snapshot["committed_usd"] == "0.080000"
    assert snapshot["reservation_count"] == 1


@pytest.mark.skipif(sys.platform != "win32", reason="exercises the Windows file-lock implementation")
def test_independent_windows_processes_cannot_oversubscribe(tmp_path: Path) -> None:
    ledger_path = tmp_path / "process-usage.json"
    gate_path = tmp_path / "go"
    worker = (
        "import pathlib,sys,time;"
        "from metis_head.usage import BudgetExceeded,UsageLedger;"
        "ledger=UsageLedger(sys.argv[1],'0.10');"
        "gate=pathlib.Path(sys.argv[2]);"
        "\nwhile not gate.exists(): time.sleep(0.005)"
        "\ntry:"
        "\n ledger.reserve(provider='fixture',model='shared',estimated_usd='0.08',pricing_version='v1')"
        "\n print('reserved')"
        "\nexcept BudgetExceeded: print('blocked')"
    )
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", worker, str(ledger_path), str(gate_path)],
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    gate_path.write_text("go", encoding="utf-8")
    results = [process.communicate(timeout=15) for process in processes]

    assert [process.returncode for process in processes] == [0, 0], results
    assert sorted(stdout.strip() for stdout, _ in results) == ["blocked", "reserved"]
    snapshot = UsageLedger(ledger_path, "0.10").snapshot()
    assert snapshot["committed_usd"] == "0.080000"
    assert snapshot["reservation_count"] == 1


def test_unreconciled_reservation_survives_restart_and_blocks_new_spend(tmp_path: Path) -> None:
    path = tmp_path / "durable-usage.json"
    first = UsageLedger(path, "0.10")
    reservation = first.reserve(
        provider="fixture",
        model="shared",
        estimated_usd="0.08",
        pricing_version="fixture-v1",
        estimate_metadata={"input_accounting": "heuristic_estimate_not_hard_cap"},
    )

    restarted = UsageLedger(path, "0.10")
    with pytest.raises(BudgetExceeded):
        restarted.reserve(
            provider="fixture",
            model="shared",
            estimated_usd="0.03",
            pricing_version="fixture-v1",
        )

    record = restarted.snapshot()["records"][0]
    assert record["reservation_id"] == reservation.reservation_id
    assert record["status"] == "reserved"
    assert record["estimate_metadata"]["input_accounting"] == "heuristic_estimate_not_hard_cap"


def test_shared_ledger_rejects_processes_with_inconsistent_budget_configuration(tmp_path: Path) -> None:
    path = tmp_path / "shared-budget.json"
    UsageLedger(path, "0.10")

    with pytest.raises(LedgerConfigurationError, match="one shared cumulative budget"):
        UsageLedger(path, "1.00")
