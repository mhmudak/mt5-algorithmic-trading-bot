from pathlib import Path
import datetime
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_BRANCH = "feature/rithmic-setup-verdict-supervisor"
EXPECTED_HEAD = "1c08471"

MODULE = (
    ROOT
    / "src"
    / "order_flow_features"
    / "rithmic_evidence_families.py"
)

TEST = (
    ROOT
    / "scripts"
    / "test_rithmic_evidence_families_v2.py"
)

stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def run(*args, check=True):
    result = subprocess.run(
        list(args),
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    if check and result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(
            f"command failed rc={result.returncode}: "
            f"{' '.join(args)}"
        )

    return result


branch = run(
    "git",
    "rev-parse",
    "--abbrev-ref",
    "HEAD",
).stdout.strip()

head = run(
    "git",
    "rev-parse",
    "--short",
    "HEAD",
).stdout.strip()

if branch != EXPECTED_BRANCH:
    raise SystemExit(
        f"[STOP] branch mismatch: "
        f"expected={EXPECTED_BRANCH} got={branch}"
    )

if head != EXPECTED_HEAD:
    raise SystemExit(
        f"[STOP] HEAD mismatch: "
        f"expected={EXPECTED_HEAD} got={head}"
    )

if MODULE.exists():
    raise SystemExit(
        f"[STOP] target already exists: {MODULE}"
    )

if TEST.exists():
    raise SystemExit(
        f"[STOP] target already exists: {TEST}"
    )


module_source = r'''from __future__ import annotations

from typing import Any


DECISION_IMPACT = "NONE"
CAN_INFLUENCE_DECISION = False
SAFE_FOR_EXECUTION = False

BUY = "BUY"
SELL = "SELL"
NEUTRAL = "NEUTRAL"
CONFLICT = "CONFLICT"
UNAVAILABLE = "UNAVAILABLE"

FAMILY_ORDER = (
    "AGGRESSION",
    "AUCTION_PROFILE",
    "FOOTPRINT_ACCEPTANCE",
    "ABSORPTION_EXHAUSTION",
    "LIQUIDITY_DYNAMICS",
    "DIVERGENCE_TRAP",
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _status(value: Any) -> str:
    return str(
        _dict(value).get("status") or ""
    ).upper()


def _bool(
    payload: dict[str, Any],
    *path: str,
) -> bool:
    value: Any = payload

    for key in path:
        if not isinstance(value, dict):
            return False
        value = value.get(key)

    return bool(value)


def _family(
    name: str,
    state: str,
    *,
    reason: str,
    source_engine: str | None = None,
    source_status: str | None = None,
    evidence: list[str] | None = None,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "state": state,
        "available": state != UNAVAILABLE,
        "directional": state in {BUY, SELL},
        "reason": reason,
        "source_engine": source_engine,
        "source_status": source_status,
        "evidence": list(evidence or []),
        "raw": dict(raw or {}),
        "decision_impact": DECISION_IMPACT,
        "can_influence_decision": CAN_INFLUENCE_DECISION,
        "safe_for_execution": SAFE_FOR_EXECUTION,
    }


def _feed_usable(
    bridge: dict[str, Any],
) -> tuple[bool, str]:
    feed = _dict(
        bridge.get("feed_integrity")
    )

    if not feed:
        return False, "feed_integrity_missing"

    if not bool(feed.get("integrity_ok")):
        return False, "feed_integrity_not_ok"

    if not bool(feed.get("continuity_valid")):
        return False, "feed_continuity_invalid"

    return True, "healthy"


def _aggression_family(
    bridge: dict[str, Any],
) -> dict[str, Any]:
    anti = _dict(
        bridge.get("anti_fakeout")
    )
    flow = _dict(
        anti.get("executed_flow")
    )

    if not flow:
        return _family(
            "AGGRESSION",
            UNAVAILABLE,
            reason="executed_flow_missing",
            source_engine=anti.get("engine"),
            source_status=_status(anti),
        )

    if not bool(flow.get("sufficient")):
        return _family(
            "AGGRESSION",
            UNAVAILABLE,
            reason="insufficient_executed_flow",
            source_engine=anti.get("engine"),
            source_status=_status(anti),
            raw=flow,
        )

    try:
        direction = int(
            flow.get("direction") or 0
        )
    except (TypeError, ValueError):
        direction = 0

    if direction > 0:
        state = BUY
        reason = "executed_buy_aggression"
    elif direction < 0:
        state = SELL
        reason = "executed_sell_aggression"
    else:
        state = NEUTRAL
        reason = "executed_flow_direction_neutral"

    evidence = [
        f"delta={flow.get('delta')}",
        (
            "cumulative_delta="
            f"{flow.get('cumulative_delta')}"
        ),
        (
            "flow_imbalance="
            f"{flow.get('flow_imbalance')}"
        ),
        f"trade_count={flow.get('trade_count')}",
        f"total_volume={flow.get('total_volume')}",
    ]

    return _family(
        "AGGRESSION",
        state,
        reason=reason,
        source_engine=anti.get("engine"),
        source_status=_status(anti),
        evidence=evidence,
        raw=flow,
    )


def _auction_profile_family(
    bridge: dict[str, Any],
) -> dict[str, Any]:
    profile = _dict(
        bridge.get("volume_profile_migration")
    )

    if not profile:
        return _family(
            "AUCTION_PROFILE",
            UNAVAILABLE,
            reason="volume_profile_migration_missing",
        )

    status = _status(profile)
    poc = _dict(profile.get("poc"))
    price = _dict(
        profile.get("price_context")
    )

    unusable = {
        "TRADE_FLOW_STALE",
        "POC_OR_PRICE_UNAVAILABLE",
        "FEED_INTEGRITY_NOT_USABLE",
    }

    if status in unusable:
        return _family(
            "AUCTION_PROFILE",
            UNAVAILABLE,
            reason=status.lower(),
            source_engine=profile.get("engine"),
            source_status=status,
        )

    migration_conflict = bool(
        price.get("migration_price_conflict")
    )

    migrating_up = bool(
        poc.get("migrating_up")
    )
    migrating_down = bool(
        poc.get("migrating_down")
    )

    following_up = bool(
        price.get(
            "price_following_up_migration"
        )
    )
    following_down = bool(
        price.get(
            "price_following_down_migration"
        )
    )

    rejection_above = bool(
        price.get("rejection_above_poc")
    )
    rejection_below = bool(
        price.get("rejection_below_poc")
    )

    if migration_conflict:
        state = CONFLICT
        reason = "poc_price_migration_conflict"

    elif (
        migrating_up
        and following_up
    ):
        state = BUY
        reason = "poc_up_price_following"

    elif (
        migrating_down
        and following_down
    ):
        state = SELL
        reason = "poc_down_price_following"

    elif rejection_above:
        state = SELL
        reason = "price_rejected_above_poc"

    elif rejection_below:
        state = BUY
        reason = "price_rejected_below_poc"

    else:
        # POC movement alone is context, not enough
        # for a family vote. This deliberately avoids
        # treating an unsupported POC shift as confirmation.
        state = NEUTRAL
        reason = (
            "profile_context_present_without_"
            "directional_confirmation"
        )

    evidence = [
        f"status={status}",
        (
            "poc_change_ticks="
            f"{poc.get('change_ticks')}"
        ),
        (
            "price_vs_poc_ticks="
            f"{price.get('price_vs_poc_ticks')}"
        ),
        (
            "accepting_near_poc="
            f"{price.get('accepting_near_poc')}"
        ),
    ]

    return _family(
        "AUCTION_PROFILE",
        state,
        reason=reason,
        source_engine=profile.get("engine"),
        source_status=status,
        evidence=evidence,
        raw={
            "poc": poc,
            "price_context": price,
        },
    )


def _footprint_family(
    bridge: dict[str, Any],
) -> dict[str, Any]:
    anti = _dict(
        bridge.get("anti_fakeout")
    )
    footprint = _dict(
        anti.get("footprint")
    )

    evidence = []

    if footprint:
        evidence = [
            (
                "aggregate_footprint_imbalance="
                f"{footprint.get('footprint_imbalance')}"
            ),
            (
                "recent_candle_delta="
                f"{footprint.get('recent_candle_delta')}"
            ),
            (
                "recent_candle_volume="
                f"{footprint.get('recent_candle_volume')}"
            ),
        ]

    return _family(
        "FOOTPRINT_ACCEPTANCE",
        UNAVAILABLE,
        reason=(
            "independent_price_level_footprint_"
            "not_ready"
        ),
        source_engine=anti.get("engine"),
        source_status=_status(anti),
        evidence=evidence + [
            (
                "aggregate footprint withheld from "
                "directional voting because it overlaps "
                "with executed aggression"
            )
        ],
        raw=footprint,
    )


def _absorption_family(
    bridge: dict[str, Any],
) -> dict[str, Any]:
    payload = _dict(
        bridge.get("absorption_exhaustion")
    )

    if not payload:
        return _family(
            "ABSORPTION_EXHAUSTION",
            UNAVAILABLE,
            reason="absorption_exhaustion_missing",
        )

    status = _status(payload)

    if status in {
        "FEED_INTEGRITY_NOT_USABLE",
        "TRADE_FLOW_STALE",
        "INSUFFICIENT_EXECUTED_FLOW",
    }:
        return _family(
            "ABSORPTION_EXHAUSTION",
            UNAVAILABLE,
            reason=status.lower(),
            source_engine=payload.get("engine"),
            source_status=status,
        )

    flow = _dict(payload.get("flow"))
    classification = _dict(
        payload.get("classification")
    )

    try:
        flow_direction = int(
            flow.get("direction") or 0
        )
    except (TypeError, ValueError):
        flow_direction = 0

    absorbed = bool(
        classification.get("absorbed")
    )
    exhaustion = bool(
        classification.get("exhaustion")
    )

    if not absorbed and (
        status.startswith(
            "BUY_AGGRESSION_ABSORBED"
        )
        or status.startswith(
            "SELL_AGGRESSION_ABSORBED"
        )
    ):
        absorbed = True

    if not exhaustion and status in {
        "BUY_AGGRESSION_EXHAUSTING",
        "SELL_AGGRESSION_EXHAUSTING",
    }:
        exhaustion = True

    if flow_direction == 0:
        if status.startswith("BUY_AGGRESSION_"):
            flow_direction = 1
        elif status.startswith(
            "SELL_AGGRESSION_"
        ):
            flow_direction = -1

    if (
        absorbed or exhaustion
    ) and flow_direction > 0:
        state = SELL
        reason = (
            "buy_aggression_absorbed"
            if absorbed
            else "buy_aggression_exhausting"
        )

    elif (
        absorbed or exhaustion
    ) and flow_direction < 0:
        state = BUY
        reason = (
            "sell_aggression_absorbed"
            if absorbed
            else "sell_aggression_exhausting"
        )

    else:
        # Effective aggression belongs to AGGRESSION.
        # Do not count it again here.
        state = NEUTRAL
        reason = (
            "no_independent_absorption_or_"
            "exhaustion_event"
        )

    return _family(
        "ABSORPTION_EXHAUSTION",
        state,
        reason=reason,
        source_engine=payload.get("engine"),
        source_status=status,
        evidence=[
            f"status={status}",
            f"absorbed={absorbed}",
            f"exhaustion={exhaustion}",
            f"flow_direction={flow_direction}",
        ],
        raw={
            "flow": flow,
            "classification": classification,
        },
    )


def _liquidity_family(
    bridge: dict[str, Any],
) -> dict[str, Any]:
    payload = _dict(
        bridge.get(
            "liquidity_pull_replenishment"
        )
    )

    if not payload:
        return _family(
            "LIQUIDITY_DYNAMICS",
            UNAVAILABLE,
            reason="liquidity_engine_missing",
        )

    status = _status(payload)

    if status in {
        "FEED_INTEGRITY_NOT_USABLE",
        "ORDER_BOOK_UNAVAILABLE",
        "INSUFFICIENT_HISTORY",
    }:
        return _family(
            "LIQUIDITY_DYNAMICS",
            UNAVAILABLE,
            reason=status.lower(),
            source_engine=payload.get("engine"),
            source_status=status,
        )

    bid = _dict(payload.get("bid"))
    ask = _dict(payload.get("ask"))

    if not bid or not ask:
        return _family(
            "LIQUIDITY_DYNAMICS",
            UNAVAILABLE,
            reason="two_sided_liquidity_detail_missing",
            source_engine=payload.get("engine"),
            source_status=status,
        )

    bid_replenishment = bool(
        bid.get("replenishment")
    )
    ask_replenishment = bool(
        ask.get("replenishment")
    )
    bid_pull = bool(
        bid.get("pull_risk")
    )
    ask_pull = bool(
        ask.get("pull_risk")
    )

    # Bid replenishment / ask withdrawal lean BUY.
    buy_context = bool(
        bid_replenishment or ask_pull
    )

    # Ask replenishment / bid withdrawal lean SELL.
    sell_context = bool(
        ask_replenishment or bid_pull
    )

    if buy_context and sell_context:
        state = CONFLICT
        reason = "opposing_liquidity_cues"

    elif buy_context:
        state = BUY
        reason = "buy_supportive_liquidity_context"

    elif sell_context:
        state = SELL
        reason = "sell_supportive_liquidity_context"

    else:
        state = NEUTRAL
        reason = "stable_or_mixed_liquidity"

    return _family(
        "LIQUIDITY_DYNAMICS",
        state,
        reason=reason,
        source_engine=payload.get("engine"),
        source_status=status,
        evidence=[
            (
                "bid_replenishment="
                f"{bid_replenishment}"
            ),
            (
                "ask_replenishment="
                f"{ask_replenishment}"
            ),
            f"bid_pull_risk={bid_pull}",
            f"ask_pull_risk={ask_pull}",
            (
                "aggregate_depth_only="
                f"{_dict(payload.get('policy')).get('aggregate_depth_only')}"
            ),
        ],
        raw={
            "bid": bid,
            "ask": ask,
        },
    )


def _divergence_family(
    bridge: dict[str, Any],
) -> dict[str, Any]:
    payload = _dict(
        bridge.get("delta_price_divergence")
    )

    if not payload:
        return _family(
            "DIVERGENCE_TRAP",
            UNAVAILABLE,
            reason="delta_price_divergence_missing",
        )

    status = _status(payload)

    if status in {
        "FEED_INTEGRITY_NOT_USABLE",
        "TRADE_FLOW_STALE",
        "INSUFFICIENT_HISTORY",
    }:
        return _family(
            "DIVERGENCE_TRAP",
            UNAVAILABLE,
            reason=status.lower(),
            source_engine=payload.get("engine"),
            source_status=status,
        )

    classification = _dict(
        payload.get("classification")
    )

    trapped_buyers = bool(
        classification.get(
            "potential_trapped_buyers"
        )
    )
    trapped_sellers = bool(
        classification.get(
            "potential_trapped_sellers"
        )
    )

    bullish_without_delta = bool(
        classification.get(
            "bullish_price_without_delta"
        )
    )
    bearish_without_delta = bool(
        classification.get(
            "bearish_price_without_delta"
        )
    )

    if trapped_buyers and trapped_sellers:
        state = CONFLICT
        reason = "two_sided_trap_flags"

    elif trapped_buyers:
        state = SELL
        reason = "potential_trapped_buyers"

    elif trapped_sellers:
        state = BUY
        reason = "potential_trapped_sellers"

    elif bullish_without_delta or bearish_without_delta:
        # Price-without-delta is a divergence observation,
        # but not yet treated as standalone directional
        # confirmation until outcome research validates it.
        state = NEUTRAL
        reason = "price_delta_divergence_context_only"

    else:
        # BUY_FLOW_PRICE_CONFIRMED / SELL_FLOW_PRICE_CONFIRMED
        # overlap materially with the Aggression family and
        # therefore do not receive another family vote here.
        state = NEUTRAL
        reason = "no_independent_trap_signal"

    return _family(
        "DIVERGENCE_TRAP",
        state,
        reason=reason,
        source_engine=payload.get("engine"),
        source_status=status,
        evidence=[
            f"status={status}",
            (
                "potential_trapped_buyers="
                f"{trapped_buyers}"
            ),
            (
                "potential_trapped_sellers="
                f"{trapped_sellers}"
            ),
            (
                "bullish_price_without_delta="
                f"{bullish_without_delta}"
            ),
            (
                "bearish_price_without_delta="
                f"{bearish_without_delta}"
            ),
        ],
        raw=classification,
    )


def _unavailable_families(
    reason: str,
) -> dict[str, dict[str, Any]]:
    return {
        name: _family(
            name,
            UNAVAILABLE,
            reason=reason,
        )
        for name in FAMILY_ORDER
    }


def _summary(
    families: dict[str, dict[str, Any]],
    signal: str | None,
) -> dict[str, Any]:
    states = {
        name: family.get("state")
        for name, family in families.items()
    }

    available_count = sum(
        state != UNAVAILABLE
        for state in states.values()
    )

    buy_count = sum(
        state == BUY
        for state in states.values()
    )
    sell_count = sum(
        state == SELL
        for state in states.values()
    )
    neutral_count = sum(
        state == NEUTRAL
        for state in states.values()
    )
    conflict_count = sum(
        state == CONFLICT
        for state in states.values()
    )
    unavailable_count = sum(
        state == UNAVAILABLE
        for state in states.values()
    )

    signal_name = str(
        signal or ""
    ).upper()

    support_count = 0
    against_count = 0
    supporting_families: list[str] = []
    opposing_families: list[str] = []

    if signal_name in {BUY, SELL}:
        opposing_direction = (
            SELL
            if signal_name == BUY
            else BUY
        )

        for name, state in states.items():
            if state == signal_name:
                support_count += 1
                supporting_families.append(name)

            elif state == opposing_direction:
                against_count += 1
                opposing_families.append(name)

    return {
        "family_count": len(FAMILY_ORDER),
        "available_count": available_count,
        "coverage": (
            f"{available_count}/{len(FAMILY_ORDER)}"
        ),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "neutral_count": neutral_count,
        "conflict_count": conflict_count,
        "unavailable_count": unavailable_count,
        "directional_family_count": (
            buy_count + sell_count
        ),
        "net_directional_score": (
            buy_count - sell_count
        ),
        "setup_direction": (
            signal_name
            if signal_name in {BUY, SELL}
            else None
        ),
        "support_count": support_count,
        "against_count": against_count,
        "supporting_families": supporting_families,
        "opposing_families": opposing_families,
    }


def build_rithmic_evidence_families(
    bridge: dict[str, Any] | None,
    *,
    signal: str | None = None,
) -> dict[str, Any]:
    bridge = (
        bridge
        if isinstance(bridge, dict)
        else {}
    )

    feed_usable, feed_reason = (
        _feed_usable(bridge)
    )

    if not feed_usable:
        families = _unavailable_families(
            feed_reason
        )

    else:
        families = {
            "AGGRESSION": (
                _aggression_family(bridge)
            ),
            "AUCTION_PROFILE": (
                _auction_profile_family(bridge)
            ),
            "FOOTPRINT_ACCEPTANCE": (
                _footprint_family(bridge)
            ),
            "ABSORPTION_EXHAUSTION": (
                _absorption_family(bridge)
            ),
            "LIQUIDITY_DYNAMICS": (
                _liquidity_family(bridge)
            ),
            "DIVERGENCE_TRAP": (
                _divergence_family(bridge)
            ),
        }

    order_flow_regime = _dict(
        bridge.get("order_flow_regime")
    )
    anti_fakeout = _dict(
        bridge.get("anti_fakeout")
    )

    return {
        "engine": "RITHMIC_EVIDENCE_FAMILIES_V2",
        "feed_gate": {
            "usable": feed_usable,
            "reason": feed_reason,
            "feed_status": _status(
                bridge.get("feed_integrity")
            ),
        },
        "families": families,
        "summary": _summary(
            families,
            signal,
        ),
        "modifiers": {
            "order_flow_regime": {
                "regime": (
                    order_flow_regime.get(
                        "regime"
                    )
                ),
                "direction": (
                    order_flow_regime.get(
                        "direction"
                    )
                ),
                "confidence": (
                    order_flow_regime.get(
                        "confidence"
                    )
                ),
            },
            "anti_fakeout": {
                "status": _status(
                    anti_fakeout
                ),
                "spoof_risk": bool(
                    anti_fakeout.get(
                        "spoof_risk"
                    )
                ),
                "dom_only_untrusted": bool(
                    anti_fakeout.get(
                        "dom_only_untrusted"
                    )
                ),
            },
            "volume_regime": {
                "status": (
                    "UNAVAILABLE_NOT_IMPLEMENTED"
                ),
                "counts_as_directional_vote": False,
            },
        },
        "policy": {
            "one_vote_max_per_family": True,
            "unavailable_is_not_neutral": True,
            "feed_integrity_is_gate_not_vote": True,
            "order_flow_regime_is_modifier_not_vote": True,
            "anti_fakeout_is_modifier_not_vote": True,
            "volume_regime_is_modifier_not_vote": True,
            "aggregate_footprint_is_not_independent_vote": True,
            "effective_aggression_not_recounted_in_absorption": True,
            "effective_flow_not_recounted_in_divergence": True,
            "research_only": True,
        },
        "decision_impact": DECISION_IMPACT,
        "can_influence_decision": CAN_INFLUENCE_DECISION,
        "safe_for_execution": SAFE_FOR_EXECUTION,
        "execution_allowed": False,
        "trade_action": "NO_AUTO_TRADE",
    }
'''

test_source = r'''from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.order_flow_features.rithmic_evidence_families import (
    BUY,
    CONFLICT,
    NEUTRAL,
    SELL,
    UNAVAILABLE,
    build_rithmic_evidence_families,
)


def base_bridge() -> dict:
    return {
        "feed_integrity": {
            "engine": (
                "RITHMIC_FEED_INTEGRITY_GUARD_V1"
            ),
            "status": "HEALTHY",
            "integrity_ok": True,
            "continuity_valid": True,
        },
        "anti_fakeout": {
            "engine": "RITHMIC_ANTI_FAKEOUT_V1",
            "status": "NEUTRAL",
            "executed_flow": {
                "trade_count": 82,
                "total_volume": 84.0,
                "delta": -16.0,
                "cumulative_delta": -16.0,
                "flow_imbalance": -0.190476,
                "direction": -1,
                "sufficient": True,
            },
            "footprint": {
                "footprint_imbalance": -0.190476,
                "direction": -1,
                "recent_candle_delta": -16.0,
                "recent_candle_volume": 68.0,
                "strength_ok": True,
            },
            "spoof_risk": False,
            "dom_only_untrusted": False,
        },
        "absorption_exhaustion": {
            "engine": (
                "RITHMIC_ABSORPTION_EXHAUSTION_V1"
            ),
            "status": "SELL_AGGRESSION_EFFECTIVE",
            "flow": {
                "direction": -1,
            },
            "classification": {
                "aggression_effective": True,
                "absorbed": False,
                "exhaustion": False,
            },
        },
        "liquidity_pull_replenishment": {
            "engine": (
                "RITHMIC_LIQUIDITY_PULL_REPLENISHMENT_V1"
            ),
            "status": "STABLE_OR_MIXED",
            "bid": {
                "replenishment": False,
                "pull_risk": False,
            },
            "ask": {
                "replenishment": False,
                "pull_risk": False,
            },
            "policy": {
                "aggregate_depth_only": True,
            },
        },
        "delta_price_divergence": {
            "engine": (
                "RITHMIC_DELTA_PRICE_DIVERGENCE_V1"
            ),
            "status": "DELTA_CHANGE_TOO_SMALL",
            "classification": {
                "potential_trapped_buyers": False,
                "potential_trapped_sellers": False,
                "buyer_flow_effective": False,
                "seller_flow_effective": False,
                "bullish_price_without_delta": False,
                "bearish_price_without_delta": False,
            },
        },
        "volume_profile_migration": {
            "engine": (
                "RITHMIC_VOLUME_PROFILE_MIGRATION_V1"
            ),
            "status": (
                "PRICE_ACCEPTING_NEAR_STABLE_POC"
            ),
            "poc": {
                "change_ticks": 0.0,
                "migrating_up": False,
                "migrating_down": False,
                "stable": True,
            },
            "price_context": {
                "price_vs_poc_ticks": -1.0,
                "accepting_near_poc": True,
                "rejection_above_poc": False,
                "rejection_below_poc": False,
                "price_following_up_migration": False,
                "price_following_down_migration": False,
                "migration_price_conflict": False,
            },
        },
        "order_flow_regime": {
            "regime": "SELL_FLOW_EFFECTIVE",
            "direction": "SELL",
            "confidence": "MODERATE",
        },
    }


def assert_state(
    result: dict,
    family: str,
    expected: str,
) -> None:
    actual = (
        result["families"][family]["state"]
    )

    assert actual == expected, (
        family,
        actual,
        expected,
    )


def test_live_like_case_avoids_double_counting():
    bridge = base_bridge()

    result = build_rithmic_evidence_families(
        bridge,
        signal="BUY",
    )

    assert_state(
        result,
        "AGGRESSION",
        SELL,
    )
    assert_state(
        result,
        "AUCTION_PROFILE",
        NEUTRAL,
    )
    assert_state(
        result,
        "FOOTPRINT_ACCEPTANCE",
        UNAVAILABLE,
    )
    assert_state(
        result,
        "ABSORPTION_EXHAUSTION",
        NEUTRAL,
    )
    assert_state(
        result,
        "LIQUIDITY_DYNAMICS",
        NEUTRAL,
    )
    assert_state(
        result,
        "DIVERGENCE_TRAP",
        NEUTRAL,
    )

    summary = result["summary"]

    assert summary["coverage"] == "5/6"
    assert summary["buy_count"] == 0
    assert summary["sell_count"] == 1
    assert summary["neutral_count"] == 4
    assert summary["unavailable_count"] == 1

    assert summary["support_count"] == 0
    assert summary["against_count"] == 1

    print(
        "PASS: effective SELL flow becomes one "
        "independent family vote, not duplicated "
        "across footprint/absorption/divergence"
    )


def test_bad_feed_makes_every_family_unavailable():
    bridge = base_bridge()

    bridge["feed_integrity"][
        "integrity_ok"
    ] = False

    result = build_rithmic_evidence_families(
        bridge,
        signal="SELL",
    )

    assert (
        result["summary"]["available_count"]
        == 0
    )
    assert (
        result["summary"]["unavailable_count"]
        == 6
    )
    assert (
        result["summary"]["support_count"]
        == 0
    )
    assert (
        result["summary"]["against_count"]
        == 0
    )

    print(
        "PASS: Feed Integrity is a hard evidence "
        "availability gate, never a directional vote"
    )


def test_absorbed_buyers_vote_sell_once():
    bridge = base_bridge()

    bridge["anti_fakeout"][
        "executed_flow"
    ]["direction"] = 1

    bridge["anti_fakeout"][
        "executed_flow"
    ]["delta"] = 20

    bridge["anti_fakeout"][
        "executed_flow"
    ]["flow_imbalance"] = 0.25

    absorption = bridge[
        "absorption_exhaustion"
    ]

    absorption[
        "status"
    ] = "BUY_AGGRESSION_ABSORBED"

    absorption[
        "flow"
    ]["direction"] = 1

    absorption[
        "classification"
    ]["absorbed"] = True

    absorption[
        "classification"
    ]["aggression_effective"] = False

    result = build_rithmic_evidence_families(
        bridge,
        signal="BUY",
    )

    assert_state(
        result,
        "AGGRESSION",
        BUY,
    )
    assert_state(
        result,
        "ABSORPTION_EXHAUSTION",
        SELL,
    )

    assert (
        result["summary"]["support_count"]
        == 1
    )
    assert (
        result["summary"]["against_count"]
        == 1
    )

    print(
        "PASS: buy aggression and buyer absorption "
        "remain separate conflicting families"
    )


def test_profile_requires_price_confirmation():
    bridge = base_bridge()

    profile = bridge[
        "volume_profile_migration"
    ]

    profile[
        "status"
    ] = "POC_MIGRATING_UP"

    profile["poc"]["migrating_up"] = True

    result = build_rithmic_evidence_families(
        bridge
    )

    assert_state(
        result,
        "AUCTION_PROFILE",
        NEUTRAL,
    )

    profile[
        "status"
    ] = "POC_MIGRATING_UP_WITH_PRICE"

    profile[
        "price_context"
    ][
        "price_following_up_migration"
    ] = True

    result = build_rithmic_evidence_families(
        bridge
    )

    assert_state(
        result,
        "AUCTION_PROFILE",
        BUY,
    )

    print(
        "PASS: POC movement alone is context; "
        "POC + price confirmation becomes directional"
    )


def test_liquidity_context_is_directional_but_secondary():
    bridge = base_bridge()

    liquidity = bridge[
        "liquidity_pull_replenishment"
    ]

    liquidity[
        "bid"
    ]["replenishment"] = True

    result = build_rithmic_evidence_families(
        bridge
    )

    assert_state(
        result,
        "LIQUIDITY_DYNAMICS",
        BUY,
    )

    liquidity[
        "ask"
    ]["replenishment"] = True

    result = build_rithmic_evidence_families(
        bridge
    )

    assert_state(
        result,
        "LIQUIDITY_DYNAMICS",
        CONFLICT,
    )

    print(
        "PASS: aggregate liquidity cues create at "
        "most one liquidity-family vote"
    )


def test_trapped_sellers_vote_buy():
    bridge = base_bridge()

    divergence = bridge[
        "delta_price_divergence"
    ]

    divergence[
        "status"
    ] = "POTENTIAL_TRAPPED_SELLERS"

    divergence[
        "classification"
    ][
        "potential_trapped_sellers"
    ] = True

    result = build_rithmic_evidence_families(
        bridge,
        signal="BUY",
    )

    assert_state(
        result,
        "DIVERGENCE_TRAP",
        BUY,
    )

    assert (
        result["summary"]["support_count"]
        == 1
    )

    print(
        "PASS: trapped-seller divergence supports "
        "BUY as one independent family"
    )


def test_effective_flow_is_not_recounted_as_divergence():
    bridge = base_bridge()

    divergence = bridge[
        "delta_price_divergence"
    ]

    divergence[
        "status"
    ] = "SELL_FLOW_PRICE_CONFIRMED"

    divergence[
        "classification"
    ][
        "seller_flow_effective"
    ] = True

    result = build_rithmic_evidence_families(
        bridge
    )

    assert_state(
        result,
        "DIVERGENCE_TRAP",
        NEUTRAL,
    )

    print(
        "PASS: flow effectiveness is not counted "
        "again inside Divergence/Trap"
    )


def test_safety_contract():
    result = build_rithmic_evidence_families(
        base_bridge(),
        signal="SELL",
    )

    assert result["decision_impact"] == "NONE"
    assert (
        result["can_influence_decision"]
        is False
    )
    assert result["safe_for_execution"] is False
    assert result["execution_allowed"] is False

    assert (
        result["policy"][
            "one_vote_max_per_family"
        ]
        is True
    )

    assert (
        result["policy"][
            "unavailable_is_not_neutral"
        ]
        is True
    )

    print(
        "PASS: Evidence Families V2 has zero "
        "decision/execution authority"
    )


def main() -> None:
    test_live_like_case_avoids_double_counting()
    test_bad_feed_makes_every_family_unavailable()
    test_absorbed_buyers_vote_sell_once()
    test_profile_requires_price_confirmation()
    test_liquidity_context_is_directional_but_secondary()
    test_trapped_sellers_vote_buy()
    test_effective_flow_is_not_recounted_as_divergence()
    test_safety_contract()

    print("")
    print(
        "[PASS] Rithmic Evidence Families V2 "
        "independent-family contract verified."
    )


if __name__ == "__main__":
    main()
'''

created = []

try:
    MODULE.write_text(
        module_source,
        encoding="utf-8",
        newline="\n",
    )
    created.append(MODULE)

    TEST.write_text(
        test_source,
        encoding="utf-8",
        newline="\n",
    )
    created.append(TEST)

    compile_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(MODULE),
            str(TEST),
        ],
        cwd=ROOT,
    )

    if compile_result.returncode != 0:
        raise RuntimeError(
            "compile validation failed"
        )

    test_result = subprocess.run(
        [
            sys.executable,
            str(TEST),
        ],
        cwd=ROOT,
    )

    if test_result.returncode != 0:
        raise RuntimeError(
            "Evidence Families V2 test failed"
        )

except Exception:
    for path in reversed(created):
        if path.exists():
            path.unlink()

    print(
        "[ROLLBACK] Evidence Families V2 "
        "Phase 1 files removed."
    )

    raise


print("")
print(
    "[PASS] Evidence Families V2 Phase 1 applied"
)
print("[CREATED]", MODULE.relative_to(ROOT))
print("[CREATED]", TEST.relative_to(ROOT))
print("[UNCHANGED] Phase 5G bridge")
print("[UNCHANGED] src/rithmic_setup_verdict.py")
print("[UNCHANGED] src/live_bot.py")
print("[UNCHANGED] MT5 execution path")
print(
    "[SAFETY] Research/observe-only; "
    "zero decision authority"
)
