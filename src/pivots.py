import pandas as pd


def calculate_daily_pivots(df: pd.DataFrame):
    if df.empty:
        return None

    current_day = df["time"].dt.date.iloc[-1]
    previous_days = df[df["time"].dt.date < current_day]

    if previous_days.empty:
        return None

    prev_day = previous_days["time"].dt.date.max()
    prev = previous_days[previous_days["time"].dt.date == prev_day]

    high = prev["high"].max()
    low = prev["low"].min()
    close = prev["close"].iloc[-1]

    p = (high + low + close) / 3.0
    r1 = 2 * p - low
    s1 = 2 * p - high
    r2 = p + (high - low)
    s2 = p - (high - low)
    r3 = high + 2 * (p - low)
    s3 = low - 2 * (high - p)

    levels = {
        "S3": round(s3, 2),
        "S2": round(s2, 2),
        "S1": round(s1, 2),
        "P": round(p, 2),
        "R1": round(r1, 2),
        "R2": round(r2, 2),
        "R3": round(r3, 2),
    }

    ordered = sorted(levels.items(), key=lambda x: x[1])
    return {"levels": levels, "ordered": ordered}