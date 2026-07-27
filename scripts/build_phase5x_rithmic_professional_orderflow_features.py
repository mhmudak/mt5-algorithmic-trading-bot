from __future__ import annotations

import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any


PHASE = "PHASE_5X_RITHMIC_PROFESSIONAL_ORDERFLOW_FEATURES"

ROOT = Path(".")
ORDER_FLOW_DIR = ROOT / "data" / "order_flow" / "rithmic"
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

SYMBOL = "MGCQ6"

STATE_PATH = ORDER_FLOW_DIR / f"{SYMBOL}_phase5c_rithmic_state_latest.json"
REGISTRATION_PATH = ORDER_FLOW_DIR / "phase5v_rithmic_observe_only_provider_registration.json"

OUT_JSON = ORDER_FLOW_DIR / "phase5x_rithmic_professional_orderflow_features.json"
OUT_TXT = ORDER_FLOW_DIR / "phase5x_rithmic_professional_orderflow_features_summary.txt"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def deep_find(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]

        for value in obj.values():
            found = deep_find(value, key)
            if found is not None:
                return found

    elif isinstance(obj, list):
        for item in obj:
            found = deep_find(item, key)
            if found is not None:
                return found

    return None


def extract_order_book(state: dict[str, Any]) -> dict[str, Any]:
    book = state.get("order_book") or deep_find(state, "order_book") or {}

    if not isinstance(book, dict):
        return {}

    return book


def extract_volume_profile(state: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        state.get("volume_profile"),
        state.get("volume_at_price"),
        deep_find(state, "volume_profile"),
        deep_find(state, "volume_at_price"),
        deep_find(state, "vap"),
    ]

    for candidate in candidates:
        if isinstance(candidate, list):
            levels = []
            for item in candidate:
                if not isinstance(item, dict):
                    continue

                price = as_float(item.get("price"))
                volume = as_float(
                    item.get("volume")
                    or item.get("total_volume")
                    or item.get("size")
                    or item.get("qty")
                )

                buy_volume = as_float(item.get("buy_volume"))
                sell_volume = as_float(item.get("sell_volume"))

                if price > 0 and volume > 0:
                    levels.append({
                        "price": price,
                        "volume": volume,
                        "buy_volume": buy_volume,
                        "sell_volume": sell_volume,
                    })

            if levels:
                return sorted(levels, key=lambda x: x["price"])

        if isinstance(candidate, dict):
            levels = []
            for price_raw, value in candidate.items():
                price = as_float(price_raw)

                if isinstance(value, dict):
                    volume = as_float(
                        value.get("volume")
                        or value.get("total_volume")
                        or value.get("size")
                        or value.get("qty")
                    )
                    buy_volume = as_float(value.get("buy_volume"))
                    sell_volume = as_float(value.get("sell_volume"))
                else:
                    volume = as_float(value)
                    buy_volume = 0.0
                    sell_volume = 0.0

                if price > 0 and volume > 0:
                    levels.append({
                        "price": price,
                        "volume": volume,
                        "buy_volume": buy_volume,
                        "sell_volume": sell_volume,
                    })

            if levels:
                return sorted(levels, key=lambda x: x["price"])

    latest_trade_price = as_float(deep_find(state, "price") or deep_find(state, "rolling_poc_price"))
    latest_trade_count = as_float(deep_find(state, "rolling_trade_count"))

    if latest_trade_price > 0 and latest_trade_count > 0:
        return [{
            "price": latest_trade_price,
            "volume": latest_trade_count,
            "buy_volume": 0.0,
            "sell_volume": 0.0,
        }]

    return []


def compute_profile_features(levels: list[dict[str, Any]], value_area_ratio: float = 0.70) -> dict[str, Any]:
    if not levels:
        return {
            "available": False,
            "poc": None,
            "vah": None,
            "val": None,
            "total_volume": 0,
            "value_area_ratio": value_area_ratio,
            "levels_used": 0,
            "warning": "NO_VOLUME_PROFILE_AVAILABLE",
        }

    total_volume = sum(as_float(x.get("volume")) for x in levels)
    if total_volume <= 0:
        return {
            "available": False,
            "poc": None,
            "vah": None,
            "val": None,
            "total_volume": 0,
            "value_area_ratio": value_area_ratio,
            "levels_used": len(levels),
            "warning": "ZERO_VOLUME_PROFILE",
        }

    poc_level = max(levels, key=lambda x: as_float(x.get("volume")))
    poc = as_float(poc_level.get("price"))

    sorted_by_distance = sorted(
        levels,
        key=lambda x: (abs(as_float(x.get("price")) - poc), -as_float(x.get("volume"))),
    )

    selected = []
    selected_volume = 0.0
    target_volume = total_volume * value_area_ratio

    for level in sorted_by_distance:
        selected.append(level)
        selected_volume += as_float(level.get("volume"))

        if selected_volume >= target_volume:
            break

    prices = [as_float(x.get("price")) for x in selected if as_float(x.get("price")) > 0]

    return {
        "available": True,
        "poc": poc,
        "vah": max(prices) if prices else poc,
        "val": min(prices) if prices else poc,
        "total_volume": round(total_volume, 6),
        "value_area_volume": round(selected_volume, 6),
        "value_area_ratio": value_area_ratio,
        "levels_used": len(levels),
    }


def detect_liquidity_walls(book: dict[str, Any]) -> dict[str, Any]:
    bid_levels = book.get("bid_levels") or []
    ask_levels = book.get("ask_levels") or []

    all_sizes = []
    for level in bid_levels + ask_levels:
        size = as_float(level.get("size"))
        if size > 0:
            all_sizes.append(size)

    if not all_sizes:
        return {
            "available": False,
            "walls": [],
            "warning": "NO_DOM_SIZES_AVAILABLE",
        }

    median_size = statistics.median(all_sizes)
    threshold = max(median_size * 3, 10)

    walls = []

    for side, levels in [("BID", bid_levels), ("ASK", ask_levels)]:
        for level in levels[:20]:
            size = as_float(level.get("size"))
            price = as_float(level.get("price"))

            if price > 0 and size >= threshold:
                walls.append({
                    "side": side,
                    "price": price,
                    "size": size,
                    "threshold": threshold,
                    "level": level.get("level"),
                })

    walls = sorted(walls, key=lambda x: x["size"], reverse=True)

    return {
        "available": True,
        "median_size": median_size,
        "wall_threshold": threshold,
        "walls": walls[:10],
    }


def detect_thin_book(book: dict[str, Any]) -> dict[str, Any]:
    bid_depth = as_float(book.get("bid_depth"))
    ask_depth = as_float(book.get("ask_depth"))

    bid_levels = book.get("bid_levels") or []
    ask_levels = book.get("ask_levels") or []

    best_bid_size = as_float(bid_levels[0].get("size")) if bid_levels else 0.0
    best_ask_size = as_float(ask_levels[0].get("size")) if ask_levels else 0.0

    total_depth = bid_depth + ask_depth

    thin = bool(
        total_depth <= 20
        or best_bid_size <= 1
        or best_ask_size <= 1
    )

    return {
        "thin_book_warning": thin,
        "bid_depth": bid_depth,
        "ask_depth": ask_depth,
        "total_depth": total_depth,
        "best_bid_size": best_bid_size,
        "best_ask_size": best_ask_size,
        "interpretation": (
            "Thin book / fragile liquidity. Be careful with manual entries."
            if thin
            else "Book depth not thin by current heuristic."
        ),
    }


def detect_absorption(state: dict[str, Any], book: dict[str, Any]) -> dict[str, Any]:
    delta = as_float(deep_find(state, "rolling_delta") or deep_find(state, "delta"))
    cumulative_delta = as_float(deep_find(state, "session_cumulative_delta") or deep_find(state, "cumulative_delta"))

    bid_depth = as_float(book.get("bid_depth"))
    ask_depth = as_float(book.get("ask_depth"))
    imbalance = as_float(book.get("depth_imbalance"))

    signals = []

    if delta < 0 and bid_depth > ask_depth * 1.5:
        signals.append({
            "type": "POTENTIAL_BUYER_ABSORPTION",
            "reason": "Negative trade delta but bid depth is much larger than ask depth.",
            "delta": delta,
            "bid_depth": bid_depth,
            "ask_depth": ask_depth,
        })

    if delta > 0 and ask_depth > bid_depth * 1.5:
        signals.append({
            "type": "POTENTIAL_SELLER_ABSORPTION",
            "reason": "Positive trade delta but ask depth is much larger than bid depth.",
            "delta": delta,
            "bid_depth": bid_depth,
            "ask_depth": ask_depth,
        })

    if cumulative_delta < 0 and imbalance > 0.25:
        signals.append({
            "type": "POTENTIAL_BUYER_ABSORPTION_SESSION",
            "reason": "Cumulative delta negative while DOM is bid-heavy.",
            "cumulative_delta": cumulative_delta,
            "depth_imbalance": imbalance,
        })

    if cumulative_delta > 0 and imbalance < -0.25:
        signals.append({
            "type": "POTENTIAL_SELLER_ABSORPTION_SESSION",
            "reason": "Cumulative delta positive while DOM is ask-heavy.",
            "cumulative_delta": cumulative_delta,
            "depth_imbalance": imbalance,
        })

    return {
        "available": True,
        "signals": signals,
        "absorption_detected": bool(signals),
        "warning": "Heuristic only. Needs historical validation before decision influence.",
    }


def detect_footprint_imbalance(profile_levels: list[dict[str, Any]]) -> dict[str, Any]:
    imbalances = []

    for level in profile_levels:
        price = as_float(level.get("price"))
        buy_volume = as_float(level.get("buy_volume"))
        sell_volume = as_float(level.get("sell_volume"))
        total = buy_volume + sell_volume

        if price <= 0 or total <= 0:
            continue

        ratio = (buy_volume - sell_volume) / total

        if abs(ratio) >= 0.60:
            imbalances.append({
                "price": price,
                "buy_volume": buy_volume,
                "sell_volume": sell_volume,
                "imbalance_ratio": round(ratio, 6),
                "side": "BUY_IMBALANCE" if ratio > 0 else "SELL_IMBALANCE",
            })

    return {
        "available": bool(profile_levels),
        "imbalance_count": len(imbalances),
        "imbalances": imbalances[:20],
        "warning": (
            "Production-grade footprint needs more per-price aggressive buy/sell data."
            if not imbalances
            else "Footprint imbalance heuristic detected levels."
        ),
    }


def main() -> None:
    ORDER_FLOW_DIR.mkdir(parents=True, exist_ok=True)
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    state = load_json(STATE_PATH)
    registration = load_json(REGISTRATION_PATH)

    book = extract_order_book(state)
    profile_levels = extract_volume_profile(state)
    profile = compute_profile_features(profile_levels)

    walls = detect_liquidity_walls(book)
    thin_book = detect_thin_book(book)
    absorption = detect_absorption(state, book)
    footprint = detect_footprint_imbalance(profile_levels)

    provider_registered = registration.get("registration_status") == "REGISTERED_OBSERVE_ONLY"

    report = {
        "phase": PHASE,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "symbol": SYMBOL,
        "provider": "RITHMIC_R_PROTOCOL",
        "mode": "OBSERVE_ONLY",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "trade_action": "NO_AUTO_TRADE",
        "manual_review_only": True,
        "provider_registered_observe_only": provider_registered,
        "feature_status": "BUILT_OBSERVE_ONLY",
        "volume_profile": profile,
        "dom": {
            "bid_depth": as_float(book.get("bid_depth")),
            "ask_depth": as_float(book.get("ask_depth")),
            "depth_imbalance": book.get("depth_imbalance"),
            "top_bid_price": book.get("top_bid_price"),
            "top_ask_price": book.get("top_ask_price"),
            "bid_level_count": len(book.get("bid_levels") or []),
            "ask_level_count": len(book.get("ask_levels") or []),
        },
        "liquidity_walls": walls,
        "thin_book": thin_book,
        "absorption": absorption,
        "footprint_imbalance": footprint,
        "not_yet_decision_grade": [
            "Absorption is heuristic only.",
            "Iceberg/spoofing/pulling-stacking require multi-snapshot history.",
            "Footprint needs stronger per-price aggressive buy/sell accumulation.",
            "XAUUSD vs MGCQ6/GCQ6 basis calibration not added yet.",
            "Automatic decision influence remains disabled.",
        ],
        "recommendation": (
            "Use these features in Telegram/manual review only. "
            "Next phase should collect long-session history for validation, pulling/stacking, spoofing/iceberg suspicion, and basis calibration."
        ),
    }

    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "[PHASE 5X RITHMIC PROFESSIONAL ORDER-FLOW FEATURES]",
        f"updated_at = {report['updated_at']}",
        f"symbol = {SYMBOL}",
        f"provider = {report['provider']}",
        f"mode = {report['mode']}",
        f"decision_impact = {report['decision_impact']}",
        f"can_influence_decision = {report['can_influence_decision']}",
        f"safe_for_execution = {report['safe_for_execution']}",
        f"trade_action = {report['trade_action']}",
        f"provider_registered_observe_only = {provider_registered}",
        "",
        "[VOLUME PROFILE]",
        f"available = {profile.get('available')}",
        f"session_poc = {profile.get('poc')}",
        f"value_area_high = {profile.get('vah')}",
        f"value_area_low = {profile.get('val')}",
        f"total_volume = {profile.get('total_volume')}",
        f"levels_used = {profile.get('levels_used')}",
        "",
        "[DOM]",
        f"bid_depth = {report['dom']['bid_depth']}",
        f"ask_depth = {report['dom']['ask_depth']}",
        f"depth_imbalance = {report['dom']['depth_imbalance']}",
        f"top_bid_price = {report['dom']['top_bid_price']}",
        f"top_ask_price = {report['dom']['top_ask_price']}",
        f"bid_level_count = {report['dom']['bid_level_count']}",
        f"ask_level_count = {report['dom']['ask_level_count']}",
        "",
        "[LIQUIDITY WALLS]",
        f"available = {walls.get('available')}",
        f"wall_count = {len(walls.get('walls') or [])}",
        f"top_walls = {walls.get('walls')[:5] if walls.get('walls') else []}",
        "",
        "[THIN BOOK]",
        f"thin_book_warning = {thin_book.get('thin_book_warning')}",
        f"interpretation = {thin_book.get('interpretation')}",
        "",
        "[ABSORPTION]",
        f"absorption_detected = {absorption.get('absorption_detected')}",
        f"signals = {absorption.get('signals')}",
        "",
        "[FOOTPRINT]",
        f"available = {footprint.get('available')}",
        f"imbalance_count = {footprint.get('imbalance_count')}",
        f"warning = {footprint.get('warning')}",
        "",
        "[NOT YET DECISION GRADE]",
        *[f"- {item}" for item in report["not_yet_decision_grade"]],
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