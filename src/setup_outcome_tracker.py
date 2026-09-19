import json
from datetime import datetime, timedelta

from config.settings import (
    ENABLE_SETUP_OUTCOME_TRACKER,
    SETUP_OUTCOME_EXPIRY_MINUTES,
    SETUP_OUTCOME_WIN_PRICE_MOVE,
    SETUP_OUTCOME_TRACK_EVENTS,
    SETUP_OUTCOME_SCENARIO_WINDOW_MINUTES,
    SETUP_OUTCOME_MIN_ADVERSE_FOR_REENTRY,
    SETUP_OUTCOME_REENTRY_PROFIT_TRIGGER,
)

from src.account_context import get_account_file
from src.logger import logger

from src.google_sheets_logger import send_setup_outcome_to_google_sheets
from src.market_participation_context import (
    build_market_participation_context,
    build_market_participation_statistics_fields,
)
from config.settings import ENABLE_SETUP_HISTORICAL_OPTIMIZER_WALK_FORWARD_SNAPSHOTS

def get_setup_outcomes_file():
    return get_account_file("setup_outcomes.json")


def load_setup_outcomes():
    path = get_setup_outcomes_file()

    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[SETUP OUTCOME] Failed to load file: {e}")
        return {}


def save_setup_outcomes(items):
    path = get_setup_outcomes_file()

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[SETUP OUTCOME] Failed to save file: {e}")


def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _score_bucket(score):
    try:
        score = int(float(score))
    except Exception:
        return "SCORE_UNKNOWN"

    if score >= 95:
        return "SCORE_95_100"

    if score >= 90:
        return "SCORE_90_94"

    if score >= 80:
        return "SCORE_80_89"

    return "SCORE_LOW"


def _time_window(dt):
    hour = dt.hour
    minute = dt.minute

    if hour < 7:
        return "ASIA_HOURS"

    if 7 <= hour < 10:
        return "LONDON_OPEN"

    if 10 <= hour < 13:
        return "MIDDAY"

    if 13 <= hour < 16:
        return "NEWYORK_OPEN"

    if 16 <= hour < 20:
        return "NEWYORK_LATE"

    if hour >= 20:
        return "OFF_HOURS"

    return f"{hour:02d}:{minute:02d}"


def _scenario_bucket(dt):
    minutes = SETUP_OUTCOME_SCENARIO_WINDOW_MINUTES

    bucket_minute = (dt.minute // minutes) * minutes

    return dt.replace(
        minute=bucket_minute,
        second=0,
        microsecond=0,
    ).isoformat()


def build_context_key(item):
    parts = [
        item.get("strategy", "UNKNOWN"),
        item.get("signal", "NA"),
        item.get("entry_model", "NA"),
        item.get("session", "UNKNOWN"),
        item.get("market_condition", "UNKNOWN"),
        item.get("day_of_week", "UNKNOWN"),
        item.get("time_window", "UNKNOWN"),
        item.get("score_bucket", "SCORE_UNKNOWN"),
    ]

    return "|".join(str(part).upper() for part in parts)


def _build_scenario_key(symbol, dt):
    return f"{symbol}|{_scenario_bucket(dt)}"


def _get_nearby_strategies(items, scenario_key):
    strategies = []

    for item in items.values():
        if item.get("scenario_key") != scenario_key:
            continue

        strategy = item.get("strategy")

        if strategy and strategy not in strategies:
            strategies.append(strategy)

    return strategies



def _capture_participation_statistics_fail_open(
    *,
    symbol,
    signal,
    event,
    market_participation_context=None,
):
    """
    Capture research features for a newly-created
    setup-outcome row.

    Existing rows are intentionally not overwritten
    with later participation context, avoiding future
    information leakage in later model research.
    """

    explicit_snapshot = isinstance(
        market_participation_context,
        dict,
    )

    try:
        context = (
            market_participation_context
            if explicit_snapshot
            else build_market_participation_context(
                symbol=symbol,
                signal=signal,
            )
        )

        fields = (
            build_market_participation_statistics_fields(
                context
            )
        )

        fields[
            "participation_capture_event"
        ] = event

        fields[
            "participation_capture_source"
        ] = (
            "EXACT_SETUP_SNAPSHOT"
            if explicit_snapshot
            else "TRACKER_EVENT_FALLBACK"
        )

        return fields

    except Exception as exc:
        logger.warning(
            "[SETUP OUTCOME] "
            "Market participation statistics "
            f"failed open | error={exc}"
        )

        fields = (
            build_market_participation_statistics_fields(
                None
            )
        )

        fields[
            "participation_capture_event"
        ] = event

        fields[
            "participation_capture_source"
        ] = "FAILED_OPEN"

        return fields


def _capture_historical_optimizer_snapshot_fail_open(
    *,
    setup_id,
    strategy,
    signal,
    entry_model,
    session,
    market_condition,
    score,
    entry,
    sl,
    tp,
    extra,
    captured_at,
):
    if (
        not ENABLE_SETUP_HISTORICAL_OPTIMIZER_WALK_FORWARD_SNAPSHOTS
    ):
        return None

    try:
        from src.setup_historical_optimizer import (
            SETUP_HISTORICAL_OPTIMIZER_VERSION,
            build_setup_historical_optimizer_walk_forward_snapshot,
        )

        return build_setup_historical_optimizer_walk_forward_snapshot(
            {
                "setup_id": setup_id,
                "strategy": strategy,
                "signal": signal,
                "entry_model": entry_model,
                "session": session,
                "market_condition": market_condition,
                "score": score,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "extra": dict(extra or {}),
                "setup_historical_optimizer_account_dir": str(
                    get_setup_outcomes_file().parent
                ),
                "optimizer_snapshot_captured_at": captured_at,
            }
        )
    except Exception as exc:
        logger.error(
            "[SETUP HISTORICAL OPTIMIZER V2] "
            f"Snapshot capture failed: {exc}"
        )

        return {
            "snapshot_schema_version": "V2",
            "optimizer_version": locals().get(
                "SETUP_HISTORICAL_OPTIMIZER_VERSION",
                "V1.1",
            ),
            "captured_at": captured_at,
            "capture_mode": "LIVE_FILE_STATE_AT_DETECTION",
            "setup_id": setup_id,
            "available": False,
            "reason": "snapshot_capture_failed",
            "decision_impact": "DISPLAY_ONLY",
            "can_execute": False,
            "can_block_trade": False,
            "can_modify_score": False,
            "can_modify_risk": False,
            "can_modify_entry_sl_tp": False,
        }

def _better_entry_safe_context_value(value):
    if value is None or isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    if isinstance(value, dict):
        return {
            str(key): _better_entry_safe_context_value(item)
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            _better_entry_safe_context_value(item)
            for item in value
        ]

    return str(value)


def _build_better_entry_detection_context(item):
    """
    Immutable detection-time context for later entry-policy research.

    Participation is a proxy and remains observational. We preserve
    whatever participation/momentum/volatility fields were available
    at registration without interpreting them here.
    """

    extra = item.get("extra")

    if not isinstance(extra, dict):
        extra = {}

    context = {
        "session": item.get("session"),
        "market_condition": item.get(
            "market_condition"
        ),
        "momentum": (
            item.get("momentum")
            if item.get("momentum") is not None
            else extra.get("momentum")
        ),
        "direction_context": (
            item.get("direction_context")
            if item.get("direction_context") is not None
            else extra.get("direction_context")
        ),
    }

    for canonical_key in (
        "atr_14",
        "atr",
        "spread",
    ):
        value = item.get(
            canonical_key
        )

        if value is None:
            value = extra.get(
                canonical_key
            )

        if value is not None:
            context[
                canonical_key
            ] = _better_entry_safe_context_value(
                value
            )

    signal_terms = (
        "participation",
        "tick_volume",
        "volume",
        "velocity",
        "pressure",
        "activity",
        "microstructure",
        "spread",
        "momentum",
        "atr",
    )

    signals = {}

    for source in (
        item,
        extra,
    ):
        for key, value in source.items():
            key_text = str(
                key
            )
            key_lower = key_text.lower()

            if any(
                term in key_lower
                for term in signal_terms
            ):
                signals[
                    key_text
                ] = _better_entry_safe_context_value(
                    value
                )

    context[
        "signals"
    ] = signals

    return context


def _better_entry_elapsed_seconds(
    created_at,
    observed_at,
):
    try:
        start = datetime.fromisoformat(
            str(
                created_at
            ).replace(
                "Z",
                "+00:00",
            )
        )
        end = datetime.fromisoformat(
            str(
                observed_at
            ).replace(
                "Z",
                "+00:00",
            )
        )

        elapsed = (
            end
            - start
        ).total_seconds()

        if elapsed < 0:
            return None

        return elapsed
    except Exception:
        return None


def _update_pre_w10_path_metrics(
    item,
    current_price,
    observed_at=None,
):
    """
    Update adverse excursion only before the first +$10 favorable hit.

    Once W10 is hit the metric is frozen forever. This prevents later
    MAE from contaminating historical better-entry calibration.
    """

    if item.get(
        "pre_w10_path_frozen"
    ):
        return False

    if item.get(
        "hit_plus_10"
    ):
        return False

    try:
        entry = float(
            item.get(
                "entry"
            )
        )
        price = float(
            current_price
        )
    except Exception:
        return False

    signal = str(
        item.get(
            "signal"
        )
        or ""
    ).upper()

    if signal == "BUY":
        adverse = max(
            0.0,
            entry
            - price,
        )
    elif signal == "SELL":
        adverse = max(
            0.0,
            price
            - entry,
        )
    else:
        return False

    observed_at = (
        observed_at
        or datetime.now().isoformat()
    )

    changed = False

    if not item.get(
        "pre_w10_path_observed"
    ):
        item[
            "pre_w10_path_observed"
        ] = True
        changed = True

    previous = float(
        item.get(
            "pre_w10_max_adverse_usd",
            0.0,
        )
        or 0.0
    )

    if adverse > previous:
        item[
            "pre_w10_max_adverse_usd"
        ] = adverse
        item[
            "pre_w10_max_adverse_price"
        ] = price
        item[
            "pre_w10_max_adverse_at"
        ] = observed_at
        item[
            "time_to_pre_w10_max_adverse_seconds"
        ] = _better_entry_elapsed_seconds(
            item.get(
                "created_at"
            ),
            observed_at,
        )
        changed = True

    return changed


def _freeze_pre_w10_path_metrics(
    item,
    observed_at=None,
):
    if item.get(
        "pre_w10_path_frozen"
    ):
        return False

    observed_at = (
        observed_at
        or datetime.now().isoformat()
    )

    item[
        "pre_w10_path_frozen"
    ] = True
    item[
        "w10_hit_at"
    ] = observed_at
    item[
        "time_to_w10_seconds"
    ] = _better_entry_elapsed_seconds(
        item.get(
            "created_at"
        ),
        observed_at,
    )

    return True


def _better_entry_counterfactual_rows(
    item,
):
    rows = item.get(
        "better_entry_counterfactuals"
    )

    if not isinstance(rows, dict):
        return {}

    return rows


def _better_entry_counterfactual_authority():
    return {
        "decision_impact": "OBSERVE_ONLY",
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_score": False,
        "can_modify_risk": False,
        "can_modify_entry_sl_tp": False,
        "can_modify_lot": False,
    }


def _better_entry_candidate_record(
    *,
    candidate_id,
    basis,
    candidate_entry,
    original_entry,
    original_sl,
    original_tp,
    created_at,
):
    return {
        "schema_version": "V1.3",
        "candidate_id": candidate_id,
        "basis": basis,
        "candidate_entry": candidate_entry,
        "original_entry": original_entry,
        "original_sl": original_sl,
        "original_tp": original_tp,
        "created_at": created_at,
        "status": "WAITING_FILL",
        "filled": False,
        "fill_at": None,
        "fill_observed_price": None,
        "fill_wait_seconds": None,
        "missed_trade": False,
        "missed_winner": False,
        "missed_at": None,
        "max_favorable_usd_after_fill": 0.0,
        "max_adverse_usd_after_fill": 0.0,
        "hit_plus_10_after_fill": False,
        "w10_after_fill_at": None,
        "hit_tp_after_fill": False,
        "tp_after_fill_at": None,
        "hit_sl_after_fill": False,
        "sl_after_fill_at": None,
        "terminal": False,
        **_better_entry_counterfactual_authority(),
    }



def _better_entry_counterfactual_scope(
    source_event,
):
    """
    Classify a tracker row for Better Entry research.

    PRIMARY:
      mature setup/entry events where entry timing is directly relevant.

    ENTRY_RESCUE:
      low-RR rejections where a better entry could directly repair RR.

    INELIGIBLE:
      generic rejections, execution failures, and MTF-conflict research.
    """
    try:
        from config import settings as runtime_settings

        primary_events = set(
            getattr(
                runtime_settings,
                "BETTER_ENTRY_COUNTERFACTUAL_PRIMARY_EVENTS",
                (),
            )
            or ()
        )
        rescue_events = set(
            getattr(
                runtime_settings,
                "BETTER_ENTRY_COUNTERFACTUAL_ENTRY_RESCUE_EVENTS",
                (),
            )
            or ()
        )
    except Exception:
        primary_events = set()
        rescue_events = set()

    event = str(
        source_event
        or ""
    ).strip().upper()

    primary_events = {
        str(value).strip().upper()
        for value in primary_events
    }
    rescue_events = {
        str(value).strip().upper()
        for value in rescue_events
    }

    if event in primary_events:
        return "PRIMARY"

    if event in rescue_events:
        return "ENTRY_RESCUE"

    return "INELIGIBLE"

def _initialize_better_entry_counterfactuals(
    item,
    historical_items,
    source_event=None,
):
    """
    Capture first-write counterfactual entry candidates.

    The live setup is not yet inserted into historical_items when this
    is called from registration, so it cannot train on its own future.
    """

    try:
        from config.settings import (
            ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER,
        )
    except Exception:
        return False

    if not (
        ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER
    ):
        return False

    research_scope = (
        _better_entry_counterfactual_scope(
            source_event
        )
    )

    item[
        "better_entry_counterfactual_source_event"
    ] = str(
        source_event
        or ""
    ).strip().upper()
    item[
        "better_entry_counterfactual_scope"
    ] = research_scope
    item[
        "better_entry_counterfactual_eligible"
    ] = (
        research_scope
        != "INELIGIBLE"
    )

    if research_scope == "INELIGIBLE":
        return True

    if item.get(
        "better_entry_counterfactuals"
    ):
        return False

    try:
        from src.better_entry_optimizer import (
            build_better_entry_observer,
        )

        if isinstance(
            historical_items,
            dict,
        ):
            historical_rows = [
                row
                for row in historical_items.values()
                if isinstance(
                    row,
                    dict,
                )
            ]
        elif isinstance(
            historical_items,
            list,
        ):
            historical_rows = [
                row
                for row in historical_items
                if isinstance(
                    row,
                    dict,
                )
            ]
        else:
            historical_rows = []

        snapshot = build_better_entry_observer(
            item,
            historical_rows=historical_rows,
            enabled_override=True,
        )
    except Exception as exc:
        item[
            "better_entry_counterfactual_error"
        ] = (
            f"{type(exc).__name__}: {exc}"
        )
        return True

    item[
        "better_entry_observer_snapshot"
    ] = snapshot

    original_entry = snapshot.get(
        "original_entry"
    )
    original_sl = item.get("sl")
    original_tp = item.get("tp")
    created_at = item.get(
        "created_at"
    )

    candidates = {}

    for candidate_id, basis, value in (
        (
            "STRUCTURAL",
            "STRUCTURAL_ANCHOR",
            snapshot.get(
                "structural_candidate_entry"
            ),
        ),
        (
            "ADAPTIVE",
            "ADAPTIVE_HISTORICAL_RETRACEMENT",
            snapshot.get(
                "adaptive_statistical_entry"
            ),
        ),
    ):
        try:
            candidate_entry = float(
                value
            )
        except Exception:
            continue

        try:
            original_entry_float = float(
                original_entry
            )
        except Exception:
            continue

        if candidate_entry <= 0:
            continue

        if candidate_entry == original_entry_float:
            continue

        candidates[
            candidate_id
        ] = _better_entry_candidate_record(
            candidate_id=candidate_id,
            basis=basis,
            candidate_entry=candidate_entry,
            original_entry=original_entry_float,
            original_sl=original_sl,
            original_tp=original_tp,
            created_at=created_at,
        )

    item[
        "better_entry_counterfactuals"
    ] = candidates

    for candidate in candidates.values():
        _maybe_notify_better_entry_shadow(
            item,
            candidate,
        )

    return True



def _better_entry_shadow_format_price(
    value,
):
    try:
        return f"{float(value):.2f}"
    except Exception:
        return "N/A"


def _better_entry_shadow_notification_text(
    item,
    candidate,
):
    snapshot = item.get(
        "better_entry_observer_snapshot"
    )

    if not isinstance(
        snapshot,
        dict,
    ):
        snapshot = {}

    wait_profile = snapshot.get(
        "adaptive_wait_profile"
    )

    if not isinstance(
        wait_profile,
        dict,
    ):
        wait_profile = {}

    status = str(
        candidate.get(
            "status"
        )
        or "UNKNOWN"
    ).upper()

    status_label = {
        "WAITING_FILL": "WAITING FOR BETTER ENTRY",
        "FILLED_TRACKING": "SHADOW ENTRY FILLED",
        "MISSED_WINNER": "MISSED ORIGINAL +$10 WINNER",
        "FILLED_W10_REACHED": "SHADOW +$10 SETUP WIN",
        "FILLED_TP": "SHADOW TP REACHED",
        "FILLED_SL": "SHADOW SL REACHED",
    }.get(
        status,
        status.replace(
            "_",
            " ",
        ),
    )

    lines = [
        "🟦 BETTER ENTRY SHADOW",
        "",
        f"Status: {status_label}",
        f"Strategy: {item.get('strategy') or 'N/A'}",
        f"Entry Model: {item.get('entry_model') or 'N/A'}",
        f"Signal: {item.get('signal') or 'N/A'}",
        f"Scope: {item.get('better_entry_counterfactual_scope') or 'N/A'}",
        (
            "Original Entry: "
            + _better_entry_shadow_format_price(
                candidate.get(
                    "original_entry"
                )
            )
        ),
        (
            "Shadow Entry: "
            + _better_entry_shadow_format_price(
                candidate.get(
                    "candidate_entry"
                )
            )
        ),
        f"Basis: {candidate.get('basis') or candidate.get('candidate_id') or 'N/A'}",
        (
            "CISD: "
            + str(
                snapshot.get(
                    "cisd_policy"
                )
                or snapshot.get(
                    "cisd_mode"
                )
                or "N/A"
            )
        ),
        (
            "Wait Profile: "
            + str(
                wait_profile.get(
                    "profile"
                )
                or "N/A"
            )
        ),
    ]

    if candidate.get(
        "filled"
    ):
        wait_seconds = candidate.get(
            "fill_wait_seconds"
        )

        if wait_seconds is not None:
            try:
                lines.append(
                    "Fill Wait: "
                    + f"{float(wait_seconds):.0f}s"
                )
            except Exception:
                pass

    if status in {
        "FILLED_W10_REACHED",
        "FILLED_TP",
        "FILLED_SL",
    }:
        lines.append(
            "MFE after fill: "
            + _better_entry_shadow_format_price(
                candidate.get(
                    "max_favorable_usd_after_fill"
                )
            )
        )
        lines.append(
            "MAE after fill: "
            + _better_entry_shadow_format_price(
                candidate.get(
                    "max_adverse_usd_after_fill"
                )
            )
        )

    lines.extend(
        [
            "",
            "OBSERVATION ONLY — live execution unchanged.",
        ]
    )

    return "\n".join(
        lines
    )


def _maybe_notify_better_entry_shadow(
    item,
    candidate,
):
    """
    Telegram visibility only.

    Fail-open by design:
    notifier failures never affect setup tracking or execution.
    """

    if not item.get(
        "better_entry_counterfactual_eligible"
    ):
        return False

    try:
        from config import settings as runtime_settings

        if not bool(
            getattr(
                runtime_settings,
                "ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER",
                False,
            )
        ):
            return False
    except Exception:
        return False

    status = str(
        candidate.get(
            "status"
        )
        or ""
    ).upper()

    if not status:
        return False

    notified = candidate.get(
        "telegram_notified_statuses"
    )

    if not isinstance(
        notified,
        list,
    ):
        notified = []

    if status in notified:
        return False

    try:
        from src.notifier import (
            send_telegram_message,
        )

        send_telegram_message(
            _better_entry_shadow_notification_text(
                item,
                candidate,
            )
        )
    except Exception:
        return False

    notified.append(
        status
    )
    candidate[
        "telegram_notified_statuses"
    ] = notified

    return True

def _better_entry_favorable_move(
    *,
    signal,
    reference_price,
    current_price,
):
    if signal == "BUY":
        return (
            current_price
            - reference_price
        )

    if signal == "SELL":
        return (
            reference_price
            - current_price
        )

    return None


def _better_entry_adverse_move(
    *,
    signal,
    reference_price,
    current_price,
):
    favorable = (
        _better_entry_favorable_move(
            signal=signal,
            reference_price=reference_price,
            current_price=current_price,
        )
    )

    if favorable is None:
        return None

    return max(
        0.0,
        -favorable,
    )


def _better_entry_fill_touched(
    *,
    signal,
    candidate_entry,
    current_price,
):
    if signal == "BUY":
        return (
            current_price
            <= candidate_entry
        )

    if signal == "SELL":
        return (
            current_price
            >= candidate_entry
        )

    return False


def _update_better_entry_counterfactuals(
    item,
    current_price,
    observed_at=None,
):
    """
    Update hypothetical better-entry orders from live observed price.

    Critical anti-hindsight rule:
    if the original setup reaches +$10 before an entry candidate fills,
    that candidate becomes MISSED_WINNER permanently. A later retrace
    cannot retroactively fill it.
    """

    rows = (
        _better_entry_counterfactual_rows(
            item
        )
    )

    if not rows:
        return False

    try:
        price = float(
            current_price
        )
        original_entry = float(
            item.get(
                "entry"
            )
        )
    except Exception:
        return False

    signal = str(
        item.get(
            "signal"
        )
        or ""
    ).upper()

    if signal not in {
        "BUY",
        "SELL",
    }:
        return False

    observed_at = (
        observed_at
        or datetime.now().isoformat()
    )

    original_favorable = (
        _better_entry_favorable_move(
            signal=signal,
            reference_price=original_entry,
            current_price=price,
        )
    )

    changed = False

    for candidate in rows.values():
        if not isinstance(
            candidate,
            dict,
        ):
            continue

        if candidate.get(
            "terminal"
        ):
            continue

        try:
            candidate_entry = float(
                candidate.get(
                    "candidate_entry"
                )
            )
        except Exception:
            continue

        if not candidate.get(
            "filled"
        ):
            if _better_entry_fill_touched(
                signal=signal,
                candidate_entry=candidate_entry,
                current_price=price,
            ):
                candidate[
                    "filled"
                ] = True
                candidate[
                    "status"
                ] = "FILLED_TRACKING"
                candidate[
                    "fill_at"
                ] = observed_at
                candidate[
                    "fill_observed_price"
                ] = price
                candidate[
                    "fill_wait_seconds"
                ] = _better_entry_elapsed_seconds(
                    candidate.get(
                        "created_at"
                    ),
                    observed_at,
                )
                _maybe_notify_better_entry_shadow(
                    item,
                    candidate,
                )
                changed = True

            elif (
                original_favorable
                is not None
                and original_favorable
                >= 10.0
            ):
                candidate[
                    "status"
                ] = "MISSED_WINNER"
                candidate[
                    "missed_trade"
                ] = True
                candidate[
                    "missed_winner"
                ] = True
                candidate[
                    "missed_at"
                ] = observed_at
                candidate[
                    "terminal"
                ] = True
                _maybe_notify_better_entry_shadow(
                    item,
                    candidate,
                )
                changed = True
                continue

            else:
                continue

        favorable = (
            _better_entry_favorable_move(
                signal=signal,
                reference_price=candidate_entry,
                current_price=price,
            )
        )
        adverse = (
            _better_entry_adverse_move(
                signal=signal,
                reference_price=candidate_entry,
                current_price=price,
            )
        )

        if favorable is not None:
            previous_favorable = float(
                candidate.get(
                    "max_favorable_usd_after_fill",
                    0.0,
                )
                or 0.0
            )
            favorable_nonnegative = max(
                0.0,
                favorable,
            )

            if (
                favorable_nonnegative
                > previous_favorable
            ):
                candidate[
                    "max_favorable_usd_after_fill"
                ] = favorable_nonnegative
                changed = True

        if adverse is not None:
            previous_adverse = float(
                candidate.get(
                    "max_adverse_usd_after_fill",
                    0.0,
                )
                or 0.0
            )

            if adverse > previous_adverse:
                candidate[
                    "max_adverse_usd_after_fill"
                ] = adverse
                changed = True

        if (
            favorable is not None
            and favorable >= 10.0
            and not candidate.get(
                "hit_plus_10_after_fill"
            )
        ):
            candidate[
                "hit_plus_10_after_fill"
            ] = True
            candidate[
                "w10_after_fill_at"
            ] = observed_at
            candidate[
                "status"
            ] = "FILLED_W10_REACHED"
            _maybe_notify_better_entry_shadow(
                item,
                candidate,
            )
            changed = True

        try:
            sl = float(
                candidate.get(
                    "original_sl"
                )
            )
        except Exception:
            sl = None

        try:
            tp = float(
                candidate.get(
                    "original_tp"
                )
            )
        except Exception:
            tp = None

        sl_touched = False
        tp_touched = False

        if signal == "BUY":
            if sl is not None:
                sl_touched = (
                    price <= sl
                )

            if tp is not None:
                tp_touched = (
                    price >= tp
                )

        elif signal == "SELL":
            if sl is not None:
                sl_touched = (
                    price >= sl
                )

            if tp is not None:
                tp_touched = (
                    price <= tp
                )

        if (
            sl_touched
            and not candidate.get(
                "hit_sl_after_fill"
            )
        ):
            candidate[
                "hit_sl_after_fill"
            ] = True
            candidate[
                "sl_after_fill_at"
            ] = observed_at
            candidate[
                "status"
            ] = "FILLED_SL"
            candidate[
                "terminal"
            ] = True
            _maybe_notify_better_entry_shadow(
                item,
                candidate,
            )
            changed = True
            continue

        if (
            tp_touched
            and not candidate.get(
                "hit_tp_after_fill"
            )
        ):
            candidate[
                "hit_tp_after_fill"
            ] = True
            candidate[
                "tp_after_fill_at"
            ] = observed_at
            candidate[
                "status"
            ] = "FILLED_TP"
            candidate[
                "terminal"
            ] = True
            _maybe_notify_better_entry_shadow(
                item,
                candidate,
            )
            changed = True

    return changed

def register_setup_outcome(
    *,
    symbol,
    setup_id,
    event,
    strategy,
    signal,
    entry_model=None,
    score=None,
    session=None,
    market_condition=None,
    entry=None,
    sl=None,
    tp=None,
    reason=None,
    extra=None,
    market_participation_context=None,
):
    if not ENABLE_SETUP_OUTCOME_TRACKER:
        return False

    if event not in SETUP_OUTCOME_TRACK_EVENTS:
        return False

    if not setup_id or setup_id == "N/A":
        return False

    if signal not in ["BUY", "SELL"]:
        return False

    entry = _safe_float(entry)
    sl = _safe_float(sl)
    tp = _safe_float(tp)

    if entry is None:
        return False

    items = load_setup_outcomes()

    now = datetime.now()
    scenario_key = _build_scenario_key(symbol, now)

    existing = items.get(setup_id)

    if existing:
        source_events = existing.get("source_events", [])
    
        if event not in source_events:
            source_events.append(event)
    
        existing["source_events"] = source_events
        existing["last_seen_at"] = now.isoformat()
        existing["updated_at"] = now.isoformat()
    
        save_setup_outcomes(items)
    
        try:
            send_setup_outcome_to_google_sheets(existing)
        except Exception as e:
            logger.error(f"[SETUP OUTCOME] Google Sheets sync failed: {e}")
    
        return True
    
    participation_statistics = (
        _capture_participation_statistics_fail_open(
            symbol=symbol,
            signal=signal,
            event=event,
            market_participation_context=(
                market_participation_context
            ),
        )
    )

    optimizer_snapshot = (
        _capture_historical_optimizer_snapshot_fail_open(
            setup_id=setup_id,
            strategy=strategy,
            signal=signal,
            entry_model=entry_model,
            session=session,
            market_condition=market_condition,
            score=score,
            entry=entry,
            sl=sl,
            tp=tp,
            extra=extra,
            captured_at=now.isoformat(),
        )
    )

    item = {
        "setup_id": setup_id,
        "symbol": symbol,
        "source_events": [event],
        "status": "TRACKING",
        "created_at": now.isoformat(),
        "last_seen_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=SETUP_OUTCOME_EXPIRY_MINUTES)).isoformat(),

        "strategy": strategy,
        "signal": signal,
        "entry_model": entry_model,
        "score": score,
        "score_bucket": _score_bucket(score),
        "session": session,
        "market_condition": market_condition,
        "day_of_week": now.strftime("%A").upper(),
        "time_window": _time_window(now),

        "entry": round(entry, 2),
        "sl": round(sl, 2) if sl is not None else None,
        "tp": round(tp, 2) if tp is not None else None,
        "reason": reason,
        "extra": extra or {},

        "context_key": None,
        "scenario_key": scenario_key,
        "nearby_strategies": [],

        "path_observed": False,
        "pre_w10_path_observed": False,
        "pre_w10_path_frozen": False,
        "pre_w10_max_adverse_usd": 0.0,
        "pre_w10_max_adverse_price": None,
        "pre_w10_max_adverse_at": None,
        "time_to_pre_w10_max_adverse_seconds": None,
        "w10_hit_at": None,
        "time_to_w10_seconds": None,
        "max_favorable_usd": 0.0,
        "max_adverse_usd": 0.0,

        "hit_plus_10": False,
        "hit_tp": False,
        "hit_sl": False,
        "first_hit": None,

        "time_to_plus_10_min": None,
        "time_to_tp_min": None,
        "time_to_sl_min": None,

        "max_adverse_seen": False,
        "max_recovery_swing_usd": 0.0,
        "recovered_from_adverse": False,
        "reentry_candidate_after_adverse": False,

        "final_outcome": None,
    }

    if optimizer_snapshot is not None:
        item[
            "historical_optimizer_snapshot"
        ] = optimizer_snapshot

    item["context_key"] = build_context_key(item)

    item.update(
        participation_statistics
    )

    item["better_entry_detection_context"] = (
        _build_better_entry_detection_context(item)
    )

    _initialize_better_entry_counterfactuals(
        item,
        items,
        source_event=event,
    )

    items[setup_id] = item

    nearby = _get_nearby_strategies(items, scenario_key)

    for stored_item in items.values():
        if stored_item.get("scenario_key") == scenario_key:
            stored_item["nearby_strategies"] = nearby

    save_setup_outcomes(items)
    
    try:
        send_setup_outcome_to_google_sheets(item)
    except Exception as e:
        logger.error(f"[SETUP OUTCOME] Google Sheets sync failed: {e}")

    logger.info(
        f"[SETUP OUTCOME] Registered | "
        f"setup_id={setup_id} strategy={strategy} signal={signal} "
        f"event={event} context={item['context_key']}"
    )

    return True


def _calculate_moves(item, tick):
    signal = item.get("signal")
    entry = float(item.get("entry"))

    if signal == "BUY":
        current_price = float(tick.bid)
        favorable = current_price - entry
        adverse = entry - current_price

    elif signal == "SELL":
        current_price = float(tick.ask)
        favorable = entry - current_price
        adverse = current_price - entry

    else:
        return None, None, None

    return round(current_price, 2), round(favorable, 2), round(adverse, 2)


def _minutes_since(created_at):
    try:
        created = datetime.fromisoformat(created_at)
        return round((datetime.now() - created).total_seconds() / 60, 2)
    except Exception:
        return None


def _mark_first_hit(item, hit_name):
    if item.get("first_hit") is None:
        item["first_hit"] = hit_name


def _check_tp_sl(item, current_price):
    signal = item.get("signal")
    sl = _safe_float(item.get("sl"))
    tp = _safe_float(item.get("tp"))

    hit_tp = False
    hit_sl = False

    if signal == "BUY":
        if tp is not None and current_price >= tp:
            hit_tp = True

        if sl is not None and current_price <= sl:
            hit_sl = True

    elif signal == "SELL":
        if tp is not None and current_price <= tp:
            hit_tp = True

        if sl is not None and current_price >= sl:
            hit_sl = True

    return hit_tp, hit_sl


def update_setup_outcomes(symbol, tick):
    if not ENABLE_SETUP_OUTCOME_TRACKER:
        return []

    items = load_setup_outcomes()

    if not items:
        return []

    changed = False
    milestones = []
    now = datetime.now()

    for setup_id, item in items.items():
        if item.get("symbol") != symbol:
            continue

        if item.get("status") != "TRACKING":
            continue

        try:
            expires_at = datetime.fromisoformat(item.get("expires_at"))
        except Exception:
            expires_at = now

        if now > expires_at:
            item["status"] = "EXPIRED"
            item["final_outcome"] = item.get("final_outcome") or "EXPIRED"
            changed = True
            continue

        current_price, favorable, adverse = _calculate_moves(item, tick)

        if current_price is None:
            continue
        if _update_pre_w10_path_metrics(
            item,
            current_price,
        ):
            changed = True
        if _update_better_entry_counterfactuals(
            item,
            current_price,
        ):
            changed = True


        if not item.get("path_observed"):
            item["path_observed"] = True
            changed = True


        previous_favorable = float(item.get("max_favorable_usd", 0.0))
        previous_adverse = float(item.get("max_adverse_usd", 0.0))

        if favorable > previous_favorable:
            item["max_favorable_usd"] = favorable
            changed = True

        if adverse > previous_adverse:
            item["max_adverse_usd"] = adverse
            item["max_adverse_seen"] = True
            changed = True

        recovery_swing = round(
            float(item.get("max_adverse_usd", 0.0) or 0.0)
            + float(item.get("max_favorable_usd", 0.0) or 0.0),
            2,
        )

        if recovery_swing > float(item.get("max_recovery_swing_usd", 0.0) or 0.0):
            item["max_recovery_swing_usd"] = recovery_swing
            changed = True

        if (
            item.get("max_adverse_usd", 0.0) >= SETUP_OUTCOME_MIN_ADVERSE_FOR_REENTRY
            and item.get("max_recovery_swing_usd", 0.0) >= SETUP_OUTCOME_REENTRY_PROFIT_TRIGGER
            and not item.get("reentry_candidate_after_adverse")
        ):
            item["recovered_from_adverse"] = True
            item["reentry_candidate_after_adverse"] = True
            changed = True

            milestones.append({
                "event": "SETUP_OUTCOME_REENTRY_CANDIDATE",
                "setup_id": setup_id,
                "item": item.copy(),
                "current_price": current_price,
                "favorable": favorable,
                "adverse": adverse,
            })

        if favorable >= SETUP_OUTCOME_WIN_PRICE_MOVE and not item.get("hit_plus_10"):
            item["hit_plus_10"] = True
            if _freeze_pre_w10_path_metrics(item):
                changed = True
            item["time_to_plus_10_min"] = _minutes_since(item.get("created_at"))
            item["final_outcome"] = item.get("final_outcome") or "W10"
            _mark_first_hit(item, "W10")
            changed = True

            milestones.append({
                "event": "SETUP_OUTCOME_W10",
                "setup_id": setup_id,
                "item": item.copy(),
                "current_price": current_price,
                "favorable": favorable,
                "adverse": adverse,
            })

        hit_tp, hit_sl = _check_tp_sl(item, current_price)

        if hit_tp and not item.get("hit_tp"):
            item["hit_tp"] = True
            item["time_to_tp_min"] = _minutes_since(item.get("created_at"))
            item["final_outcome"] = item.get("final_outcome") or "TP_TOUCH"
            _mark_first_hit(item, "TP_TOUCH")
            changed = True

            milestones.append({
                "event": "SETUP_OUTCOME_TP_TOUCH",
                "setup_id": setup_id,
                "item": item.copy(),
                "current_price": current_price,
                "favorable": favorable,
                "adverse": adverse,
            })

        if hit_sl and not item.get("hit_sl"):
            item["hit_sl"] = True
            item["time_to_sl_min"] = _minutes_since(item.get("created_at"))
            item["final_outcome"] = item.get("final_outcome") or "SL_TOUCH"
            _mark_first_hit(item, "SL_TOUCH")
            changed = True

            milestones.append({
                "event": "SETUP_OUTCOME_SL_TOUCH",
                "setup_id": setup_id,
                "item": item.copy(),
                "current_price": current_price,
                "favorable": favorable,
                "adverse": adverse,
            })

    if changed:
        save_setup_outcomes(items)
        
        synced_setup_ids = set()

    for milestone in milestones:
        setup_id = milestone.get("setup_id")

        if not setup_id or setup_id in synced_setup_ids:
            continue

        item = items.get(setup_id)

        if not item:
            continue

        try:
            send_setup_outcome_to_google_sheets(item)
            synced_setup_ids.add(setup_id)
        except Exception as e:
            logger.error(f"[SETUP OUTCOME] Google Sheets milestone sync failed: {e}")

    return milestones
