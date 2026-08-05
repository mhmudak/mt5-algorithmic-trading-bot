from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


KNOWN_SESSIONS = {
    "OFF_HOURS",
    "ASIA",
    "LONDON_OPEN",
    "LONDON",
    "LONDON_NY_OVERLAP",
    "NEWYORK_OPEN",
    "NEWYORK",
    "NEWYORK_LATE",
}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in {None, "", "None", "NaN", "nan"}:
            return default
        return float(value)
    except Exception:
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value in {None, "", "None", "NaN", "nan"}:
            return default
        return int(float(value))
    except Exception:
        return default


def _account_key_fallback() -> str:
    try:
        from src.account_context import get_account_key

        return str(get_account_key())
    except Exception:
        return "Tickmill-Demo_25323531"


def _intelligence_dir_fallback() -> Path:
    try:
        from src.account_context import get_account_intelligence_dir

        return Path(get_account_intelligence_dir())
    except Exception:
        return Path("data") / "strategy_intelligence" / _account_key_fallback()


def parse_intrabar_policy_key(policy_key: str) -> Optional[Dict[str, str]]:
    parts = [part.strip().upper() for part in str(policy_key or "").split("|") if part.strip()]

    if len(parts) < 4:
        return None

    if "INTRABAR" not in parts and not any("INTRABAR" in part for part in parts):
        return None

    strategy = parts[0]
    signal = parts[1] if len(parts) > 1 else ""

    if signal not in {"BUY", "SELL"}:
        return None

    session_index = None
    for index, part in enumerate(parts[2:], start=2):
        if part in KNOWN_SESSIONS:
            session_index = index
            break

    if session_index is None:
        return None

    session = parts[session_index]
    market_condition = parts[session_index + 1] if len(parts) > session_index + 1 else "*"
    entry_model = parts[2] if session_index > 2 else ""

    return {
        "strategy": strategy,
        "signal": signal,
        "session": session,
        "market_condition": market_condition,
        "entry_model": entry_model,
    }


def read_csv_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def generate_rules_from_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    min_samples: int,
    block_decisions: Iterable[str],
    max_loss_rate: float,
    min_expectancy: float,
) -> List[Dict[str, Any]]:
    block_decision_set = {str(item).upper() for item in block_decisions}
    rules_by_key: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        policy_key = row.get("policy_key") or row.get("key") or ""
        parsed = parse_intrabar_policy_key(policy_key)

        if not parsed:
            continue

        sample_count = _int(row.get("sample_count"))
        decision = str(row.get("decision") or "").upper()
        actual_expectancy = _float(row.get("actual_expectancy"), default=0.0)
        loss_rate = _float(row.get("loss_rate"), default=0.0)

        if sample_count < min_samples:
            continue

        should_block = False
        block_reason = None

        if decision in block_decision_set:
            should_block = True
            block_reason = f"dynamic decision={decision}"

        if actual_expectancy < min_expectancy and loss_rate >= max_loss_rate:
            should_block = True
            block_reason = (
                f"dynamic stats weak actual_expectancy={actual_expectancy} "
                f"loss_rate={loss_rate}"
            )

        if not should_block:
            continue

        rule_key = (
            f"{parsed['strategy']}|{parsed['signal']}|{parsed['session']}|"
            f"{parsed['market_condition']}"
        )

        rules_by_key[rule_key] = {
            "strategy": parsed["strategy"],
            "signal": parsed["signal"],
            "session": parsed["session"],
            "market_condition": parsed["market_condition"],
            "entry_model": parsed["entry_model"],
            "rule_reason": block_reason,
            "source_policy_key": policy_key,
            "decision": decision,
            "sample_count": sample_count,
            "actual_expectancy": actual_expectancy,
            "loss_rate": loss_rate,
        }

    return list(rules_by_key.values())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", default=None)
    parser.add_argument("--output-file", default=None)
    parser.add_argument("--min-samples", type=int, default=5)
    parser.add_argument("--max-loss-rate", type=float, default=0.60)
    parser.add_argument("--min-expectancy", type=float, default=0.0)
    parser.add_argument(
        "--block-decisions",
        default="BLOCK_TEMPORARILY",
        help="Comma-separated analyzer decisions that create block rules",
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir) if args.source_dir else _intelligence_dir_fallback()

    candidate_files = [
        source_dir / "trade_tracker_health_by_bucket.csv",
        source_dir / "strategy_performance_detail.csv",
    ]

    rows: List[Dict[str, Any]] = []
    used_files = []

    for candidate_file in candidate_files:
        file_rows = read_csv_rows(candidate_file)
        if file_rows:
            rows.extend(file_rows)
            used_files.append(str(candidate_file))

    block_decisions = [
        item.strip().upper()
        for item in str(args.block_decisions or "").split(",")
        if item.strip()
    ]

    rules = generate_rules_from_rows(
        rows,
        min_samples=args.min_samples,
        block_decisions=block_decisions,
        max_loss_rate=args.max_loss_rate,
        min_expectancy=args.min_expectancy,
    )

    output_file = (
        Path(args.output_file)
        if args.output_file
        else source_dir / "intrabar_subprofile_block_rules.json"
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "decision_impact": "DYNAMIC_INTRABAR_EXECUTION_GUARD",
        "source_dir": str(source_dir),
        "source_files": used_files,
        "min_samples": args.min_samples,
        "max_loss_rate": args.max_loss_rate,
        "min_expectancy": args.min_expectancy,
        "block_decisions": block_decisions,
        "rule_count": len(rules),
        "rules": rules,
    }

    output_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\n=== PHASE 6W3 DYNAMIC INTRABAR SUB-PROFILE RULES ===")
    print("source_dir =", source_dir)
    print("output_file =", output_file)
    print("source_files =", used_files)
    print("rule_count =", len(rules))

    for rule in rules[:20]:
        print(
            "-",
            rule.get("strategy"),
            rule.get("signal"),
            rule.get("session"),
            rule.get("market_condition"),
            "|",
            rule.get("rule_reason"),
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
