from pathlib import Path
import ast
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_DIR = ROOT / "src" / "strategies"
LIVE_BOT_PATH = ROOT / "src" / "live_bot.py"

EXPECTED_STRATEGY_FILES = 53


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def has_public_generate_signal(source: str) -> bool:
    tree = ast.parse(source)
    return any(
        isinstance(node, ast.FunctionDef) and node.name == "generate_signal"
        for node in tree.body
    )


def extract_strategy_name(source: str) -> str | None:
    import re

    patterns = [
        r'PHASE6[A-Z0-9_]*_STRATEGY_NAME\s*=\s*"([^"]+)"',
        r'STRATEGY_NAME\s*=\s*"([^"]+)"',
        r'"strategy"\s*:\s*"([^"]+)"',
    ]

    for pattern in patterns:
        match = re.search(pattern, source)
        if match:
            return match.group(1)

    return None


def extract_live_bot_imports(live_source: str):
    tree = ast.parse(live_source)
    imports = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue

        module = node.module or ""

        if not module.startswith("src.strategies.strategy_"):
            continue

        file_name = module.split(".")[-1] + ".py"

        for alias in node.names:
            if alias.name == "generate_signal" and alias.asname:
                imports[alias.asname] = file_name

    return imports


def extract_strategy_map_blocks(live_source: str):
    tree = ast.parse(live_source)
    blocks = []

    def tuple_record(node):
        if not isinstance(node, ast.Tuple) or len(node.elts) != 2:
            return None

        name_node, fn_node = node.elts

        if not isinstance(name_node, ast.Constant) or not isinstance(name_node.value, str):
            return None

        if not isinstance(fn_node, ast.Name):
            return None

        return name_node.value, fn_node.id

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if not any(isinstance(t, ast.Name) and t.id == "strategy_map" for t in node.targets):
                continue

            if not isinstance(node.value, ast.List):
                continue

            records = []
            for elt in node.value.elts:
                rec = tuple_record(elt)
                if rec:
                    records.append(rec)

            if records:
                blocks.append(
                    {
                        "type": "assignment",
                        "line": node.lineno,
                        "records": records,
                    }
                )

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Attribute):
                continue

            if node.func.attr not in {"append", "insert"}:
                continue

            if not isinstance(node.func.value, ast.Name) or node.func.value.id != "strategy_map":
                continue

            tuple_arg = None

            if node.func.attr == "append" and node.args:
                tuple_arg = node.args[0]

            if node.func.attr == "insert" and len(node.args) >= 2:
                tuple_arg = node.args[1]

            rec = tuple_record(tuple_arg)

            if rec:
                blocks.append(
                    {
                        "type": node.func.attr,
                        "line": node.lineno,
                        "records": [rec],
                    }
                )

    return blocks


def main():
    failures = []

    strategy_files = sorted(STRATEGY_DIR.glob("strategy_*.py"))

    if len(strategy_files) != EXPECTED_STRATEGY_FILES:
        failures.append(
            f"Expected {EXPECTED_STRATEGY_FILES} strategy files, found {len(strategy_files)}"
        )

    strategy_file_to_name = {}

    for path in strategy_files:
        source = read(path)

        if "\ufeff" in source:
            failures.append(f"{path}: contains BOM U+FEFF")

        try:
            ast.parse(source)
        except SyntaxError as exc:
            failures.append(f"{path}: syntax error: {exc}")
            continue

        if not has_public_generate_signal(source):
            failures.append(f"{path}: missing public generate_signal function")

        strategy_name = extract_strategy_name(source)

        if not strategy_name:
            failures.append(f"{path}: could not determine strategy name")
            continue

        strategy_file_to_name[path.name] = strategy_name

    strategy_names = set(strategy_file_to_name.values())

    live_source = read(LIVE_BOT_PATH)
    imports = extract_live_bot_imports(live_source)
    imported_files = set(imports.values())

    map_blocks = extract_strategy_map_blocks(live_source)

    all_map_records = []
    duplicate_block_failures = []

    for block in map_blocks:
        names = [name for name, _alias in block["records"]]
        counts = Counter(names)
        duplicates = sorted(name for name, count in counts.items() if count > 1)

        if duplicates:
            duplicate_block_failures.append(
                f"strategy_map block line {block['line']} has duplicate names: {duplicates}"
            )

        all_map_records.extend(block["records"])

    mapped_names = {name for name, _alias in all_map_records}
    mapped_aliases = {alias for _name, alias in all_map_records}

    missing_live_import = sorted(set(strategy_file_to_name) - imported_files)
    imported_unknown_files = sorted(imported_files - set(strategy_file_to_name))
    mapped_unknown_names = sorted(mapped_names - strategy_names)
    strategy_names_not_mapped = sorted(strategy_names - mapped_names)
    mapped_aliases_without_import = sorted(mapped_aliases - set(imports))

    failures.extend(duplicate_block_failures)

    if missing_live_import:
        failures.append(f"Strategy files not imported in live_bot.py: {missing_live_import}")

    if imported_unknown_files:
        failures.append(f"live_bot.py imports unknown strategy files: {imported_unknown_files}")

    if mapped_unknown_names:
        failures.append(f"strategy_map contains unknown strategy names: {mapped_unknown_names}")

    if strategy_names_not_mapped:
        failures.append(f"Standardized strategies not reachable in any strategy_map: {strategy_names_not_mapped}")

    if mapped_aliases_without_import:
        failures.append(f"strategy_map uses aliases not imported from strategies: {mapped_aliases_without_import}")

    print("\n[PHASE 6Q] live_bot strategy integration audit")
    print("=" * 70)
    print(f"strategy_files={len(strategy_files)}")
    print(f"standardized_strategy_names={len(strategy_names)}")
    print(f"live_bot_strategy_imports={len(imports)}")
    print(f"strategy_map_blocks={len(map_blocks)}")
    print(f"strategy_map_unique_names={len(mapped_names)}")
    print(f"strategy_map_records_total={len(all_map_records)}")

    print("\n[IMPORTED STRATEGY FILES]")
    for alias, file_name in sorted(imports.items()):
        print(f"  {alias} -> {file_name}")

    print("\n[STRATEGY MAP BLOCKS]")
    for block in map_blocks:
        names = [name for name, _alias in block["records"]]
        print(f"  line={block['line']} type={block['type']} count={len(names)} names={names}")

    if failures:
        print("\n[FAILURES]")
        for failure in failures:
            print(f"  ❌ {failure}")
        raise SystemExit(1)

    print("\n[PASS] Phase 6Q live_bot strategy integration audit passed.")


if __name__ == "__main__":
    main()