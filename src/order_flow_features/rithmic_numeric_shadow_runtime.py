from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import time

from src.order_flow_features.rithmic_numeric_shadow_plan import (
    build_rithmic_numeric_shadow_plan,
)
from src.order_flow_features.rithmic_numeric_shadow_translation import (
    build_numeric_shadow_translation_context,
)


MODEL = "RITHMIC_NUMERIC_SHADOW_RUNTIME_V1"

_PROJECT_ROOT = (
    Path(__file__).resolve().parents[2]
)

_RITHMIC_DATA_DIR = (
    _PROJECT_ROOT
    / "data"
    / "order_flow"
    / "rithmic"
)

DEFAULT_BASIS_PATH = (
    _RITHMIC_DATA_DIR
    / "phase5ac_xauusd_rithmic_basis_calibration.json"
)


def _authority() -> dict[str, Any]:
    return {
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "execution_allowed": False,
        "trade_action": "NO_AUTO_TRADE",
        "can_modify_entry": False,
        "can_modify_sl": False,
        "can_modify_tp": False,
        "can_modify_size": False,
    }


def _state_path(
    symbol: str,
) -> Path:
    safe = (
        str(symbol or "")
        .strip()
        .upper()
        .replace("/", "_")
        .replace("\\", "_")
        .replace(".", "_")
    )

    return (
        _RITHMIC_DATA_DIR
        / (
            f"{safe}_"
            "phase5c_rithmic_state_latest.json"
        )
    )


def _load_json(
    path: Path,
) -> tuple[
    dict[str, Any] | None,
    str | None,
]:
    try:
        if not path.exists():
            return (
                None,
                "file_missing",
            )

        payload = json.loads(
            path.read_text(
                encoding="utf-8-sig",
            )
        )

        if not isinstance(
            payload,
            dict,
        ):
            return (
                None,
                "json_root_not_object",
            )

        return (
            payload,
            None,
        )

    except Exception as exc:
        return (
            None,
            (
                "json_load_error:"
                f"{type(exc).__name__}"
            ),
        )


def _normalize_alignment(
    verdict: Any,
) -> str:
    if not isinstance(
        verdict,
        dict,
    ):
        return "UNAVAILABLE"

    for key in (
        "alignment",
        "verdict",
    ):
        value = str(
            verdict.get(key)
            or ""
        ).strip().upper()

        if value in {
            "SUPPORTS_SETUP",
            "AGAINST_SETUP",
            "NEUTRAL",
            "MIXED",
            "UNAVAILABLE",
        }:
            return value

    if (
        verdict.get(
            "supports_setup"
        )
        is True
    ):
        return "SUPPORTS_SETUP"

    if (
        verdict.get(
            "against_setup"
        )
        is True
    ):
        return "AGAINST_SETUP"

    return "NEUTRAL"


def build_rithmic_numeric_shadow_runtime_context(
    *,
    enabled: bool,
    signal: Any,
    rithmic_verdict: Any,
    rithmic_symbol: str = "GCZ6",
    exchange: str = "COMEX",
    state_path: str | Path | None = None,
    basis_path: str | Path | None = None,
    now_epoch: float | None = None,
    max_basis_age_seconds: float = 300.0,
    max_state_age_seconds: float = 15.0,
    max_component_age_seconds: float = 15.0,
    max_gc_spread: float = 1.0,
) -> dict[str, Any]:
    """
    Build display-only numeric Rithmic SHADOW context.

    Critical invariant:
    if enabled=False, return before any runtime JSON path
    is inspected or read.
    """

    result = {
        "model": MODEL,
        "mode": "SHADOW_ONLY",
        "enabled": bool(
            enabled
        ),
        "status": "DISABLED",
        "reason": (
            "numeric_shadow_runtime_disabled"
        ),
        "rithmic_symbol": (
            str(
                rithmic_symbol
                or ""
            )
            .strip()
            .upper()
        ),
        "exchange": (
            str(
                exchange
                or ""
            )
            .strip()
            .upper()
        ),
        "alignment": (
            _normalize_alignment(
                rithmic_verdict
            )
        ),
        "state_path": None,
        "basis_path": None,
        "translation_context": None,
        "numeric_shadow_plan": None,
        **_authority(),
    }

    # Hard short-circuit:
    # no file existence check, stat or JSON read.
    if not bool(
        enabled
    ):
        return result

    symbol = result[
        "rithmic_symbol"
    ]

    if not symbol:
        result.update(
            {
                "status": "BLOCKED",
                "reason": (
                    "rithmic_symbol_missing"
                ),
            }
        )
        return result

    resolved_state = (
        Path(state_path)
        if state_path is not None
        else _state_path(
            symbol
        )
    )

    resolved_basis = (
        Path(basis_path)
        if basis_path is not None
        else DEFAULT_BASIS_PATH
    )

    result["state_path"] = str(
        resolved_state
    )

    result["basis_path"] = str(
        resolved_basis
    )

    state, state_error = (
        _load_json(
            resolved_state
        )
    )

    if state is None:
        result.update(
            {
                "status": "BLOCKED",
                "reason": (
                    "phase5c_state_"
                    + str(
                        state_error
                        or "unavailable"
                    )
                ),
            }
        )
        return result

    basis, basis_error = (
        _load_json(
            resolved_basis
        )
    )

    if basis is None:
        result.update(
            {
                "status": "BLOCKED",
                "reason": (
                    "basis_"
                    + str(
                        basis_error
                        or "unavailable"
                    )
                ),
            }
        )
        return result

    try:
        basis_mtime = (
            resolved_basis
            .stat()
            .st_mtime
        )
    except Exception as exc:
        result.update(
            {
                "status": "BLOCKED",
                "reason": (
                    "basis_mtime_error:"
                    f"{type(exc).__name__}"
                ),
            }
        )
        return result

    runtime_now = (
        float(
            now_epoch
        )
        if now_epoch is not None
        else time.time()
    )

    translation = (
        build_numeric_shadow_translation_context(
            state=state,
            basis_payload=basis,
            basis_file_mtime_epoch=(
                basis_mtime
            ),
            now_epoch=runtime_now,
            expected_symbol=symbol,
            expected_exchange=(
                result["exchange"]
            ),
            max_basis_age_seconds=(
                max_basis_age_seconds
            ),
            max_state_age_seconds=(
                max_state_age_seconds
            ),
            max_component_age_seconds=(
                max_component_age_seconds
            ),
            max_gc_spread=(
                max_gc_spread
            ),
        )
    )

    result[
        "translation_context"
    ] = translation

    if (
        translation.get(
            "status"
        )
        != "SHADOW_CANDIDATES_READY"
    ):
        basis_gate = (
            translation.get(
                "basis_gate"
            )
        )

        state_gate = (
            translation.get(
                "state_gate"
            )
        )

        gate_reason = None

        if isinstance(
            basis_gate,
            dict,
        ):
            gate_reason = (
                basis_gate.get(
                    "reason"
                )
            )

        if (
            gate_reason is None
            and isinstance(
                state_gate,
                dict,
            )
        ):
            gate_reason = (
                state_gate.get(
                    "reason"
                )
            )

        if gate_reason is None:
            gate_reason = (
                translation.get(
                    "reason"
                )
            )

        result.update(
            {
                "status": "BLOCKED",
                "reason": (
                    "translation_blocked:"
                    + str(
                        gate_reason
                        or "unknown"
                    )
                ),
            }
        )
        return result

    plan = (
        build_rithmic_numeric_shadow_plan(
            signal=signal,
            rithmic_alignment=(
                result[
                    "alignment"
                ]
            ),
            translation_context=(
                translation
            ),
        )
    )

    result[
        "numeric_shadow_plan"
    ] = plan

    if (
        plan.get(
            "status"
        )
        != "NUMERIC_SHADOW_PLAN"
        or plan.get(
            "numeric_plan_available"
        )
        is not True
    ):
        result.update(
            {
                "status": "BLOCKED",
                "reason": (
                    "plan_blocked:"
                    + str(
                        plan.get(
                            "reason"
                        )
                        or "unknown"
                    )
                ),
            }
        )
        return result

    result.update(
        {
            "status": (
                "NUMERIC_SHADOW_READY"
            ),
            "reason": (
                "validated_runtime_numeric_shadow_ready"
            ),
        }
    )

    return result
