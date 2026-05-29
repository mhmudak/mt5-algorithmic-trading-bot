from datetime import datetime

import MetaTrader5 as mt5

from config.settings import (
    ENABLE_FUNDED_SAFE_MODE,
    FUNDED_BLOCK_TELEGRAM_SIGNAL_TRADING,
    FUNDED_REQUIRE_SL_AND_TP,
    FUNDED_ALLOW_OPPOSITE_DIRECTION_TRADES,
    FUNDED_MAX_LOT_PER_TRADE,
    FUNDED_MAX_TOTAL_OPEN_LOT,
    FUNDED_MAX_OPEN_POSITIONS,
    FUNDED_MAX_SPREAD,
    FUNDED_BLOCK_ROLLOVER_TRADING,
    FUNDED_ROLLOVER_WINDOWS,
    FUNDED_MAX_FLOATING_LOSS_USD,
    FUNDED_MAX_TRADES_PER_DAY,
    FUNDED_MAX_DAILY_VOLUME_LOT,
    FUNDED_MAX_DAILY_REALIZED_LOSS_USD,
)
from src.logger import logger


def _parse_time(value):
    return datetime.strptime(value, "%H:%M").time()


def _is_now_in_window(start, end):
    now = datetime.now().time()
    start_time = _parse_time(start)
    end_time = _parse_time(end)

    if start_time <= end_time:
        return start_time <= now <= end_time

    return now >= start_time or now <= end_time


def _is_rollover_time():
    if not FUNDED_BLOCK_ROLLOVER_TRADING:
        return False, None

    for window in FUNDED_ROLLOVER_WINDOWS:
        if _is_now_in_window(window["start"], window["end"]):
            return True, window.get("name", "ROLLOVER")

    return False, None


def _is_telegram_trade_plan(trade_plan):
    strategy = str(trade_plan.get("strategy", "")).upper()
    entry_model = str(trade_plan.get("entry_model", "")).upper()
    risk_mode = str(trade_plan.get("risk_mode", "")).upper()

    return (
        strategy.startswith("TELEGRAM")
        or entry_model.startswith("TELEGRAM")
        or risk_mode.startswith("TELEGRAM")
        or trade_plan.get("telegram_partial_tp_enabled") is True
    )


def _get_position_direction(position):
    if position.type == mt5.POSITION_TYPE_BUY:
        return "BUY"

    if position.type == mt5.POSITION_TYPE_SELL:
        return "SELL"

    return "UNKNOWN"

def _today_range():
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    return start, now


def _get_today_deals():
    start, now = _today_range()
    deals = mt5.history_deals_get(start, now)

    if deals is None:
        return []

    return list(deals)


def _get_deal_symbol(deal):
    return str(getattr(deal, "symbol", "") or "")


def _is_entry_deal(deal):
    return getattr(deal, "entry", None) == mt5.DEAL_ENTRY_IN


def _get_daily_trade_count_and_volume(symbol):
    deals = _get_today_deals()

    entry_deals = [
        deal
        for deal in deals
        if _is_entry_deal(deal)
        and _get_deal_symbol(deal) == symbol
    ]

    trade_count = len(entry_deals)
    total_volume = sum(float(getattr(deal, "volume", 0.0) or 0.0) for deal in entry_deals)

    return trade_count, round(total_volume, 2)


def _get_daily_realized_pnl():
    deals = _get_today_deals()

    realized_pnl = 0.0

    for deal in deals:
        profit = float(getattr(deal, "profit", 0.0) or 0.0)
        commission = float(getattr(deal, "commission", 0.0) or 0.0)
        swap = float(getattr(deal, "swap", 0.0) or 0.0)

        realized_pnl += profit + commission + swap

    return round(realized_pnl, 2)

def validate_funded_safe_trade(signal, trade_plan, symbol):
    if not ENABLE_FUNDED_SAFE_MODE:
        return True, "funded_safe_mode_disabled"

    strategy = trade_plan.get("strategy", "UNKNOWN")
    lot = float(trade_plan.get("lot", 0.0) or 0.0)
    sl = float(trade_plan.get("stop_loss", 0.0) or 0.0)
    tp = float(trade_plan.get("take_profit", 0.0) or 0.0)

    if FUNDED_BLOCK_TELEGRAM_SIGNAL_TRADING and _is_telegram_trade_plan(trade_plan):
        return False, "funded_block_telegram_signal_trading"

    if FUNDED_REQUIRE_SL_AND_TP and (sl <= 0 or tp <= 0):
        return False, "funded_requires_sl_and_tp"

    if lot <= 0:
        return False, "funded_invalid_lot"

    if lot > FUNDED_MAX_LOT_PER_TRADE:
        return False, (
            f"funded_lot_too_high lot={lot} max={FUNDED_MAX_LOT_PER_TRADE}"
        )

    daily_trade_count, daily_volume = _get_daily_trade_count_and_volume(symbol)

    if daily_trade_count >= FUNDED_MAX_TRADES_PER_DAY:
        return False, (
            f"funded_max_trades_per_day "
            f"count={daily_trade_count} max={FUNDED_MAX_TRADES_PER_DAY}"
        )

    if daily_volume + lot > FUNDED_MAX_DAILY_VOLUME_LOT:
        return False, (
            f"funded_daily_volume_too_high "
            f"current={daily_volume} "
            f"new={lot} "
            f"max={FUNDED_MAX_DAILY_VOLUME_LOT}"
        )

    daily_realized_pnl = _get_daily_realized_pnl()

    if daily_realized_pnl < 0 and abs(daily_realized_pnl) >= FUNDED_MAX_DAILY_REALIZED_LOSS_USD:
        return False, (
            f"funded_daily_realized_loss_guard "
            f"loss={abs(daily_realized_pnl)} "
            f"max={FUNDED_MAX_DAILY_REALIZED_LOSS_USD}"
        )

    rollover_blocked, rollover_name = _is_rollover_time()

    if rollover_blocked:
        return False, f"funded_rollover_blocked window={rollover_name}"

    tick = mt5.symbol_info_tick(symbol)

    if tick is None:
        return False, "funded_no_tick_data"

    spread = abs(float(tick.ask) - float(tick.bid))

    if spread > FUNDED_MAX_SPREAD:
        return False, f"funded_spread_too_high spread={round(spread, 2)} max={FUNDED_MAX_SPREAD}"

    account_info = mt5.account_info()

    if account_info is not None:
        floating_loss = float(account_info.balance) - float(account_info.equity)

        if floating_loss > FUNDED_MAX_FLOATING_LOSS_USD:
            return False, (
                f"funded_floating_loss_guard "
                f"loss={round(floating_loss, 2)} "
                f"max={FUNDED_MAX_FLOATING_LOSS_USD}"
            )

    positions = mt5.positions_get(symbol=symbol)

    if positions is None:
        positions = []

    open_positions = list(positions)

    if len(open_positions) >= FUNDED_MAX_OPEN_POSITIONS:
        return False, (
            f"funded_max_open_positions "
            f"open={len(open_positions)} max={FUNDED_MAX_OPEN_POSITIONS}"
        )

    total_open_lot = sum(float(position.volume) for position in open_positions)

    if total_open_lot + lot > FUNDED_MAX_TOTAL_OPEN_LOT:
        return False, (
            f"funded_total_lot_too_high "
            f"current={round(total_open_lot, 2)} "
            f"new={lot} "
            f"max={FUNDED_MAX_TOTAL_OPEN_LOT}"
        )

    if not FUNDED_ALLOW_OPPOSITE_DIRECTION_TRADES:
        for position in open_positions:
            position_direction = _get_position_direction(position)

            if position_direction != "UNKNOWN" and position_direction != signal:
                return False, (
                    f"funded_opposite_position_blocked "
                    f"existing={position_direction} new={signal}"
                )

    logger.info(
        f"[FUNDED SAFE MODE] Trade allowed | "
        f"strategy={strategy} signal={signal} lot={lot}"
    )

    return True, "funded_safe_mode_passed"