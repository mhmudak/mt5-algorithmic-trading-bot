from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import fmean, pstdev
from typing import Any


DECISION_IMPACT = "NONE"
CAN_INFLUENCE_DECISION = False
SAFE_FOR_EXECUTION = False


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _sign(value: float | None, deadband: float = 0.0) -> int:
    if value is None:
        return 0
    if value > deadband:
        return 1
    if value < -deadband:
        return -1
    return 0


def _nested(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


@dataclass(frozen=True)
class SessionThresholds:
    min_trade_count: int
    min_total_volume: float
    min_flow_imbalance: float
    min_footprint_imbalance: float
    min_price_response_ticks: float
    max_depth_churn_ratio: float
    max_dom_flip_ratio: float


def thresholds_for_session(session: str | None) -> SessionThresholds:
    """
    Research defaults only. These are deliberately conservative placeholders,
    not calibrated production thresholds.
    """
    name = str(session or "").upper()

    if any(token in name for token in ("OVERLAP", "NEW_YORK", "NEW YORK", "NY_OPEN", "COMEX")):
        return SessionThresholds(
            min_trade_count=20,
            min_total_volume=20.0,
            min_flow_imbalance=0.18,
            min_footprint_imbalance=0.15,
            min_price_response_ticks=2.0,
            max_depth_churn_ratio=0.65,
            max_dom_flip_ratio=0.45,
        )

    if "LONDON" in name:
        return SessionThresholds(
            min_trade_count=14,
            min_total_volume=14.0,
            min_flow_imbalance=0.16,
            min_footprint_imbalance=0.14,
            min_price_response_ticks=1.5,
            max_depth_churn_ratio=0.70,
            max_dom_flip_ratio=0.50,
        )

    return SessionThresholds(
        min_trade_count=10,
        min_total_volume=10.0,
        min_flow_imbalance=0.14,
        min_footprint_imbalance=0.12,
        min_price_response_ticks=1.0,
        max_depth_churn_ratio=0.75,
        max_dom_flip_ratio=0.55,
    )


class FuturesSpotBasisTracker:
    """
    Research-only GC/MGC-to-XAUUSD basis tracker.

    Raw futures price levels must not be applied directly to XAUUSD. Once the
    rolling basis is stable, futures levels can be translated by subtracting
    the estimated basis.
    """

    def __init__(
        self,
        *,
        max_samples: int = 120,
        min_samples: int = 20,
        max_stdev: float = 1.50,
    ) -> None:
        self.max_samples = max(5, int(max_samples))
        self.min_samples = max(3, int(min_samples))
        self.max_stdev = float(max_stdev)
        self._basis: deque[float] = deque(maxlen=self.max_samples)

    def update(
        self,
        *,
        futures_mid: Any,
        xauusd_mid: Any,
    ) -> dict[str, Any]:
        futures = _safe_float(futures_mid)
        spot = _safe_float(xauusd_mid)

        if futures is not None and spot is not None:
            self._basis.append(futures - spot)

        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        samples = list(self._basis)
        count = len(samples)

        mean_basis = fmean(samples) if samples else None
        stdev_basis = pstdev(samples) if len(samples) >= 2 else None

        stable = bool(
            count >= self.min_samples
            and stdev_basis is not None
            and stdev_basis <= self.max_stdev
        )

        return {
            "sample_count": count,
            "mean_basis": round(mean_basis, 6) if mean_basis is not None else None,
            "basis_stdev": round(stdev_basis, 6) if stdev_basis is not None else None,
            "stable": stable,
            "quality": (
                "STABLE"
                if stable
                else "INSUFFICIENT_OR_UNSTABLE"
            ),
            "decision_impact": DECISION_IMPACT,
        }

    def futures_to_xauusd(self, futures_price: Any) -> float | None:
        price = _safe_float(futures_price)
        state = self.snapshot()

        if (
            price is None
            or not state["stable"]
            or state["mean_basis"] is None
        ):
            return None

        return round(price - float(state["mean_basis"]), 6)


class RithmicAntiFakeoutEngine:
    """
    Stateful, observe-only anti-fakeout evaluator.

    It consumes successive Rithmic state-cache snapshots. Resting DOM can
    modify confidence but can never create CONFIRMED without fresh executed
    flow, footprint agreement, and price response.
    """

    def __init__(
        self,
        *,
        tick_size: float = 0.1,
        history_size: int = 12,
    ) -> None:
        self.tick_size = max(1e-9, float(tick_size))
        self.history: deque[dict[str, Any]] = deque(
            maxlen=max(4, int(history_size))
        )

    def reset(self) -> None:
        self.history.clear()

    def update(
        self,
        snapshot: dict[str, Any],
        *,
        signal: str | None = None,
        session: str | None = None,
        basis_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.evaluate(
            snapshot,
            signal=signal,
            session=session,
            basis_state=basis_state,
        )
        self.history.append(snapshot)
        return result

    def _freshness(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        fresh_trade = bool(
            _nested(snapshot, "freshness", "has_fresh_trade", default=False)
        )
        fresh_bbo = bool(
            _nested(snapshot, "freshness", "has_fresh_bbo", default=False)
        )
        fresh_book = bool(
            _nested(snapshot, "freshness", "has_fresh_order_book", default=False)
        )

        return {
            "has_fresh_trade": fresh_trade,
            "has_fresh_bbo": fresh_bbo,
            "has_fresh_order_book": fresh_book,
            "all_fresh": fresh_trade and fresh_bbo and fresh_book,
        }

    def _flow_metrics(
        self,
        snapshot: dict[str, Any],
        thresholds: SessionThresholds,
    ) -> dict[str, Any]:
        trade_count = _safe_int(
            _nested(snapshot, "sample", "rolling_trade_count", default=0)
        )
        total_volume = _safe_float(
            _nested(snapshot, "trade_flow", "rolling_total_volume", default=0)
        ) or 0.0
        delta = _safe_float(
            _nested(snapshot, "trade_flow", "rolling_delta", default=0)
        ) or 0.0
        cumulative_delta = _safe_float(
            _nested(snapshot, "trade_flow", "session_cumulative_delta", default=0)
        ) or 0.0
        flow_imbalance = _safe_float(
            _nested(snapshot, "trade_flow", "rolling_imbalance_ratio", default=None)
        )

        if flow_imbalance is None and total_volume > 0:
            flow_imbalance = delta / total_volume

        flow_imbalance = flow_imbalance or 0.0

        sufficient = bool(
            trade_count >= thresholds.min_trade_count
            and total_volume >= thresholds.min_total_volume
            and abs(flow_imbalance) >= thresholds.min_flow_imbalance
        )

        return {
            "trade_count": trade_count,
            "total_volume": round(total_volume, 6),
            "delta": round(delta, 6),
            "cumulative_delta": round(cumulative_delta, 6),
            "flow_imbalance": round(flow_imbalance, 6),
            "direction": _sign(flow_imbalance),
            "sufficient": sufficient,
        }

    def _footprint_metrics(
        self,
        snapshot: dict[str, Any],
        thresholds: SessionThresholds,
    ) -> dict[str, Any]:
        footprint = _safe_float(
            _nested(
                snapshot,
                "adapter_compatible_metrics",
                "footprint_imbalance",
                default=0,
            )
        ) or 0.0

        candles = _nested(
            snapshot,
            "footprint",
            "candles",
            default=[],
        )
        candles = candles if isinstance(candles, list) else []

        recent_delta = 0.0
        recent_volume = 0.0

        if candles:
            last = candles[-1]
            if isinstance(last, dict):
                recent_delta = _safe_float(last.get("delta")) or 0.0
                recent_volume = _safe_float(last.get("total_volume")) or 0.0

        confirms_strength = (
            abs(footprint) >= thresholds.min_footprint_imbalance
        )

        return {
            "footprint_imbalance": round(footprint, 6),
            "direction": _sign(footprint),
            "recent_candle_delta": round(recent_delta, 6),
            "recent_candle_volume": round(recent_volume, 6),
            "strength_ok": confirms_strength,
        }

    def _price_response(
        self,
        snapshot: dict[str, Any],
        flow_direction: int,
        thresholds: SessionThresholds,
    ) -> dict[str, Any]:
        first_price = _safe_float(
            _nested(snapshot, "trade_flow", "first_trade_price", default=None)
        )
        last_price = _safe_float(
            _nested(snapshot, "trade_flow", "last_trade_price", default=None)
        )

        if first_price is None or last_price is None:
            return {
                "price_change": None,
                "response_ticks": None,
                "direction": 0,
                "confirms_executed_flow": False,
                "absorption_against_flow": False,
            }

        price_change = last_price - first_price
        response_ticks = price_change / self.tick_size
        response_direction = _sign(response_ticks)

        confirms = bool(
            flow_direction != 0
            and response_direction == flow_direction
            and abs(response_ticks) >= thresholds.min_price_response_ticks
        )

        absorption = bool(
            flow_direction != 0
            and (
                response_direction == -flow_direction
                or abs(response_ticks) < thresholds.min_price_response_ticks
            )
        )

        return {
            "price_change": round(price_change, 6),
            "response_ticks": round(response_ticks, 6),
            "direction": response_direction,
            "confirms_executed_flow": confirms,
            "absorption_against_flow": absorption,
        }

    def _dom_history_metrics(
        self,
        current: dict[str, Any],
        thresholds: SessionThresholds,
    ) -> dict[str, Any]:
        snapshots = list(self.history) + [current]

        imbalances: list[float] = []
        total_depths: list[float] = []
        top_bids: list[float] = []
        top_asks: list[float] = []

        for snapshot in snapshots:
            imbalance = _safe_float(
                _nested(snapshot, "order_book", "depth_imbalance", default=None)
            )
            bid_depth = _safe_float(
                _nested(snapshot, "order_book", "bid_depth", default=0)
            ) or 0.0
            ask_depth = _safe_float(
                _nested(snapshot, "order_book", "ask_depth", default=0)
            ) or 0.0
            top_bid = _safe_float(
                _nested(snapshot, "order_book", "top_bid_price", default=None)
            )
            top_ask = _safe_float(
                _nested(snapshot, "order_book", "top_ask_price", default=None)
            )

            if imbalance is not None:
                imbalances.append(imbalance)
            total_depths.append(bid_depth + ask_depth)

            if top_bid is not None:
                top_bids.append(top_bid)
            if top_ask is not None:
                top_asks.append(top_ask)

        current_imbalance = imbalances[-1] if imbalances else 0.0
        current_direction = _sign(current_imbalance, 0.05)

        same_direction = 0
        directional_samples = 0
        flips = 0
        prior_sign = 0

        for value in imbalances:
            sign = _sign(value, 0.05)
            if sign != 0:
                directional_samples += 1
                if sign == current_direction and current_direction != 0:
                    same_direction += 1
                if prior_sign != 0 and sign != prior_sign:
                    flips += 1
                prior_sign = sign

        persistence = (
            same_direction / directional_samples
            if directional_samples
            else 0.0
        )
        flip_ratio = (
            flips / max(1, directional_samples - 1)
            if directional_samples >= 2
            else 0.0
        )

        churn_components = []
        for previous, latest in zip(total_depths, total_depths[1:]):
            denominator = max(1.0, previous)
            churn_components.append(abs(latest - previous) / denominator)

        depth_churn_ratio = (
            fmean(churn_components)
            if churn_components
            else 0.0
        )

        bid_flicker_ticks = 0.0
        ask_flicker_ticks = 0.0

        if len(top_bids) >= 2:
            bid_flicker_ticks = max(top_bids) - min(top_bids)
            bid_flicker_ticks /= self.tick_size

        if len(top_asks) >= 2:
            ask_flicker_ticks = max(top_asks) - min(top_asks)
            ask_flicker_ticks /= self.tick_size

        quote_flicker_score = min(
            1.0,
            (
                flip_ratio
                + min(1.0, depth_churn_ratio)
                + min(1.0, (bid_flicker_ticks + ask_flicker_ticks) / 20.0)
            )
            / 3.0,
        )

        persistent = bool(
            len(imbalances) >= 3
            and current_direction != 0
            and persistence >= 0.60
            and flip_ratio <= thresholds.max_dom_flip_ratio
        )

        return {
            "depth_imbalance": round(current_imbalance, 6),
            "direction": current_direction,
            "persistence_ratio": round(persistence, 6),
            "dom_flip_ratio": round(flip_ratio, 6),
            "depth_churn_ratio_proxy": round(depth_churn_ratio, 6),
            "quote_flicker_score": round(quote_flicker_score, 6),
            "persistent": persistent,
            "sample_count": len(imbalances),
            "note": (
                "depth_churn_ratio_proxy is inferred from successive aggregated "
                "book snapshots; it is not a true exchange-level cancel/add ratio"
            ),
        }

    def evaluate(
        self,
        snapshot: dict[str, Any],
        *,
        signal: str | None = None,
        session: str | None = None,
        basis_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        signal_name = str(signal or "").upper()
        signal_direction = 1 if signal_name == "BUY" else -1 if signal_name == "SELL" else 0
        thresholds = thresholds_for_session(session)

        freshness = self._freshness(snapshot)
        flow = self._flow_metrics(snapshot, thresholds)
        footprint = self._footprint_metrics(snapshot, thresholds)
        response = self._price_response(
            snapshot,
            flow["direction"],
            thresholds,
        )
        dom = self._dom_history_metrics(
            snapshot,
            thresholds,
        )

        executed_flow_present = bool(
            freshness["has_fresh_trade"]
            and flow["sufficient"]
        )

        executed_vs_resting_agreement = bool(
            executed_flow_present
            and dom["direction"] != 0
            and dom["direction"] == flow["direction"]
        )

        dom_only = bool(
            dom["direction"] != 0
            and not executed_flow_present
        )

        high_churn = (
            dom["depth_churn_ratio_proxy"]
            > thresholds.max_depth_churn_ratio
        )
        high_flicker = (
            dom["quote_flicker_score"] >= 0.55
            or dom["dom_flip_ratio"] > thresholds.max_dom_flip_ratio
        )

        unsupported_dom = bool(
            dom["direction"] != 0
            and (
                flow["direction"] == 0
                or dom["direction"] != flow["direction"]
            )
        )

        spoof_risk = bool(
            freshness["has_fresh_order_book"]
            and dom["sample_count"] >= 3
            and (
                high_flicker
                or (
                    high_churn
                    and unsupported_dom
                )
            )
        )

        flow_confirms_signal = bool(
            signal_direction != 0
            and flow["direction"] == signal_direction
            and executed_flow_present
        )

        footprint_confirms_signal = bool(
            signal_direction != 0
            and footprint["direction"] == signal_direction
            and footprint["strength_ok"]
        )

        price_confirms_signal = bool(
            signal_direction != 0
            and response["direction"] == signal_direction
            and response["confirms_executed_flow"]
        )

        absorption_against_signal = bool(
            signal_direction != 0
            and flow["direction"] == signal_direction
            and response["absorption_against_flow"]
        )

        conflict = bool(
            signal_direction != 0
            and executed_flow_present
            and flow["direction"] == -signal_direction
        )

        if not freshness["all_fresh"]:
            status = "STALE"
        elif spoof_risk:
            status = "SPOOF_RISK"
        elif dom_only:
            status = "DOM_ONLY_UNTRUSTED"
        elif not executed_flow_present:
            status = "INSUFFICIENT_EXECUTED_FLOW"
        elif absorption_against_signal:
            status = "ABSORPTION_AGAINST"
        elif conflict:
            status = "CONFLICT"
        elif (
            signal_direction != 0
            and flow_confirms_signal
            and footprint_confirms_signal
            and price_confirms_signal
            and not spoof_risk
        ):
            status = "CONFIRMED"
        else:
            status = "NEUTRAL"

        rolling_poc = _safe_float(
            _nested(snapshot, "volume_profile", "rolling_poc_price", default=None)
        )

        adjusted_poc = None
        if (
            rolling_poc is not None
            and isinstance(basis_state, dict)
            and bool(basis_state.get("stable"))
            and _safe_float(basis_state.get("mean_basis")) is not None
        ):
            adjusted_poc = round(
                rolling_poc - float(basis_state["mean_basis"]),
                6,
            )

        score_components = {
            "executed_flow": (
                signal_direction * flow["direction"]
                if flow_confirms_signal
                else 0
            ),
            "footprint": (
                signal_direction * footprint["direction"]
                if footprint["strength_ok"]
                else 0
            ),
            "price_response": (
                signal_direction * response["direction"]
                if response["confirms_executed_flow"]
                else 0
            ),
            "dom_modifier": (
                signal_direction * dom["direction"]
                if dom["persistent"]
                and executed_flow_present
                else 0
            ),
        }

        return {
            "engine": "RITHMIC_ANTI_FAKEOUT_V1",
            "status": status,
            "signal": signal_name or None,
            "session": session,
            "decision_impact": DECISION_IMPACT,
            "can_influence_decision": CAN_INFLUENCE_DECISION,
            "safe_for_execution": SAFE_FOR_EXECUTION,
            "freshness_gate": freshness,
            "executed_flow": flow,
            "footprint": footprint,
            "price_response": response,
            "dom": dom,
            "executed_vs_resting_agreement": executed_vs_resting_agreement,
            "dom_only_untrusted": dom_only,
            "spoof_risk": spoof_risk,
            "absorption_against_signal": absorption_against_signal,
            "flow_confirms_signal": flow_confirms_signal,
            "footprint_confirms_signal": footprint_confirms_signal,
            "price_confirms_signal": price_confirms_signal,
            "volume_profile": {
                "rolling_poc_futures": rolling_poc,
                "basis_adjusted_poc_xauusd": adjusted_poc,
                "basis_quality": (
                    basis_state.get("quality")
                    if isinstance(basis_state, dict)
                    else "UNAVAILABLE"
                ),
            },
            "score_components": score_components,
            "policy": {
                "dom_can_pass_alone": False,
                "requires_fresh_executed_flow": True,
                "requires_footprint_confirmation_for_confirmed": True,
                "requires_price_response_for_confirmed": True,
                "depth_churn_is_cancel_add_proxy_only": True,
            },
        }
