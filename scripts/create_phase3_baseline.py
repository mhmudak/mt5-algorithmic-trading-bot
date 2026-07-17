import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ACCOUNT_DIR = ROOT / "data" / "accounts" / "Tickmill-Demo_25323531"
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

BASELINE_PATH = INTEL_DIR / "phase3_baseline.json"


def count_json(path):
    if not path.exists():
        return 0

    try:
        data = json.loads(path.read_text(encoding="utf-8"))

        if isinstance(data, list):
            return len(data)

        if isinstance(data, dict):
            for key in ("trades", "outcomes", "setups", "records", "items"):
                if isinstance(data.get(key), list):
                    return len(data[key])
            return len(data)

    except Exception:
        return 0

    return 0


def count_jsonl(path):
    if not path.exists():
        return 0

    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except Exception:
        return 0


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    if BASELINE_PATH.exists():
        print(f"[SKIP] Phase 3 baseline already exists: {BASELINE_PATH}")
        print(BASELINE_PATH.read_text(encoding="utf-8"))
        return

    baseline = {
        "phase": "PHASE_3_BASELINE",
        "mode": "OBSERVE_ONLY",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "account_dir": str(ACCOUNT_DIR),
        "counts": {
            "trades_json_records": count_json(ACCOUNT_DIR / "trades.json"),
            "setup_outcomes_records": count_json(ACCOUNT_DIR / "setup_outcomes.json"),
            "confirmation_observations_records": count_jsonl(ACCOUNT_DIR / "confirmation_observations.jsonl"),
        },
        "decision": "BASELINE_CREATED_DO_NOT_RESET_UNLESS_INTENTIONAL",
        "purpose": "Separate old historical data from fresh post-Phase-3A evidence.",
    }

    BASELINE_PATH.write_text(json.dumps(baseline, indent=2, ensure_ascii=False), encoding="utf-8")

    print("[PHASE 3 BASELINE CREATED]")
    print(json.dumps(baseline, indent=2, ensure_ascii=False))
    print(f"\nbaseline = {BASELINE_PATH}")


if __name__ == "__main__":
    main()