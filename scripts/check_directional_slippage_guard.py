import json
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.order_executor import (
    calculate_directional_slippage,
    is_adverse_slippage_too_high,
    is_favorable_execution_drift_too_high,
)


DIRECTIONAL_TEST_CASES = [
    ("BUY adverse movement blocks", "BUY", 100.00, 100.50, 0.30, True, 0.50, 0.00),
    ("BUY favorable movement allowed", "BUY", 100.00, 99.50, 0.30, False, 0.00, 0.50),
    ("SELL adverse movement blocks", "SELL", 100.00, 99.50, 0.30, True, 0.50, 0.00),
    ("SELL favorable movement allowed", "SELL", 100.00, 100.50, 0.30, False, 0.00, 0.50),
    ("SELL example from blocked setup should be allowed", "SELL", 4027.89, 4028.52, 0.30, False, 0.00, 0.63),
]


FAVORABLE_DRIFT_TEST_CASES = [
    ("BUY favorable drift within strict limit allowed", "BUY", 100.00, 99.25, 1.00, False, 0.75),
    ("BUY favorable drift above strict limit blocked", "BUY", 100.00, 98.75, 1.00, True, 1.25),
    ("SELL favorable drift within strict limit allowed", "SELL", 100.00, 100.75, 1.00, False, 0.75),
    ("SELL favorable drift above strict limit blocked", "SELL", 100.00, 101.25, 1.00, True, 1.25),
    ("SELL real example favorable 0.63 allowed", "SELL", 4027.89, 4028.52, 1.00, False, 0.63),
    ("SELL strict fake-spike favorable 1.31 blocked", "SELL", 4027.89, 4029.20, 1.00, True, 1.31),
]


def approx_equal(a, b, tolerance=0.0001):
    return abs(float(a) - float(b)) <= tolerance


def main():
    output_dir = PROJECT_ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    failed = []

    for name, signal, expected, execution, max_slippage, expected_blocked, expected_adverse, expected_favorable in DIRECTIONAL_TEST_CASES:
        blocked, report = is_adverse_slippage_too_high(
            signal=signal,
            expected_price=expected,
            execution_price=execution,
            max_slippage=max_slippage,
        )

        ok = (
            blocked == expected_blocked
            and approx_equal(report["adverse"], expected_adverse)
            and approx_equal(report["favorable"], expected_favorable)
        )

        row = {
            "test_type": "adverse_slippage",
            "name": name,
            "signal": signal,
            "expected": expected,
            "execution": execution,
            "limit": max_slippage,
            "blocked": blocked,
            "expected_blocked": expected_blocked,
            "adverse": report["adverse"],
            "expected_adverse": expected_adverse,
            "favorable": report["favorable"],
            "expected_favorable": expected_favorable,
            "absolute": report["absolute"],
            "signed": report["signed"],
            "ok": ok,
        }

        results.append(row)

        if not ok:
            failed.append(row)

    for name, signal, expected, execution, max_favorable, expected_blocked, expected_favorable in FAVORABLE_DRIFT_TEST_CASES:
        blocked, report = is_favorable_execution_drift_too_high(
            signal=signal,
            expected_price=expected,
            execution_price=execution,
            max_favorable_drift=max_favorable,
        )

        ok = (
            blocked == expected_blocked
            and approx_equal(report["favorable"], expected_favorable)
        )

        row = {
            "test_type": "favorable_drift",
            "name": name,
            "signal": signal,
            "expected": expected,
            "execution": execution,
            "limit": max_favorable,
            "blocked": blocked,
            "expected_blocked": expected_blocked,
            "adverse": report["adverse"],
            "favorable": report["favorable"],
            "expected_favorable": expected_favorable,
            "absolute": report["absolute"],
            "signed": report["signed"],
            "ok": ok,
        }

        results.append(row)

        if not ok:
            failed.append(row)

    all_ok = len(failed) == 0

    payload = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2BG",
        "all_ok": all_ok,
        "recommendation": (
            "DIRECTIONAL_SLIPPAGE_AND_FAVORABLE_DRIFT_GUARDS_OK"
            if all_ok
            else "FIX_EXECUTION_GUARDS"
        ),
        "failed_count": len(failed),
        "results": results,
    }

    report_path = output_dir / "directional_slippage_guard_safety_report.json"

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)

    print("[PHASE 2BG EXECUTION GUARD SAFETY]")
    print("all_ok =", all_ok)
    print("recommendation =", payload["recommendation"])

    print()
    print("[TEST CASES]")
    for row in results:
        print(
            f"{row['test_type']} | {row['name']} | signal={row['signal']} "
            f"expected={row['expected']} execution={row['execution']} "
            f"blocked={row['blocked']} adverse={row['adverse']} "
            f"favorable={row['favorable']} absolute={row['absolute']} "
            f"limit={row['limit']} ok={row['ok']}"
        )

    print()
    print("report =", report_path)

    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()