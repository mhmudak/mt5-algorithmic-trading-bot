from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path


DATA_PATH = Path("data/fcr_m1_fvg_regime_shadow.jsonl")
_LOADED = False
_SEEN_IDS = set()


def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_seen_once():
    global _LOADED
    if _LOADED:
        return

    _LOADED = True

    if not DATA_PATH.exists():
        return

    try:
        for line in DATA_PATH.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines():
            if not line.strip():
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            shadow_id = item.get("shadow_id")
            if shadow_id:
                _SEEN_IDS.add(str(shadow_id))

    except OSError:
        return


def _shadow_id(signal_data, market_condition):
    setup_id = signal_data.get("setup_id")

    if setup_id:
        raw = (
            f"{setup_id}|{market_condition}|"
            f"{signal_data.get('signal')}|"
            f"{signal_data.get('entry_model')}"
        )
    else:
        raw = (
            f"FCR_M1_FVG|{market_condition}|"
            f"{signal_data.get('signal')}|"
            f"{signal_data.get('entry_model')}|"
            f"{signal_data.get('entry_reference')}|"
            f"{signal_data.get('sl_reference')}|"
            f"{signal_data.get('tp_reference')}"
        )

    return hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()[:20]


def persist_fcr_regime_shadow_observation(
    *,
    signal_data,
    symbol,
    session,
    market_condition,
    closed_m1_time_epoch,
    mt5_time_epoch,
):
    """Persist an excluded-regime FCR setup with no execution authority."""
    if not isinstance(signal_data, dict):
        return False, "invalid_signal_data"

    signal = signal_data.get("signal")
    if signal not in {"BUY", "SELL"}:
        return False, "not_directional"

    entry = _float_or_none(
        signal_data.get(
            "entry_reference",
            signal_data.get("entry"),
        )
    )
    sl = _float_or_none(
        signal_data.get(
            "sl_reference",
            signal_data.get("stop_loss"),
        )
    )
    tp = _float_or_none(
        signal_data.get(
            "tp_reference",
            signal_data.get("take_profit"),
        )
    )

    if entry is None or sl is None or tp is None:
        return False, "missing_entry_sl_tp"

    if signal == "BUY":
        if not (sl < entry < tp):
            return False, "invalid_buy_geometry"
    else:
        if not (tp < entry < sl):
            return False, "invalid_sell_geometry"

    _load_seen_once()

    shadow_id = _shadow_id(
        signal_data,
        market_condition,
    )

    if shadow_id in _SEEN_IDS:
        return False, "duplicate"

    record = {
        "shadow_id": shadow_id,
        "observed_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "observed_at_epoch": int(time.time()),
        "mt5_time_epoch": int(mt5_time_epoch),
        "closed_m1_time_epoch": int(
            closed_m1_time_epoch
        ),
        "symbol": symbol,
        "strategy": "FCR_M1_FVG",
        "signal": signal,
        "entry_model": signal_data.get("entry_model"),
        "setup_id": signal_data.get("setup_id"),
        "score": signal_data.get("score"),
        "session": session,
        "market_condition": market_condition,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "rr": _float_or_none(
            signal_data.get(
                "rr",
                signal_data.get("risk_reward"),
            )
        ),
        "fcr_high": _float_or_none(
            signal_data.get("fcr_high")
        ),
        "fcr_low": _float_or_none(
            signal_data.get("fcr_low")
        ),
        "fcr_time": str(
            signal_data.get("fcr_time")
        ),
        "reason": signal_data.get("reason"),
        "regime_excluded_from_live_map": True,
        "decision_impact": "OBSERVE_ONLY",
        "execution_authority": False,
        "setup_win_definition": "FAVORABLE_PLUS_10_USD_PRICE_MOVE",
    }

    try:
        DATA_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with DATA_PATH.open(
            "a",
            encoding="utf-8",
            newline="\n",
        ) as handle:
            handle.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )
    except OSError as exc:
        return False, f"persist_failed:{exc}"

    _SEEN_IDS.add(shadow_id)
    return True, shadow_id
