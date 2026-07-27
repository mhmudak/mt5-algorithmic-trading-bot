from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


PHASE = "PHASE_5AD_RITHMIC_PRODUCTION_SUBSCRIPTION_CHECKPOINT"

ROOT = Path(__file__).resolve().parents[1]
ORDER_FLOW_DIR = ROOT / "data" / "order_flow" / "rithmic"

SYMBOL_MATRIX_PATH = ORDER_FLOW_DIR / "phase5aa_rithmic_symbol_quality_matrix.json"
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
    matrix: dict[str, Any],
    analysis: dict[str, Any],
    basis: dict[str, Any],
) -> dict[str, Any]:
    selection = matrix.get("selection") or {}
    primary_symbol = selection.get("primary_symbol")

    mgc = get_symbol_result(matrix, "MGCQ6")
    gc = get_symbol_result(matrix, "GCQ6")

    quality = analysis.get("quality") or {}
    readiness = analysis.get("decision_readiness") or {}
    basis_summary = basis.get("summary") or {}

    checks = {
        "primary_symbol_selected": primary_symbol == "MGCQ6",
        "mgc_observe_only_accepted": mgc.get("status") == "ACCEPTED_OBSERVE_ONLY",
        "gc_bad_quality_rejected": gc.get("status") == "REJECTED_BAD_QUALITY",
        "mgc_sample_count_ok": as_float(quality.get("sample_count")) >= 50,
        "mgc_bbo_rate_ok": as_float(quality.get("positive_bbo_rate")) >= 0.95,
        "mgc_two_sided_dom_rate_ok": as_float(quality.get("two_sided_dom_rate")) >= 0.95,
        "mgc_spread_ok": 0 < as_float(quality.get("max_spread"), default=999.0) <= 1.0,
        "mgc_dom_dynamics_available": "dom_dynamics_available" in (readiness.get("passed") or []),
        "basis_ready_observe_only": bool(basis_summary.get("basis_ready_observe_only")),
        "basis_valid_pair_rate_ok": as_float(basis_summary.get("valid_pair_rate")) >= 0.90,
        "basis_stability_ok": as_float(basis_summary.get("basis_std"), default=999.0) <= 2.0,
        "trade_flow_still_weak": as_float(quality.get("max_rolling_trade_count")) < 5,
        "automation_still_disabled": readiness.get("automation_allowed") is False,
    }

    failed = [k for k, v in checks.items() if not v]
    passed = [k for k, v in checks.items() if v]

    production_subscription_recommended = bool(
        checks["primary_symbol_selected"]
        and checks["mgc_observe_only_accepted"]
        and checks["mgc_sample_count_ok"]
        and checks["mgc_bbo_rate_ok"]
        and checks["mgc_two_sided_dom_rate_ok"]
        and checks["mgc_spread_ok"]
        and checks["mgc_dom_dynamics_available"]
        and checks["basis_ready_observe_only"]
        and checks["basis_valid_pair_rate_ok"]
        and checks["basis_stability_ok"]
        and checks["trade_flow_still_weak"]
    )

    if production_subscription_recommended:
        checkpoint_status = "READY_TO_SUBSCRIBE_FOR_PRODUCTION_VALIDATION"
        recommendation = (
            "Subscribe to one paid production provider first: Rithmic production + COMEX market depth for MGC/GC. "
            "Reason: observe-only DOM/BBO/basis are validated, but test-feed trade flow remains weak. "
            "Production data is needed before decision-grade automation."
        )
    elif len(failed) <= 3:
        checkpoint_status = "ALMOST_READY_REPEAT_ONE_MORE_SESSION"
        recommendation = (
            "Repeat one more active-market MGCQ6 fast history + basis calibration session before subscribing."
        )
    else:
        checkpoint_status = "NOT_READY_TO_SUBSCRIBE_YET"
        recommendation = (
            "Do not subscribe yet. Fix failed validation checks first."
        )

    return {
        "checkpoint_status": checkpoint_status,
        "production_subscription_recommended": production_subscription_recommended,
        "subscribe_to_many_providers": False,
        "recommended_provider_path": "RITHMIC_PRIMARY_ONLY_FIRST",
        "recommended_subscription_scope": [
            "Rithmic production/live access",
            "R | Protocol API or R | API+ access",
            "COMEX real-time market data",
            "COMEX market depth / Level 2 / DOM",
            "MGC permission",
            "GC permission if available, but MGC remains primary until GC spread is fixed",
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
    ORDER_FLOW_DIR.mkdir(parents=True, exist_ok=True)

    matrix = load_json(SYMBOL_MATRIX_PATH)
    analysis = load_json(ORDERFLOW_ANALYSIS_PATH)
    basis = load_json(BASIS_PATH)

    checkpoint = classify_checkpoint(
        matrix=matrix,
        analysis=analysis,
        basis=basis,
    )

    report = {
        "phase": PHASE,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "OBSERVE_ONLY",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "trade_action": "NO_AUTO_TRADE",
        "checkpoint": checkpoint,
        "inputs": {
            "symbol_matrix": str(SYMBOL_MATRIX_PATH),
            "orderflow_analysis": str(ORDERFLOW_ANALYSIS_PATH),
            "basis_calibration": str(BASIS_PATH),
        },
        "industrial_rule": (
            "Rithmic can become decision-grade only after production data, repeated-session validation, "
            "basis stability, and setup-outcome evidence. It must not become the only decision maker."
        ),
    }

    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "[PHASE 5AD RITHMIC PRODUCTION SUBSCRIPTION CHECKPOINT]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"decision_impact = {report['decision_impact']}",
        f"can_influence_decision = {report['can_influence_decision']}",
        f"safe_for_execution = {report['safe_for_execution']}",
        f"trade_action = {report['trade_action']}",
        "",
        "[CHECKPOINT]",
        f"checkpoint_status = {checkpoint.get('checkpoint_status')}",
        f"production_subscription_recommended = {checkpoint.get('production_subscription_recommended')}",
        f"subscribe_to_many_providers = {checkpoint.get('subscribe_to_many_providers')}",
        f"recommended_provider_path = {checkpoint.get('recommended_provider_path')}",
        "",
        "[PASSED]",
        *[f"- {x}" for x in checkpoint.get("passed") or []],
        "",
        "[FAILED]",
        *[f"- {x}" for x in checkpoint.get("failed") or []],
        "",
        "[RECOMMENDED SUBSCRIPTION SCOPE]",
        *[f"- {x}" for x in checkpoint.get("recommended_subscription_scope") or []],
        "",
        "[DO NOT ENABLE YET]",
        *[f"- {x}" for x in checkpoint.get("do_not_enable_yet") or []],
        "",
        "[RECOMMENDATION]",
        checkpoint.get("recommendation"),
        "",
        "[INDUSTRIAL RULE]",
        report["industrial_rule"],
        "",
        f"json = {OUT_JSON}",
        f"summary = {OUT_TXT}",
    ]

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()