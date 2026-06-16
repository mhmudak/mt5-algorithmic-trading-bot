import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SOURCE_DIR = ROOT / "data" / "accounts" / "Tickmill-Demo_25323531"
DEFAULT_OUTPUT_ROOT = ROOT / "data" / "strategy_intelligence"

SOURCE_FILES = {
    "trades": ["Statistics - Trades.csv", "trades.json"],
    "setup_outcomes": ["Statistics - SetupOutcomes.csv", "setup_outcomes.json"],
    "events": ["Statistics - Events.csv", "setup_audit.json"],
    "setups": ["Statistics - Setups.csv"],
    "memory": ["Statistics - MemoryDecisionReports.csv"],
}


def clean_value(value):
    if value is None:
        return None

    if isinstance(value, (np.integer,)):
        return int(value)

    if isinstance(value, (np.floating,)):
        value = float(value)

    if isinstance(value, float) and math.isnan(value):
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    return value


def to_float(value, default=0.0):
    value = clean_value(value)

    if value in [None, "", "NaN", "nan"]:
        return default

    try:
        return float(value)
    except Exception:
        return default


def to_bool(value):
    value = clean_value(value)

    if isinstance(value, bool):
        return value

    value = str(value or "").strip().lower()

    return value in [
        "true",
        "yes",
        "1",
        "y",
        "hit",
        "tp_touch",
        "sl_touch",
        "true_hit",
    ]


def safe_text(value, default="UNKNOWN"):
    value = clean_value(value)

    if value in [None, ""]:
        return default

    return str(value).strip().upper()


def series_text(df, column, default="UNKNOWN"):
    if column in df.columns:
        return df[column].apply(lambda value: safe_text(value, default))

    return pd.Series([default] * len(df), index=df.index)


def series_float(df, column, default=0.0):
    if column in df.columns:
        return df[column].apply(lambda value: to_float(value, default))

    return pd.Series([default] * len(df), index=df.index)


def series_bool(df, column):
    if column in df.columns:
        return df[column].apply(to_bool)

    return pd.Series([False] * len(df), index=df.index)


def read_json_table(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to read JSON {path}: {e}")
        return pd.DataFrame()

    if isinstance(data, list):
        return pd.DataFrame(data)

    if isinstance(data, dict):
        rows = []

        for key, value in data.items():
            if isinstance(value, dict):
                row = value.copy()

                if "setup_id" not in row and "SETUP" in str(key).upper():
                    row["setup_id"] = key

                if "position_id" not in row and "POSITION" not in str(key).upper():
                    row.setdefault("position_id", key)

                rows.append(row)

        return pd.DataFrame(rows)

    return pd.DataFrame()


def read_source(name, source_dir):
    candidates = SOURCE_FILES.get(name, [])

    for filename in candidates:
        path = source_dir / filename

        if not path.exists():
            fallback = ROOT / filename
            if fallback.exists():
                path = fallback

        if not path.exists():
            continue

        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path)
            df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]
            print(f"[LOAD] {name}: {len(df)} rows from CSV {path}")
            return df

        if path.suffix.lower() == ".json":
            df = read_json_table(path)
            print(f"[LOAD] {name}: {len(df)} rows from JSON {path}")
            return df

    print(f"[WARN] Missing source for {name} in {source_dir}")
    return pd.DataFrame()


def detect_execution_bucket(row):
    setup_id = safe_text(row.get("setup_id"), "")
    source_events = safe_text(row.get("source_events"), "")
    entry_model = safe_text(row.get("entry_model"), "")
    market_condition = safe_text(row.get("market_condition"), "")
    strategy = safe_text(row.get("strategy"), "")

    combined = f"{setup_id}|{source_events}|{entry_model}|{market_condition}|{strategy}"

    if "INTRABAR" in combined:
        return "INTRABAR"

    if "TICK_SNIPER" in combined:
        return "TICK_SNIPER"

    if "ORB_TICK" in combined:
        return "ORB_TICK_WATCHER"

    if "MTF_CONFLICT" in combined:
        return "MTF_CONFLICT_TRACKED"

    if "CANDIDATE_REJECTED" in combined:
        return "REJECTED_CANDIDATE_TRACKED"

    return "NORMAL_OR_TRACKED"

def detect_setup_source_bucket(row):
    setup_id = safe_text(row.get("setup_id"), "")
    source_events = row.get("source_events", "")
    entry_model = safe_text(row.get("entry_model"), "")
    market_condition = safe_text(row.get("market_condition"), "")
    strategy = safe_text(row.get("strategy"), "")

    if isinstance(source_events, list):
        source_events_text = "|".join(str(x).upper() for x in source_events)
    else:
        source_events_text = safe_text(source_events, "")

    combined = f"{setup_id}|{source_events_text}|{entry_model}|{market_condition}|{strategy}"

    if "INTRABAR" in combined:
        return "INTRABAR"

    if "TICK_SNIPER" in combined:
        return "TICK_SNIPER"

    if "ORB_TICK" in combined:
        return "ORB_TICK_WATCHER"

    if "MTF_CONFLICT" in combined:
        return "MTF_CONFLICT_TRACKED"

    if "CANDIDATE_REJECTED" in combined:
        return "REJECTED_CANDIDATE_TRACKED"

    if "LOW_RR" in combined:
        return "REJECTED_CANDIDATE_TRACKED"

    return "NORMAL_OR_TRACKED"

def normalize_setup_outcomes(setup_outcomes, trades):
    if setup_outcomes.empty:
        return pd.DataFrame()

    df = setup_outcomes.copy()

    if "setup_id" not in df.columns:
        raise SystemExit("[STOP] setup_outcomes file has no setup_id column.")

    if not trades.empty and "setup_id" in trades.columns:
        trades_copy = trades.copy()

        if "realized_profit" in trades_copy.columns:
            trades_copy["realized_profit"] = trades_copy["realized_profit"].apply(
                lambda value: to_float(value, default=0.0)
            )

            trade_profit = (
                trades_copy.groupby("setup_id", dropna=False)["realized_profit"]
                .sum()
                .reset_index()
                .rename(columns={"realized_profit": "actual_realized_profit"})
            )

            df = df.merge(trade_profit, on="setup_id", how="left")
        else:
            df["actual_realized_profit"] = None
    else:
        df["actual_realized_profit"] = None

    for col in [
        "max_favorable_usd",
        "max_adverse_usd",
        "max_recovery_swing_usd",
        "entry",
        "sl",
        "tp",
        "score",
    ]:
        df[col] = series_float(df, col, default=0.0)

    if "actual_realized_profit" in df.columns:
        df["actual_realized_profit"] = df["actual_realized_profit"].apply(
            lambda value: to_float(value, default=None)
        )
    else:
        df["actual_realized_profit"] = None

    for col in ["hit_plus_10", "hit_tp", "hit_sl"]:
        df[col] = series_bool(df, col)

    df["strategy"] = series_text(df, "strategy")
    df["signal"] = series_text(df, "signal")
    df["entry_model"] = series_text(df, "entry_model")
    df["session"] = series_text(df, "session")
    df["market_condition"] = series_text(df, "market_condition")
    df["final_outcome"] = series_text(df, "final_outcome")
    df["first_hit"] = series_text(df, "first_hit")
    df["source_events"] = series_text(df, "source_events", default="")

    df["execution_bucket"] = df.apply(detect_execution_bucket, axis=1)
    
    df["setup_source_bucket"] = df.apply(detect_setup_source_bucket, axis=1)

    df["is_normal_or_tracked"] = df["setup_source_bucket"] == "NORMAL_OR_TRACKED"
    df["is_rejected_candidate"] = df["setup_source_bucket"] == "REJECTED_CANDIDATE_TRACKED"
    df["is_mtf_conflict"] = df["setup_source_bucket"] == "MTF_CONFLICT_TRACKED"
    df["is_intrabar"] = df["setup_source_bucket"] == "INTRABAR"

    df["synthetic_expectancy"] = (
        df["max_favorable_usd"] * 0.35
        - df["max_adverse_usd"] * 0.65
    )

    df["favorable_then_sl"] = (
        (df["max_favorable_usd"] >= 5.0)
        & (df["hit_sl"] == True)
    )

    df["strong_move_no_tp"] = (
        (df["max_favorable_usd"] >= 10.0)
        & (df["hit_tp"] == False)
    )

    return df


def normalize_trades(trades):
    if trades.empty:
        return pd.DataFrame()

    df = trades.copy()

    df["strategy"] = series_text(df, "strategy")
    df["signal"] = series_text(df, "signal")
    df["entry_model"] = series_text(df, "entry_model")
    df["session"] = series_text(df, "session")
    df["market_condition"] = series_text(df, "market_condition")
    df["trade_role"] = series_text(df, "trade_role")
    df["status"] = series_text(df, "status")
    df["final_result"] = series_text(df, "final_result")
    df["close_reason"] = series_text(df, "close_reason", default="")
    df["setup_id"] = series_text(df, "setup_id", default="")

    df["realized_profit"] = series_float(df, "realized_profit", default=0.0)
    df["initial_volume"] = series_float(df, "initial_volume", default=0.0)
    df["entry_price"] = series_float(df, "entry_price", default=0.0)
    df["stop_loss"] = series_float(df, "stop_loss", default=0.0)
    df["take_profit"] = series_float(df, "take_profit", default=0.0)
    df["setup_score"] = series_float(df, "setup_score", default=0.0)

    df = df[df["strategy"] != "MANUAL"].copy()

    df["is_win"] = df["realized_profit"] > 0
    df["is_loss"] = df["realized_profit"] < 0
    df["is_breakeven"] = df["realized_profit"] == 0

    df["execution_bucket"] = df.apply(detect_execution_bucket, axis=1)
    
    df["is_closed"] = df["status"] == "CLOSED"
    df["has_realized_result"] = df["realized_profit"] != 0
    df["is_main"] = df["trade_role"] == "MAIN"
    df["is_extra"] = df["trade_role"] == "EXTRA"

    return df

def decide_policy(metrics, min_samples):
    n = metrics["sample_count"]
    w10_rate = metrics["w10_rate"]
    tp_rate = metrics["tp_rate"]
    sl_rate = metrics["sl_rate"]
    synthetic_expectancy = metrics["synthetic_expectancy"]
    actual_expectancy = metrics["actual_expectancy"]
    favorable_then_sl_rate = metrics["favorable_then_sl_rate"]
    strong_move_no_tp_rate = metrics["strong_move_no_tp_rate"]

    if n < min_samples:
        return "TRACK_ONLY", f"not enough samples: {n}/{min_samples}"

    # Real block only when the setup is weak and dangerous.
    if n >= 20 and sl_rate >= 0.60 and w10_rate < 0.50:
        return "BLOCK_TEMPORARILY", "high SL rate and weak W10 behavior"

    if n >= 20 and synthetic_expectancy <= -8 and w10_rate < 0.50:
        return "BLOCK_TEMPORARILY", "very negative expectancy and weak W10 behavior"

    # If price often moves +10 but still fails TP or hits SL, don't block.
    # This means the entry has potential, but TP/SL/timing/management needs tuning.
    if w10_rate >= 0.60 and (tp_rate < 0.55 or sl_rate >= 0.35):
        return "TUNE_RULES", "good W10 movement but TP/SL or timing needs tuning"

    if favorable_then_sl_rate >= 0.25 or strong_move_no_tp_rate >= 0.35:
        return "TUNE_RULES", "good move exists but management/timing is weak"

    if actual_expectancy is not None and actual_expectancy > 0 and sl_rate <= 0.45:
        return "KEEP_EXECUTING", "positive actual expectancy and controlled SL rate"

    if w10_rate >= 0.55 and sl_rate <= 0.35 and synthetic_expectancy > 0:
        return "KEEP_EXECUTING", "positive setup behavior: W10 strong and adverse controlled"

    if w10_rate >= 0.50:
        return "TUNE_RULES", "edge exists but needs better execution filters"

    return "TRACK_ONLY", "unclear edge; track more before execution"


def aggregate_group(df, dimensions, min_samples):
    rows = []

    grouped = df.groupby(dimensions, dropna=False)

    for keys, group in grouped:
        if not isinstance(keys, tuple):
            keys = (keys,)

        item = dict(zip(dimensions, keys))

        sample_count = int(len(group))
        tp_rate = round(float(group["hit_tp"].mean()), 4)
        sl_rate = round(float(group["hit_sl"].mean()), 4)
        w10_rate = round(float(group["hit_plus_10"].mean()), 4)

        avg_favorable = round(float(group["max_favorable_usd"].mean()), 2)
        avg_adverse = round(float(group["max_adverse_usd"].mean()), 2)
        avg_recovery = round(float(group["max_recovery_swing_usd"].mean()), 2)
        synthetic_expectancy = round(float(group["synthetic_expectancy"].mean()), 2)

        actual_values = group["actual_realized_profit"].dropna()
        actual_expectancy = None

        if len(actual_values) >= 3:
            actual_expectancy = round(float(actual_values.mean()), 2)

        favorable_then_sl_rate = round(float(group["favorable_then_sl"].mean()), 4)
        strong_move_no_tp_rate = round(float(group["strong_move_no_tp"].mean()), 4)

        metrics = {
            "sample_count": sample_count,
            "tp_rate": tp_rate,
            "sl_rate": sl_rate,
            "w10_rate": w10_rate,
            "avg_favorable": avg_favorable,
            "avg_adverse": avg_adverse,
            "avg_recovery": avg_recovery,
            "synthetic_expectancy": synthetic_expectancy,
            "actual_expectancy": actual_expectancy,
            "favorable_then_sl_rate": favorable_then_sl_rate,
            "strong_move_no_tp_rate": strong_move_no_tp_rate,
        }

        decision, decision_reason = decide_policy(metrics, min_samples)

        item.update(metrics)
        item["decision"] = decision
        item["decision_reason"] = decision_reason
        item["policy_key"] = "|".join(str(item.get(col, "UNKNOWN")) for col in dimensions)

        rows.append(item)

    result = pd.DataFrame(rows)

    if result.empty:
        return result

    decision_order = {
        "DISABLE_STRATEGY": 0,
        "BLOCK_TEMPORARILY": 1,
        "TUNE_RULES": 2,
        "KEEP_EXECUTING": 3,
        "TRACK_ONLY": 4,
    }

    result["_decision_sort"] = result["decision"].map(decision_order).fillna(9)

    result = result.sort_values(
        by=["_decision_sort", "sample_count", "synthetic_expectancy"],
        ascending=[True, False, True],
    ).drop(columns=["_decision_sort"])

    return result


def aggregate_trades(df, dimensions, min_samples):
    rows = []

    if df.empty:
        return pd.DataFrame()

    grouped = df.groupby(dimensions, dropna=False)

    for keys, group in grouped:
        if not isinstance(keys, tuple):
            keys = (keys,)

        item = dict(zip(dimensions, keys))

        sample_count = int(len(group))
        closed_count = int(group["is_closed"].sum())
        realized_count = int(group["has_realized_result"].sum())
        main_count = int(group["is_main"].sum())
        extra_count = int(group["is_extra"].sum())

        win_rate = round(float(group["is_win"].mean()), 4)
        loss_rate = round(float(group["is_loss"].mean()), 4)
        breakeven_rate = round(float(group["is_breakeven"].mean()), 4)

        closed_group = group[group["is_closed"] == True]
        realized_group = group[group["has_realized_result"] == True]

        total_profit = round(float(group["realized_profit"].sum()), 2)
        expectancy = round(float(group["realized_profit"].mean()), 2)
        
        closed_expectancy = None
        realized_expectancy = None
        
        if len(closed_group) > 0:
            closed_expectancy = round(float(closed_group["realized_profit"].mean()), 2)
        
        if len(realized_group) > 0:
            realized_expectancy = round(float(realized_group["realized_profit"].mean()), 2)

        avg_win = round(float(group.loc[group["is_win"], "realized_profit"].mean()), 2) if group["is_win"].any() else 0.0
        avg_loss = round(float(group.loc[group["is_loss"], "realized_profit"].mean()), 2) if group["is_loss"].any() else 0.0

        if realized_count < min_samples:
            decision = "DIAGNOSTIC_ONLY"
            decision_reason = (
                f"trade tracker not reliable yet: only {realized_count}/{sample_count} "
                f"trades have real non-zero realized profit"
            )
        elif breakeven_rate >= 0.80:
            decision = "DIAGNOSTIC_ONLY"
            decision_reason = (
                f"trade tracker likely inaccurate: breakeven_rate={breakeven_rate}"
            )
        elif expectancy > 0 and win_rate >= 0.45:
            decision = "KEEP_EXECUTING"
            decision_reason = "positive realized expectancy"
        elif expectancy < -3 or loss_rate >= 0.60:
            decision = "BLOCK_TEMPORARILY"
            decision_reason = "negative realized expectancy or high loss rate"
        else:
            decision = "TUNE_RULES"
            decision_reason = "mixed execution results; needs tuning"

        item.update({
            "sample_count": sample_count,
            "win_rate": win_rate,
            "loss_rate": loss_rate,
            "breakeven_rate": breakeven_rate,
            "total_profit": total_profit,
            "actual_expectancy": expectancy,
            "closed_count": closed_count,
            "realized_count": realized_count,
            "main_count": main_count,
            "extra_count": extra_count,
            "closed_expectancy": closed_expectancy,
            "realized_expectancy": realized_expectancy,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "decision": decision,
            "decision_reason": decision_reason,
            "policy_key": "|".join(str(item.get(col, "UNKNOWN")) for col in dimensions),
        })

        rows.append(item)

    result = pd.DataFrame(rows)

    if result.empty:
        return result

    return result.sort_values(
        by=["sample_count", "actual_expectancy"],
        ascending=[False, True],
    )

def dataframe_to_records(df):
    records = []

    for row in df.to_dict(orient="records"):
        clean = {}

        for key, value in row.items():
            clean[key] = clean_value(value)

        records.append(clean)

    return records


def build_execution_policy(detail_df):
    policy = {}

    for row in dataframe_to_records(detail_df):
        key = row["policy_key"]

        policy[key] = {
            "decision": row["decision"],
            "decision_reason": row["decision_reason"],
            "sample_count": row["sample_count"],
            "tp_rate": row["tp_rate"],
            "sl_rate": row["sl_rate"],
            "w10_rate": row["w10_rate"],
            "avg_favorable": row["avg_favorable"],
            "avg_adverse": row["avg_adverse"],
            "avg_recovery": row["avg_recovery"],
            "synthetic_expectancy": row["synthetic_expectancy"],
            "actual_expectancy": row["actual_expectancy"],
        }

    return policy

def build_data_quality_report(setup_df, trade_df):
    warnings = []

    setup_count = int(len(setup_df)) if setup_df is not None else 0
    trade_count = int(len(trade_df)) if trade_df is not None else 0

    report = {
        "setup_outcomes_rows": setup_count,
        "trade_rows": trade_count,
        "trade_tracker_status": "UNKNOWN",
        "trade_realized_nonzero_count": 0,
        "trade_realized_nonzero_rate": 0.0,
        "trade_breakeven_count": 0,
        "trade_breakeven_rate": 0.0,
        "setup_intrabar_count": 0,
        "trade_intrabar_count": 0,
        "warnings": warnings,
    }

    if setup_df is not None and not setup_df.empty and "setup_source_bucket" in setup_df.columns:
        report["setup_intrabar_count"] = int((setup_df["setup_source_bucket"] == "INTRABAR").sum())

    if trade_df is not None and not trade_df.empty:
        realized_profit = trade_df.get("realized_profit")

        if realized_profit is not None:
            realized_nonzero_count = int((realized_profit.fillna(0).astype(float) != 0).sum())
        else:
            realized_nonzero_count = 0

        final_result = trade_df.get("final_result")

        if final_result is not None:
            breakeven_count = int((final_result.fillna("").astype(str).str.upper() == "BREAKEVEN").sum())
        else:
            breakeven_count = 0

        report["trade_realized_nonzero_count"] = realized_nonzero_count
        report["trade_realized_nonzero_rate"] = round(realized_nonzero_count / trade_count, 4) if trade_count else 0.0
        report["trade_breakeven_count"] = breakeven_count
        report["trade_breakeven_rate"] = round(breakeven_count / trade_count, 4) if trade_count else 0.0

        if "execution_bucket" in trade_df.columns:
            report["trade_intrabar_count"] = int((trade_df["execution_bucket"] == "INTRABAR").sum())

        if report["trade_realized_nonzero_rate"] < 0.20 and report["trade_breakeven_rate"] >= 0.70:
            report["trade_tracker_status"] = "UNRELIABLE_HISTORY_DIAGNOSTIC_ONLY"
            warnings.append(
                "Most trade rows are breakeven/zero realized profit. Old trades.json should be diagnostic only."
            )
        else:
            report["trade_tracker_status"] = "USABLE_WITH_CAUTION"

    if report["trade_intrabar_count"] > 0 and report["setup_intrabar_count"] == 0:
        warnings.append(
            "Intrabar trades exist in trades.json, but no intrabar setup outcomes exist yet. Future data should improve after live_bot intrabar tracking fix."
        )

    if setup_count > 0 and trade_count > 0 and report["trade_tracker_status"] == "UNRELIABLE_HISTORY_DIAGNOSTIC_ONLY":
        warnings.append(
            "Use setup_outcomes.json for strategy decisions. Do not block strategies from old trades.json results."
        )

    return report

def build_legacy_intrabar_shadow_report(trade_df):
    if trade_df is None or trade_df.empty:
        return pd.DataFrame()

    if "execution_bucket" not in trade_df.columns:
        return pd.DataFrame()

    intrabar_df = trade_df[trade_df["execution_bucket"] == "INTRABAR"].copy()

    if intrabar_df.empty:
        return pd.DataFrame()

    group_cols = [
        "strategy",
        "signal",
        "session",
        "market_condition",
        "execution_bucket",
    ]

    rows = []

    for keys, group in intrabar_df.groupby(group_cols, dropna=False):
        realized_profit = group["realized_profit"].fillna(0).astype(float)
        final_result = group["final_result"].fillna("").astype(str).str.upper()

        sample_count = len(group)
        realized_count = int((realized_profit != 0).sum())
        breakeven_count = int((final_result == "BREAKEVEN").sum())

        rows.append({
            "policy_key": "|".join(str(x) for x in keys),
            "strategy": keys[0],
            "signal": keys[1],
            "session": keys[2],
            "market_condition": keys[3],
            "execution_bucket": keys[4],
            "sample_count": sample_count,
            "realized_count": realized_count,
            "breakeven_count": breakeven_count,
            "breakeven_rate": round(breakeven_count / sample_count, 4) if sample_count else 0.0,
            "total_profit": round(realized_profit.sum(), 2),
            "actual_expectancy": round(realized_profit.mean(), 2) if sample_count else 0.0,
            "data_quality": "LEGACY_TRADE_TRACKER_DIAGNOSTIC_ONLY",
            "decision": "DIAGNOSTIC_ONLY",
            "decision_reason": "legacy intrabar trades come from trades.json only; not reliable enough for setup policy",
        })

    return pd.DataFrame(rows).sort_values(
        ["sample_count", "actual_expectancy"],
        ascending=[False, False],
    )

def build_trade_tracker_health_report(trade_df):
    if trade_df is None or trade_df.empty:
        return {
            "trade_rows": 0,
            "status": "NO_TRADE_DATA",
            "warnings": ["No trades available for tracker health report."],
        }, pd.DataFrame()

    def text_col(name, default=""):
        if name in trade_df.columns:
            return trade_df[name].fillna(default).astype(str)
        return pd.Series([default] * len(trade_df), index=trade_df.index)

    def numeric_col(name, default=0.0):
        if name in trade_df.columns:
            return pd.to_numeric(trade_df[name], errors="coerce").fillna(default)
        return pd.Series([default] * len(trade_df), index=trade_df.index)

    status = text_col("status").str.upper()
    final_result = text_col("final_result").str.upper()
    realized_profit = numeric_col("realized_profit")
    missing_position_checks = numeric_col("missing_position_checks")

    position_id = text_col("position_id")
    raw_order_id = text_col("raw_order_id")
    raw_deal_id = text_col("raw_deal_id")

    closed_mask = status == "CLOSED"
    open_mask = status == "OPEN"
    breakeven_mask = closed_mask & (final_result == "BREAKEVEN")
    zero_realized_closed_mask = closed_mask & (realized_profit == 0)
    missing_position_mask = missing_position_checks > 0

    has_raw_id_mask = (raw_order_id != "") | (raw_deal_id != "")
    legacy_without_raw_ids_mask = ~has_raw_id_mask

    possible_raw_id_position_mask = (
        (position_id == raw_order_id)
        | (position_id == raw_deal_id)
    ) & has_raw_id_mask

    trade_rows = len(trade_df)
    closed_count = int(closed_mask.sum())
    open_count = int(open_mask.sum())
    breakeven_count = int(breakeven_mask.sum())
    zero_realized_closed_count = int(zero_realized_closed_mask.sum())
    missing_position_rows = int(missing_position_mask.sum())
    legacy_without_raw_ids = int(legacy_without_raw_ids_mask.sum())
    possible_raw_id_position_rows = int(possible_raw_id_position_mask.sum())

    warnings = []

    breakeven_rate = round(breakeven_count / closed_count, 4) if closed_count else 0.0
    zero_realized_closed_rate = round(zero_realized_closed_count / closed_count, 4) if closed_count else 0.0

    if breakeven_rate >= 0.70:
        warnings.append(
            "High BREAKEVEN rate detected. Old trade tracker history is still unreliable."
        )

    if zero_realized_closed_rate >= 0.70:
        warnings.append(
            "Most closed trades have zero realized profit. Use trade stats as diagnostic only."
        )

    if missing_position_rows > 0:
        warnings.append(
            "Some trades had missing position checks. Watch if they later resolve with real close deals."
        )

    if legacy_without_raw_ids > 0:
        warnings.append(
            "Legacy trades without raw_order_id/raw_deal_id exist. These were created before tracker fix."
        )

    if possible_raw_id_position_rows > 0:
        warnings.append(
            "Some rows still have position_id equal to raw order/deal id. Future rows should reduce this."
        )

    summary = {
        "trade_rows": trade_rows,
        "open_count": open_count,
        "closed_count": closed_count,
        "breakeven_count": breakeven_count,
        "breakeven_rate": breakeven_rate,
        "zero_realized_closed_count": zero_realized_closed_count,
        "zero_realized_closed_rate": zero_realized_closed_rate,
        "missing_position_rows": missing_position_rows,
        "legacy_without_raw_ids": legacy_without_raw_ids,
        "possible_raw_id_position_rows": possible_raw_id_position_rows,
        "status": "WATCH_NEW_TRADES" if warnings else "HEALTHY",
        "warnings": warnings,
    }

    detail_df = trade_df.copy()
    detail_df["_is_closed"] = closed_mask
    detail_df["_is_open"] = open_mask
    detail_df["_is_breakeven"] = breakeven_mask
    detail_df["_is_zero_realized_closed"] = zero_realized_closed_mask
    detail_df["_has_missing_position_checks"] = missing_position_mask
    detail_df["_is_legacy_without_raw_ids"] = legacy_without_raw_ids_mask
    detail_df["_possible_raw_id_position"] = possible_raw_id_position_mask

    group_cols = [
        col for col in [
            "strategy",
            "execution_bucket",
            "session",
            "market_condition",
        ]
        if col in detail_df.columns
    ]

    if not group_cols:
        return summary, pd.DataFrame()

    rows = []

    for keys, group in detail_df.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)

        row = {
            "policy_key": "|".join(str(x) for x in keys),
            "sample_count": len(group),
            "open_count": int(group["_is_open"].sum()),
            "closed_count": int(group["_is_closed"].sum()),
            "breakeven_count": int(group["_is_breakeven"].sum()),
            "zero_realized_closed_count": int(group["_is_zero_realized_closed"].sum()),
            "missing_position_rows": int(group["_has_missing_position_checks"].sum()),
            "legacy_without_raw_ids": int(group["_is_legacy_without_raw_ids"].sum()),
            "possible_raw_id_position_rows": int(group["_possible_raw_id_position"].sum()),
        }

        for idx, col in enumerate(group_cols):
            row[col] = keys[idx]

        row["breakeven_rate"] = (
            round(row["breakeven_count"] / row["closed_count"], 4)
            if row["closed_count"]
            else 0.0
        )

        rows.append(row)

    detail_report = pd.DataFrame(rows).sort_values(
        ["sample_count", "breakeven_rate"],
        ascending=[False, False],
    )

    return summary, detail_report

def build_missed_profitable_rejected_candidates_report(df, min_samples):
    if df is None or df.empty:
        return pd.DataFrame()

    def text_series(name, default=""):
        if name in df.columns:
            return df[name].fillna(default).astype(str)
        return pd.Series([default] * len(df), index=df.index)

    def bool_series(frame, name):
        if name not in frame.columns:
            return pd.Series([False] * len(frame), index=frame.index)

        return (
            frame[name]
            .fillna(False)
            .astype(str)
            .str.upper()
            .isin(["TRUE", "1", "YES", "Y"])
        )

    source_events = text_series("source_events").str.upper()
    event = text_series("event").str.upper()
    setup_source_bucket = text_series("setup_source_bucket").str.upper()

    rejected_mask = (
        source_events.str.contains("CANDIDATE_REJECTED", na=False)
        | event.str.contains("CANDIDATE_REJECTED", na=False)
        | (setup_source_bucket == "REJECTED_CANDIDATE_TRACKED")
    )

    rejected_df = df[rejected_mask].copy()

    if rejected_df.empty:
        return pd.DataFrame()

    rejected_events = (
        rejected_df.get("source_events", "")
        .fillna("")
        .astype(str)
        .str.upper()
    )

    rejected_df["rejection_type"] = rejected_events.apply(
        lambda value: "LOW_RR" if "LOW_RR" in value else "STANDARD_REJECTION"
    )

    group_cols = [
        "strategy",
        "signal",
        "entry_model",
        "session",
        "market_condition",
        "rejection_type",
    ]

    for col in group_cols:
        if col not in rejected_df.columns:
            rejected_df[col] = "UNKNOWN"

    rows = []

    for keys, group in rejected_df.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)

        sample_count = len(group)

        hit_w10 = bool_series(group, "hit_plus_10")
        hit_tp = bool_series(group, "hit_tp")
        hit_sl = bool_series(group, "hit_sl")

        w10_count = int(hit_w10.sum())
        tp_count = int(hit_tp.sum())
        sl_count = int(hit_sl.sum())

        w10_rate = round(w10_count / sample_count, 4) if sample_count else 0.0
        tp_rate = round(tp_count / sample_count, 4) if sample_count else 0.0
        sl_rate = round(sl_count / sample_count, 4) if sample_count else 0.0

        missed_profit_score = round(
            (w10_rate * 40)
            + (tp_rate * 55)
            - (sl_rate * 45),
            2,
        )

        if sample_count < min_samples:
            recommendation = "TRACK_MORE"
            reason = f"not enough rejected samples: {sample_count}/{min_samples}"
        elif tp_rate >= 0.45 and sl_rate <= 0.35:
            recommendation = "ALLOW_RECOVERY"
            reason = "rejected candidates often reach TP with controlled SL"
        elif w10_rate >= 0.60 and sl_rate <= 0.45:
            recommendation = "ALLOW_BETTER_ENTRY_OR_SMALL_TP"
            reason = "rejected candidates often move +10 but need better TP/entry"
        elif sl_rate >= 0.50:
            recommendation = "KEEP_REJECTED"
            reason = "rejected candidates still hit SL too often"
        else:
            recommendation = "TRACK_MORE"
            reason = "mixed rejected-candidate behavior"

        row = {
            "policy_key": "|".join(str(x) for x in keys),
            "strategy": keys[0],
            "signal": keys[1],
            "entry_model": keys[2],
            "session": keys[3],
            "market_condition": keys[4],
            "rejection_type": keys[5],
            "sample_count": sample_count,
            "w10_count": w10_count,
            "tp_count": tp_count,
            "sl_count": sl_count,
            "w10_rate": w10_rate,
            "tp_rate": tp_rate,
            "sl_rate": sl_rate,
            "missed_profit_score": missed_profit_score,
            "recommendation": recommendation,
            "reason": reason,
        }

        rows.append(row)

    report = pd.DataFrame(rows)

    if report.empty:
        return report

    return report.sort_values(
        ["missed_profit_score", "sample_count"],
        ascending=[False, False],
    )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-samples", type=int, default=10)
    parser.add_argument(
        "--source-dir",
        type=str,
        default=str(DEFAULT_SOURCE_DIR),
        help="Account folder containing Statistics CSV files",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Optional output folder. Default: data/strategy_intelligence/<account_name>",
    )

    args = parser.parse_args()

    source_dir = Path(args.source_dir).resolve()

    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        output_dir = DEFAULT_OUTPUT_ROOT / source_dir.name

    output_dir.mkdir(parents=True, exist_ok=True)

    trades = read_source("trades", source_dir)
    setup_outcomes = read_source("setup_outcomes", source_dir)

    df = normalize_setup_outcomes(setup_outcomes, trades)
    trade_df = normalize_trades(trades)
    
    quality_report = build_data_quality_report(df, trade_df)

    quality_json = output_dir / "data_quality_report.json"

    with open(quality_json, "w", encoding="utf-8") as f:
        json.dump(quality_report, f, indent=2, ensure_ascii=False)
    
    
    legacy_intrabar_shadow = build_legacy_intrabar_shadow_report(trade_df)
    legacy_intrabar_shadow_csv = output_dir / "legacy_intrabar_shadow_report.csv"
    legacy_intrabar_shadow.to_csv(legacy_intrabar_shadow_csv, index=False)
    
    tracker_health_summary, tracker_health_detail = build_trade_tracker_health_report(trade_df)

    tracker_health_json = output_dir / "trade_tracker_health_report.json"
    tracker_health_csv = output_dir / "trade_tracker_health_by_bucket.csv"

    with open(tracker_health_json, "w", encoding="utf-8") as f:
        json.dump(tracker_health_summary, f, indent=2, ensure_ascii=False)

    tracker_health_detail.to_csv(tracker_health_csv, index=False)
    
    missed_rejected_report = build_missed_profitable_rejected_candidates_report(
        df,
        args.min_samples,
    )

    missed_rejected_csv = output_dir / "missed_profitable_rejected_candidates.csv"
    missed_rejected_report.to_csv(missed_rejected_csv, index=False)
    
    setup_intrabar_count = int((df["setup_source_bucket"] == "INTRABAR").sum())
    trade_intrabar_count = int((trade_df["execution_bucket"] == "INTRABAR").sum())

    if trade_intrabar_count > 0 and setup_intrabar_count == 0:
        print(
            "[WARN] Intrabar trades exist in trades.json, "
            "but no intrabar rows exist in setup_outcomes.json. "
            "Live intrabar setup outcome logging is probably missing."
        )

    if df.empty:
        raise SystemExit("[STOP] No setup outcome data found.")

    # =========================
    # Setup behavior reports
    # =========================
    group_levels = {
        "strategy": ["strategy"],
        "source_bucket": ["setup_source_bucket"],
        "strategy_source_bucket": ["strategy", "setup_source_bucket"],
        "strategy_signal": ["strategy", "signal"],
        "strategy_entry_model": ["strategy", "entry_model"],
        "strategy_session": ["strategy", "session"],
        "strategy_execution_bucket": ["strategy", "execution_bucket"],
        "strategy_market": ["strategy", "market_condition"],
        "normal_or_tracked_detail": [
            "strategy",
            "signal",
            "entry_model",
            "session",
            "market_condition",
            "setup_source_bucket",
        ],
        "detail": [
            "strategy",
            "signal",
            "entry_model",
            "session",
            "market_condition",
            "setup_source_bucket",
        ],
    }

    grouped_reports = {}

    for level_name, dimensions in group_levels.items():
        grouped_reports[level_name] = aggregate_group(df, dimensions, args.min_samples)
        
    filtered_report_definitions = {
        "normal_only": (
            df[df["setup_source_bucket"] == "NORMAL_OR_TRACKED"],
            ["strategy", "signal", "entry_model", "session", "market_condition"],
        ),
        "rejected_candidates_only": (
            df[df["setup_source_bucket"] == "REJECTED_CANDIDATE_TRACKED"],
            ["strategy", "signal", "entry_model", "session", "market_condition"],
        ),
        "mtf_conflict_only": (
            df[df["setup_source_bucket"] == "MTF_CONFLICT_TRACKED"],
            ["strategy", "signal", "entry_model", "session", "market_condition"],
        ),
        "intrabar_only": (
            df[df["setup_source_bucket"] == "INTRABAR"],
            ["strategy", "signal", "entry_model", "session", "market_condition"],
        ),
    }

    for level_name, (filtered_df, dimensions) in filtered_report_definitions.items():
        if filtered_df.empty:
            grouped_reports[level_name] = pd.DataFrame()
        else:
            grouped_reports[level_name] = aggregate_group(
                filtered_df,
                dimensions,
                args.min_samples,
            )

    summary = grouped_reports["strategy"]
    detail = grouped_reports["detail"]

    # =========================
    # Real executed trade reports
    # =========================
    trade_group_levels = {
        "trade_strategy": ["strategy"],
        "trade_execution_bucket": ["execution_bucket"],
        "trade_strategy_execution_bucket": ["strategy", "execution_bucket"],
        "trade_strategy_signal": ["strategy", "signal"],
        "trade_strategy_entry_model": ["strategy", "entry_model"],
        "trade_strategy_session": ["strategy", "session"],
        "trade_detail": [
            "strategy",
            "signal",
            "entry_model",
            "session",
            "market_condition",
            "execution_bucket",
        ],
    }

    trade_reports = {}

    for level_name, dimensions in trade_group_levels.items():
        trade_reports[level_name] = aggregate_trades(
            trade_df,
            dimensions,
            args.min_samples,
        )
        
    intrabar_trade_df = trade_df[trade_df["execution_bucket"] == "INTRABAR"]

    if intrabar_trade_df.empty:
        trade_reports["trade_intrabar_only"] = pd.DataFrame()
    else:
        trade_reports["trade_intrabar_only"] = aggregate_trades(
            intrabar_trade_df,
            ["strategy", "signal", "session", "market_condition", "execution_bucket"],
            args.min_samples,
        )

    # =========================
    # Output files
    # =========================
    normalized_csv = output_dir / "normalized_setup_outcomes.csv"
    normalized_trades_csv = output_dir / "normalized_trades.csv"
    summary_csv = output_dir / "strategy_performance_summary.csv"
    detail_csv = output_dir / "strategy_performance_detail.csv"
    report_json = output_dir / "strategy_performance_report.json"
    policy_json = output_dir / "strategy_advisory_policy.json"

    df.to_csv(normalized_csv, index=False)
    trade_df.to_csv(normalized_trades_csv, index=False)
    summary.to_csv(summary_csv, index=False)
    detail.to_csv(detail_csv, index=False)

    for level_name, report_df in grouped_reports.items():
        report_df.to_csv(
            output_dir / f"strategy_performance_{level_name}.csv",
            index=False,
        )

    for level_name, report_df in trade_reports.items():
        report_df.to_csv(
            output_dir / f"executed_performance_{level_name}.csv",
            index=False,
        )

    report = {
        "source_dir": str(source_dir),
        "min_samples": args.min_samples,
        "source_rows": len(df),
        "trade_rows": len(trade_df),
        "grouped_reports": {
            level_name: dataframe_to_records(report_df)
            for level_name, report_df in grouped_reports.items()
        },
        "trade_reports": {
            level_name: dataframe_to_records(report_df)
            for level_name, report_df in trade_reports.items()
        },
        "summary": dataframe_to_records(summary),
        "detail": dataframe_to_records(detail),
    }

    with open(report_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    policy_source = grouped_reports.get("strategy_source_bucket", detail)
    policy = build_execution_policy(policy_source)

    with open(policy_json, "w", encoding="utf-8") as f:
        json.dump(policy, f, indent=2, ensure_ascii=False)

    print("[DONE] Strategy intelligence generated:")
    print(f" - {normalized_csv}")
    print(f" - {normalized_trades_csv}")
    print(f" - {summary_csv}")
    print(f" - {detail_csv}")
    print(f" - {report_json}")
    print(f" - {policy_json}")
    print(f" - {quality_json}")
    print(f" - {legacy_intrabar_shadow_csv}")
    print(f" - {tracker_health_json}")
    print(f" - {tracker_health_csv}")
    print(f" - {missed_rejected_csv}")
    
    if quality_report.get("warnings"):
        print("\n[DATA QUALITY WARNINGS]")
        for warning in quality_report["warnings"]:
            print(f" - {warning}")

    if tracker_health_summary.get("warnings"):
        print("\n[TRADE TRACKER HEALTH WARNINGS]")
        for warning in tracker_health_summary["warnings"]:
            print(f" - {warning}")

    cols = [
        "policy_key",
        "sample_count",
        "decision",
        "synthetic_expectancy",
        "actual_expectancy",
        "w10_rate",
        "tp_rate",
        "sl_rate",
        "decision_reason",
    ]

    print("\n[TOP STRATEGY DECISIONS]")
    if summary.empty:
        print("[WARN] No setup behavior summary generated.")
    else:
        print(summary[cols].head(30).to_string(index=False))

    source_bucket_report = grouped_reports.get("source_bucket", pd.DataFrame())
    strategy_source_bucket_report = grouped_reports.get("strategy_source_bucket", pd.DataFrame())
    normal_only_report = grouped_reports.get("normal_only", pd.DataFrame())
    rejected_only_report = grouped_reports.get("rejected_candidates_only", pd.DataFrame())
    mtf_only_report = grouped_reports.get("mtf_conflict_only", pd.DataFrame())
    intrabar_only_report = grouped_reports.get("intrabar_only", pd.DataFrame())

    print("\n[TOP SOURCE BUCKET DECISIONS]")
    if source_bucket_report.empty:
        print("[WARN] No source bucket report generated.")
    else:
        print(source_bucket_report[cols].head(30).to_string(index=False))

    print("\n[TOP STRATEGY + SOURCE BUCKET DECISIONS]")
    if strategy_source_bucket_report.empty:
        print("[WARN] No strategy source bucket report generated.")
    else:
        print(strategy_source_bucket_report[cols].head(30).to_string(index=False))

    print("\n[TOP NORMAL/TRACKED SETUP DECISIONS]")
    if normal_only_report.empty:
        print("[WARN] No normal/tracked setup report generated.")
    else:
        print(normal_only_report[cols].head(30).to_string(index=False))

    print("\n[TOP REJECTED CANDIDATE DECISIONS]")
    if rejected_only_report.empty:
        print("[WARN] No rejected candidate report generated.")
    else:
        print(rejected_only_report[cols].head(30).to_string(index=False))

    print("\n[TOP MISSED PROFITABLE REJECTED CANDIDATES]")
    if missed_rejected_report.empty:
        print("[WARN] No missed profitable rejected candidate report generated.")
    else:
        missed_cols = [
            "policy_key",
            "sample_count",
            "w10_rate",
            "tp_rate",
            "sl_rate",
            "missed_profit_score",
            "recommendation",
            "reason",
        ]
        print(missed_rejected_report[missed_cols].head(30).to_string(index=False))

    print("\n[TOP MTF CONFLICT DECISIONS]")
    if mtf_only_report.empty:
        print("[WARN] No MTF conflict report generated.")
    else:
        print(mtf_only_report[cols].head(30).to_string(index=False))

    print("\n[TOP INTRABAR DECISIONS]")
    if intrabar_only_report.empty:
        print("[WARN] No intrabar report generated.")
    else:
        print(intrabar_only_report[cols].head(30).to_string(index=False))

    print("\n[TOP DETAILED DECISIONS]")
    if detail.empty:
        print("[WARN] No grouped detail generated.")
    else:
        print(detail[cols].head(30).to_string(index=False))

    trade_summary = trade_reports.get("trade_strategy", pd.DataFrame())

    trade_cols = [
        "policy_key",
        "sample_count",
        "closed_count",
        "realized_count",
        "main_count",
        "extra_count",
        "decision",
        "total_profit",
        "actual_expectancy",
        "closed_expectancy",
        "realized_expectancy",
        "win_rate",
        "loss_rate",
        "breakeven_rate",
        "decision_reason",
    ]

    print("\n[TOP EXECUTED TRADE DECISIONS]")
    if trade_summary.empty:
        print("[WARN] No executed trade summary generated.")
    else:
        print(trade_summary[trade_cols].head(30).to_string(index=False))

    intrabar_trade_report = trade_reports.get("trade_intrabar_only", pd.DataFrame())

    print("\n[TOP INTRABAR TRADE DIAGNOSTIC]")
    if intrabar_trade_report.empty:
        print("[WARN] No intrabar trades found in trades.json.")
    else:
        print(intrabar_trade_report[trade_cols].head(30).to_string(index=False))

if __name__ == "__main__":
    main()