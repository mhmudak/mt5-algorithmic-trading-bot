from __future__ import annotations

import MetaTrader5 as mt5
import pandas as pd

from config import settings
from src.daily_ladder_provider import (
    AUTO_STRONG_MODE,
    DailyLadderValidationError,
    build_auto_strong_execution_ladder,
    derive_broker_date_from_current_d1_time,
)
from src.execution import check_trade_guard
from src.indicators import calculate_atr
from src.logger import logger
from src.market_condition import detect_market_condition
from src.news_filter import is_news_blackout_active
from src.position_guard import has_same_direction_position
from src.risk import calculate_trade_plan
from src.session_engine import detect_session
from src.strategies.strategy_daily_level_ladder_reclaim_reversal import (
    STRATEGY_NAME as DLRR_STRATEGY_NAME,
    build_reversal_candidate,
    detect_closed_m5_reclaim,
    find_closed_m1_cisd_confirmation,
)
from src.time_filter import is_trading_blackout_active


def _calculate_rr_value(trade_plan):
    try:
        signal = str(trade_plan.get("signal", "")).upper()
        entry = float(trade_plan["entry_price"])
        stop = float(trade_plan["stop_loss"])
        target = float(trade_plan["take_profit"])
        risk = entry - stop if signal == "BUY" else stop - entry
        reward = target - entry if signal == "BUY" else entry - target
        if signal not in {"BUY", "SELL"} or risk <= 0 or reward <= 0:
            return None
        return round(reward / risk, 4)
    except Exception:
        return None


def process_daily_ladder_reclaim_reversal_v1(
    *,
    symbol,
    df,
    tick,
    account_info,
    execute_trade_fn,
    execution_memory_check_fn,
    log_setup_event_fn,
):
    """Execute AUTO_STRONG daily-level sweep/reclaim reversals.

    Cadence is intentionally split:
    - completed M5 arms a reclaim event;
    - every bot loop checks for a NEW closed-M1 CISD;
    - once CISD confirms, the event is one-shot even if a downstream guard blocks.
    """

    if not bool(
        getattr(
            settings,
            "ENABLE_DAILY_LEVEL_LADDER_RECLAIM_REVERSAL",
            False,
        )
    ):
        return False

    runtime = getattr(
        process_daily_ladder_reclaim_reversal_v1,
        "_runtime",
        None,
    )

    if not isinstance(runtime, dict):
        runtime = {
            "provider_key": None,
            "broker_date": None,
            "approved_ladder": None,
            "last_closed_m5_time": None,
            "pending": {},
            "consumed_setup_ids": set(),
            "last_mode_block": None,
        }
        process_daily_ladder_reclaim_reversal_v1._runtime = runtime

    execution_mode = str(
        getattr(
            settings,
            "DAILY_LEVEL_LADDER_DLLB_EXECUTION_MODE",
            AUTO_STRONG_MODE,
        )
    ).strip().upper()

    if execution_mode != AUTO_STRONG_MODE:
        mode_key = ("MODE", execution_mode)
        if runtime.get("last_mode_block") != mode_key:
            logger.info(
                "[DLRR BLOCK] reason=auto_strong_required "
                f"execution_mode={execution_mode}"
            )
            runtime["last_mode_block"] = mode_key
        return False

    runtime["last_mode_block"] = None

    d1_rates = mt5.copy_rates_from_pos(
        symbol,
        mt5.TIMEFRAME_D1,
        0,
        3,
    )
    if d1_rates is None or len(d1_rates) < 2:
        return False

    d1_df = pd.DataFrame(d1_rates)
    if "time" in d1_df.columns:
        d1_df["time"] = pd.to_datetime(
            d1_df["time"],
            unit="s",
        )

    try:
        current_d1 = d1_df.iloc[-1]
        previous_d1 = d1_df.iloc[-2]
        broker_date = derive_broker_date_from_current_d1_time(
            current_d1["time"]
        )
        approved_ladder = build_auto_strong_execution_ladder(
            symbol=symbol,
            broker_date=broker_date,
            previous_open=float(previous_d1["open"]),
            previous_high=float(previous_d1["high"]),
            previous_low=float(previous_d1["low"]),
            previous_close=float(previous_d1["close"]),
            current_open=float(current_d1["open"]),
            pivot_exclusion_range_pct=float(
                getattr(
                    settings,
                    "DAILY_LEVEL_LADDER_SHADOW_PIVOT_EXCLUSION_RANGE_PCT",
                    0.015,
                )
            ),
            cluster_range_pct=float(
                getattr(
                    settings,
                    "DAILY_LEVEL_LADDER_SHADOW_CLUSTER_RANGE_PCT",
                    0.070,
                )
            ),
        )
    except (DailyLadderValidationError, KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "[DLRR BLOCK] reason=approved_auto_strong_ladder_unavailable "
            f"error={exc}"
        )
        return False

    provider_key = (
        approved_ladder.broker_date.isoformat(),
        str(approved_ladder.source),
        round(float(approved_ladder.pivot), 5),
        tuple(round(float(value), 5) for value in approved_ladder.upper),
        tuple(round(float(value), 5) for value in approved_ladder.lower),
    )

    m5_bars = max(
        30,
        int(
            getattr(
                settings,
                "DAILY_LEVEL_LADDER_M5_BARS",
                80,
            )
        ),
    )
    m5_rates = mt5.copy_rates_from_pos(
        symbol,
        mt5.TIMEFRAME_M5,
        0,
        m5_bars,
    )
    if m5_rates is None or len(m5_rates) < 20:
        return False

    m5_df = pd.DataFrame(m5_rates)
    m5_df["time"] = pd.to_datetime(
        m5_df["time"],
        unit="s",
    )
    m5_df["atr_14"] = calculate_atr(
        m5_df,
        settings.ATR_PERIOD,
    )

    latest_closed_m5 = m5_df.iloc[-2]
    previous_closed_m5 = m5_df.iloc[-3]
    latest_closed_m5_time = pd.Timestamp(
        latest_closed_m5["time"]
    )

    if runtime.get("provider_key") != provider_key:
        runtime["provider_key"] = provider_key
        runtime["broker_date"] = approved_ladder.broker_date.isoformat()
        runtime["approved_ladder"] = approved_ladder
        runtime["pending"] = {}
        runtime["consumed_setup_ids"] = set()
        runtime["last_closed_m5_time"] = latest_closed_m5_time
        logger.info(
            "[DLRR ARM] AUTO_STRONG provider armed on latest closed M5; "
            "no retroactive execution "
            f"| broker_date={approved_ladder.broker_date.isoformat()} "
            f"m5={latest_closed_m5_time}"
        )
        return False

    runtime["approved_ladder"] = approved_ladder

    if runtime.get("last_closed_m5_time") is None:
        runtime["last_closed_m5_time"] = latest_closed_m5_time
        logger.info(
            "[DLRR ARM] startup armed on latest closed M5; "
            f"no retroactive execution | m5={latest_closed_m5_time}"
        )
        return False

    if latest_closed_m5_time != runtime.get("last_closed_m5_time"):
        runtime["last_closed_m5_time"] = latest_closed_m5_time

        atr = latest_closed_m5.get("atr_14")
        try:
            atr = float(atr)
        except Exception:
            atr = None

        reclaim = detect_closed_m5_reclaim(
            previous_bar=previous_closed_m5,
            current_bar=latest_closed_m5,
            approved_ladder=approved_ladder,
            atr=atr,
            minimum_sweep_usd=float(
                getattr(
                    settings,
                    "DAILY_LEVEL_LADDER_RECLAIM_REVERSAL_MIN_SWEEP_USD",
                    0.10,
                )
            ),
            atr_sweep_fraction=float(
                getattr(
                    settings,
                    "DAILY_LEVEL_LADDER_RECLAIM_REVERSAL_ATR_SWEEP_FRACTION",
                    0.03,
                )
            ),
        )

        if isinstance(reclaim, dict):
            reclaim_key = (
                f"{approved_ladder.broker_date.isoformat()}|"
                f"{reclaim.get('signal')}|"
                f"{round(float(reclaim.get('level')), 5)}|"
                f"{latest_closed_m5_time}"
            )

            if reclaim_key not in runtime["pending"]:
                armed_after = (
                    latest_closed_m5_time
                    + pd.Timedelta(minutes=5)
                )
                timeout_minutes = int(
                    getattr(
                        settings,
                        "DAILY_LEVEL_LADDER_RECLAIM_REVERSAL_CISD_TIMEOUT_MINUTES",
                        20,
                    )
                )
                pending = {
                    **reclaim,
                    "reclaim_m5_time": str(latest_closed_m5_time),
                    "reclaim_atr": atr,
                    "armed_after": str(armed_after),
                    "expires_after": str(
                        armed_after
                        + pd.Timedelta(minutes=timeout_minutes)
                    ),
                }
                runtime["pending"][reclaim_key] = pending
                logger.info(
                    "[DLRR RECLAIM] waiting_for_closed_m1_cisd "
                    f"signal={pending.get('signal')} "
                    f"level={pending.get('level')} "
                    f"side={pending.get('level_side')} "
                    f"sweep_extreme={pending.get('sweep_extreme')} "
                    f"reclaim_close={pending.get('reclaim_close')} "
                    f"m5={pending.get('reclaim_m5_time')} "
                    f"armed_after={pending.get('armed_after')}"
                )

    if not runtime.get("pending"):
        return False

    m1_bars = max(
        40,
        int(
            getattr(
                settings,
                "DAILY_LEVEL_LADDER_RECLAIM_REVERSAL_M1_BARS",
                120,
            )
        ),
    )
    # start_pos=1 excludes the forming M1 candle.
    m1_rates = mt5.copy_rates_from_pos(
        symbol,
        mt5.TIMEFRAME_M1,
        1,
        m1_bars,
    )
    if m1_rates is None or len(m1_rates) < 3:
        return False

    m1_df = pd.DataFrame(m1_rates)
    m1_df["time"] = pd.to_datetime(
        m1_df["time"],
        unit="s",
    )
    m1_df = m1_df.sort_values("time").reset_index(drop=True)
    latest_closed_m1_time = pd.Timestamp(
        m1_df.iloc[-1]["time"]
    )

    for reclaim_key, pending in list(runtime["pending"].items()):
        expires_after = pd.Timestamp(pending["expires_after"])

        if latest_closed_m1_time > expires_after:
            logger.info(
                "[DLRR BLOCK] reason=cisd_timeout "
                f"signal={pending.get('signal')} "
                f"level={pending.get('level')} "
                f"reclaim_m5={pending.get('reclaim_m5_time')}"
            )
            del runtime["pending"][reclaim_key]
            continue

        cisd = find_closed_m1_cisd_confirmation(
            m1_df=m1_df,
            signal=pending.get("signal"),
            armed_after=pending.get("armed_after"),
        )
        if cisd is None:
            continue

        del runtime["pending"][reclaim_key]

        try:
            atr = float(pending.get("reclaim_atr"))
        except Exception:
            atr = None

        minimum_rr = float(
            getattr(
                settings,
                "DAILY_LEVEL_LADDER_RECLAIM_REVERSAL_MIN_RR",
                1.20,
            )
        )
        candidate = build_reversal_candidate(
            pending=pending,
            cisd=cisd,
            approved_ladder=approved_ladder,
            atr=atr,
            minimum_rr=minimum_rr,
        )

        if not isinstance(candidate, dict):
            logger.info(
                "[DLRR BLOCK] reason=candidate_geometry_invalid "
                f"signal={pending.get('signal')} "
                f"level={pending.get('level')}"
            )
            return False

        setup_id = candidate.get("setup_id")
        consumed = runtime.get("consumed_setup_ids")
        if not isinstance(consumed, set):
            consumed = set()
            runtime["consumed_setup_ids"] = consumed

        if setup_id in consumed:
            logger.info(
                "[DLRR BLOCK] reason=duplicate_setup "
                f"setup_id={setup_id}"
            )
            return False

        # Confirmation is one-shot. Any later downstream rejection must not
        # chase this old reclaim/CISD at a materially different market price.
        consumed.add(setup_id)

        signal = candidate.get("signal")
        runtime_entry = (
            float(tick.ask)
            if signal == "BUY"
            else float(tick.bid)
        )

        logger.info(
            "[DLRR CANDIDATE] "
            f"setup_id={setup_id} "
            f"direction={signal} "
            f"strong_level={candidate.get('strong_level')} "
            f"reclaim_m5={candidate.get('reclaim_m5_time')} "
            f"cisd_m1={candidate.get('cisd_confirmation_time')} "
            f"cisd_entry={candidate.get('entry_reference')} "
            f"runtime_entry={round(runtime_entry, 2)} "
            f"sl={candidate.get('sl_reference')} "
            f"tp={candidate.get('tp_reference')}"
        )

        try:
            candidate_sl = float(candidate["sl_reference"])
            candidate_tp = float(candidate["tp_reference"])
            runtime_geometry_ok = (
                candidate_sl < runtime_entry < candidate_tp
                if signal == "BUY"
                else candidate_tp < runtime_entry < candidate_sl
            )
        except Exception:
            runtime_geometry_ok = False

        if not runtime_geometry_ok:
            logger.info(
                "[DLRR BLOCK] reason=runtime_price_outside_authoritative_geometry "
                f"setup_id={setup_id} "
                f"runtime_entry={round(runtime_entry, 2)} "
                f"sl={candidate.get('sl_reference')} "
                f"tp={candidate.get('tp_reference')}"
            )
            return False

        try:
            session_name = detect_session(
                pd.Timestamp(candidate.get("cisd_confirmation_time"))
            )
        except Exception:
            session_name = "UNKNOWN"

        try:
            market_condition = detect_market_condition(df)
        except Exception:
            market_condition = "UNKNOWN"

        candidate["session"] = session_name
        candidate["market_condition"] = market_condition

        trade_plan = calculate_trade_plan(
            df=m5_df,
            signal=signal,
            tick=tick,
            account_balance=account_info.balance,
            signal_data=candidate,
        )
        if not isinstance(trade_plan, dict):
            logger.info(
                "[DLRR BLOCK] reason=trade_plan_invalid "
                f"setup_id={setup_id}"
            )
            return False

        try:
            geometry_preserved = (
                round(float(trade_plan.get("stop_loss")), 2)
                == round(float(candidate.get("sl_reference")), 2)
                and round(float(trade_plan.get("take_profit")), 2)
                == round(float(candidate.get("tp_reference")), 2)
            )
        except Exception:
            geometry_preserved = False

        if not geometry_preserved:
            logger.warning(
                "[DLRR BLOCK] reason=authoritative_geometry_not_preserved "
                f"setup_id={setup_id} "
                f"expected_sl={candidate.get('sl_reference')} "
                f"actual_sl={trade_plan.get('stop_loss')} "
                f"expected_tp={candidate.get('tp_reference')} "
                f"actual_tp={trade_plan.get('take_profit')}"
            )
            return False

        for key in (
            "score",
            "strategy",
            "entry_model",
            "sl_model",
            "tp_model",
            "reason",
            "daily_approved_source",
            "daily_broker_date",
            "daily_pivot",
            "strong_level",
            "level_side",
            "reclaim_mode",
            "reclaim_m5_time",
            "reclaim_close",
            "sweep_extreme",
            "cisd_reference_time",
            "cisd_confirmation_time",
            "position_management_mode",
            "tp_authority",
        ):
            trade_plan[key] = candidate.get(key)

        trade_plan["session"] = session_name
        trade_plan["market_condition"] = market_condition
        trade_plan["setup_id"] = setup_id
        trade_plan["strategy_geometry_authoritative"] = True
        trade_plan["broker_take_profit"] = float(
            candidate["tp_reference"]
        )
        trade_plan["main_tp_ladder_managed"] = False
        trade_plan["main_runner_after_tp3"] = False

        rr_value = _calculate_rr_value(trade_plan)
        trade_plan["rr"] = rr_value
        trade_plan["risk_reward"] = rr_value

        logger.info(
            "[DLRR RR] "
            f"setup_id={setup_id} "
            f"rr={rr_value} required={minimum_rr} "
            f"reference_rr={candidate.get('rr_reference')}"
        )

        if rr_value is None or float(rr_value) < minimum_rr:
            logger.info(
                "[DLRR BLOCK] reason=minimum_rr "
                f"setup_id={setup_id} rr={rr_value} required={minimum_rr}"
            )
            return False

        news_blocked, news_reason = is_news_blackout_active()
        if news_blocked:
            logger.info(
                "[DLRR BLOCK] reason=news_blackout "
                f"setup_id={setup_id} detail={news_reason}"
            )
            return False

        time_blocked, time_reason = is_trading_blackout_active()
        if time_blocked:
            logger.info(
                "[DLRR BLOCK] reason=time_blackout "
                f"setup_id={setup_id} detail={time_reason}"
            )
            return False

        trade_allowed, guard_reason = check_trade_guard(
            signal,
            tick,
        )
        if not trade_allowed:
            logger.info(
                "[DLRR BLOCK] reason=trade_guard "
                f"setup_id={setup_id} detail={guard_reason}"
            )
            return False

        opposite = "SELL" if signal == "BUY" else "BUY"
        if has_same_direction_position(symbol, opposite):
            logger.info(
                "[DLRR BLOCK] reason=opposite_position_exists "
                f"setup_id={setup_id}"
            )
            return False

        memory_blocked, memory_reason = (
            execution_memory_check_fn(
                strategy_name=DLRR_STRATEGY_NAME,
                signal=signal,
                session_name=session_name,
                market_condition=market_condition,
                setup_id=setup_id,
                entry_model=candidate.get("entry_model"),
                trade_plan=trade_plan,
                signal_data=candidate,
            )
        )
        if memory_blocked:
            logger.info(
                "[DLRR BLOCK] reason=execution_memory "
                f"setup_id={setup_id} detail={memory_reason}"
            )
            return False

        logger.info(
            "[DLRR EXECUTION ATTEMPT] "
            f"setup_id={setup_id} signal={signal} "
            f"level={candidate.get('strong_level')} "
            f"entry={trade_plan.get('entry_price')} "
            f"sl={trade_plan.get('stop_loss')} "
            f"tp={trade_plan.get('take_profit')} "
            f"rr={rr_value}"
        )

        try:
            log_setup_event_fn(
                setup_id=setup_id,
                event="DAILY_LADDER_RECLAIM_REVERSAL_EXECUTION_ATTEMPT",
                strategy=DLRR_STRATEGY_NAME,
                signal=signal,
                entry_model=candidate.get("entry_model"),
                score=candidate.get("score"),
                session=session_name,
                market_condition=market_condition,
                entry=trade_plan.get("entry_price"),
                sl=trade_plan.get("stop_loss"),
                tp=trade_plan.get("take_profit"),
                rr=rr_value,
                required_rr=minimum_rr,
                reason=candidate.get("reason"),
                extra={
                    "strong_level": candidate.get("strong_level"),
                    "reclaim_m5_time": candidate.get("reclaim_m5_time"),
                    "cisd_confirmation_time": candidate.get("cisd_confirmation_time"),
                    "daily_approved_source": candidate.get("daily_approved_source"),
                },
            )
        except Exception as exc:
            logger.warning(
                "[DLRR] setup audit failed open "
                f"| setup_id={setup_id} error={exc}"
            )

        executed = execute_trade_fn(
            signal,
            trade_plan,
            symbol,
        )

        if not executed:
            logger.info(
                "[DLRR EXECUTION FAILED] "
                "reason=execute_trade_returned_false "
                f"setup_id={setup_id}"
            )
            return False

        logger.info(
            "[DLRR EXECUTED] "
            f"setup_id={setup_id} direction={signal} "
            f"entry={trade_plan.get('entry_price')} "
            f"sl={trade_plan.get('stop_loss')} "
            f"tp={trade_plan.get('take_profit')}"
        )

        try:
            log_setup_event_fn(
                setup_id=setup_id,
                event="DAILY_LADDER_RECLAIM_REVERSAL_EXECUTED",
                strategy=DLRR_STRATEGY_NAME,
                signal=signal,
                entry_model=candidate.get("entry_model"),
                score=candidate.get("score"),
                session=session_name,
                market_condition=market_condition,
                entry=trade_plan.get("entry_price"),
                sl=trade_plan.get("stop_loss"),
                tp=trade_plan.get("take_profit"),
                rr=rr_value,
                required_rr=minimum_rr,
                reason=candidate.get("reason"),
            )
        except Exception as exc:
            logger.warning(
                "[DLRR] executed audit failed open "
                f"| setup_id={setup_id} error={exc}"
            )

        return True

    return False
