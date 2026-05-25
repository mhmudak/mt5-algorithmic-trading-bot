from collections import Counter, defaultdict
from datetime import datetime
import sys
import argparse
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.setup_audit import load_setup_audit, get_setup_audit_file


def normalize_event(event):
    if not event:
        return "UNKNOWN"

    event = str(event).upper()

    if "TRADE_CLOSED" in event:
        return "TRADE_CLOSED"

    if "FAILED" in event:
        return "EXECUTION_FAILED"

    if "EXECUTED" in event or event == "EXECUTION_ATTEMPT":
        return "EXECUTED"

    if "RR" in event:
        return "RR_REJECTED"

    if "SMC" in event:
        return "SMC_REJECTED"

    if "M5" in event or "CONFIRMATION" in event:
        return "CONFIRMATION_REJECTED"

    if "DELAYED" in event:
        return "DELAYED_ENTRY"

    if "BETTER" in event:
        return "BETTER_ENTRY"

    if "EXPIRED" in event:
        return "EXPIRED"

    if "INVALID" in event:
        return "INVALIDATED"

    return event

def normalize_reason(reason):
    if not reason:
        return "UNKNOWN"

    reason = str(reason).lower()

    if "mtf_conflict" in reason:
        return "MTF_CONFLICT"

    if "htf_liquidity" in reason:
        return "HTF_LIQUIDITY_REJECTED"

    if "htf_rejected" in reason:
        return "HTF_REJECTED"

    if "low_rr" in reason:
        return "LOW_RR"
    
    if "soft_smc_pass" in reason:
        return "SOFT_SMC_PASS"

    if "smc_failed" in reason:
        return "SMC_REJECTED"

    if "m5" in reason or "confirmation" in reason:
        return "CONFIRMATION_REJECTED"

    if "slippage" in reason:
        return "SLIPPAGE_BLOCKED"

    if "price drift" in reason or "drift" in reason:
        return "PRICE_DRIFT_BLOCKED"

    if "too_extended" in reason:
        return "TOO_EXTENDED"

    if "sending order" in reason:
        return "ORDER_SENT"
    
    if "split_delayed_entry" in reason:
        return "SPLIT_DELAYED_ENTRY"

    if "confluence:" in reason:
        return "SETUP_CONTEXT"

    if "session:" in reason:
        return "SETUP_CONTEXT"

    if "macro:" in reason:
        return "SETUP_CONTEXT"

    if "smc:" in reason:
        return "SETUP_CONTEXT"

    return "OTHER"

def load_audit_from_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_report(file_path=None, exclude_manual=False):
    if file_path:
        audit = load_audit_from_file(file_path)
        audit_file = Path(file_path)
    else:
        audit = load_setup_audit()
        audit_file = get_setup_audit_file()

    if not audit:
        print("No setup audit data found.")
        print(f"Expected file: {get_setup_audit_file()}")
        return

    total_setups = 0
    latest_event_counter = Counter()
    all_event_counter = Counter()
    strategy_counter = Counter()
    rejection_reason_counter = Counter()
    strategy_event_counter = defaultdict(Counter)
    reason_bucket_counter = Counter()
    strategy_reason_bucket_counter = defaultdict(Counter)
    blocking_reason_bucket_counter = Counter()
    strategy_blocking_reason_bucket_counter = defaultdict(Counter)
    
    blocking_events = {
        "CANDIDATE_REJECTED",
        "RR_REJECTED",
        "TRADE_BLOCKED",
        "EXECUTION_FAILED",
        "SMC_REJECTED",
        "CONFIRMATION_REJECTED",
    }

    executed = 0
    closed = 0

    for setup in audit.values():
        strategy = setup.get("strategy", "UNKNOWN")
        setup_id = str(setup.get("setup_id", ""))

        if exclude_manual and (
            strategy == "MANUAL"
            or setup_id.startswith("MANUAL")
        ):
            continue
        total_setups += 1
        latest_event = normalize_event(setup.get("latest_event"))

        strategy_counter[strategy] += 1
        latest_event_counter[latest_event] += 1
        strategy_event_counter[strategy][latest_event] += 1

        if latest_event == "EXECUTED":
            executed += 1

        if latest_event == "TRADE_CLOSED":
            closed += 1

        for event in setup.get("events", []):
            event_name = normalize_event(event.get("event"))
            all_event_counter[event_name] += 1

            reason = event.get("reason")

            if reason:
                reason_text = str(reason)
                reason_bucket = normalize_reason(reason_text)

                rejection_reason_counter[reason_text] += 1
                reason_bucket_counter[reason_bucket] += 1
                strategy_reason_bucket_counter[strategy][reason_bucket] += 1

                if event_name in blocking_events:
                    blocking_reason_bucket_counter[reason_bucket] += 1
                    strategy_blocking_reason_bucket_counter[strategy][reason_bucket] += 1

    if total_setups == 0:
        print("No matching setup audit data found.")
        print(f"Audit File: {audit_file}")
        return

    print("\n==============================")
    print("SETUP FUNNEL REPORT")
    print("==============================")
    print(f"Generated At: {datetime.now().isoformat(timespec='seconds')}")
    print(f"Audit File: {audit_file}")
    print(f"Total Setups: {total_setups}")
    print(f"Executed Latest: {executed}")
    print(f"Closed Latest: {closed}")

    print("\n--- Latest Event Summary ---")
    for event, count in latest_event_counter.most_common():
        pct = round((count / total_setups) * 100, 2)
        print(f"{event}: {count} ({pct}%)")

    print("\n--- All Events Summary ---")
    for event, count in all_event_counter.most_common():
        print(f"{event}: {count}")

    print("\n--- Strategy Summary ---")
    for strategy, count in strategy_counter.most_common():
        print(f"{strategy}: {count}")

    print("\n--- Strategy x Latest Event ---")
    for strategy, events in sorted(strategy_event_counter.items()):
        parts = [f"{event}={count}" for event, count in events.most_common()]
        print(f"{strategy}: " + ", ".join(parts))

    print("\n--- Reason Buckets ---")
    for reason, count in reason_bucket_counter.most_common():
        pct = round((count / max(1, sum(reason_bucket_counter.values()))) * 100, 2)
        print(f"{reason}: {count} ({pct}%)")
        
    print("\n--- Strategy x Reason Bucket ---")
    for strategy, buckets in sorted(strategy_reason_bucket_counter.items()):
        parts = [
            f"{bucket}={count}"
            for bucket, count in buckets.most_common()
        ]
    
        print(f"{strategy}: " + ", ".join(parts))
    
    print("\n--- Blocking Reason Buckets Only ---")
    for reason, count in blocking_reason_bucket_counter.most_common():
        print(f"{reason}: {count}")

    print("\n--- Strategy x Blocking Reason Bucket ---")
    for strategy, buckets in sorted(strategy_blocking_reason_bucket_counter.items()):
        parts = [
            f"{bucket}={count}"
            for bucket, count in buckets.most_common()
        ]
        print(f"{strategy}: " + ", ".join(parts))
    
    print("\n--- Top Reasons ---")
    for reason, count in rejection_reason_counter.most_common(25):
        print(f"{count}x | {reason}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Path to setup_audit.json")
    parser.add_argument(
        "--exclude-manual",
        action="store_true",
        help="Exclude manually imported/open positions from the report",
    )
    args = parser.parse_args()
    
    build_report(
        file_path=args.file,
        exclude_manual=args.exclude_manual,
    )