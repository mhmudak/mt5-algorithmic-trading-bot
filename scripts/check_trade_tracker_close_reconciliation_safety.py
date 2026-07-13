import argparse
import json
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def resolve_paths(source_dir):
    source_dir = Path(source_dir)

    if not source_dir.is_absolute():
        source_dir = PROJECT_ROOT / source_dir

    account_name = source_dir.name
    output_dir = PROJECT_ROOT / "data" / "strategy_intelligence" / account_name
    output_dir.mkdir(parents=True, exist_ok=True)

    return {
        "source_dir": source_dir,
        "account_name": account_name,
        "output_dir": output_dir,
        "trade_tracker_file": PROJECT_ROOT / "src" / "trade_tracker.py",
        "report_json": output_dir / "trade_tracker_close_reconciliation_safety_report.json",
    }


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)

    return path


def extract_block(text, start_marker, end_marker):
    start = text.find(start_marker)

    if start < 0:
        return ""

    end = text.find(end_marker, start)

    if end < 0:
        return text[start:]

    return text[start:end]


def check_order(block, first, second):
    first_pos = block.find(first)
    second_pos = block.find(second)

    return {
        "first": first,
        "second": second,
        "first_found": first_pos >= 0,
        "second_found": second_pos >= 0,
        "first_before_second": first_pos >= 0 and second_pos >= 0 and first_pos < second_pos,
        "first_position": first_pos,
        "second_position": second_pos,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Static safety check for trade tracker close reconciliation logic."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--strict",
        action="store_true",
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)

    text = paths["trade_tracker_file"].read_text(encoding="utf-8")

    fully_closed_block = extract_block(
        text,
        "# Fully closed / missing from open positions.",
        "# Partial close",
    )

    markers = {
        "phase_2ac_comment": "Phase 2AC" in fully_closed_block,
        "do_not_mark_closed_comment": "Do not mark the trade CLOSED until a matching MT5 close deal is resolved." in fully_closed_block,
        "detect_before_closed": check_order(
            fully_closed_block,
            'close_details = detect_close_details(position_id, trade=trade)',
            'trade["status"] = "CLOSED"',
        ),
        "unresolved_pending_flag": 'trade["close_reconciliation_pending"] = True' in fully_closed_block,
        "unresolved_status_open": 'trade["status"] = "OPEN"' in fully_closed_block,
        "resolved_pending_false": 'trade["close_reconciliation_pending"] = False' in fully_closed_block,
        "close_price_saved": 'trade["close_price"] = close_price' in fully_closed_block,
        "missing_position_counter": 'trade["missing_position_checks"]' in fully_closed_block,
        "status_remains_open_log": "status remains OPEN" in fully_closed_block,
    }

    checks = {
        "fully_closed_block_found": bool(fully_closed_block),
        "phase_2ac_comment_present": markers["phase_2ac_comment"],
        "detect_close_before_marking_closed": markers["detect_before_closed"]["first_before_second"],
        "unresolved_sets_pending_true": markers["unresolved_pending_flag"],
        "unresolved_keeps_status_open": markers["unresolved_status_open"],
        "resolved_sets_pending_false": markers["resolved_pending_false"],
        "resolved_saves_close_price": markers["close_price_saved"],
        "missing_position_counter_present": markers["missing_position_counter"],
        "status_remains_open_log_present": markers["status_remains_open_log"],
    }

    all_ok = all(checks.values())

    if not checks["fully_closed_block_found"]:
        recommendation = "REVIEW_TRADE_TRACKER_BLOCK_NOT_FOUND"
    elif not checks["detect_close_before_marking_closed"]:
        recommendation = "FIX_ORDER_DETECT_CLOSE_BEFORE_CLOSED"
    elif not checks["unresolved_keeps_status_open"]:
        recommendation = "FIX_UNRESOLVED_CLOSE_STATUS"
    elif not checks["resolved_saves_close_price"]:
        recommendation = "FIX_CLOSE_PRICE_PERSISTENCE"
    elif all_ok:
        recommendation = "TRADE_TRACKER_CLOSE_RECONCILIATION_SAFETY_CONFIRMED"
    else:
        recommendation = "REVIEW_TRADE_TRACKER_CLOSE_RECONCILIATION"

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2AD",
        "source_dir": str(paths["source_dir"]),
        "trade_tracker_file": str(paths["trade_tracker_file"]),
        "all_ok": all_ok,
        "recommendation": recommendation,
        "checks": checks,
        "markers": markers,
        "generated_files": {
            "report_json": str(paths["report_json"]),
        },
        "notes": [
            "This is a static safety check only.",
            "It does not modify live trading behavior.",
            "Old broken CLOSED rows are not repaired by this check.",
            "The goal is to prevent future unresolved missing-position trades from being saved as CLOSED.",
        ],
    }

    write_json(paths["report_json"], report)

    print("[PHASE 2AD TRADE TRACKER CLOSE RECONCILIATION SAFETY]")
    print("all_ok =", all_ok)
    print("recommendation =", recommendation)

    print()
    print("[CHECKS]")
    for key, value in checks.items():
        print(f"{key} = {value}")

    print()
    print("[ORDER]")
    order = markers["detect_before_closed"]
    print("detect_close_found =", order.get("first_found"))
    print("closed_status_found =", order.get("second_found"))
    print("detect_before_closed =", order.get("first_before_second"))

    print()
    print("report =", paths["report_json"])

    if args.strict and not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
