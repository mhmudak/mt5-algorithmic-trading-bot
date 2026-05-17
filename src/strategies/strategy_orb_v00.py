from config.settings import ATR_MIN, ATR_MAX

ORB_WINDOW = 15


def generate_signal(df):
    if len(df) < ORB_WINDOW + 5:
        return None

    data = df.iloc[-(ORB_WINDOW + 5):-2]

    orb_high = data["high"].max()
    orb_low = data["low"].min()
    orb_width = orb_high - orb_low

    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body = abs(entry["close"] - entry["open"])

    # =========================
    # BUY
    # =========================
    if price > orb_high and body > atr * 0.3 and price > ema:

        breakout_distance = price - orb_high

        max_immediate = min(atr * 0.35, orb_width * 0.20)
        max_retest = min(atr * 0.80, orb_width * 0.45)

        if breakout_distance <= max_immediate:
            entry_model = "BREAKOUT"
        elif breakout_distance <= max_retest:
            entry_model = "WAIT_RETEST"
        else:
            return None  # ❌ too extended → skip
        
        sl_reference = round(orb_high - max(atr * 0.25, 1.5), 2) # may delete this

        return {
            "signal": "BUY",
            "score": 92,
            "strategy": "ORB_V00",
            "entry_model": entry_model,
            "pattern_height": orb_width,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "breakout_distance": breakout_distance,
            "sl_reference": sl_reference,
            "reason": f"ORB_V00 BUY ({entry_model}) -> range {round(orb_low,2)}-{round(orb_high,2)}",
        }

    # =========================
    # SELL
    # =========================
    if price < orb_low and body > atr * 0.3 and price < ema:

        breakout_distance = orb_low - price

        max_immediate = min(atr * 0.35, orb_width * 0.20)
        max_retest = min(atr * 0.80, orb_width * 0.45)

        if breakout_distance <= max_immediate:
            entry_model = "BREAKOUT"
        elif breakout_distance <= max_retest:
            entry_model = "WAIT_RETEST"
        else:
            return None  # ❌ too extended → skip
        
        sl_reference = round(orb_low + max(atr * 0.25, 1.5), 2)

        return {
            "signal": "SELL",
            "score": 92,
            "strategy": "ORB_V00",
            "entry_model": entry_model,
            "pattern_height": orb_width,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "breakout_distance": breakout_distance,
            "sl_reference": sl_reference,
            "reason": f"ORB_V00 SELL ({entry_model}) -> range {round(orb_low,2)}-{round(orb_high,2)}",
        }

    return None