from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

TARGET_STRATEGIES = {
    "AUTO_STRUCTURAL_LEVEL_SCALP",
    "FAILED_FVG_REVERSAL",
}

BULL_TAGS = (
    "ema_bullish",
    "bullish_bos",
    "bullish_momentum",
    "bullish_displacement",
    "price_above_ema",
)

BEAR_TAGS = (
    "ema_bearish",
    "bearish_bos",
    "bearish_momentum",
    "bearish_displacement",
    "price_below_ema",
)

TREND = {
    "TRENDING",
    "STRONG_TREND",
    "EXPANSION",
    "VOLATILE",
}

PULLBACK = {
    "PULLBACK_TREND",
    "PULLBACK",
    "CORRECTION",
    "RETRACE",
    "RETRACEMENT",
}

RANGE = {
    "RANGING",
    "RANGE",
    "SIDEWAYS",
    "CONSOLIDATION",
    "COMPRESSION",
    "LOW_VOLATILITY",
}


def text(value, default=""):
    if value is None:
        return default

    value = str(value).strip()

    return value if value else default


def number(value):
    try:
        value = float(value)

    except (TypeError, ValueError):
        return None

    return value if math.isfinite(value) else None


def load_json(path):
    with path.open(
        "r",
        encoding="utf-8-sig",
    ) as handle:
        return json.load(handle)


def outcome_rows(source_dir):
    path = (
        source_dir
        / "setup_outcomes.json"
    )

    if not path.exists():
        return [], None

    data = load_json(path)

    if isinstance(data, list):
        return [
            row
            for row in data
            if isinstance(row, dict)
        ], path

    if isinstance(data, dict):
        rows = []

        for key, value in data.items():
            if not isinstance(value, dict):
                continue

            row = dict(value)

            row.setdefault(
                "setup_id",
                key,
            )

            rows.append(row)

        return rows, path

    return [], path


def audit_map(source_dir):
    path = (
        source_dir
        / "setup_audit.json"
    )

    if not path.exists():
        return {}, None

    data = load_json(path)

    if not isinstance(data, dict):
        return {}, path

    result = {}

    for key, value in data.items():
        if not isinstance(value, dict):
            continue

        row = dict(value)

        row.setdefault(
            "setup_id",
            key,
        )

        setup_id = text(
            row.get("setup_id"),
            key,
        )

        result[setup_id] = row

    return result, path


def is_target_intrabar(row):
    strategy = text(
        row.get("strategy")
    ).upper()

    if strategy not in TARGET_STRATEGIES:
        return False

    combined = "|".join(
        text(
            row.get(key)
        ).upper()
        for key in (
            "setup_id",
            "source_events",
            "entry_model",
            "market_condition",
        )
    )

    if "INTRABAR" in combined:
        return True

    return (
        strategy
        == "AUTO_STRUCTURAL_LEVEL_SCALP"
        and text(
            row.get(
                "market_condition"
            )
        ).upper()
        == "INTRABAR_STRUCTURAL_LEVEL_SCALP"
    )


def recursive_text(value):
    parts = []

    if isinstance(value, dict):
        for key, item in value.items():
            parts.append(
                str(key)
            )

            parts.extend(
                recursive_text(item)
            )

    elif isinstance(value, list):
        for item in value:
            parts.extend(
                recursive_text(item)
            )

    elif value is not None:
        parts.append(
            str(value)
        )

    return parts


def extract_audit_context(
    record,
    signal,
):
    record = record or {}

    parts = [
        text(
            record.get("reason")
        ),
        text(
            record.get(
                "market_condition"
            )
        ),
        text(
            record.get(
                "entry_model"
            )
        ),
    ]

    m15_signal = None
    explicit_relation = None

    for event in (
        record.get("events")
        or []
    ):
        if not isinstance(
            event,
            dict,
        ):
            continue

        name = text(
            event.get("event")
        ).upper()

        reason = text(
            event.get("reason")
        )

        extra = event.get("extra")

        if not isinstance(
            extra,
            dict,
        ):
            extra = {}

        parts.extend(
            [
                name,
                reason,
            ]
        )

        parts.extend(
            recursive_text(extra)
        )

        active_lock = extra.get(
            "active_lock"
        )

        if isinstance(
            active_lock,
            dict,
        ):
            candidate = text(
                active_lock.get(
                    "signal"
                )
            ).upper()

            if candidate in {
                "BUY",
                "SELL",
            }:
                m15_signal = candidate

        if (
            "M15_DIRECTION_LOCK_ALIGNED"
            in name
        ):
            explicit_relation = (
                "WITH_M15"
            )

        if (
            "M15_DIRECTION_LOCK"
            in name
            and (
                "BLOCK"
                in name
                or "OPPOSITE"
                in reason.upper()
            )
        ):
            explicit_relation = (
                "COUNTER_M15"
            )

    signal = text(
        signal
    ).upper()

    if (
        m15_signal
        in {
            "BUY",
            "SELL",
        }
        and signal
        in {
            "BUY",
            "SELL",
        }
    ):
        relation = (
            "WITH_M15"
            if m15_signal
            == signal
            else "COUNTER_M15"
        )

    else:
        relation = (
            explicit_relation
            or "UNKNOWN"
        )

    combined = " | ".join(
        part
        for part in parts
        if part
    )

    lower = combined.lower()

    bull = sum(
        lower.count(tag)
        for tag in BULL_TAGS
    )

    bear = sum(
        lower.count(tag)
        for tag in BEAR_TAGS
    )

    if (
        bull > bear
        and bull >= 2
    ):
        momentum = (
            "BULLISH_STRONG"
        )

    elif (
        bear > bull
        and bear >= 2
    ):
        momentum = (
            "BEARISH_STRONG"
        )

    elif bull > bear:
        momentum = (
            "BULLISH_HINT"
        )

    elif bear > bull:
        momentum = (
            "BEARISH_HINT"
        )

    else:
        momentum = "UNKNOWN"

    if (
        momentum.startswith(
            "BULLISH"
        )
        and signal == "BUY"
    ):
        momentum_relation = (
            "WITH_MOMENTUM"
        )

    elif (
        momentum.startswith(
            "BEARISH"
        )
        and signal == "SELL"
    ):
        momentum_relation = (
            "WITH_MOMENTUM"
        )

    elif (
        momentum.startswith(
            "BULLISH"
        )
        and signal == "SELL"
    ):
        momentum_relation = (
            "COUNTER_MOMENTUM"
        )

    elif (
        momentum.startswith(
            "BEARISH"
        )
        and signal == "BUY"
    ):
        momentum_relation = (
            "COUNTER_MOMENTUM"
        )

    else:
        momentum_relation = (
            "UNKNOWN"
        )

    return (
        m15_signal or "UNKNOWN",
        relation,
        momentum,
        momentum_relation,
    )


def regime_family(value):
    value = text(
        value
    ).upper()

    if value in PULLBACK:
        return (
            "PULLBACK_OR_CORRECTION"
        )

    if value in TREND:
        return (
            "TREND_OR_EXPANSION"
        )

    if value in RANGE:
        return (
            "RANGE_OR_COMPRESSION"
        )

    return "UNKNOWN"


def context_row(
    account,
    row,
    audit,
):
    entry = number(
        row.get("entry")
    )

    sl = number(
        row.get("sl")
    )

    tp = number(
        row.get("tp")
    )

    risk = None
    planned_rr = None

    if (
        entry is not None
        and sl is not None
        and entry != sl
    ):
        risk = abs(
            entry - sl
        )

        if tp is not None:
            planned_rr = (
                abs(
                    tp - entry
                )
                / risk
            )

    favorable = number(
        row.get(
            "max_favorable_usd"
        )
    )

    adverse = number(
        row.get(
            "max_adverse_usd"
        )
    )

    mfe_r = (
        favorable / risk
        if (
            favorable is not None
            and risk
        )
        else None
    )

    mae_r = (
        adverse / risk
        if (
            adverse is not None
            and risk
        )
        else None
    )

    signal = text(
        row.get("signal")
    ).upper()

    (
        m15_signal,
        m15_relation,
        momentum,
        momentum_relation,
    ) = extract_audit_context(
        audit,
        signal,
    )

    market_condition = text(
        row.get(
            "market_condition"
        ),
        text(
            (audit or {}).get(
                "market_condition"
            ),
            "UNKNOWN",
        ),
    ).upper()

    return {
        "account": account,
        "setup_id": text(
            row.get("setup_id")
        ),
        "strategy": text(
            row.get("strategy")
        ).upper(),
        "signal": signal,
        "entry_model": text(
            row.get(
                "entry_model"
            ),
            "UNKNOWN",
        ).upper(),
        "session": text(
            row.get("session"),
            "UNKNOWN",
        ).upper(),
        "market_condition": (
            market_condition
        ),
        "regime_family": (
            regime_family(
                market_condition
            )
        ),
        "m15_signal": (
            m15_signal
        ),
        "m15_relation": (
            m15_relation
        ),
        "momentum_hint": (
            momentum
        ),
        "momentum_relation": (
            momentum_relation
        ),
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "risk_distance": risk,
        "planned_rr": planned_rr,
        "mfe_r": mfe_r,
        "mae_r": mae_r,
        "first_hit": text(
            row.get("first_hit"),
            "UNKNOWN",
        ).upper(),
        "final_outcome": text(
            row.get(
                "final_outcome"
            ),
            "UNKNOWN",
        ).upper(),
    }


def ratio(
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


def write_csv(
    path,
    rows,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not rows:
        path.write_text(
            "",
            encoding="utf-8",
        )

        return

    fields = list(
        rows[0].keys()
    )

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )

        writer.writeheader()

        writer.writerows(
            rows
        )


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
        for path
        in sorted(
            base.iterdir()
        )
        if (
            path.is_dir()
            and (
                path
                / "setup_outcomes.json"
            ).exists()
        )
    ]


def self_test():
    audit = {
        "events": [
            {
                "event": (
                    "INTRABAR_M15_"
                    "DIRECTION_LOCK_ALIGNED"
                ),
                "reason": (
                    "same direction"
                ),
                "extra": {
                    "active_lock": {
                        "signal": "SELL",
                    },
                    "smc": (
                        "ema_bearish "
                        "bearish_bos"
                    ),
                },
            }
        ]
    }

    (
        m15,
        relation,
        momentum,
        momentum_relation,
    ) = extract_audit_context(
        audit,
        "SELL",
    )

    assert m15 == "SELL"

    assert (
        relation
        == "WITH_M15"
    )

    assert (
        momentum
        == "BEARISH_STRONG"
    )

    assert (
        momentum_relation
        == "WITH_MOMENTUM"
    )

    assert (
        regime_family(
            "PULLBACK_TREND"
        )
        == "PULLBACK_OR_CORRECTION"
    )

    assert (
        regime_family(
            "TRENDING"
        )
        == "TREND_OR_EXPANSION"
    )

    assert (
        regime_family(
            "RANGING"
        )
        == "RANGE_OR_COMPRESSION"
    )

    print(
        "[PASS] Intrabar context "
        "coverage self-test passed."
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Read-only intrabar "
            "direction/momentum/regime "
            "data coverage audit."
        )
    )

    parser.add_argument(
        "--source-dir",
        action="append",
        default=[],
    )

    parser.add_argument(
        "--all-accounts",
        action="store_true",
    )

    parser.add_argument(
        "--self-test",
        action="store_true",
    )

    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    sources = []

    for value in args.source_dir:
        path = Path(value)

        if not path.is_absolute():
            path = (
                ROOT
                / path
            )

        sources.append(
            path.resolve()
        )

    if args.all_accounts:
        sources.extend(
            discover_accounts()
        )

    unique = []
    seen = set()

    for path in sources:
        path = path.resolve()

        if path in seen:
            continue

        seen.add(path)

        unique.append(path)

    if not unique:
        raise SystemExit(
            "[STOP] No account source "
            "selected. Use --all-accounts "
            "or --source-dir."
        )

    rows = []

    for source in unique:
        outcomes, outcomes_path = (
            outcome_rows(
                source
            )
        )

        audits, audit_path = (
            audit_map(
                source
            )
        )

        selected = [
            row
            for row in outcomes
            if is_target_intrabar(
                row
            )
        ]

        print(
            f"[LOAD] account={source.name} "
            f"outcomes={len(outcomes)} "
            f"target_intrabar="
            f"{len(selected)} "
            f"audit_setups="
            f"{len(audits)}"
        )

        for row in selected:
            setup_id = text(
                row.get("setup_id")
            )

            rows.append(
                context_row(
                    source.name,
                    row,
                    audits.get(
                        setup_id
                    ),
                )
            )

    if not rows:
        raise SystemExit(
            "[STOP] No ASLS / "
            "FAILED_FVG intrabar "
            "setup outcomes found."
        )

    coverage = {
        "row_count": len(rows),

        "risk_coverage": ratio(
            rows,
            lambda row: (
                row[
                    "risk_distance"
                ]
                is not None
                and row[
                    "risk_distance"
                ]
                > 0
            ),
        ),

        "m15_context_coverage": (
            ratio(
                rows,
                lambda row: (
                    row[
                        "m15_relation"
                    ]
                    != "UNKNOWN"
                ),
            )
        ),

        "momentum_hint_coverage": (
            ratio(
                rows,
                lambda row: (
                    row[
                        "momentum_relation"
                    ]
                    != "UNKNOWN"
                ),
            )
        ),

        "regime_coverage": (
            ratio(
                rows,
                lambda row: (
                    row[
                        "regime_family"
                    ]
                    != "UNKNOWN"
                ),
            )
        ),

        "first_hit_coverage": (
            ratio(
                rows,
                lambda row: (
                    row[
                        "first_hit"
                    ]
                    != "UNKNOWN"
                ),
            )
        ),
    }

    ready = (
        len(rows) >= 50
        and coverage[
            "risk_coverage"
        ]
        >= 0.90
        and coverage[
            "m15_context_coverage"
        ]
        >= 0.60
        and coverage[
            "momentum_hint_coverage"
        ]
        >= 0.60
        and coverage[
            "first_hit_coverage"
        ]
        >= 0.60
    )

    coverage["readiness"] = (
        "READY_FOR_REGIME_STATISTICS"
        if ready
        else (
            "NOT_READY_FOR_"
            "REGIME_STATISTICS"
        )
    )

    timestamp = (
        datetime.now().strftime(
            "%Y%m%d-%H%M%S"
        )
    )

    output = (
        ROOT
        / "data"
        / "reports"
        / "intrabar_context_coverage"
        / timestamp
    )

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_csv(
        output
        / "intrabar_context_rows.csv",
        rows,
    )

    with (
        output
        / "coverage.json"
    ).open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            coverage,
            handle,
            indent=2,
        )

    print()

    print(
        "=" * 88
    )

    print(
        "INTRABAR CONTEXT "
        "COVERAGE AUDIT"
    )

    print(
        "=" * 88
    )

    print(
        f"Rows: {len(rows)}"
    )

    print(
        "Risk coverage: "
        f"{coverage['risk_coverage']:.1%}"
    )

    print(
        "M15 context coverage: "
        f"{coverage['m15_context_coverage']:.1%}"
    )

    print(
        "Momentum hint coverage: "
        f"{coverage['momentum_hint_coverage']:.1%}"
    )

    print(
        "Regime coverage: "
        f"{coverage['regime_coverage']:.1%}"
    )

    print(
        "First-hit coverage: "
        f"{coverage['first_hit_coverage']:.1%}"
    )

    print(
        "Readiness: "
        f"{coverage['readiness']}"
    )

    print(
        f"Output: {output}"
    )

    print(
        "[SAFE] Reporting only. "
        "No MT5 import, no order send, "
        "no settings or strategy changes."
    )


if __name__ == "__main__":
    main()