import json
import time
from datetime import datetime, timedelta

import MetaTrader5 as mt5

from src.logger import logger
from src.notifier import send_telegram_message
from src.setup_audit import log_setup_event
from src.setup_outcome_reconciler import reconcile_setup_outcome_from_closed_trade
from config.settings import (
    ENABLE_COOLDOWN_AFTER_SL,
    COOLDOWN_AFTER_SL_MINUTES,
    TELEGRAM_NOTIFY_TRADE_TRACKER_OPENED,
)

from src.account_context import get_account_file

def get_tracker_file():
    return get_account_file("trades.json")
TRACKED_LEVELS = [3, 5, 8, 12, 18, 28]

cooldown_until = None


def load_trades():
    tracker_file = get_tracker_file()

    if not tracker_file.exists():
        return {}

    try:
        with open(tracker_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[TRACKER] Failed to load trades: {e}")
        return {}


def save_trades(trades):
    tracker_file = get_tracker_file()

    try:
        tracker_file.parent.mkdir(parents=True, exist_ok=True)
        with open(tracker_file, "w", encoding="utf-8") as f:
            json.dump(trades, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[TRACKER] Failed to save trades: {e}")

def _first_mt5_item(items):
    if not items:
        return None

    try:
        return items[0]
    except Exception:
        return None


def _safe_ticket_int(value):
    try:
        value = int(value)
    except Exception:
        return None

    if value <= 0:
        return None

    return value


def resolve_trade_position_id_from_history(
    position_id,
    trade,
):
    """
    Resolve the real MT5 position identifier from
    authoritative stored execution deal/order tickets.

    This never guesses from side, volume, entry price,
    recency, or another open position.
    """
    if not isinstance(
        trade,
        dict,
    ):
        return str(position_id), None

    seen = set()

    for field in (
        "raw_deal_id",
        "deal_id",
    ):
        ticket = _safe_ticket_int(
            trade.get(field)
        )

        key = (
            "DEAL",
            ticket,
        )

        if (
            ticket is None
            or key in seen
        ):
            continue

        seen.add(key)

        try:
            deal = _first_mt5_item(
                mt5.history_deals_get(
                    ticket=ticket
                )
            )
        except Exception as exc:
            logger.warning(
                "[TRACKER] direct deal identity "
                f"lookup failed | ticket={ticket} "
                f"error={exc}"
            )
            deal = None

        if deal is not None:
            real_position_id = getattr(
                deal,
                "position_id",
                None,
            )

            if real_position_id:
                return (
                    str(real_position_id),
                    f"DIRECT_{field.upper()}",
                )

    for field in (
        "raw_order_id",
        "order_id",
    ):
        ticket = _safe_ticket_int(
            trade.get(field)
        )

        key = (
            "ORDER",
            ticket,
        )

        if (
            ticket is None
            or key in seen
        ):
            continue

        seen.add(key)

        try:
            order = _first_mt5_item(
                mt5.history_orders_get(
                    ticket=ticket
                )
            )
        except Exception as exc:
            logger.warning(
                "[TRACKER] direct order identity "
                f"lookup failed | ticket={ticket} "
                f"error={exc}"
            )
            order = None

        if order is not None:
            real_position_id = getattr(
                order,
                "position_id",
                None,
            )

            if real_position_id:
                return (
                    str(real_position_id),
                    f"DIRECT_{field.upper()}",
                )

    return str(position_id), None


def resolve_position_id_after_execution(
    symbol,
    signal,
    trade_plan,
    result,
):
    """
    Resolve the real MT5 position ticket after order_send.

    Identity authority, in order:
      1. exact physical position ticket
      2. exact execution deal -> position_id
      3. exact execution order -> position_id
      4. open position whose MT5 identifier matches order id

    MT5 history can lag briefly after order_send, so the
    exact checks are retried for a short bounded period.

    Never select the "newest same-side/same-volume" position:
    that can attach a new execution to an unrelated trade.
    """
    order_id = getattr(
        result,
        "order",
        None,
    )

    deal_id = getattr(
        result,
        "deal",
        None,
    )

    order_ticket = _safe_ticket_int(
        order_id
    )

    identity_trade = {
        "deal_id": deal_id,
        "raw_deal_id": deal_id,
        "order_id": order_id,
        "raw_order_id": order_id,
    }

    max_attempts = 4

    for attempt in range(
        max_attempts
    ):
        # Exact physical ticket lookup.
        if order_ticket is not None:
            try:
                positions = mt5.positions_get(
                    ticket=order_ticket
                )
            except Exception as exc:
                logger.warning(
                    "[TRACKER] exact physical "
                    "position lookup failed | "
                    f"order={order_id} error={exc}"
                )
                positions = None

            position = _first_mt5_item(
                positions
            )

            if position is not None:
                return str(
                    position.ticket
                )

        # Exact deal/order history identity.
        (
            history_position_id,
            history_source,
        ) = (
            resolve_trade_position_id_from_history(
                position_id=(
                    order_id
                    if order_id
                    else deal_id
                ),
                trade=identity_trade,
            )
        )

        if history_source:
            logger.info(
                "[TRACKER] execution position "
                "resolved from authoritative history | "
                f"position={history_position_id} "
                f"source={history_source}"
            )

            return history_position_id

        # Exact MT5 position identifier match.
        # This is not a side/volume/recency guess.
        try:
            open_positions = (
                mt5.positions_get(
                    symbol=symbol
                )
            )
        except Exception as exc:
            logger.warning(
                "[TRACKER] execution open-position "
                f"identity scan failed | "
                f"symbol={symbol} error={exc}"
            )
            open_positions = None

        if (
            open_positions
            and order_ticket is not None
        ):
            for position in open_positions:
                try:
                    ticket = int(
                        getattr(
                            position,
                            "ticket",
                            0,
                        )
                        or 0
                    )

                    identifier = int(
                        getattr(
                            position,
                            "identifier",
                            0,
                        )
                        or 0
                    )
                except Exception:
                    continue

                if (
                    ticket == order_ticket
                    or identifier
                    == order_ticket
                ):
                    return str(ticket)

        if attempt < (
            max_attempts - 1
        ):
            time.sleep(0.05)

    # Fail-safe identity fallback:
    # keep the execution's own order/deal identity rather
    # than attaching it to an unrelated physical position.
    fallback_id = (
        order_id
        if order_id
        else deal_id
    )

    logger.warning(
        "[TRACKER] Real MT5 position id was not "
        "confirmed during bounded execution retry | "
        f"fallback={fallback_id} "
        f"order={order_id} deal={deal_id} | "
        "NO side/volume/recency position guess used"
    )

    return str(fallback_id)

def relink_trade_position_if_needed(position_id, trade, open_positions_map):
    """
    Fix old trades saved with result.order/result.deal instead of real MT5 position ticket.
    If we can find the real open position, return the new real position_id.
    """
    if position_id in open_positions_map:
        return position_id

    symbol = trade.get("symbol")
    signal = str(trade.get("signal") or "").upper()
    expected_volume = round(float(trade.get("remaining_volume", trade.get("initial_volume", 0.0)) or 0.0), 2)

    if not symbol or signal not in ["BUY", "SELL"]:
        return position_id

    expected_type = mt5.POSITION_TYPE_BUY if signal == "BUY" else mt5.POSITION_TYPE_SELL

    candidates = []

    for real_position_id, position in open_positions_map.items():
        if getattr(position, "symbol", None) != symbol:
            continue

        if getattr(position, "type", None) != expected_type:
            continue

        position_volume = round(float(getattr(position, "volume", 0.0)), 2)

        if expected_volume and position_volume != expected_volume:
            continue

        trade_entry = round(float(trade.get("entry_price", 0.0) or 0.0), 2)
        position_entry = round(float(getattr(position, "price_open", 0.0) or 0.0), 2)

        if trade_entry and abs(trade_entry - position_entry) > 1.0:
            continue

        candidates.append((real_position_id, position))

    if not candidates:
        return position_id

    real_position_id, position = max(
        candidates,
        key=lambda item: getattr(item[1], "time_msc", getattr(item[1], "time", 0)),
    )

    logger.warning(
        f"[TRACKER] Relinked legacy trade position id | "
        f"old={position_id} new={real_position_id} "
        f"symbol={symbol} signal={signal}"
    )

    return real_position_id

def activate_cooldown():
    global cooldown_until

    if not ENABLE_COOLDOWN_AFTER_SL:
        return

    cooldown_until = datetime.now() + timedelta(minutes=COOLDOWN_AFTER_SL_MINUTES)
    logger.info(f"[TRACKER] Cooldown activated until {cooldown_until.isoformat()}")

    send_telegram_message(
        f"Cooldown Activated\n"
        f"Reason: Stop loss hit\n"
        f"Duration: {COOLDOWN_AFTER_SL_MINUTES} minutes\n"
        f"Until: {cooldown_until.strftime('%H:%M:%S')}"
    )


def is_cooldown_active():
    global cooldown_until

    if cooldown_until is None:
        return False

    return datetime.now() < cooldown_until


def _build_trade_record(
    *,
    position_id,
    main_position_id,
    trade_role,
    setup_id="N/A",
    entry_model=None,
    symbol,
    signal,
    entry_price,
    stop_loss,
    take_profit,
    initial_volume,
    remaining_volume,
    deal_id,
    order_id,
    imported_manually=False,
    setup_score=0,
    strategy_name="UNKNOWN",
    market_condition="UNKNOWN",
    session=None,
    reason="N/A",
    tp_buffer=0.0,
):
    return {
        "position_id": str(position_id),
        "main_position_id": str(main_position_id),
        "trade_role": trade_role,
        "setup_id": setup_id,
        "entry_model": entry_model,
        "symbol": symbol,
        "signal": signal,
        "entry_price": float(entry_price),
        "stop_loss": float(stop_loss) if stop_loss is not None else 0.0,
        "take_profit": float(take_profit) if take_profit is not None else 0.0,
        "initial_volume": float(initial_volume),
        "remaining_volume": float(remaining_volume),
        "closed_volume": 0.0,
        "status": "OPEN",
        "open_time": datetime.now().isoformat(),
        "deal_id": deal_id,
        "order_id": order_id,
        "raw_deal_id": deal_id,
        "raw_order_id": order_id,
        "partial_closes": [],
        "stage_1_done": False,
        "stage_2_done": False,
        "stage_3_done": False,
        "runner_mode_active": False,
        "runner_tp_removed": False,
        "runner_started_at": None,
        "imported_manually": imported_manually,
        "setup_score": float(setup_score),
        "strategy": strategy_name,
        "market_condition": market_condition,
        "session": session,
        "reason": reason,
        "tp_buffer": float(tp_buffer),
        "max_profit_price": 0.0,
        "reached_levels": {str(level): False for level in TRACKED_LEVELS},
        "final_result": None,
        "close_reason": None,
    }


def _find_open_main_trade_id(trades, symbol, signal):
    for position_id, trade in trades.items():
        if (
            trade.get("symbol") == symbol
            and trade.get("signal") == signal
            and trade.get("status") == "OPEN"
            and trade.get("trade_role") == "MAIN"
        ):
            return position_id
    return None


def _resolve_execution_trade_role(
    trades,
    symbol,
    signal,
    position_id,
    trade_plan,
):
    """
    New trades may carry an explicit role frozen from
    physical MT5 state immediately before execution.

    Explicit role wins over stale tracker state.

    Legacy trades without the contract retain the old
    tracker-based MAIN/EXTRA behavior.
    """
    existing_main_id = (
        _find_open_main_trade_id(
            trades,
            symbol,
            signal,
        )
    )

    explicit_role = str(
        trade_plan.get(
            "execution_trade_role",
            "",
        )
        or ""
    ).upper()

    if explicit_role == "MAIN":
        return (
            "MAIN",
            position_id,
            True,
        )

    if explicit_role == "EXTRA":
        return (
            "EXTRA",
            (
                existing_main_id
                or "UNTRACKED_PHYSICAL_MAIN"
            ),
            True,
        )

    if existing_main_id is None:
        return (
            "MAIN",
            position_id,
            False,
        )

    return (
        "EXTRA",
        existing_main_id,
        False,
    )


def register_executed_trade(symbol, signal, trade_plan, result):
    trades = load_trades()

    position_id = resolve_position_id_after_execution(
        symbol=symbol,
        signal=signal,
        trade_plan=trade_plan,
        result=result,
    )

    (
        trade_role,
        main_position_id,
        role_locked,
    ) = _resolve_execution_trade_role(
        trades,
        symbol,
        signal,
        position_id,
        trade_plan,
    )

    trades[position_id] = _build_trade_record(
        position_id=position_id,
        main_position_id=main_position_id,
        trade_role=trade_role,
        setup_id=trade_plan.get("setup_id", "N/A"),
        entry_model=trade_plan.get("entry_model"),
        symbol=symbol,
        signal=signal,
        entry_price=trade_plan["entry_price"],
        stop_loss=trade_plan["stop_loss"],
        take_profit=trade_plan["take_profit"],
        initial_volume=trade_plan["lot"],
        remaining_volume=trade_plan["lot"],
        deal_id=result.deal,
        order_id=result.order,
        imported_manually=False,
        setup_score=trade_plan.get("score", 0),
        strategy_name=trade_plan.get("strategy", "UNKNOWN"),
        market_condition=trade_plan.get("market_condition", "UNKNOWN"),
        session=trade_plan.get("session"),
        reason=trade_plan.get("reason", "N/A"),
        tp_buffer=trade_plan.get("tp_buffer", 0.0),
    )

    tracked_trade = trades[
        position_id
    ]

    tracked_trade[
        "main_tp_ladder_managed"
    ] = bool(
        trade_plan.get(
            "main_tp_ladder_managed",
            False,
        )
    )

    tracked_trade[
        "main_tp_ladder_role"
    ] = trade_plan.get(
        "main_tp_ladder_role"
    )

    tracked_trade[
        "trade_role_locked"
    ] = bool(
        role_locked
    )

    tracked_trade[
        "execution_role_authority"
    ] = trade_plan.get(
        "execution_role_authority",
        "TRACKER_OPEN_MAIN_FALLBACK",
    )

    tracked_trade[
        "execution_same_direction_count"
    ] = trade_plan.get(
        "execution_same_direction_count"
    )

    tracked_trade[
        "main_tp1"
    ] = trade_plan.get(
        "main_tp1"
    )

    tracked_trade[
        "main_tp2"
    ] = trade_plan.get(
        "main_tp2"
    )

    tracked_trade[
        "main_tp3"
    ] = trade_plan.get(
        "main_tp3"
    )

    tracked_trade[
        "tp_ladder"
    ] = trade_plan.get(
        "tp_ladder"
    )

    tracked_trade[
        "decision_take_profit"
    ] = trade_plan.get(
        "decision_take_profit",
        trade_plan.get(
            "take_profit"
        ),
    )

    tracked_trade[
        "broker_take_profit"
    ] = trade_plan.get(
        "broker_take_profit",
        trade_plan.get(
            "take_profit"
        ),
    )

    tracked_trade[
        "main_runner_after_tp3"
    ] = bool(
        trade_plan.get(
            "main_runner_after_tp3",
            False,
        )
    )

    tracked_trade[
        "tp_management_mode"
    ] = trade_plan.get(
        "tp_management_mode"
    )

    tracked_trade[
        "runner_tp2_lock_done"
    ] = False

    tracked_trade[
        "runner_tp3_lock_done"
    ] = False

    save_trades(trades)

    logger.info(f"[TRACKER] Registered trade {position_id} as {trade_role}")

    if TELEGRAM_NOTIFY_TRADE_TRACKER_OPENED:
        send_telegram_message(
            f"Trade Opened\n"
            f"Position: {position_id}\n"
            f"Setup ID: {trade_plan.get('setup_id', 'N/A')}\n"
            f"Role: {trade_role}\n"
            f"Main Position: {main_position_id}\n"
            f"Symbol: {symbol}\n"
            f"Side: {signal}\n"
            f"Strategy: {trade_plan.get('strategy', 'UNKNOWN')}\n"
            f"Market: {trade_plan.get('market_condition', 'UNKNOWN')}\n"
            f"Reason: {trade_plan.get('reason', 'N/A')}\n"
            f"Volume: {trade_plan['lot']}\n"
            f"Entry: {trade_plan['entry_price']}\n"
            f"SL: {trade_plan['stop_loss']}\n"
            f"TP: {trade_plan['take_profit']}\n"
            f"TP Buffer: {trade_plan.get('tp_buffer', 0.0)}\n"
            f"Setup Score: {trade_plan.get('score', 0)}"
        )


def update_trade_statistics(position, trade, tick):
    entry_price = position.price_open

    if position.type == mt5.POSITION_TYPE_BUY:
        current_price = tick.bid
        price_profit = current_price - entry_price
    else:
        current_price = tick.ask
        price_profit = entry_price - current_price

    previous_max = float(trade.get("max_profit_price", 0.0))
    trade["max_profit_price"] = round(max(previous_max, price_profit), 2)

    reached_levels = trade.get("reached_levels", {})
    for level in TRACKED_LEVELS:
        if price_profit >= level:
            reached_levels[str(level)] = True

    trade["reached_levels"] = reached_levels


def classify_stop_trigger_result(realized_profit, prefix="SL"):
    try:
        profit = float(realized_profit or 0.0)
    except Exception:
        profit = 0.0

    if profit > 0:
        return f"{prefix}_IN_PROFIT"

    if profit < 0:
        return f"{prefix}_LOSS"

    return f"{prefix}_BREAKEVEN"


def infer_close_reason_from_trade(trade, close_price, realized_profit):
    if trade is None:
        if realized_profit > 0:
            return "PROFIT_CLOSE"

        if realized_profit < 0:
            return "LOSS_CLOSE"

        return "OTHER"

    stop_loss = float(trade.get("stop_loss", 0.0) or 0.0)
    take_profit = float(trade.get("take_profit", 0.0) or 0.0)

    tolerance = 0.50

    if stop_loss > 0 and abs(close_price - stop_loss) <= tolerance:
        return classify_stop_trigger_result(realized_profit, prefix="SL_LIKELY")

    if take_profit > 0 and abs(close_price - take_profit) <= tolerance:
        return "TP_LIKELY"

    if realized_profit > 0:
        return "PROFIT_CLOSE"

    if realized_profit < 0:
        return "LOSS_CLOSE"

    return "BREAKEVEN"

def detect_close_details(
    position_id: str,
    trade=None,
):
    """
    Resolve closing deals from the authoritative MT5
    position identifier.

    Direct position history is preferred because broad
    date-range history queries can omit deals that MT5
    returns correctly through history_deals_get(position=).
    """
    empty = {
        "found_close_deal": False,
        "close_reason": None,
        "realized_profit": 0.0,
        "close_price": 0.0,
        "close_time": None,
    }

    position_id_int = _safe_ticket_int(
        position_id
    )

    if position_id_int is None:
        return empty

    closing_entry_types = {
        mt5.DEAL_ENTRY_OUT,
    }

    deal_entry_inout = getattr(
        mt5,
        "DEAL_ENTRY_INOUT",
        None,
    )

    if deal_entry_inout is not None:
        closing_entry_types.add(
            deal_entry_inout
        )

    deal_entry_out_by = getattr(
        mt5,
        "DEAL_ENTRY_OUT_BY",
        None,
    )

    if deal_entry_out_by is not None:
        closing_entry_types.add(
            deal_entry_out_by
        )

    # --------------------------------------------------------
    # Primary authority: direct MT5 position history
    # --------------------------------------------------------

    try:
        direct_deals = (
            mt5.history_deals_get(
                position=position_id_int
            )
        )
    except Exception as exc:
        logger.warning(
            "[TRACKER] direct position history "
            f"lookup failed | "
            f"position={position_id} error={exc}"
        )
        direct_deals = None

    matching_deals = (
        list(direct_deals)
        if direct_deals
        else []
    )

    closing_deals = [
        deal
        for deal in matching_deals
        if getattr(
            deal,
            "entry",
            None,
        )
        in closing_entry_types
    ]

    # --------------------------------------------------------
    # Legacy fallback only if direct position history did
    # not expose a closing deal.
    # --------------------------------------------------------

    if not closing_deals:
        now = datetime.now()
        start = now - timedelta(
            days=7
        )

        try:
            broad_deals = (
                mt5.history_deals_get(
                    start,
                    now,
                )
            )
        except Exception as exc:
            logger.warning(
                "[TRACKER] fallback broad history "
                f"lookup failed | "
                f"position={position_id} error={exc}"
            )
            broad_deals = None

        broad_matching = [
            deal
            for deal in (
                broad_deals
                or []
            )
            if getattr(
                deal,
                "position_id",
                None,
            )
            == position_id_int
        ]

        broad_closes = [
            deal
            for deal in broad_matching
            if getattr(
                deal,
                "entry",
                None,
            )
            in closing_entry_types
        ]

        if broad_closes:
            matching_deals = (
                broad_matching
            )

            closing_deals = (
                broad_closes
            )

    if not closing_deals:
        return empty

    latest_deal = max(
        closing_deals,
        key=lambda d: getattr(
            d,
            "time",
            0,
        ),
    )

    reason = getattr(
        latest_deal,
        "reason",
        None,
    )

    close_price = float(
        getattr(
            latest_deal,
            "price",
            0.0,
        )
    )

    realized_profit = sum(
        float(
            getattr(
                deal,
                "profit",
                0.0,
            )
        )
        for deal in closing_deals
    )

    if reason == mt5.DEAL_REASON_SL:
        close_reason = (
            classify_stop_trigger_result(
                realized_profit,
                prefix="SL",
            )
        )

    elif reason == mt5.DEAL_REASON_TP:
        close_reason = "TP"

    elif reason == mt5.DEAL_REASON_SO:
        close_reason = "STOP_OUT"

    else:
        close_reason = (
            infer_close_reason_from_trade(
                trade=trade,
                close_price=close_price,
                realized_profit=realized_profit,
            )
        )

    close_timestamp = getattr(
        latest_deal,
        "time",
        None,
    )

    close_time = None

    if close_timestamp:
        try:
            close_time = (
                datetime.fromtimestamp(
                    close_timestamp
                ).isoformat()
            )
        except Exception:
            close_time = None

    return {
        "found_close_deal": True,
        "close_reason": close_reason,
        "realized_profit": round(
            realized_profit,
            2,
        ),
        "close_price": round(
            close_price,
            2,
        ),
        "close_time": close_time,
    }


def update_trade_lifecycle(symbol: str):
    trades = load_trades()
    if not trades:
        logger.info("[TRACKER] No tracked trades")
        return

    open_positions = mt5.positions_get(symbol=symbol)

    if open_positions is None:
        logger.warning(f"[TRACKER] positions_get returned None for {symbol}; lifecycle update skipped")
        return

    open_positions_map = {}

    for pos in open_positions:
        open_positions_map[str(pos.ticket)] = pos

    changed = False

    for position_id, trade in list(trades.items()):
        if trade.get("symbol") != symbol:
            continue

        if trade.get("status") == "CLOSED":
            continue

        tracked_remaining = float(trade.get("remaining_volume", 0.0))
        current_position = open_positions_map.get(position_id)

        if current_position is None:
            (
                history_position_id,
                history_source,
            ) = (
                resolve_trade_position_id_from_history(
                    position_id=position_id,
                    trade=trade,
                )
            )

            # Authoritative MT5 execution history wins.
            if history_source:
                if (
                    history_position_id
                    != position_id
                ):
                    if history_position_id in trades:
                        trade[
                            "position_relink_collision"
                        ] = history_position_id

                        logger.error(
                            "[TRACKER] Historical position "
                            "identity collision; relink skipped | "
                            f"old={position_id} "
                            f"resolved={history_position_id} "
                            f"source={history_source}"
                        )

                        changed = True

                    else:
                        old_position_id = (
                            position_id
                        )

                        trades[
                            history_position_id
                        ] = trade

                        trade[
                            "position_id"
                        ] = history_position_id

                        trade[
                            "position_id_relinked_from"
                        ] = old_position_id

                        trade[
                            "position_id_relinked_source"
                        ] = history_source

                        trade[
                            "position_id_relinked_at"
                        ] = (
                            datetime.now()
                            .isoformat()
                        )

                        for other_trade in (
                            trades.values()
                        ):
                            if not isinstance(
                                other_trade,
                                dict,
                            ):
                                continue

                            if str(
                                other_trade.get(
                                    "main_position_id",
                                    "",
                                )
                            ) == str(
                                old_position_id
                            ):
                                other_trade[
                                    "main_position_id"
                                ] = history_position_id

                        del trades[
                            old_position_id
                        ]

                        position_id = (
                            history_position_id
                        )

                        changed = True

                        logger.warning(
                            "[TRACKER] Relinked tracker "
                            "identity from authoritative "
                            "MT5 execution history | "
                            f"old={old_position_id} "
                            f"new={position_id} "
                            f"source={history_source}"
                        )

                current_position = (
                    open_positions_map.get(
                        position_id
                    )
                )

            # Only manual / legacy records without a
            # resolvable execution deal/order may use the
            # older physical-position relink heuristic.
            else:
                relinked_position_id = (
                    relink_trade_position_if_needed(
                        position_id=position_id,
                        trade=trade,
                        open_positions_map=open_positions_map,
                    )
                )

                if (
                    relinked_position_id
                    != position_id
                ):
                    trades[
                        relinked_position_id
                    ] = trade

                    trades[
                        relinked_position_id
                    ][
                        "position_id"
                    ] = relinked_position_id

                    if (
                        trades[
                            relinked_position_id
                        ].get(
                            "main_position_id"
                        )
                        == position_id
                    ):
                        trades[
                            relinked_position_id
                        ][
                            "main_position_id"
                        ] = relinked_position_id

                    del trades[
                        position_id
                    ]

                    position_id = (
                        relinked_position_id
                    )

                    current_position = (
                        open_positions_map.get(
                            position_id
                        )
                    )

                    changed = True

        # Fully closed / missing from open positions.
        # Phase 2AC:
        # Do not mark the trade CLOSED until a matching MT5 close deal is resolved.
        # Previously, the tracker set status=CLOSED before checking close details.
        # If no close deal was found, the trade remained saved as broken CLOSED and
        # future lifecycle passes skipped it.
        if current_position is None:
            if tracked_remaining > 0:
                close_details = detect_close_details(position_id, trade=trade)

                if not close_details.get("found_close_deal"):
                    trade["missing_position_checks"] = int(trade.get("missing_position_checks", 0)) + 1
                    trade["last_missing_position_check"] = datetime.now().isoformat()
                    trade["close_reconciliation_pending"] = True
                    trade["status"] = "OPEN"
                    changed = True

                    logger.warning(
                        f"[TRACKER] Position missing but no close deal found yet | "
                        f"position={position_id} checks={trade['missing_position_checks']} "
                        f"status remains OPEN"
                    )

                    continue

                closed_now = tracked_remaining
                trade["closed_volume"] = round(float(trade.get("closed_volume", 0.0)) + closed_now, 2)
                trade["remaining_volume"] = 0.0
                trade["status"] = "CLOSED"
                trade["close_time"] = (
                    close_details.get("close_time")
                    or datetime.now().isoformat()
                )
                trade["close_reconciliation_pending"] = False

                close_reason = close_details["close_reason"]
                realized_profit = close_details["realized_profit"]
                close_price = close_details["close_price"]

                trade["close_reason"] = close_reason
                trade["realized_profit"] = realized_profit
                trade["close_price"] = close_price

                if realized_profit > 0:
                    trade["final_result"] = "WIN"
                elif realized_profit < 0:
                    trade["final_result"] = "LOSS"
                else:
                    trade["final_result"] = "BREAKEVEN"
                changed = True

                logger.info(f"[TRACKER] Trade fully closed {position_id} | reason={close_reason}")

                if close_reason in ["SL_LOSS", "SL_LIKELY_LOSS"]:
                    activate_cooldown()

                send_telegram_message(
                    f"Trade Fully Closed\n"
                    f"Position: {position_id}\n"
                    f"Role: {trade.get('trade_role', 'UNKNOWN')}\n"
                    f"Symbol: {trade['symbol']}\n"
                    f"Side: {trade['signal']}\n"
                    f"Initial Volume: {trade['initial_volume']}\n"
                    f"Closed Volume: {trade['closed_volume']}\n"
                    f"Remaining Volume: 0.0\n"
                    f"Setup Score: {trade.get('setup_score', 0)}\n"
                    f"Strategy: {trade.get('strategy', 'UNKNOWN')}\n"
                    f"Market: {trade.get('market_condition', 'UNKNOWN')}\n"
                    f"Reason: {trade.get('reason', 'N/A')}\n"
                    f"TP Buffer: {trade.get('tp_buffer', 0.0)}\n"
                    f"Max Profit Price: {trade.get('max_profit_price', 0.0)}\n"
                    f"Close Reason: {close_reason}"
                )

                log_setup_event(
                    setup_id=trade.get("setup_id", f"MANUAL-{position_id}"),
                    event="TRADE_CLOSED",
                    strategy=trade.get("strategy", "UNKNOWN"),
                    signal=trade.get("signal"),
                    entry_model=trade.get("entry_model"),
                    score=trade.get("setup_score", 0),
                    session=trade.get("session"),
                    market_condition=trade.get("market_condition"),
                    entry=trade.get("entry_price"),
                    sl=trade.get("stop_loss"),
                    tp=trade.get("take_profit"),
                    reason=trade.get("reason"),
                    extra={
                        "position_id": position_id,
                        "role": trade.get("trade_role"),
                        "close_reason": close_reason,
                        "final_result": trade.get("final_result"),
                        "realized_profit": realized_profit,
                        "close_price": close_price,
                        "max_profit_price": trade.get("max_profit_price", 0.0),
                        "closed_volume": trade.get("closed_volume", 0.0),
                    },
                )

                # Phase 2AM:
                # Keep setup_outcomes.json synchronized with clean trade closes.
                # Best-effort only. It must never block live execution.
                reconcile_result = reconcile_setup_outcome_from_closed_trade(trade)

                if not reconcile_result.get("ok"):
                    logger.warning(
                        "[TRACKER] setup outcome reconciliation issue | position=%s result=%s",
                        position_id,
                        reconcile_result,
                    )
            continue

        # Partial close
        current_volume = round(float(current_position.volume), 2)

        if current_volume < tracked_remaining:
            closed_now = round(tracked_remaining - current_volume, 2)

            trade["partial_closes"].append(
                {
                    "time": datetime.now().isoformat(),
                    "closed_volume": closed_now,
                    "remaining_volume": current_volume,
                }
            )

            trade["closed_volume"] = round(float(trade.get("closed_volume", 0.0)) + closed_now, 2)
            trade["remaining_volume"] = current_volume
            changed = True

            logger.info(
                f"[TRACKER] Partial close detected | "
                f"position={position_id} closed_now={closed_now} remaining={current_volume}"
            )

            send_telegram_message(
                f"Partial Close\n"
                f"Position: {position_id}\n"
                f"Role: {trade.get('trade_role', 'UNKNOWN')}\n"
                f"Symbol: {trade['symbol']}\n"
                f"Closed Volume: {closed_now}\n"
                f"Remaining Volume: {current_volume}"
            )

    if changed:
        save_trades(trades)


def sync_open_positions(symbol: str):
    trades = load_trades()

    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        logger.info(f"[TRACKER] No positions returned for sync on {symbol}")
        return

    changed = False

    for position in positions:
        position_id = str(position.ticket)

        if position_id in trades:
            continue

        signal = "BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL"

        trades[position_id] = _build_trade_record(
            position_id=position_id,
            main_position_id=position_id,
            trade_role="MAIN",
            setup_id=f"MANUAL-{position_id}",
            entry_model="MANUAL",
            symbol=position.symbol,
            signal=signal,
            entry_price=position.price_open,
            stop_loss=position.sl,
            take_profit=position.tp,
            initial_volume=float(position.volume),
            remaining_volume=float(position.volume),
            deal_id=None,
            order_id=None,
            imported_manually=True,
            setup_score=0,
            strategy_name="MANUAL",
            market_condition="MANUAL",
            session="MANUAL",
            reason="Imported manual/open position",
            tp_buffer=0.0,
        )

        logger.info(f"[TRACKER] Imported manual/open position {position_id}")
        changed = True

    if changed:
        save_trades(trades)