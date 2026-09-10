from __future__ import annotations

import sys

import argparse

import json
from datetime import datetime
from pathlib import Path
from typing import Any


PHASE = "PHASE_5AD_RITHMIC_PRODUCTION_SUBSCRIPTION_CHECKPOINT"

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.order_flow_providers.rithmic_contract_identity import (
    require_rithmic_symbol as _require_rithmic_symbol,
    require_rithmic_symbols as _require_rithmic_symbols,
    resolve_rithmic_symbol as _resolve_rithmic_symbol,
    safe_symbol_for_file as _rithmic_safe_symbol_for_file,
)
ORDER_FLOW_DIR = ROOT / "data" / "order_flow" / "rithmic"

ORDERFLOW_ANALYSIS_PATH = ORDER_FLOW_DIR / "phase5z_rithmic_long_session_orderflow_analysis.json"
BASIS_PATH = ORDER_FLOW_DIR / "phase5ac_xauusd_rithmic_basis_calibration.json"

OUT_JSON = ORDER_FLOW_DIR / "phase5ad_rithmic_production_subscription_checkpoint.json"
OUT_TXT = ORDER_FLOW_DIR / "phase5ad_rithmic_production_subscription_checkpoint_summary.txt"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def get_symbol_result(matrix: dict[str, Any], symbol: str) -> dict[str, Any]:
    for item in matrix.get("symbols") or []:
        if str(item.get("symbol")).upper() == symbol.upper():
            return item

    return {}


def classify_checkpoint(
    *,
    symbol: str,
    analysis: dict[str, Any],
    basis: dict[str, Any],
) -> dict[str, Any]:
    symbol = str(
        symbol
    ).strip().upper()

    analysis_symbol = str(
        analysis.get("symbol")
        or ""
    ).strip().upper()

    basis_symbol = str(
        basis.get("rithmic_symbol")
        or basis.get("symbol")
        or ""
    ).strip().upper()

    quality = (
        analysis.get("quality")
        or {}
    )

    readiness = (
        analysis.get(
            "decision_readiness"
        )
        or {}
    )

    basis_summary = (
        basis.get("summary")
        or {}
    )

    max_spread = as_float(
        quality.get(
            "max_spread"
        ),
        default=999.0,
    )

    checks = {
        "analysis_symbol_matches": (
            analysis_symbol
            == symbol
        ),
        "basis_symbol_matches": (
            basis_symbol
            == symbol
        ),
        "current_symbol_sample_count_ok": (
            as_float(
                quality.get(
                    "sample_count"
                )
            )
            >= 50
        ),
        "current_symbol_bbo_rate_ok": (
            as_float(
                quality.get(
                    "positive_bbo_rate"
                )
            )
            >= 0.95
        ),
        "current_symbol_two_sided_dom_rate_ok": (
            as_float(
                quality.get(
                    "two_sided_dom_rate"
                )
            )
            >= 0.95
        ),
        "current_symbol_spread_ok": (
            0
            < max_spread
            <= 1.0
        ),
        "current_symbol_dom_dynamics_available": (
            "dom_dynamics_available"
            in (
                readiness.get(
                    "passed"
                )
                or []
            )
        ),
        "basis_ready_observe_only": bool(
            basis_summary.get(
                "basis_ready_observe_only"
            )
        ),
        "basis_valid_pair_rate_ok": (
            as_float(
                basis_summary.get(
                    "valid_pair_rate"
                )
            )
            >= 0.90
        ),
        "basis_stability_ok": (
            as_float(
                basis_summary.get(
                    "basis_std"
                ),
                default=999.0,
            )
            <= 2.0
        ),
        "test_feed_trade_flow_still_weak": (
            as_float(
                quality.get(
                    "max_rolling_trade_count"
                )
            )
            < 5
        ),
        "automation_still_disabled": (
            readiness.get(
                "automation_allowed"
            )
            is False
        ),
    }

    failed = [
        key
        for key, value
        in checks.items()
        if not value
    ]

    passed = [
        key
        for key, value
        in checks.items()
        if value
    ]

    required_for_subscription = (
        "analysis_symbol_matches",
        "basis_symbol_matches",
        "current_symbol_sample_count_ok",
        "current_symbol_bbo_rate_ok",
        "current_symbol_two_sided_dom_rate_ok",
        "current_symbol_spread_ok",
        "current_symbol_dom_dynamics_available",
        "basis_ready_observe_only",
        "basis_valid_pair_rate_ok",
        "basis_stability_ok",
        "test_feed_trade_flow_still_weak",
        "automation_still_disabled",
    )

    production_subscription_recommended = all(
        checks[key]
        for key
        in required_for_subscription
    )

    if production_subscription_recommended:
        checkpoint_status = (
            "READY_TO_SUBSCRIBE_FOR_"
            "PRODUCTION_VALIDATION"
        )

        recommendation = (
            "Subscribe to one paid Rithmic "
            "production provider first for "
            f"{symbol}, with COMEX real-time "
            "market data and market depth. "
            "Production data is still required "
            "before any decision-grade use."
        )

    elif len(
        failed
    ) <= 3:
        checkpoint_status = (
            "ALMOST_READY_REPEAT_"
            "ONE_MORE_SESSION"
        )

        recommendation = (
            "Repeat one more active-market "
            f"{symbol} history and basis "
            "calibration session before the "
            "production-validation checkpoint."
        )

    else:
        checkpoint_status = (
            "NOT_READY_TO_SUBSCRIBE_YET"
        )

        recommendation = (
            "Do not use this checkpoint as "
            "production-ready. Resolve the "
            "failed current-contract validation "
            "checks first."
        )

    return {
        "symbol": symbol,
        "checkpoint_status": (
            checkpoint_status
        ),
        "production_subscription_recommended": (
            production_subscription_recommended
        ),
        "subscribe_to_many_providers": False,
        "recommended_provider_path": (
            "RITHMIC_PRIMARY_ONLY_FIRST"
        ),
        "recommended_subscription_scope": [
            "Rithmic production/live access",
            "R | Protocol API or R | API+ access",
            "COMEX real-time market data",
            "COMEX market depth / Level 2 / DOM",
            (
                "Active configured gold futures "
                f"contract permission: {symbol}"
            ),
        ],
        "do_not_enable_yet": [
            "automatic decision influence",
            "automatic trade confirmation",
            "automatic Rithmic blocking/approval",
            "multi-provider complexity",
        ],
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "recommendation": recommendation,
    }

def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--symbol",
        default=None,
    )

    args = parser.parse_args()

    try:
        symbol = _require_rithmic_symbol(
            args.symbol,
            root=ROOT,
        )
    except ValueError as exc:
        parser.error(
            str(exc)
        )

    ORDER_FLOW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    analysis = load_json(
        ORDERFLOW_ANALYSIS_PATH
    )

    basis = load_json(
        BASIS_PATH
    )

    checkpoint = classify_checkpoint(
        symbol=symbol,
        analysis=analysis,
        basis=basis,
    )

    report = {
        "phase": PHASE,
        "updated_at": (
            datetime.now().isoformat(
                timespec="seconds"
            )
        ),
        "symbol": symbol,
        "mode": "OBSERVE_ONLY",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "trade_action": "NO_AUTO_TRADE",
        "checkpoint": checkpoint,
        "inputs": {
            "orderflow_analysis": str(
                ORDERFLOW_ANALYSIS_PATH
            ),
            "basis_calibration": str(
                BASIS_PATH
            ),
        },
        "industrial_rule": (
            "Rithmic can become decision-grade only "
            "after production data, repeated-session "
            "validation, basis stability, and "
            "setup-outcome evidence. It must not "
            "become the only decision maker."
        ),
    }

    OUT_JSON.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        "[PHASE 5AD RITHMIC PRODUCTION "
        "SUBSCRIPTION CHECKPOINT]",
        f"updated_at = {report['updated_at']}",
        f"symbol = {symbol}",
        f"mode = {report['mode']}",
        (
            "can_influence_decision = "
            f"{report['can_influence_decision']}"
        ),
        (
            "safe_for_execution = "
            f"{report['safe_for_execution']}"
        ),
        "",
        "[CHECKPOINT]",
        (
            "checkpoint_status = "
            f"{checkpoint.get('checkpoint_status')}"
        ),
        (
            "production_subscription_recommended = "
            f"{checkpoint.get('production_subscription_recommended')}"
        ),
        (
            "subscribe_to_many_providers = "
            f"{checkpoint.get('subscribe_to_many_providers')}"
        ),
        (
            "recommended_provider_path = "
            f"{checkpoint.get('recommended_provider_path')}"
        ),
        "",
        "[PASSED]",
        *[
            f"- {item}"
            for item
            in checkpoint.get("passed")
            or []
        ],
        "",
        "[FAILED]",
        *[
            f"- {item}"
            for item
            in checkpoint.get("failed")
            or []
        ],
        "",
        "[RECOMMENDED SUBSCRIPTION SCOPE]",
        *[
            f"- {item}"
            for item
            in checkpoint.get(
                "recommended_subscription_scope"
            )
            or []
        ],
        "",
        "[DO NOT ENABLE YET]",
        *[
            f"- {item}"
            for item
            in checkpoint.get(
                "do_not_enable_yet"
            )
            or []
        ],
        "",
        "[RECOMMENDATION]",
        checkpoint.get(
            "recommendation"
        ),
        "",
        "[INDUSTRIAL RULE]",
        report["industrial_rule"],
        "",
        f"json = {OUT_JSON}",
        f"summary = {OUT_TXT}",
    ]

    OUT_TXT.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print(
        "\n".join(lines)
    )

if __name__ == "__main__":
    main()