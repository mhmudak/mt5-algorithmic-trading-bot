from collections import Counter, defaultdict
from datetime import datetime

from src.setup_audit import load_setup_audit, get_setup_audit_file


def normalize_event(event):
    if not event:
        return "UNKNOWN"

    event = str(event).upper()

    if "EXECUT" in event:
        return "EXECUTED"

    if "FAILED" in event:
        return "EXECUTION_FAILED"

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

    if "TRADE_CLOSED" in event:
        return "TRADE_CLOSED"

    return event


def build_report():
    audit = load_setup_audit()

    if not audit:
        print("No setup audit data found.")
        print(f"Expected file: {get_setup_audit_file()}")
        return

    total_setups = len(audit)
    latest_event_counter = Counter()
    all_event_counter = Counter()
    strategy_counter = Counter()
    rejection_reason_counter = Counter()
    strategy_event_counter = defaultdict(Counter)

    executed = 0
    closed = 0

    for setup in audit.values():
        strategy = setup.get("strategy", "UNKNOWN")
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
                rejection_reason_counter[str(reason)] += 1

    print("\n==============================")
    print("SETUP FUNNEL REPORT")
    print("==============================")
    print(f"Generated At: {datetime.now().isoformat(timespec='seconds')}")
    print(f"Audit File: {get_setup_audit_file()}")
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

    print("\n--- Top Reasons ---")
    for reason, count in rejection_reason_counter.most_common(25):
        print(f"{count}x | {reason}")


if __name__ == "__main__":
    build_report()