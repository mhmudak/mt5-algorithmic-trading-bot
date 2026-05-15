import csv
import json
from collections import defaultdict
from pathlib import Path

import MetaTrader5 as mt5

from src.account_context import get_account_file


def load_json(path: Path):
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def safe_float(value):
    try:
        if value in [None, "", "N/A"]:
            return None
        return float(value)
    except Exception:
        return None


def summarize_strategy_events(setup_audit):
    summary = defaultdict(lambda: {
        "detected": 0,
        "candidate_rejected": 0,
        "trade_plan_ready": 0,
        "trade_blocked": 0,
        "execution_attempt": 0,
        "execution_failed": 0,
        "trade_closed": 0,
        "win": 0,
        "loss": 0,
        "breakeven": 0,
        "avg_score_values": [],
        "avg_rr_values": [],
        "common_reasons": defaultdict(int),
    })

    for _, setup in setup_audit.items():
        strategy = setup.get("strategy", "UNKNOWN")
        events = setup.get("events", [])

        for event in events:
            event_name = event.get("event")
            reason = event.get("reason", "")
            rr = safe_float(event.get("rr"))
            score = safe_float(setup.get("score"))

            if score is not None:
                summary[strategy]["avg_score_values"].append(score)

            if rr is not None:
                summary[strategy]["avg_rr_values"].append(rr)

            if reason:
                summary[strategy]["common_reasons"][reason] += 1

            if event_name == "SETUP_DETECTED":
                summary[strategy]["detected"] += 1
            elif event_name == "CANDIDATE_REJECTED":
                summary[strategy]["candidate_rejected"] += 1
            elif event_name == "TRADE_PLAN_READY":
                summary[strategy]["trade_plan_ready"] += 1
            elif event_name == "TRADE_BLOCKED":
                summary[strategy]["trade_blocked"] += 1
            elif event_name == "EXECUTION_ATTEMPT":
                summary[strategy]["execution_attempt"] += 1
            elif event_name == "EXECUTION_FAILED":
                summary[strategy]["execution_failed"] += 1
            elif event_name == "TRADE_CLOSED":
                summary[strategy]["trade_closed"] += 1

                extra = event.get("extra", {})
                final_result = extra.get("final_result")

                if final_result == "WIN":
                    summary[strategy]["win"] += 1
                elif final_result == "LOSS":
                    summary[strategy]["loss"] += 1
                elif final_result == "BREAKEVEN":
                    summary[strategy]["breakeven"] += 1

    return summary


def build_rows(summary):
    rows = []

    for strategy, data in summary.items():
        detected = data["detected"]
        executed = data["execution_attempt"]
        closed = data["trade_closed"]
        wins = data["win"]
        losses = data["loss"]

        execution_rate = round((executed / detected) * 100, 2) if detected else 0
        win_rate = round((wins / closed) * 100, 2) if closed else 0

        avg_score = (
            round(sum(data["avg_score_values"]) / len(data["avg_score_values"]), 2)
            if data["avg_score_values"]
            else 0
        )

        avg_rr = (
            round(sum(data["avg_rr_values"]) / len(data["avg_rr_values"]), 2)
            if data["avg_rr_values"]
            else 0
        )

        top_reason = ""
        if data["common_reasons"]:
            top_reason = max(
                data["common_reasons"].items(),
                key=lambda item: item[1],
            )[0]

        if detected >= 5 and executed == 0:
            decision = "REVIEW: detects but never executes"
        elif closed >= 5 and win_rate < 40:
            decision = "REVIEW: weak win rate"
        elif closed >= 5 and win_rate >= 55:
            decision = "KEEP: promising"
        elif data["trade_blocked"] > detected * 0.5:
            decision = "REVIEW: often blocked"
        else:
            decision = "WATCH"

        rows.append({
            "strategy": strategy,
            "detected": detected,
            "candidate_rejected": data["candidate_rejected"],
            "trade_plan_ready": data["trade_plan_ready"],
            "trade_blocked": data["trade_blocked"],
            "execution_attempt": executed,
            "execution_failed": data["execution_failed"],
            "trade_closed": closed,
            "wins": wins,
            "losses": losses,
            "breakeven": data["breakeven"],
            "execution_rate_percent": execution_rate,
            "win_rate_percent": win_rate,
            "avg_score": avg_score,
            "avg_rr": avg_rr,
            "top_reason": top_reason,
            "decision": decision,
        })

    return sorted(rows, key=lambda row: row["detected"], reverse=True)


def export_csv(rows, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "strategy",
        "detected",
        "candidate_rejected",
        "trade_plan_ready",
        "trade_blocked",
        "execution_attempt",
        "execution_failed",
        "trade_closed",
        "wins",
        "losses",
        "breakeven",
        "execution_rate_percent",
        "win_rate_percent",
        "avg_score",
        "avg_rr",
        "top_reason",
        "decision",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    mt5.initialize()

    setup_audit_file = get_account_file("setup_audit.json")
    output_file = get_account_file("strategy_audit_report.csv")

    setup_audit = load_json(setup_audit_file)

    if not setup_audit:
        print(f"No setup audit data found: {setup_audit_file}")
        return

    summary = summarize_strategy_events(setup_audit)
    rows = build_rows(summary)

    export_csv(rows, output_file)

    print(f"Strategy audit exported: {output_file}")

    mt5.shutdown()


if __name__ == "__main__":
    main()