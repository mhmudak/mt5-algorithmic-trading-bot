from __future__ import annotations

import sys

import argparse

import json
from datetime import datetime
from pathlib import Path
from typing import Any


PHASE = "PHASE_5AE_RITHMIC_PRODUCTION_ONBOARDING_RUNBOOK"

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

CHECKPOINT_PATH = ORDER_FLOW_DIR / "phase5ad_rithmic_production_subscription_checkpoint.json"

OUT_JSON = ORDER_FLOW_DIR / "phase5ae_rithmic_production_onboarding_runbook.json"
OUT_TXT = ORDER_FLOW_DIR / "phase5ae_rithmic_production_onboarding_runbook_summary.txt"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--symbol",
        default=None,
    )

    args = parser.parse_args()

    try:
        primary_symbol = (
            _require_rithmic_symbol(
                args.symbol,
                root=ROOT,
            )
        )
    except ValueError as exc:
        parser.error(
            str(exc)
        )

    ORDER_FLOW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    checkpoint_report = load_json(
        CHECKPOINT_PATH
    )

    checkpoint = (
        checkpoint_report.get(
            "checkpoint"
        )
        or {}
    )

    checkpoint_symbol = str(
        checkpoint_report.get(
            "symbol"
        )
        or checkpoint.get(
            "symbol"
        )
        or ""
    ).strip().upper()

    checkpoint_symbol_matches = (
        checkpoint_symbol
        == primary_symbol
    )

    production_recommended = bool(
        checkpoint_symbol_matches
        and checkpoint.get(
            "production_subscription_recommended"
        )
    )

    runbook = {
        "phase": PHASE,
        "updated_at": (
            datetime.now().isoformat(
                timespec="seconds"
            )
        ),
        "mode": (
            "PRE_PRODUCTION_PREPARATION"
        ),
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "trade_action": "NO_AUTO_TRADE",
        "production_subscription_recommended": (
            production_recommended
        ),
        "checkpoint_symbol_matches": (
            checkpoint_symbol_matches
        ),
        "provider_path": (
            "RITHMIC_PRIMARY_ONLY_FIRST"
        ),
        "primary_symbol": (
            primary_symbol
        ),
        "rejected_symbol_for_now": None,
        "waiting_for_reply_from": (
            "Rithmic or broker"
        ),
        "do_not_do_while_waiting": [
            (
                "Do not enable automatic "
                "decision influence."
            ),
            (
                "Do not subscribe to multiple "
                "providers."
            ),
            (
                "Do not commit .env or "
                "credentials."
            ),
            (
                "Do not paste passwords in "
                "code or Git."
            ),
            (
                "Do not change live lot/risk "
                "because of Rithmic yet."
            ),
        ],
        "what_to_confirm_from_provider": [
            "Production/live Rithmic access",
            "R | Protocol API or R | API+ access",
            "Production websocket URL",
            "Production system name",
            "COMEX real-time market data",
            (
                "COMEX Level 2 / Depth of "
                "Market / DOM"
            ),
            (
                "Permission for the configured "
                f"contract {primary_symbol}"
            ),
            (
                "API usage classification: "
                "display or non-display"
            ),
            "Non-professional eligibility",
            "Monthly cost",
            (
                "Whether conformance is required "
                "before production access"
            ),
        ],
        "expected_env_keys_after_reply": [
            "RITHMIC_WS_URL",
            "RITHMIC_SYSTEM_NAME",
            "RITHMIC_USERNAME",
            "RITHMIC_PASSWORD",
            "RITHMIC_EXCHANGE=COMEX",
            (
                "RITHMIC_SYMBOL="
                f"{primary_symbol}"
            ),
            "RITHMIC_SDK_PATH",
        ],
        "post_subscription_validation_commands": [
            (
                "python .\\scripts\\"
                "run_phase5y_rithmic_long_session_history.py "
                f"--symbols {primary_symbol} "
                "--exchange COMEX "
                "--duration-seconds 1800 "
                "--snapshot-interval-seconds 3 "
                "--include-order-book"
            ),
            (
                "python .\\scripts\\"
                "analyze_phase5z_rithmic_long_session_orderflow.py "
                f"--symbol {primary_symbol}"
            ),
            (
                "python .\\scripts\\"
                "run_phase5ac_xauusd_rithmic_basis_calibration.py "
                "--mt5-symbol XAUUSD "
                f"--rithmic-symbol {primary_symbol} "
                "--exchange COMEX "
                "--duration-seconds 900 "
                "--snapshot-interval-seconds 3 "
                "--include-order-book"
            ),
            (
                "python .\\scripts\\"
                "build_phase5ad_rithmic_production_subscription_checkpoint.py "
                f"--symbol {primary_symbol}"
            ),
        ],
        "production_acceptance_requirements_before_decision_grade": {
            "current_symbol_positive_bbo_rate": (
                ">= 0.95"
            ),
            "current_symbol_two_sided_dom_rate": (
                ">= 0.95"
            ),
            "current_symbol_max_spread": (
                "<= 1.0"
            ),
            "basis_valid_pair_rate": (
                ">= 0.90"
            ),
            "basis_std": "<= 2.0",
            "trade_flow": (
                "must improve versus test feed"
            ),
            "repeated_sessions": (
                "required before automation"
            ),
            "setup_outcome_evidence": (
                "required before Rithmic can "
                "influence decisions"
            ),
        },
        "next_phase_after_provider_reply": (
            "PHASE_5AF_PRODUCTION_ENV_AND_"
            "CONNECTION_VALIDATION"
        ),
        "industrial_rule": (
            "Rithmic can become a decision-grade "
            "confirmation layer only after "
            "production data passes repeated "
            "validation. It must not become the "
            "only decision maker."
        ),
    }

    OUT_JSON.write_text(
        json.dumps(
            runbook,
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        "[PHASE 5AE RITHMIC PRODUCTION "
        "ONBOARDING RUNBOOK]",
        (
            "updated_at = "
            f"{runbook['updated_at']}"
        ),
        f"mode = {runbook['mode']}",
        (
            "decision_impact = "
            f"{runbook['decision_impact']}"
        ),
        (
            "safe_for_execution = "
            f"{runbook['safe_for_execution']}"
        ),
        (
            "trade_action = "
            f"{runbook['trade_action']}"
        ),
        (
            "production_subscription_recommended = "
            f"{runbook['production_subscription_recommended']}"
        ),
        (
            "checkpoint_symbol_matches = "
            f"{runbook['checkpoint_symbol_matches']}"
        ),
        (
            "provider_path = "
            f"{runbook['provider_path']}"
        ),
        (
            "primary_symbol = "
            f"{runbook['primary_symbol']}"
        ),
        (
            "rejected_symbol_for_now = "
            f"{runbook['rejected_symbol_for_now']}"
        ),
        "",
        "[DO NOT DO WHILE WAITING]",
        *[
            f"- {item}"
            for item
            in runbook[
                "do_not_do_while_waiting"
            ]
        ],
        "",
        "[CONFIRM FROM PROVIDER]",
        *[
            f"- {item}"
            for item
            in runbook[
                "what_to_confirm_from_provider"
            ]
        ],
        "",
        "[EXPECTED .ENV KEYS AFTER REPLY]",
        *[
            f"- {item}"
            for item
            in runbook[
                "expected_env_keys_after_reply"
            ]
        ],
        "",
        "[POST-SUBSCRIPTION VALIDATION COMMANDS]",
        *[
            f"- {item}"
            for item
            in runbook[
                "post_subscription_validation_commands"
            ]
        ],
        "",
        "[PRODUCTION ACCEPTANCE REQUIREMENTS]",
        *[
            f"- {key}: {value}"
            for key, value
            in runbook[
                "production_acceptance_requirements_before_decision_grade"
            ].items()
        ],
        "",
        "[NEXT PHASE]",
        runbook[
            "next_phase_after_provider_reply"
        ],
        "",
        "[INDUSTRIAL RULE]",
        runbook[
            "industrial_rule"
        ],
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