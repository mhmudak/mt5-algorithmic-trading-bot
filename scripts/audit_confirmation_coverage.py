import argparse
import ast
import csv
import json
import re
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _project_file(path):
    path = Path(path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _safe_read_lines(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return f.readlines()


def _csv_safe(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = rows or []
    headers = []

    for row in rows:
        for key in row.keys():
            if key not in headers:
                headers.append(key)

    with path.open("w", encoding="utf-8", newline="") as f:
        if not headers:
            f.write("")
            return path

        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()

        for row in rows:
            writer.writerow({key: _csv_safe(row.get(key)) for key in headers})

    return path


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)

    return path


def resolve_default_output_dir():
    try:
        from src.account_context import get_account_file
        account_name = Path(get_account_file("trades.json")).parent.name
        return PROJECT_ROOT / "data" / "strategy_intelligence" / account_name
    except Exception:
        return PROJECT_ROOT / "data" / "strategy_intelligence" / "coverage_audit"


class ParentLinker(ast.NodeVisitor):
    def visit(self, node):
        for child in ast.iter_child_nodes(node):
            child.parent = node
        super().visit(node)


def get_enclosing_function(node):
    current = getattr(node, "parent", None)

    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
        current = getattr(current, "parent", None)

    return "<module>"


def get_call_name(node):
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        parent_name = get_call_name(node.value)
        if parent_name:
            return f"{parent_name}.{node.attr}"
        return node.attr

    return None


def get_constant_string(node):
    try:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
    except Exception:
        pass

    return None


def extract_event_strings_from_window(window_text):
    events = []

    patterns = [
        r'event\s*=\s*["\']([^"\']+)["\']',
        r'decision\s*=\s*["\']([^"\']+)["\']',
        r'setup_source_bucket\s*=\s*["\']([^"\']+)["\']',
        r'execution_bucket\s*=\s*["\']([^"\']+)["\']',
        r'setup_source_bucket\s*:\s*["\']([^"\']+)["\']',
        r'execution_bucket\s*:\s*["\']([^"\']+)["\']',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, window_text):
            events.append(match.group(1))

    return sorted(set(events))


def classify_execution_path(window_text):
    text = window_text.upper()

    candidates = [
        "INTRABAR",
        "BETTER_ENTRY",
        "ORB_TICK_WATCHER",
        "TICK_SNIPER",
        "MTF_CONFLICT",
        "SPLIT_DELAYED",
        "SPLIT_IMMEDIATE",
        "SCALP_FALLBACK",
        "REVERSAL",
        "REJECTED_CANDIDATE",
        "FVG_STAGED",
        "NORMAL_OR_TRACKED",
        "EXECUTION_ATTEMPT",
    ]

    found = [item for item in candidates if item in text]

    if found:
        return "|".join(found)

    if "EXECUTING TRADE" in text:
        return "NORMAL_EXECUTION_LIKELY"

    return "UNKNOWN"


def line_window(lines, line_no, before=80, after=30):
    start = max(1, line_no - before)
    end = min(len(lines), line_no + after)

    text = "".join(lines[start - 1:end])

    return {
        "start": start,
        "end": end,
        "text": text,
    }


def find_calls(tree, target_names):
    calls = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        call_name = get_call_name(node.func)

        if call_name in target_names:
            calls.append({
                "call_name": call_name,
                "line": getattr(node, "lineno", None),
                "col": getattr(node, "col_offset", None),
                "function": get_enclosing_function(node),
            })

    calls.sort(key=lambda item: (item.get("line") or 0, item.get("col") or 0))
    return calls


def audit_live_bot(path, observe_window_lines=90):
    path = _project_file(path)
    source = path.read_text(encoding="utf-8")
    lines = _safe_read_lines(path)

    tree = ast.parse(source)
    ParentLinker().visit(tree)

    execute_calls = find_calls(tree, {"execute_trade"})
    observe_calls = find_calls(tree, {"observe_universal_confirmation_for_setup"})

    observe_lines = [
        item["line"]
        for item in observe_calls
        if item.get("line") is not None
    ]

    execution_rows = []

    for call in execute_calls:
        line_no = call["line"]

        prior_observe_lines = [
            line
            for line in observe_lines
            if line is not None and line < line_no and (line_no - line) <= observe_window_lines
        ]

        nearest_prior_observe = max(prior_observe_lines) if prior_observe_lines else None

        nearby_window = line_window(lines, line_no, before=observe_window_lines, after=40)
        window_text = nearby_window["text"]

        events = extract_event_strings_from_window(window_text)
        path_family = classify_execution_path(window_text)

        execution_rows.append({
            "file": str(path.relative_to(PROJECT_ROOT)),
            "function": call["function"],
            "execute_trade_line": line_no,
            "nearest_prior_observe_line": nearest_prior_observe,
            "observe_before_execution": bool(nearest_prior_observe),
            "distance_from_observe": (line_no - nearest_prior_observe) if nearest_prior_observe else None,
            "path_family_guess": path_family,
            "nearby_events_or_buckets": events,
            "window_start": nearby_window["start"],
            "window_end": nearby_window["end"],
        })

    observe_rows = []

    for item in observe_calls:
        line_no = item["line"]
        nearby_window = line_window(lines, line_no, before=25, after=25)
        events = extract_event_strings_from_window(nearby_window["text"])

        observe_rows.append({
            "file": str(path.relative_to(PROJECT_ROOT)),
            "function": item["function"],
            "observe_line": line_no,
            "path_family_guess": classify_execution_path(nearby_window["text"]),
            "nearby_events_or_buckets": events,
            "window_start": nearby_window["start"],
            "window_end": nearby_window["end"],
        })

    missing = [
        row
        for row in execution_rows
        if not row["observe_before_execution"]
    ]

    summary = {
        "created_at": datetime.now().isoformat(),
        "file": str(path.relative_to(PROJECT_ROOT)),
        "observe_window_lines": observe_window_lines,
        "execute_trade_call_count": len(execution_rows),
        "observe_call_count": len(observe_rows),
        "covered_execute_trade_call_count": len(execution_rows) - len(missing),
        "missing_observe_before_execute_trade_count": len(missing),
        "coverage_rate": round((len(execution_rows) - len(missing)) / len(execution_rows), 4) if execution_rows else None,
        "missing_paths": missing,
        "notes": [
            "Static audit only. Manual review required for complex branching.",
            "A path is considered covered if observe_universal_confirmation_for_setup appears before execute_trade within the configured line window.",
            "This does not change live trading behavior.",
        ],
    }

    return summary, execution_rows, observe_rows


def main():
    parser = argparse.ArgumentParser(
        description="Audit confirmation-engine observe-only coverage before execute_trade calls."
    )

    parser.add_argument(
        "--file",
        default="src/live_bot.py",
        help="Python file to audit. Default: src/live_bot.py",
    )

    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Default: account strategy_intelligence folder.",
    )

    parser.add_argument(
        "--observe-window-lines",
        type=int,
        default=90,
        help="How many lines before execute_trade to search for observe call.",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else resolve_default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    summary, execution_rows, observe_rows = audit_live_bot(
        args.file,
        observe_window_lines=args.observe_window_lines,
    )

    summary_path = output_dir / "confirmation_coverage_summary.json"
    execution_csv = output_dir / "confirmation_coverage_execute_calls.csv"
    observe_csv = output_dir / "confirmation_coverage_observe_calls.csv"

    write_json(summary_path, summary)
    write_csv(execution_csv, execution_rows)
    write_csv(observe_csv, observe_rows)

    print("[CONFIRMATION COVERAGE AUDIT] done")
    print("file =", args.file)
    print("execute_trade_call_count =", summary["execute_trade_call_count"])
    print("observe_call_count =", summary["observe_call_count"])
    print("covered_execute_trade_call_count =", summary["covered_execute_trade_call_count"])
    print("missing_observe_before_execute_trade_count =", summary["missing_observe_before_execute_trade_count"])
    print("coverage_rate =", summary["coverage_rate"])
    print("summary =", summary_path)
    print("execute_calls_csv =", execution_csv)
    print("observe_calls_csv =", observe_csv)

    if summary["missing_observe_before_execute_trade_count"]:
        print()
        print("[MISSING OBSERVE PATHS]")
        for row in summary["missing_paths"]:
            print(
                f"line={row['execute_trade_line']} "
                f"function={row['function']} "
                f"path={row['path_family_guess']} "
                f"events={row['nearby_events_or_buckets']}"
            )


if __name__ == "__main__":
    main()
