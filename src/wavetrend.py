import pandas as pd


def calculate_wavetrend(
    df: pd.DataFrame,
    channel_length: int = 10,
    average_length: int = 21,
) -> pd.DataFrame:
    df = df.copy()

    hlc3 = (df["high"] + df["low"] + df["close"]) / 3.0
    esa = hlc3.ewm(span=channel_length, adjust=False).mean()
    d = (hlc3 - esa).abs().ewm(span=channel_length, adjust=False).mean()
    ci = (hlc3 - esa) / (0.015 * d.replace(0, 1e-9))

    wt1 = ci.ewm(span=average_length, adjust=False).mean()
    wt2 = wt1.rolling(window=4).mean()

    df["wt1"] = wt1
    df["wt2"] = wt2
    return df