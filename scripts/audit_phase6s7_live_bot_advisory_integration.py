from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LIVE_BOT = Path("src/live_bot.py")
SETTINGS = Path("config/settings.py")

PATTERNS = {
    "telegram": [
        "send_telegram",
        "telegram",
        "NOTIFIER",
        "send_message",
    ],
    "execution": [
        "execute",
        "place_order",
        "order_send",
        "risk",
        "can_execute",
        "ALLOW_LIVE_TRADING",
        "EXECUTION_MODE",
    ],
    "strategy_signal": [
        "strategy_map",
        "generate_signal",
        "signal",
        "entry_reference",
        "sl_reference",
        "tp_reference",
        "rr",
        "risk_reward",
    ],
    "setup_tracking": [
        "setup_id",
        "setup_source",
        "strategy",
        "TRACKED",
        "REJECTED",
        "EXECUTED",
    ],
}


def find_matches(path: Path, patterns: list[str]) -> list[dict]:
    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    matches = []

    for index, line in enumerate(lines, start=1):
        lower = line.lower()

        for pattern in patterns:
            if pattern.lower() in lower:
                matches.append(
                    {
                        "line": index,
                        "pattern": pattern,
                        "text": line.strip()[:240],
                    }
                )
                break

    return matches


def context(path: Path, line_no: int, radius: int = 4) -> list[str]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, line_no - radius)
    end = min(len(lines), line_no + radius)

    output = []

    for line in range(start, end + 1):
        output.append(f"{line}: {lines[line - 1]}")

    return output


def main() -> None:
    print("[PHASE 6S7A LIVE_BOT ADVISORY INTEGRATION AUDIT]")

    if not LIVE_BOT.exists():
        raise SystemExit("[STOP] src/live_bot.py not found")

    if not SETTINGS.exists():
        raise SystemExit("[STOP] config/settings.py not found")

    from src.market_outlook_advisory_runtime import maybe_send_runtime_outlook_advisory

    assert callable(maybe_send_runtime_outlook_advisory)

    report = {
        "live_bot_exists": LIVE_BOT.exists(),
        "settings_exists": SETTINGS.exists(),
        "runtime_hook_import_ok": True,
        "matches": {},
        "recommended_next_step": "inspect output before patching live_bot",
    }

    for group, patterns in PATTERNS.items():
        matches = find_matches(LIVE_BOT, patterns)
        report["matches"][group] = matches[:40]

    settings_text = SETTINGS.read_text(encoding="utf-8", errors="replace")

    report["settings_flags_found"] = {
        "ENABLE_PHASE6S_RUNTIME_OUTLOOK_ADVISORY": "ENABLE_PHASE6S_RUNTIME_OUTLOOK_ADVISORY" in settings_text,
        "SEND_PHASE6S_RUNTIME_OUTLOOK_ADVISORY_TELEGRAM": "SEND_PHASE6S_RUNTIME_OUTLOOK_ADVISORY_TELEGRAM" in settings_text,
    }

    print(json.dumps(report, indent=2, ensure_ascii=False))

    print("")
    print("[MOST IMPORTANT CONTEXTS]")

    important_lines = []

    for group in ["strategy_signal", "telegram", "execution"]:
        for item in report["matches"].get(group, [])[:8]:
            important_lines.append((group, item["line"], item["pattern"]))

    seen = set()

    for group, line_no, pattern in important_lines:
        key = (line_no, pattern)

        if key in seen:
            continue

        seen.add(key)

        print("")
        print(f"--- {group.upper()} | line {line_no} | pattern={pattern} ---")
        for row in context(LIVE_BOT, line_no):
            print(row)

    print("")
    print("[PASS] Phase 6S7A audit completed. No code was changed.")


if __name__ == "__main__":
    main()