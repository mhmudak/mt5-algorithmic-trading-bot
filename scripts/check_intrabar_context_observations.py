from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FILENAME = (
    "intrabar_context_observations.jsonl"
)

TARGET_STRATEGIES = {
    "AUTO_STRUCTURAL_LEVEL_SCALP",
    "FAILED_FVG_REVERSAL",
}


def discover_accounts():
    base = (
        ROOT
        / "data"
        / "accounts"
    )

    if not base.exists():
        return []

    return [
        path
        for path in sorted(
            base.iterdir()
        )
        if path.is_dir()
    ]


def read_jsonl(path):
    rows = []
    errors = 0

    if not path.exists():
        return rows, errors

    with path.open(
        "r",
        encoding="utf-8-sig",
    ) as handle:
        for line in handle:
            line = line.strip()

            if not line:
                continue

            try:
                row = json.loads(
                    line
                )
            except Exception:
                errors += 1
                continue

            if not isinstance(
                row,
                dict,
            ):
                errors += 1
                continue

            if (
                str(
                    row.get(
                        "strategy",
                        ""
                    )
                ).upper()
                not in
                TARGET_STRATEGIES
            ):
                continue

            rows.append(
                row
            )

    return rows, errors


def coverage(
    rows,
    predicate,
):
    if not rows:
        return 0.0

    return (
        sum(
            1
            for row in rows
            if predicate(row)
        )
        / len(rows)
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Read-only checker for "
            "intrabar execution-context "
            "observations."
        )
    )

    parser.add_argument(
        "--all-accounts",
        action="store_true",
    )

    parser.add_argument(
        "--source-dir",
        action="append",
        default=[],
    )

    args = parser.parse_args()

    sources = []

    if args.all_accounts:
        sources.extend(
            discover_accounts()
        )

    for raw in args.source_dir:
        path = Path(raw)

        if not path.is_absolute():
            path = (
                ROOT / path
            )

        sources.append(
            path.resolve()
        )

    unique = []
    seen = set()

    for source in sources:
        source = source.resolve()

        if source in seen:
            continue

        seen.add(source)
        unique.append(source)

    if not unique:
        raise SystemExit(
            "[STOP] Select --all-accounts "
            "or --source-dir."
        )

    rows = []
    parse_errors = 0

    for source in unique:
        path = (
            source
            / FILENAME
        )

        account_rows, errors = (
            read_jsonl(path)
        )

        rows.extend(
            account_rows
        )

        parse_errors += errors

        print(
            f"[LOAD] account="
            f"{source.name} "
            f"observations="
            f"{len(account_rows)} "
            f"parse_errors={errors}"
        )

    print()

    print("=" * 88)

    print(
        "INTRABAR EXECUTION CONTEXT "
        "CAPTURE CHECK"
    )

    print("=" * 88)

    print(
        f"Rows: {len(rows)}"
    )

    print(
        f"Parse errors: "
        f"{parse_errors}"
    )

    if not rows:
        print(
            "Status: WAITING_FOR_NEW_"
            "INTRABAR_EXECUTIONS"
        )

        print(
            "[INFO] This is expected before "
            "the instrumented bot version "
            "has executed a target intrabar "
            "trade."
        )

        return

    strategy_counts = Counter(
        row.get(
            "strategy",
            "UNKNOWN",
        )
        for row in rows
    )

    source_counts = Counter(
        row.get(
            "source",
            "UNKNOWN",
        )
        for row in rows
    )

    m15 = coverage(
        rows,
        lambda row: (
            row.get(
                "m15_relation"
            )
            not in {
                None,
                "",
                "UNKNOWN",
            }
        ),
    )

    htf = coverage(
        rows,
        lambda row: (
            row.get(
                "htf_relation"
            )
            not in {
                None,
                "",
                "UNKNOWN",
            }
        ),
    )

    regime = coverage(
        rows,
        lambda row: (
            row.get(
                "regime_family"
            )
            not in {
                None,
                "",
                "UNKNOWN",
            }
        ),
    )

    momentum = coverage(
        rows,
        lambda row: (
            (
                row.get(
                    "price_features"
                )
                or {}
            ).get(
                "momentum_relation"
            )
            not in {
                None,
                "",
                "UNKNOWN",
            }
        ),
    )

    risk = coverage(
        rows,
        lambda row: (
            row.get(
                "risk_distance"
            )
            is not None
            and float(
                row.get(
                    "risk_distance"
                )
            )
            > 0
        ),
    )

    print(
        "Strategies:",
        dict(
            strategy_counts
        ),
    )

    print(
        "Sources:",
        dict(
            source_counts
        ),
    )

    print(
        f"M15 coverage: "
        f"{m15:.1%}"
    )

    print(
        f"HTF coverage: "
        f"{htf:.1%}"
    )

    print(
        f"Regime coverage: "
        f"{regime:.1%}"
    )

    print(
        f"Momentum coverage: "
        f"{momentum:.1%}"
    )

    print(
        f"Risk coverage: "
        f"{risk:.1%}"
    )

    pipeline_ready = (
        parse_errors == 0
        and m15 >= 0.80
        and htf >= 0.80
        and regime >= 0.80
        and momentum >= 0.80
        and risk >= 0.95
    )

    print(
        "Capture status: "
        + (
            "PIPELINE_READY"
            if pipeline_ready
            else (
                "PIPELINE_NEEDS_MORE_"
                "OR_BETTER_CONTEXT"
            )
        )
    )

    print(
        "[SAFE] Reporting only. "
        "No trading decisions are made."
    )


if __name__ == "__main__":
    main()
