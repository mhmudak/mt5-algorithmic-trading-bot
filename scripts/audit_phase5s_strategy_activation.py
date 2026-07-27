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


STRATEGY_ALIASES = {
    "strategy_mtf_order_block_entry": ["MTF_OB_ENTRY", "MTF_ORDER_BLOCK_ENTRY"],
}


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


def extract_functions_from_ast(path: Path) -> list[str]:
    try:
        tree = ast.parse(read_text(path))
    except Exception:
        return []

    return sorted(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    )


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


def candidate_names(module_name: str, strategy_name: str) -> list[str]:
    names = [strategy_name]

    for alias in STRATEGY_ALIASES.get(module_name, []):
        if alias not in names:
            names.append(alias)

    return names


def all_hits(text: str, names: list[str]) -> dict[str, list[int]]:
    return {name: find_line_numbers(text, name) for name in names}


def flatten_hits(hit_map: dict[str, list[int]]) -> list[int]:
    lines = []

    for hits in hit_map.values():
        lines.extend(hits)

    return sorted(set(lines))


def classify_strategy(
    *,
    file_is_empty: bool,
    imported_in_live_bot: bool,
    any_strategy_name_in_live_bot: bool,
    function_aliases: list[str],
    settings_mentions: int,
    risk_mentions: int,
    has_generate_signal: bool,
) -> str:
    if file_is_empty:
        return "EMPTY_STRATEGY_FILE_INACTIVE"

    if imported_in_live_bot and any_strategy_name_in_live_bot and has_generate_signal:
        return "LIKELY_ACTIVE_IN_LIVE_BOT"

    if imported_in_live_bot and function_aliases and has_generate_signal:
        return "IMPORTED_BUT_NEEDS_MAP_REVIEW"

    if any_strategy_name_in_live_bot and not imported_in_live_bot:
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
        file_text = read_text(path)
        file_is_empty = len(file_text.strip()) == 0
        file_size_bytes = path.stat().st_size if path.exists() else 0

        derived_name = derive_strategy_name_from_file(path)
        ast_name = extract_strategy_name_from_ast(path)
        strategy_name = ast_name or derived_name
        names = candidate_names(module_name, strategy_name)

        functions = extract_functions_from_ast(path)
        has_generate_signal = "generate_signal" in functions

        imported = imported_module_in_live_bot(module_name, live_bot_text)
        aliases = function_aliases_for_module(module_name, live_bot_text)

        live_bot_name_hit_map = all_hits(live_bot_text, names)
        settings_hit_map = all_hits(settings_text, names)
        risk_hit_map = all_hits(risk_text, names)

        live_bot_name_hits = flatten_hits(live_bot_name_hit_map)
        module_hits = find_line_numbers(live_bot_text, module_name)
        settings_hits = flatten_hits(settings_hit_map)
        risk_hits = flatten_hits(risk_hit_map)

        status = classify_strategy(
            file_is_empty=file_is_empty,
            imported_in_live_bot=imported,
            any_strategy_name_in_live_bot=bool(live_bot_name_hits),
            function_aliases=aliases,
            settings_mentions=len(settings_hits),
            risk_mentions=len(risk_hits),
            has_generate_signal=has_generate_signal,
        )

        records.append(
            {
                "file": str(path.relative_to(ROOT)),
                "module": module_name,
                "strategy_name": strategy_name,
                "candidate_names": names,
                "strategy_name_source": "AST_STRATEGY_NAME" if ast_name else "DERIVED_FROM_FILENAME",
                "status": status,
                "file_is_empty": file_is_empty,
                "file_size_bytes": file_size_bytes,
                "has_generate_signal": has_generate_signal,
                "imported_in_live_bot": imported,
                "function_aliases": aliases,
                "strategy_name_live_bot_lines": live_bot_name_hits[:20],
                "module_live_bot_lines": module_hits[:20],
                "settings_lines": settings_hits[:20],
                "risk_lines": risk_hits[:20],
                "live_bot_context": nearby_lines(live_bot_text, names[0], radius=2),
            }
        )

    status_counts: dict[str, int] = {}

    for record in records:
        status_counts[record["status"]] = status_counts.get(record["status"], 0) + 1

    report = {
        "phase": "PHASE_5S2_STRATEGY_ACTIVATION_AUDIT",
        "updated_at": now_iso(),
        "strategy_file_count": len(strategy_files),
        "status_counts": status_counts,
        "records": records,
        "recommendation": "Review EMPTY_STRATEGY_FILE_INACTIVE and FILE_EXISTS_NOT_ACTIVE_OR_NOT_DETECTED before assuming every strategy file is active.",
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "file",
                "module",
                "strategy_name",
                "candidate_names",
                "strategy_name_source",
                "status",
                "file_is_empty",
                "file_size_bytes",
                "has_generate_signal",
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
                "candidate_names",
                "function_aliases",
                "strategy_name_live_bot_lines",
                "module_live_bot_lines",
                "settings_lines",
                "risk_lines",
            ]:
                row[key] = json.dumps(row[key], ensure_ascii=False)

            writer.writerow({k: row.get(k) for k in writer.fieldnames})

    lines = [
        "[PHASE 5S2 STRATEGY ACTIVATION AUDIT]",
        f"updated_at = {report['updated_at']}",
        f"strategy_file_count = {len(strategy_files)}",
        "",
        "[STATUS COUNTS]",
    ]

    for status, count in sorted(status_counts.items()):
        lines.append(f"{status} = {count}")

    for target in ["PRO_TRADER_REPLICATION", "MTF_OB_ENTRY", "KEY_LEVEL_BREAK_HOLD"]:
        lines += [
            "",
            f"[{target}]",
        ]

        target_records = [
            r for r in records
            if target in r["candidate_names"] or r["strategy_name"] == target
        ]

        if target_records:
            r = target_records[0]
            lines += [
                f"status = {r['status']}",
                f"file = {r['file']}",
                f"candidate_names = {r['candidate_names']}",
                f"file_is_empty = {r['file_is_empty']}",
                f"file_size_bytes = {r['file_size_bytes']}",
                f"has_generate_signal = {r['has_generate_signal']}",
                f"imported_in_live_bot = {r['imported_in_live_bot']}",
                f"function_aliases = {r['function_aliases']}",
                f"strategy_name_live_bot_lines = {r['strategy_name_live_bot_lines']}",
                f"module_live_bot_lines = {r['module_live_bot_lines']}",
                f"settings_lines = {r['settings_lines']}",
                f"risk_lines = {r['risk_lines']}",
            ]
        else:
            lines.append(f"{target} not found.")

    lines += [
        "",
        "[NEEDS REVIEW]",
    ]

    review_statuses = {
        "IMPORTED_BUT_NEEDS_MAP_REVIEW",
        "MENTIONED_BUT_IMPORT_NOT_FOUND",
        "CONFIG_OR_RISK_ONLY_REVIEW",
        "FILE_EXISTS_NOT_ACTIVE_OR_NOT_DETECTED",
        "EMPTY_STRATEGY_FILE_INACTIVE",
    }

    review_records = [r for r in records if r["status"] in review_statuses]

    if review_records:
        for r in review_records[:50]:
            lines.append(
                f"- {r['strategy_name']} | {r['status']} | file={r['file']} | empty={r['file_is_empty']} | imported={r['imported_in_live_bot']}"
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