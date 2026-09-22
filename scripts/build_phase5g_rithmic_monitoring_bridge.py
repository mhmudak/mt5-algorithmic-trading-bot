from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.order_flow_providers.rithmic_contract_identity import (
    require_rithmic_symbol as _require_rithmic_symbol,
    require_rithmic_symbols as _require_rithmic_symbols,
    resolve_rithmic_symbol as _resolve_rithmic_symbol,
    safe_symbol_for_file as _rithmic_safe_symbol_for_file,
)

from src.order_flow_providers.rithmic_monitoring_bridge import (
    build_rithmic_monitoring_bridge,
    write_bridge_json,
    write_bridge_text,
)
from src.order_flow_providers.rithmic_snapshot_adapter import (
    build_rithmic_provider_status,
    load_latest_rithmic_state,
)


from src.order_flow_features.rithmic_liquidity_pull_replenishment import (
    evaluate_rithmic_liquidity_pull_replenishment,
    format_liquidity_pull_replenishment_text,
)
from src.order_flow_features.rithmic_absorption_exhaustion import (
    evaluate_rithmic_absorption_exhaustion,
    format_absorption_exhaustion_text,
)
from src.order_flow_features.rithmic_feed_integrity import (
    evaluate_rithmic_feed_integrity,
    format_feed_integrity_text,
)
from src.order_flow_features.rithmic_anti_fakeout_bridge import (
    build_bridge_anti_fakeout,
    format_bridge_anti_fakeout_text,
)

def _safe_symbol_for_file(symbol: str) -> str:
    return symbol.replace("/", "_").replace("\\", "_").replace(".", "_")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--input-dir", default="data/order_flow/rithmic")
    parser.add_argument("--stale-after-seconds", type=int, default=30)
    parser.add_argument("--output-dir", default="data/order_flow/rithmic")
    parser.add_argument("--signal", choices=("BUY", "SELL"), default=None)
    parser.add_argument("--session", default="UNSPECIFIED")
    parser.add_argument("--tick-size", type=float, default=0.1)
    args = parser.parse_args()

    try:
        args.symbol = _require_rithmic_symbol(
            args.symbol,
            root=ROOT,
        )
    except ValueError as exc:
        parser.error(
            str(exc)
        )

    input_dir = Path(args.input_dir)
    snapshot_path = input_dir / f"{args.symbol}_phase5c_rithmic_state_latest.json"

    loaded = load_latest_rithmic_state(snapshot_path)
    snapshot = loaded.get("snapshot") if loaded.get("loaded") else None

    provider_status = build_rithmic_provider_status(
        snapshot,
        snapshot_path=snapshot_path,
        stale_after_seconds=args.stale_after_seconds,
    )

    if not loaded.get("loaded"):
        provider_status["load_error"] = loaded.get("error")

    bridge = build_rithmic_monitoring_bridge(provider_status)

    safe_symbol = _safe_symbol_for_file(args.symbol)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    feed_integrity_history = (
        output_dir
        / f"{safe_symbol}_phase5g_rithmic_feed_integrity_history.json"
    )
    feed_integrity = evaluate_rithmic_feed_integrity(
        snapshot,
        history_path=feed_integrity_history,
    )
    bridge["feed_integrity"] = feed_integrity

    absorption_exhaustion_history = (
        output_dir
        / f"{safe_symbol}_phase5g_rithmic_absorption_exhaustion_history.json"
    )
    if not feed_integrity.get("continuity_valid", False):
        if absorption_exhaustion_history.exists():
            absorption_exhaustion_history.unlink()

    absorption_exhaustion = evaluate_rithmic_absorption_exhaustion(
        snapshot,
        history_path=absorption_exhaustion_history,
        feed_integrity=feed_integrity,
        signal=args.signal,
        session=args.session,
        tick_size=args.tick_size,
    )
    bridge["absorption_exhaustion"] = absorption_exhaustion

    liquidity_pull_replenishment_history = (
        output_dir
        / f"{safe_symbol}_phase5g_rithmic_liquidity_pull_replenishment_history.json"
    )
    if not feed_integrity.get("continuity_valid", False):
        if liquidity_pull_replenishment_history.exists():
            liquidity_pull_replenishment_history.unlink()

    liquidity_pull_replenishment = (
        evaluate_rithmic_liquidity_pull_replenishment(
            snapshot,
            history_path=liquidity_pull_replenishment_history,
            feed_integrity=feed_integrity,
            signal=args.signal,
            session=args.session,
            tick_size=args.tick_size,
        )
    )
    bridge["liquidity_pull_replenishment"] = (
        liquidity_pull_replenishment
    )

    anti_fakeout_history = (
        output_dir
        / f"{safe_symbol}_phase5g_rithmic_anti_fakeout_history.json"
    )
    if not feed_integrity.get("continuity_valid", False):
        if anti_fakeout_history.exists():
            anti_fakeout_history.unlink()

    anti_fakeout = build_bridge_anti_fakeout(
        snapshot,
        history_path=anti_fakeout_history,
        signal=args.signal,
        session=args.session,
        tick_size=args.tick_size,
    )
    bridge["anti_fakeout"] = anti_fakeout

    output_json = output_dir / f"{safe_symbol}_phase5g_rithmic_monitoring_bridge.json"
    output_txt = output_dir / f"{safe_symbol}_phase5g_rithmic_monitoring_bridge.txt"

    write_bridge_json(bridge, output_json)
    write_bridge_text(bridge, output_txt)
    with output_txt.open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write("\n")
        handle.write(
            format_feed_integrity_text(
                feed_integrity
            )
        )
        handle.write("\n")
        handle.write("\n")
        handle.write(
            format_absorption_exhaustion_text(
                absorption_exhaustion
            )
        )
        handle.write("\n")
        handle.write("\n")
        handle.write(
            format_liquidity_pull_replenishment_text(
                liquidity_pull_replenishment
            )
        )
        handle.write("\n")
        handle.write("\n")
        handle.write(
            format_bridge_anti_fakeout_text(
                anti_fakeout
            )
        )
        handle.write("\n")

    print("[DONE] Phase 5G Rithmic monitoring bridge built")
    print("symbol =", bridge.get("symbol"))
    print("bridge_status =", bridge.get("bridge_status"))
    print("provider_status =", bridge.get("provider_status"))
    print("decision_impact =", bridge.get("decision_impact"))
    print("can_influence_decision =", bridge.get("can_influence_decision"))
    print("feed_integrity_status =", feed_integrity.get("status"))
    print("feed_integrity_ok =", feed_integrity.get("integrity_ok"))
    print("feed_continuity_valid =", feed_integrity.get("continuity_valid"))
    print("absorption_exhaustion_status =", absorption_exhaustion.get("status"))
    print("liquidity_pull_replenishment_status =", liquidity_pull_replenishment.get("status"))
    print("anti_fakeout_status =", anti_fakeout.get("status"))
    print("anti_fakeout_data_grade =", anti_fakeout.get("data_grade"))
    print("anti_fakeout_history_snapshots =", anti_fakeout["bridge_history"].get("history_snapshot_count"))
    print("adapter_metric_format_ready =", bridge["phase4_compatibility"]["adapter_metric_format_ready"])
    print("can_replace_no_order_flow_provider =", bridge["phase4_compatibility"]["can_replace_no_order_flow_provider"])
    print("delta =", bridge["adapter_metrics"]["delta"])
    print("cumulative_delta =", bridge["adapter_metrics"]["cumulative_delta"])
    print("dom_available =", bridge["adapter_metrics"]["dom_available"])
    print("dom_bid_depth =", bridge["adapter_metrics"]["dom_bid_depth"])
    print("dom_ask_depth =", bridge["adapter_metrics"]["dom_ask_depth"])
    print("warnings =", ", ".join(bridge.get("warnings") or []))
    print("output_json =", output_json)
    print("output_txt =", output_txt)


if __name__ == "__main__":
    main()
