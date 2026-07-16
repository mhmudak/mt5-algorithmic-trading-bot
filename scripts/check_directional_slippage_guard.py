import json
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.order_executor import calculate_directional_slippage, is_adverse_slippage_too_high


TEST_CASES = [
    ("BUY adverse movement blocks", "BUY", 100.00, 100.50, 0.30, True, 0.50, 0.00),
    ("BUY favorable movement allowed", "BUY", 100.00, 99.50, 0.30, False, 0.00, 0.50),
    ("SELL adverse movement blocks", "SELL", 100.00, 99.50, 0.30, True, 0.50, 0.00),
    ("SELL favorable movement allowed", "SELL", 100.00, 100.50, 0.30, False, 0.00, 0.50),
    ("SELL example from blocked setup should be allowed", "SELL", 4027.89, 4028.52, 0.30, False, 0.00, 0.63),
]


def approx_equal(a, b, tolerance=0.0001):
    return abs(float(a) - float(b)) <= tolerance


def main():
    output_dir = PROJECT_ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    failed = []

    for name, signal, expected, execution, max_slippage, expected_blocked, expected_adverse, expected_favorable in TEST_CASES:
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
            "name": name,
            "signal": signal,
            "expected": expected,
            "execution": execution,
            "max_slippage": max_slippage,
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

    all_ok = len(failed) == 0

    payload = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2BE",
        "all_ok": all_ok,
        "recommendation": "DIRECTIONAL_SLIPPAGE_GUARD_OK" if all_ok else "FIX_DIRECTIONAL_SLIPPAGE_GUARD",
        "failed_count": len(failed),
        "results": results,
    }

    report_path = output_dir / "directional_slippage_guard_safety_report.json"

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)

    print("[PHASE 2BE DIRECTIONAL SLIPPAGE GUARD SAFETY]")
    print("all_ok =", all_ok)
    print("recommendation =", payload["recommendation"])

    print()
    print("[TEST CASES]")
    for row in results:
        print(
            f"{row['name']} | signal={row['signal']} "
            f"expected={row['expected']} execution={row['execution']} "
            f"blocked={row['blocked']} adverse={row['adverse']} "
            f"favorable={row['favorable']} absolute={row['absolute']} "
            f"ok={row['ok']}"
        )

    print()
    print("report =", report_path)

    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()