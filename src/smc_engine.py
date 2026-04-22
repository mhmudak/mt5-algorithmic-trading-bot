def smc_validate(df, signal_data):
    score_boost = 0
    reasons = []

    if not signal_data:
        return score_boost, reasons

    strategy = signal_data.get("strategy")
    signal = signal_data.get("signal")

    last = df.iloc[-2]
    prev = df.iloc[-3]

    close = last["close"]
    high = last["high"]
    low = last["low"]
    ema = last["ema_20"]
    atr = last["atr_14"]

    recent_highs = df.iloc[-12:-2]["high"]
    recent_lows = df.iloc[-12:-2]["low"]

    recent_high = recent_highs.max()
    recent_low = recent_lows.min()

    # =========================================================
    # 1) liquidity event
    # =========================================================
    took_highs = high > recent_high
    took_lows = low < recent_low

    if signal == "SELL" and took_highs:
        score_boost += 3
        reasons.append("liquidity_taken_high")

    if signal == "BUY" and took_lows:
        score_boost += 3
        reasons.append("liquidity_taken_low")

    # =========================================================
    # 2) EMA context
    # =========================================================
    if signal == "BUY" and close > ema:
        score_boost += 1
        reasons.append("ema_bullish")

    if signal == "SELL" and close < ema:
        score_boost += 1
        reasons.append("ema_bearish")

    # =========================================================
    # 3) displacement / momentum
    # =========================================================
    last_body = abs(last["close"] - last["open"])
    if last_body > atr * 0.25:
        score_boost += 1
        reasons.append("displacement")

    # =========================================================
    # 4) structure shift
    # =========================================================
    if signal == "BUY" and close > prev["high"]:
        score_boost += 2
        reasons.append("bullish_bos")

    if signal == "SELL" and close < prev["low"]:
        score_boost += 2
        reasons.append("bearish_bos")

    # =========================================================
    # 5) strategy-specific confluence
    # =========================================================
    if strategy == "FVG":
        if signal_data.get("fvg_top") is not None and signal_data.get("fvg_bottom") is not None:
            score_boost += 2
            reasons.append("fvg_present")

        if signal == "BUY" and close > signal_data.get("fvg_top", close + 999999):
            score_boost += 1
            reasons.append("fvg_reclaimed")

        if signal == "SELL" and close < signal_data.get("fvg_bottom", close - 999999):
            score_boost += 1
            reasons.append("fvg_rejected")

    if strategy == "ORDER_BLOCK":
        if signal_data.get("ob_high") is not None and signal_data.get("ob_low") is not None:
            score_boost += 2
            reasons.append("order_block_zone")

    if strategy == "LIQUIDITY_CANDLE":
        if signal_data.get("sl_reference") is not None:
            score_boost += 2
            reasons.append("clean_candle_risk")

    if strategy in ["SMT", "SMT_PRO"]:
        score_boost += 3
        reasons.append("smt_divergence")

    if strategy == "CRT_TBS":
        score_boost += 3
        reasons.append("trap_reversal")

    if strategy == "LIQUIDITY_SWEEP":
        score_boost += 3
        reasons.append("sweep_reversal")

    # =========================================================
    # 6) penalty for weak extension against setup logic
    # =========================================================
    if signal == "BUY" and close < ema:
        score_boost -= 2
        reasons.append("penalty_below_ema")

    if signal == "SELL" and close > ema:
        score_boost -= 2
        reasons.append("penalty_above_ema")

    return score_boost, reasons