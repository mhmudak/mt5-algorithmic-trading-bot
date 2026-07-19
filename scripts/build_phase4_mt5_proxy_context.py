import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

REPORT_PATH = INTEL_DIR / "phase4_mt5_proxy_context_report.json"
SUMMARY_PATH = INTEL_DIR / "phase4_mt5_proxy_context_summary.txt"


def main():
    from src.mt5_proxy_context import build_mt5_proxy_context

    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    context = build_mt5_proxy_context(
        symbol="XAUUSD",
        timeframe="M15",
        bars=500,
        bin_size=0.50,
    )

    profile = context.get("profile") or {}
    volume_context = context.get("volume_context") or {}
    candle_context = context.get("candle_context") or {}

    report = {
        "phase": "PHASE_4H_MT5_PROXY_CONTEXT",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "context": context,
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "recommendation": (
            "MT5_PROXY_CONTEXT_AVAILABLE_FOR_RESEARCH_ONLY"
            if context.get("available")
            else "MT5_PROXY_CONTEXT_UNAVAILABLE"
        ),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 4H MT5 PROXY CONTEXT]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"decision = {report['decision']}",
        "",
        "[CONTEXT]",
        f"context_family = {context.get('context_family')}",
        f"available = {context.get('available')}",
        f"status = {context.get('status')}",
        f"is_real_order_flow = {context.get('is_real_order_flow')}",
        f"data_quality = {context.get('data_quality')}",
        f"decision_impact = {context.get('decision_impact')}",
        f"price_vs_value_area = {context.get('price_vs_value_area')}",
        "",
        "[PROXY PROFILE]",
        f"proxy_poc = {profile.get('poc')}",
        f"proxy_value_area_low = {profile.get('value_area_low')}",
        f"proxy_value_area_high = {profile.get('value_area_high')}",
        f"proxy_total_tick_volume = {profile.get('total_tick_volume')}",
        "",
        "[RECENT TICK VOLUME]",
        f"latest_tick_volume = {volume_context.get('latest_tick_volume')}",
        f"average_tick_volume = {volume_context.get('average_tick_volume')}",
        f"tick_volume_zscore = {volume_context.get('tick_volume_zscore')}",
        f"volume_state = {volume_context.get('volume_state')}",
        "",
        "[LATEST CANDLE]",
        f"latest_close = {candle_context.get('latest_close')}",
        f"candle_direction = {candle_context.get('candle_direction')}",
        f"body_size = {candle_context.get('body_size')}",
        f"range_size = {candle_context.get('range_size')}",
        f"body_to_range_ratio = {candle_context.get('body_to_range_ratio')}",
        "",
        "[WARNING]",
        context.get("warning"),
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
    ]

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\nreport = {REPORT_PATH}")
    print(f"summary = {SUMMARY_PATH}")


if __name__ == "__main__":
    main()