from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PHASE = "PHASE_5Z_RITHMIC_LONG_SESSION_ORDERFLOW_ANALYZER"

ROOT = Path(__file__).resolve().parents[1]
ORDER_FLOW_DIR = ROOT / "data" / "order_flow" / "rithmic"

OUT_JSON = ORDER_FLOW_DIR / "phase5z_rithmic_long_session_orderflow_analysis.json"
OUT_TXT = ORDER_FLOW_DIR / "phase5z_rithmic_long_session_orderflow_analysis_summary.txt"


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    if not path.exists():
        return rows

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line:
            continue

        try:
            obj = json.loads(line)
        except Exception:
            continue

        if isinstance(obj, dict):
            rows.append(obj)

    return rows


def normalize_levels(levels: Any) -> list[dict[str, float]]:
    normalized: list[dict[str, float]] = []

    if not isinstance(levels, list):
        return normalized

    for idx, item in enumerate(levels, start=1):
        if not isinstance(item, dict):
            continue

        price = as_float(item.get("price"))
        size = as_float(item.get("size"))
        level = as_float(item.get("level"), default=float(idx))

        if price > 0:
            normalized.append({
                "price": round(price, 4),
                "size": size,
                "level": level,
            })

    return normalized


def collect_basic_quality(records: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = [r.get("metrics") or {} for r in records]

    positive_bbo = [
        m for m in metrics
        if as_float(m.get("bid")) > 0 and as_float(m.get("ask")) > 0
    ]

    two_sided_dom = [
        m for m in metrics
        if as_float(m.get("bid_depth")) > 0 and as_float(m.get("ask_depth")) > 0
    ]

    spreads = [
        as_float(m.get("spread"))
        for m in metrics
        if as_float(m.get("spread")) > 0
    ]

    trade_counts = [
        as_float(m.get("rolling_trade_count"))
        for m in metrics
    ]

    return {
        "sample_count": len(records),
        "positive_bbo_rate": round(len(positive_bbo) / len(records), 4) if records else 0,
        "two_sided_dom_rate": round(len(two_sided_dom) / len(records), 4) if records else 0,
        "avg_spread": round(sum(spreads) / len(spreads), 6) if spreads else None,
        "max_spread": max(spreads) if spreads else None,
        "avg_rolling_trade_count": round(sum(trade_counts) / len(trade_counts), 4) if trade_counts else 0,
        "max_rolling_trade_count": max(trade_counts) if trade_counts else 0,
    }


def collect_price_level_history(records: list[dict[str, Any]]) -> dict[str, dict[float, list[dict[str, Any]]]]:
    history: dict[str, dict[float, list[dict[str, Any]]]] = {
        "BID": defaultdict(list),
        "ASK": defaultdict(list),
    }

    for idx, record in enumerate(records):
        elapsed = as_float(record.get("elapsed_seconds"))
        bid_levels = normalize_levels(record.get("top_bid_levels"))
        ask_levels = normalize_levels(record.get("top_ask_levels"))

        for side, levels in [("BID", bid_levels), ("ASK", ask_levels)]:
            for level in levels:
                history[side][level["price"]].append({
                    "index": idx,
                    "elapsed_seconds": elapsed,
                    "size": level["size"],
                    "level": level["level"],
                })

    return history


def analyze_liquidity_walls(
    history: dict[str, dict[float, list[dict[str, Any]]]],
    *,
    total_samples: int,
) -> list[dict[str, Any]]:
    all_sizes = []

    for side in ["BID", "ASK"]:
        for observations in history[side].values():
            for obs in observations:
                size = as_float(obs.get("size"))
                if size > 0:
                    all_sizes.append(size)

    if not all_sizes:
        return []

    median_size = statistics.median(all_sizes)
    wall_threshold = max(median_size * 3.0, 10.0)

    walls = []

    for side in ["BID", "ASK"]:
        for price, observations in history[side].items():
            sizes = [as_float(o.get("size")) for o in observations if as_float(o.get("size")) > 0]

            if not sizes:
                continue

            max_size = max(sizes)
            avg_size = sum(sizes) / len(sizes)
            persistence_rate = len(sizes) / max(total_samples, 1)

            if max_size >= wall_threshold:
                walls.append({
                    "side": side,
                    "price": price,
                    "max_size": round(max_size, 6),
                    "avg_size": round(avg_size, 6),
                    "observations": len(sizes),
                    "persistence_rate": round(persistence_rate, 4),
                    "wall_threshold": round(wall_threshold, 6),
                    "classification": (
                        "PERSISTENT_LIQUIDITY_WALL"
                        if persistence_rate >= 0.50
                        else "TEMPORARY_LIQUIDITY_WALL"
                    ),
                })

    return sorted(walls, key=lambda x: (x["max_size"], x["persistence_rate"]), reverse=True)[:20]


def analyze_pulling_stacking(
    history: dict[str, dict[float, list[dict[str, Any]]]],
) -> dict[str, Any]:
    events = []

    for side in ["BID", "ASK"]:
        for price, observations in history[side].items():
            ordered = sorted(observations, key=lambda x: x["index"])

            for prev, cur in zip(ordered, ordered[1:]):
                prev_size = as_float(prev.get("size"))
                cur_size = as_float(cur.get("size"))

                if prev_size <= 0:
                    continue

                change = cur_size - prev_size
                change_ratio = change / prev_size

                if change >= 10 and change_ratio >= 0.50:
                    events.append({
                        "type": "STACKING",
                        "side": side,
                        "price": price,
                        "from_size": prev_size,
                        "to_size": cur_size,
                        "change": round(change, 6),
                        "change_ratio": round(change_ratio, 6),
                        "from_index": prev.get("index"),
                        "to_index": cur.get("index"),
                    })

                elif change <= -10 and change_ratio <= -0.50:
                    events.append({
                        "type": "PULLING",
                        "side": side,
                        "price": price,
                        "from_size": prev_size,
                        "to_size": cur_size,
                        "change": round(change, 6),
                        "change_ratio": round(change_ratio, 6),
                        "from_index": prev.get("index"),
                        "to_index": cur.get("index"),
                    })

    stacking = [e for e in events if e["type"] == "STACKING"]
    pulling = [e for e in events if e["type"] == "PULLING"]

    return {
        "event_count": len(events),
        "stacking_count": len(stacking),
        "pulling_count": len(pulling),
        "events": events[:50],
    }


def analyze_spoofing_suspicion(
    walls: list[dict[str, Any]],
    pulling_stacking: dict[str, Any],
) -> dict[str, Any]:
    suspicious = []

    pulling_events = pulling_stacking.get("events") or []

    for wall in walls:
        if wall.get("classification") != "TEMPORARY_LIQUIDITY_WALL":
            continue

        side = wall.get("side")
        price = wall.get("price")

        matching_pulls = [
            e for e in pulling_events
            if e.get("type") == "PULLING"
            and e.get("side") == side
            and as_float(e.get("price")) == as_float(price)
        ]

        if matching_pulls and as_float(wall.get("max_size")) >= as_float(wall.get("wall_threshold")):
            suspicious.append({
                "type": "SUSPECTED_SPOOFING_OR_FAST_PULL",
                "side": side,
                "price": price,
                "max_wall_size": wall.get("max_size"),
                "persistence_rate": wall.get("persistence_rate"),
                "pull_events": matching_pulls[:5],
                "warning": "Suspicion only. Not proof of spoofing. Needs tick-by-tick/order-id evidence.",
            })

    return {
        "spoofing_suspicion_count": len(suspicious),
        "items": suspicious[:20],
        "warning": "Spoofing cannot be confirmed from aggregated DOM snapshots. This is only a risk flag.",
    }


def analyze_iceberg_suspicion(records: list[dict[str, Any]], walls: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = [r.get("metrics") or {} for r in records]
    trade_count_max = max([as_float(m.get("rolling_trade_count")) for m in metrics], default=0.0)

    suspected = []

    for wall in walls:
        if wall.get("classification") != "PERSISTENT_LIQUIDITY_WALL":
            continue

        if as_float(wall.get("persistence_rate")) >= 0.65 and trade_count_max > 0:
            suspected.append({
                "type": "POSSIBLE_ICEBERG_OR_RELOADING_LIQUIDITY",
                "side": wall.get("side"),
                "price": wall.get("price"),
                "max_size": wall.get("max_size"),
                "avg_size": wall.get("avg_size"),
                "persistence_rate": wall.get("persistence_rate"),
                "warning": "Suspicion only. True iceberg detection needs order/execution refresh evidence.",
            })

    return {
        "iceberg_suspicion_count": len(suspected),
        "items": suspected[:20],
        "warning": "Iceberg cannot be confirmed from this feed snapshot alone. Treat as possible reloading liquidity only.",
    }


def analyze_profile_from_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    volume_by_price: dict[float, float] = defaultdict(float)

    for record in records:
        metrics = record.get("metrics") or {}
        price = as_float(metrics.get("latest_trade_price")) or as_float(metrics.get("rolling_poc_price"))
        size = as_float(metrics.get("latest_trade_size")) or as_float(metrics.get("rolling_trade_count")) or 1.0

        if price > 0:
            volume_by_price[round(price, 4)] += max(size, 1.0)

    if not volume_by_price:
        return {
            "available": False,
            "poc": None,
            "vah": None,
            "val": None,
            "total_volume": 0,
            "levels_used": 0,
            "warning": "NO_TRADE_PRICE_HISTORY_AVAILABLE",
        }

    total_volume = sum(volume_by_price.values())
    poc = max(volume_by_price.items(), key=lambda x: x[1])[0]

    target = total_volume * 0.70
    selected = []
    selected_volume = 0.0

    for price, volume in sorted(volume_by_price.items(), key=lambda x: (abs(x[0] - poc), -x[1])):
        selected.append(price)
        selected_volume += volume

        if selected_volume >= target:
            break

    return {
        "available": True,
        "poc": poc,
        "vah": max(selected),
        "val": min(selected),
        "total_volume": round(total_volume, 6),
        "value_area_volume": round(selected_volume, 6),
        "levels_used": len(volume_by_price),
        "warning": (
            "Profile is still weak if trade flow is low. Use as context only."
        ),
    }


def classify_decision_readiness(
    quality: dict[str, Any],
    profile: dict[str, Any],
    pulling_stacking: dict[str, Any],
) -> dict[str, Any]:
    sample_count = as_float(quality.get("sample_count"))
    positive_bbo_rate = as_float(quality.get("positive_bbo_rate"))
    two_sided_dom_rate = as_float(quality.get("two_sided_dom_rate"))
    max_spread = as_float(quality.get("max_spread"), default=999.0)
    max_trade_count = as_float(quality.get("max_rolling_trade_count"))

    checks = {
        "enough_samples": sample_count >= 30,
        "positive_bbo_rate_ok": positive_bbo_rate >= 0.95,
        "two_sided_dom_rate_ok": two_sided_dom_rate >= 0.95,
        "spread_ok": 0 < max_spread <= 1.0,
        "trade_flow_ok": max_trade_count >= 5,
        "profile_available": bool(profile.get("available")),
        "dom_dynamics_available": pulling_stacking.get("event_count", 0) > 0,
    }

    passed = [k for k, v in checks.items() if v]
    failed = [k for k, v in checks.items() if not v]

    return {
        "decision_grade_ready": False,
        "automation_allowed": False,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "checks": checks,
        "passed": passed,
        "failed": failed,
        "readiness_status": (
            "LONG_SESSION_OBSERVE_ONLY_GOOD_BUT_NOT_DECISION_GRADE"
            if len(failed) <= 3
            else "NOT_DECISION_GRADE_YET"
        ),
        "reason": "Industrial path requires more samples, stronger trade flow, repeated sessions, and XAUUSD/futures basis calibration before decision influence.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="MGCQ6")
    args = parser.parse_args()

    symbol = args.symbol.upper()
    jsonl_path = ORDER_FLOW_DIR / f"{symbol}_phase5y_long_session_history.jsonl"

    records = load_jsonl(jsonl_path)
    quality = collect_basic_quality(records)
    history = collect_price_level_history(records)

    walls = analyze_liquidity_walls(history, total_samples=len(records))
    pulling_stacking = analyze_pulling_stacking(history)
    spoofing = analyze_spoofing_suspicion(walls, pulling_stacking)
    iceberg = analyze_iceberg_suspicion(records, walls)
    profile = analyze_profile_from_records(records)
    readiness = classify_decision_readiness(quality, profile, pulling_stacking)

    report = {
        "phase": PHASE,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "symbol": symbol,
        "input_jsonl": str(jsonl_path),
        "mode": "OBSERVE_ONLY",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "trade_action": "NO_AUTO_TRADE",
        "quality": quality,
        "session_profile": profile,
        "liquidity_walls": walls,
        "pulling_stacking": pulling_stacking,
        "spoofing_suspicion": spoofing,
        "iceberg_suspicion": iceberg,
        "decision_readiness": readiness,
        "recommendation": (
            "Use Phase 5Z only for manual review and research. "
            "Next steps: longer sessions, GCQ6 validation, XAUUSD futures basis calibration, and repeated-session acceptance."
        ),
    }

    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "[PHASE 5Z RITHMIC LONG-SESSION ORDER-FLOW ANALYZER]",
        f"updated_at = {report['updated_at']}",
        f"symbol = {symbol}",
        f"mode = {report['mode']}",
        f"decision_impact = {report['decision_impact']}",
        f"can_influence_decision = {report['can_influence_decision']}",
        f"safe_for_execution = {report['safe_for_execution']}",
        f"trade_action = {report['trade_action']}",
        "",
        "[QUALITY]",
        f"sample_count = {quality.get('sample_count')}",
        f"positive_bbo_rate = {quality.get('positive_bbo_rate')}",
        f"two_sided_dom_rate = {quality.get('two_sided_dom_rate')}",
        f"avg_spread = {quality.get('avg_spread')}",
        f"max_spread = {quality.get('max_spread')}",
        f"avg_rolling_trade_count = {quality.get('avg_rolling_trade_count')}",
        f"max_rolling_trade_count = {quality.get('max_rolling_trade_count')}",
        "",
        "[SESSION PROFILE]",
        f"available = {profile.get('available')}",
        f"poc = {profile.get('poc')}",
        f"vah = {profile.get('vah')}",
        f"val = {profile.get('val')}",
        f"total_volume = {profile.get('total_volume')}",
        f"levels_used = {profile.get('levels_used')}",
        f"warning = {profile.get('warning')}",
        "",
        "[LIQUIDITY WALLS]",
        f"wall_count = {len(walls)}",
        f"top_walls = {walls[:5]}",
        "",
        "[PULLING / STACKING]",
        f"event_count = {pulling_stacking.get('event_count')}",
        f"stacking_count = {pulling_stacking.get('stacking_count')}",
        f"pulling_count = {pulling_stacking.get('pulling_count')}",
        f"top_events = {pulling_stacking.get('events')[:5]}",
        "",
        "[SPOOFING SUSPICION]",
        f"spoofing_suspicion_count = {spoofing.get('spoofing_suspicion_count')}",
        f"warning = {spoofing.get('warning')}",
        "",
        "[ICEBERG SUSPICION]",
        f"iceberg_suspicion_count = {iceberg.get('iceberg_suspicion_count')}",
        f"warning = {iceberg.get('warning')}",
        "",
        "[DECISION READINESS]",
        f"readiness_status = {readiness.get('readiness_status')}",
        f"decision_grade_ready = {readiness.get('decision_grade_ready')}",
        f"automation_allowed = {readiness.get('automation_allowed')}",
        f"passed = {readiness.get('passed')}",
        f"failed = {readiness.get('failed')}",
        f"reason = {readiness.get('reason')}",
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
        "",
        f"json = {OUT_JSON}",
        f"summary = {OUT_TXT}",
    ]

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()