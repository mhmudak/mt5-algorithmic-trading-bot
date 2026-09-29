from src.rithmic_setup_verdict import (
    format_rithmic_setup_verdict_telegram_block,
)

base = {
    "setup_direction": "BUY",
    "rithmic_symbol": "GCZ6",
    "exchange": "COMEX",
    "source_age_seconds": 0.4,
    "cache_age_seconds": 0.4,
    "trade_count": 168,
    "metrics": {
        "delta": 32,
        "cumulative_delta": 42,
        "dom_depth_imbalance": -0.069,
    },
    "decision_impact": "NONE",
    "can_influence_decision": False,
    "safe_for_execution": False,
    "execution_allowed": False,
}

cases = {
    "SUPPORTS": {
        **base,
        "verdict": "SUPPORTS_SETUP",
        "support_score": 2,
        "against_score": 1,
        "reason": "rithmic_evidence_supports_setup",
    },
    "AGAINST": {
        **base,
        "verdict": "AGAINST_SETUP",
        "support_score": 1,
        "against_score": 3,
        "reason": "rithmic_evidence_against_setup",
    },
    "NEUTRAL": {
        **base,
        "verdict": "NEUTRAL",
        "support_score": 1,
        "against_score": 1,
        "reason": "mixed_rithmic_evidence",
    },
    "STALE": {
        **base,
        "verdict": "UNAVAILABLE",
        "source_age_seconds": 8.2,
        "cache_age_seconds": 8.2,
        "support_score": 0,
        "against_score": 0,
        "reason": "rithmic_source_stale",
    },
    "UNAVAILABLE": {
        **base,
        "verdict": "UNAVAILABLE",
        "source_age_seconds": None,
        "cache_age_seconds": None,
        "trade_count": None,
        "metrics": {},
        "support_score": 0,
        "against_score": 0,
        "reason": "rithmic_snapshot_unavailable",
    },
}

for name, verdict in cases.items():
    print("\n" + "=" * 72)
    print(name)
    print("=" * 72)
    print(format_rithmic_setup_verdict_telegram_block(verdict))

print("\n" + "=" * 72)
print("SAFETY CONTRACT")
print("=" * 72)

for name, verdict in cases.items():
    print(
        f"{name}: "
        f"decision_impact={verdict['decision_impact']} | "
        f"can_influence={verdict['can_influence_decision']} | "
        f"safe_for_execution={verdict['safe_for_execution']} | "
        f"execution_allowed={verdict['execution_allowed']}"
    )
