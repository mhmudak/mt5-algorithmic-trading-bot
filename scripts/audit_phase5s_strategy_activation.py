from __future__ import annotations

import ast
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

STRATEGY_DIR = ROOT / "src" / "strategies"
LIVE_BOT_PATH = ROOT / "src" / "live_bot.py"
SETTINGS_PATH = ROOT / "config" / "settings.py"
RISK_PATH = ROOT / "src" / "risk.py"

INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"
REPORT_PATH = INTEL_DIR / "phase5s_strategy_activation_audit_report.json"
SUMMARY_PATH = INTEL_DIR / "phase5s_strategy_activation_audit_summary.txt"
CSV_PATH = INTEL_DIR / "phase5s_strategy_activation_audit.csv"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def derive_strategy_name_from_file(path: Path) -> str:
    name = path.stem

    if name.startswith("strategy_"):
        name = name[len("strategy_") :]

    return name.upper()


def extract_strategy_name_from_ast(path: Path) -> str | None:
    try:
        tree = ast.parse(read_text(path))
    except Exception:
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue

        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "STRATEGY_NAME":
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return node.value.value.strip()

    return None


def find_line_numbers(text: str, pattern: str) -> list[int]:
    lines = text.splitlines()
    hits = []

    for i, line in enumerate(lines, start=1):
        if pattern in line:
            hits.append(i)

    return hits


def nearby_lines(text: str, pattern: str, radius: int = 2) -> list[str]:
    lines = text.splitlines()
    hits = []

    for i, line in enumerate(lines):
        if pattern in line:
            start = max(0, i - radius)
            end = min(len(lines), i + radius + 1)

            for j in range(start, end):
                hits.append(f"L{j + 1}: {lines[j]}")

    return hits[:20]


def imported_module_in_live_bot(module_name: str, live_bot_text: str) -> bool:
    return f"src.strategies.{module_name}" in live_bot_text


def function_aliases_for_module(module_name: str, live_bot_text: str) -> list[str]:
    pattern = rf"from\s+src\.strategies\.{re.escape(module_name)}\s+import\s+generate_signal\s+as\s+([A-Za-z_][A-Za-z0-9_]*)"
    return re.findall(pattern, live_bot_text)


def classify_strategy(
    *,
    module_name: str,
    strategy_name: str,
    imported_in_live_bot: bool,
    strategy_name_in_live_bot: bool,
    function_aliases: list[str],
    settings_mentions: int,
    risk_mentions: int,
    live_bot_mentions: int,
) -> str:
    if imported_in_live_bot and strategy_name_in_live_bot:
        return "LIKELY_ACTIVE_IN_LIVE_BOT"

    if imported_in_live_bot and function_aliases:
        return "IMPORTED_BUT_NEEDS_MAP_REVIEW"

    if strategy_name_in_live_bot and not imported_in_live_bot:
        return "MENTIONED_BUT_IMPORT_NOT_FOUND"

    if settings_mentions > 0 or risk_mentions > 0:
        return "CONFIG_OR_RISK_ONLY_REVIEW"

    return "FILE_EXISTS_NOT_ACTIVE_OR_NOT_DETECTED"


def main() -> None:
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    live_bot_text = read_text(LIVE_BOT_PATH)
    settings_text = read_text(SETTINGS_PATH)
    risk_text = read_text(RISK_PATH)

    strategy_files = sorted(STRATEGY_DIR.glob("strategy_*.py"))

    records: list[dict[str, Any]] = []

    for path in strategy_files:
        module_name = path.stem
        derived_name = derive_strategy_name_from_file(path)
        ast_name = extract_strategy_name_from_ast(path)
        strategy_name = ast_name or derived_name

        imported = imported_module_in_live_bot(module_name, live_bot_text)
        aliases = function_aliases_for_module(module_name, live_bot_text)

        live_bot_name_hits = find_line_numbers(live_bot_text, strategy_name)
        module_hits = find_line_numbers(live_bot_text, module_name)
        settings_hits = find_line_numbers(settings_text, strategy_name)
        risk_hits = find_line_numbers(risk_text, strategy_name)

        status = classify_strategy(
            module_name=module_name,
            strategy_name=strategy_name,
            imported_in_live_bot=imported,
            strategy_name_in_live_bot=bool(live_bot_name_hits),
            function_aliases=aliases,
            settings_mentions=len(settings_hits),
            risk_mentions=len(risk_hits),
            live_bot_mentions=len(live_bot_name_hits) + len(module_hits),
        )

        records.append(
            {
                "file": str(path.relative_to(ROOT)),
                "module": module_name,
                "strategy_name": strategy_name,
                "strategy_name_source": "AST_STRATEGY_NAME" if ast_name else "DERIVED_FROM_FILENAME",
                "status": status,
                "imported_in_live_bot": imported,
                "function_aliases": aliases,
                "strategy_name_live_bot_lines": live_bot_name_hits[:20],
                "module_live_bot_lines": module_hits[:20],
                "settings_lines": settings_hits[:20],
                "risk_lines": risk_hits[:20],
                "live_bot_context": nearby_lines(live_bot_text, strategy_name, radius=2),
            }
        )

    status_counts: dict[str, int] = {}

    for record in records:
        status_counts[record["status"]] = status_counts.get(record["status"], 0) + 1

    report = {
        "phase": "PHASE_5S_STRATEGY_ACTIVATION_AUDIT",
        "updated_at": now_iso(),
        "strategy_file_count": len(strategy_files),
        "status_counts": status_counts,
        "records": records,
        "recommendation": "Review IMPORTED_BUT_NEEDS_MAP_REVIEW and FILE_EXISTS_NOT_ACTIVE_OR_NOT_DETECTED before assuming every strategy file is active.",
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "file",
                "module",
                "strategy_name",
                "strategy_name_source",
                "status",
                "imported_in_live_bot",
                "function_aliases",
                "strategy_name_live_bot_lines",
                "module_live_bot_lines",
                "settings_lines",
                "risk_lines",
            ],
        )
        writer.writeheader()

        for record in records:
            row = dict(record)
            for key in [
                "function_aliases",
                "strategy_name_live_bot_lines",
                "module_live_bot_lines",
                "settings_lines",
                "risk_lines",
            ]:
                row[key] = json.dumps(row[key], ensure_ascii=False)

            writer.writerow({k: row.get(k) for k in writer.fieldnames})

    lines = [
        "[PHASE 5S STRATEGY ACTIVATION AUDIT]",
        f"updated_at = {report['updated_at']}",
        f"strategy_file_count = {len(strategy_files)}",
        "",
        "[STATUS COUNTS]",
    ]

    for status, count in sorted(status_counts.items()):
        lines.append(f"{status} = {count}")

    lines += [
        "",
        "[PRO_TRADER_REPLICATION]",
    ]

    pro_records = [r for r in records if r["strategy_name"] == "PRO_TRADER_REPLICATION"]

    if pro_records:
        r = pro_records[0]
        lines += [
            f"status = {r['status']}",
            f"file = {r['file']}",
            f"imported_in_live_bot = {r['imported_in_live_bot']}",
            f"function_aliases = {r['function_aliases']}",
            f"strategy_name_live_bot_lines = {r['strategy_name_live_bot_lines']}",
            f"module_live_bot_lines = {r['module_live_bot_lines']}",
            f"settings_lines = {r['settings_lines']}",
            f"risk_lines = {r['risk_lines']}",
        ]
    else:
        lines.append("PRO_TRADER_REPLICATION not found.")

    lines += [
        "",
        "[NEEDS REVIEW]",
    ]

    review_statuses = {
        "IMPORTED_BUT_NEEDS_MAP_REVIEW",
        "MENTIONED_BUT_IMPORT_NOT_FOUND",
        "CONFIG_OR_RISK_ONLY_REVIEW",
        "FILE_EXISTS_NOT_ACTIVE_OR_NOT_DETECTED",
    }

    review_records = [r for r in records if r["status"] in review_statuses]

    if review_records:
        for r in review_records[:50]:
            lines.append(
                f"- {r['strategy_name']} | {r['status']} | file={r['file']} | imported={r['imported_in_live_bot']}"
            )
    else:
        lines.append("- No review records.")

    lines += [
        "",
        "[REPORTS]",
        f"json = {REPORT_PATH}",
        f"csv = {CSV_PATH}",
        f"summary = {SUMMARY_PATH}",
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
    ]

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))


if __name__ == "__main__":
    main()