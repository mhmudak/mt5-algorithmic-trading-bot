from datetime import datetime, timedelta

from src.confirmation_engine import confirm_rejection_entry, confirm_breakout_hold


INVALIDATED_SETUPS = []
MAX_INVALIDATED_SETUPS = 50

from config.settings import (
    ENABLE_ORB_DIRECT_BREAKOUT,
    ORB_DIRECT_BREAKOUT_MIN_SCORE,
    ORB_DIRECT_BREAKOUT_REQUIRE_SMC,
    ORB_DIRECT_BREAKOUT_EXTRA_SL_PRICE,
)

def get_recent_invalidated_setups(strategy=None, max_age_minutes=30):
    now = datetime.utcnow()
    recent = []

    for item in INVALIDATED_SETUPS:
        invalidated_at = item.get("invalidated_at")

        if invalidated_at is None:
            continue

        age_minutes = (now - invalidated_at).total_seconds() / 60

        if age_minutes > max_age_minutes:
            continue

        if strategy is not None and item.get("strategy") != strategy:
            continue

        recent.append(item)

    return recent


class ExecutionEngine:
    def __init__(self):
        self.active_setups = []

    def _is_duplicate(self, signal_data):
        strategy = signal_data.get("strategy")
        signal = signal_data.get("signal")
        entry_model = signal_data.get("entry_model")

        for setup in self.active_setups:
            if setup["state"] in ["EXECUTED", "INVALIDATED", "EXPIRED"]:
                continue

            if (
                setup["strategy"] == strategy
                and setup["signal"] == signal
                and setup["entry_model"] == entry_model
            ):
                return True

        return False

    def _mark_ready(self, setup, executable):
        setup["state"] = "READY"
        setup["wait_reason"] = None
        executable.append(setup)

    def _mark_waiting(self, setup, reason):
        setup["state"] = "WAITING"
        setup["wait_reason"] = reason

    def _mark_invalidated(self, setup, reason):
        setup["state"] = "INVALIDATED"
        setup["wait_reason"] = reason
        setup["invalidated_at"] = datetime.utcnow()
        setup["invalidation_reason"] = reason

        INVALIDATED_SETUPS.append(
            {
                "strategy": setup.get("strategy"),
                "signal": setup.get("signal"),
                "entry_model": setup.get("entry_model"),
                "invalidated_at": setup["invalidated_at"],
                "reason": reason,
                "data": setup.get("data", {}).copy(),
            }
        )

        if len(INVALIDATED_SETUPS) > MAX_INVALIDATED_SETUPS:
            del INVALIDATED_SETUPS[:-MAX_INVALIDATED_SETUPS]

    def register_setup(self, signal_data, current_price, atr):
        if self._is_duplicate(signal_data):
            return None

        setup = {
            "strategy": signal_data.get("strategy"),
            "signal": signal_data.get("signal"),
            "entry_model": signal_data.get("entry_model", "MARKET"),
            "state": "DETECTED",
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(minutes=15),
            "data": signal_data,
            "notified": False,
            "wait_reason": None,
            "invalidated_at": None,
            "invalidation_reason": None,
        }

        self.active_setups.append(setup)
        return setup

    def _orb_direct_breakout_allowed(self, setup):
        if not ENABLE_ORB_DIRECT_BREAKOUT:
            return False

        data = setup.get("data", {})

        if data.get("entry_model") != "BREAKOUT":
            return False

        if data.get("score", 0) < ORB_DIRECT_BREAKOUT_MIN_SCORE:
            return False

        if not ORB_DIRECT_BREAKOUT_REQUIRE_SMC:
            return True

        smc_reasons = data.get("smc", [])

        if not smc_reasons:
            return False

        signal = data.get("signal")

        has_displacement = "displacement" in smc_reasons

        if signal == "BUY":
            has_structure = "bullish_bos" in smc_reasons
        elif signal == "SELL":
            has_structure = "bearish_bos" in smc_reasons
        else:
            has_structure = False

        return has_displacement and has_structure

    def _apply_orb_direct_extra_sl(self, setup):
        data = setup.get("data", {})

        if data.get("orb_direct_extra_sl_applied"):
            return

        sl_reference = data.get("sl_reference")
        signal = data.get("signal")

        if sl_reference is None:
            return

        if signal == "BUY":
            data["sl_reference"] = round(
                sl_reference - ORB_DIRECT_BREAKOUT_EXTRA_SL_PRICE,
                2,
            )

        elif signal == "SELL":
            data["sl_reference"] = round(
                sl_reference + ORB_DIRECT_BREAKOUT_EXTRA_SL_PRICE,
                2,
            )

        data["orb_direct_extra_sl_applied"] = True
        data["orb_direct_extra_sl_price"] = ORB_DIRECT_BREAKOUT_EXTRA_SL_PRICE

        reason = data.get("reason", "N/A")
        data["reason"] = (
            f"{reason} | ORB_DIRECT_BREAKOUT: extra SL "
            f"{ORB_DIRECT_BREAKOUT_EXTRA_SL_PRICE}"
        )

    def process_setups(self, df, price, atr):
        executable = []

        if len(df) < 4:
            return executable

        last_closed = df.iloc[-2]

        for setup in self.active_setups:
            if setup["state"] in [
                "EXECUTED",
                "INVALIDATED",
                "EXPIRED",
                "WAIT_BETTER_ENTRY",
                "WAIT_DELAYED_ENTRY",
                "EXECUTION_FAILED",
                "SKIPPED",
            ]:
                continue

            if datetime.utcnow() > setup["expires_at"]:
                setup["state"] = "EXPIRED"
                setup["wait_reason"] = "Setup expired"
                continue

            strategy = setup["strategy"]
            signal = setup["signal"]
            data = setup["data"]

            # =========================
            # FVG
            # =========================
            if strategy == "FVG":
                top = data.get("fvg_top")
                bottom = data.get("fvg_bottom")

                if top is None or bottom is None:
                    self._mark_waiting(setup, "FVG levels missing")
                    continue

                zone_low = min(bottom, top)
                zone_high = max(bottom, top)

                if signal == "BUY" and last_closed["close"] < zone_low:
                    self._mark_invalidated(
                        setup,
                        f"FVG BUY invalidated | close below gap {round(zone_low, 2)}",
                    )
                    continue

                if signal == "SELL" and last_closed["close"] > zone_high:
                    self._mark_invalidated(
                        setup,
                        f"FVG SELL invalidated | close above gap {round(zone_high, 2)}",
                    )
                    continue

                if confirm_rejection_entry(df, signal, zone_low, zone_high, atr):
                    self._mark_ready(setup, executable)
                else:
                    self._mark_waiting(
                        setup,
                        f"FVG rejection not confirmed | zone={round(zone_low, 2)}-{round(zone_high, 2)}",
                    )

            # =========================
            # ORDER BLOCK
            # =========================
            elif strategy == "ORDER_BLOCK":
                # Order block strategy already confirms displacement + revisit.
                # Do not require a second zone rejection here.
                self._mark_ready(setup, executable)

            # =========================
            # ORB
            # =========================
            elif strategy == "ORB":
                orb_low = data.get("orb_low")
                orb_high = data.get("orb_high")
                entry_model = data.get("entry_model", "BREAKOUT")

                if orb_low is None or orb_high is None:
                    self._mark_waiting(setup, "ORB levels missing")
                    continue

                # -------------------------
                # ORB SELL
                # -------------------------
                if signal == "SELL":

                    # FAST_CONTINUATION:
                    # Strategy already confirmed a strong immediate breakout.
                    # No need to wait for another breakout-hold candle.
                    if entry_model == "FAST_CONTINUATION":
                        self._mark_ready(setup, executable)
                        continue

                    if entry_model == "BREAKOUT":
                        # Invalidation:
                        # ORB SELL is invalid if price closes back above breakdown level.
                        if last_closed["close"] > orb_low:
                            self._mark_invalidated(
                                setup,
                                f"ORB SELL invalidated | close back above breakdown level {round(orb_low, 2)}",
                            )
                            continue

                        if self._orb_direct_breakout_allowed(setup):
                            self._apply_orb_direct_extra_sl(setup)
                            self._mark_ready(setup, executable)
                            continue

                        if confirm_breakout_hold(df, signal, orb_low, atr):
                            self._mark_ready(setup, executable)
                        else:
                            self._mark_waiting(
                                setup,
                                f"ORB SELL breakout hold not confirmed | level={round(orb_low, 2)}",
                            )

                    else:
                        # WAIT_RETEST logic
                        # Invalidation if price fully recovers above the opposite side of the ORB.
                        if last_closed["close"] > orb_high:
                            self._mark_invalidated(
                                setup,
                                f"ORB SELL retest invalidated | close above ORB high {round(orb_high, 2)}",
                            )
                            continue

                        zone_low = orb_low
                        zone_high = orb_low + max(atr * 0.20, 2.0)

                        if confirm_rejection_entry(df, signal, zone_low, zone_high, atr):
                            self._mark_ready(setup, executable)
                        else:
                            self._mark_waiting(
                                setup,
                                f"ORB SELL retest rejection not confirmed | zone={round(zone_low, 2)}-{round(zone_high, 2)}",
                            )

                # -------------------------
                # ORB BUY
                # -------------------------
                elif signal == "BUY":

                    # FAST_CONTINUATION:
                    # Strategy already confirmed a strong immediate breakout.
                    # No need to wait for another breakout-hold candle.
                    if entry_model == "FAST_CONTINUATION":
                        self._mark_ready(setup, executable)
                        continue

                    if entry_model == "BREAKOUT":
                        # Invalidation:
                        # ORB BUY is invalid if price closes back below breakout level.
                        if last_closed["close"] < orb_high:
                            self._mark_invalidated(
                                setup,
                                f"ORB BUY invalidated | close back below breakout level {round(orb_high, 2)}",
                            )
                            continue

                        if self._orb_direct_breakout_allowed(setup):
                            self._apply_orb_direct_extra_sl(setup)
                            self._mark_ready(setup, executable)
                            continue

                        if confirm_breakout_hold(df, signal, orb_high, atr):
                            self._mark_ready(setup, executable)
                        else:
                            self._mark_waiting(
                                setup,
                                f"ORB BUY breakout hold not confirmed | level={round(orb_high, 2)}",
                            )

                    else:
                        # WAIT_RETEST logic
                        # Invalidation if price fully returns below the opposite side of the ORB.
                        if last_closed["close"] < orb_low:
                            self._mark_invalidated(
                                setup,
                                f"ORB BUY retest invalidated | close below ORB low {round(orb_low, 2)}",
                            )
                            continue

                        zone_low = orb_high - max(atr * 0.20, 2.0)
                        zone_high = orb_high

                        if confirm_rejection_entry(df, signal, zone_low, zone_high, atr):
                            self._mark_ready(setup, executable)
                        else:
                            self._mark_waiting(
                                setup,
                                f"ORB BUY retest rejection not confirmed | zone={round(zone_low, 2)}-{round(zone_high, 2)}",
                            )

            # =========================
            # ALL OTHER STRATEGY-SPECIFIC SETUPS
            # =========================
            else:
                self._mark_ready(setup, executable)

        return executable

    def mark_wait_better_entry(self, setup, min_rr_required, current_rr, expiry_minutes):
        setup["state"] = "WAIT_BETTER_ENTRY"
        setup["wait_reason"] = (
            f"Waiting for better RR | current={current_rr} "
            f"required={min_rr_required}"
        )
        setup["better_entry_min_rr"] = min_rr_required
        setup["better_entry_initial_rr"] = current_rr
        setup["better_entry_started_at"] = datetime.utcnow()
        setup["expires_at"] = datetime.utcnow() + timedelta(minutes=expiry_minutes)

    def get_wait_better_entry_setups(self):
        valid_setups = []

        for setup in self.active_setups:
            if setup.get("state") != "WAIT_BETTER_ENTRY":
                continue

            if datetime.utcnow() > setup["expires_at"]:
                setup["state"] = "EXPIRED"
                setup["wait_reason"] = "Better-entry setup expired"
                continue

            valid_setups.append(setup)

        return valid_setups

    def mark_wait_delayed_entry(self, setup, target_entry_price, expiry_minutes):
        setup["state"] = "WAIT_DELAYED_ENTRY"
        setup["wait_reason"] = (
            f"Waiting for delayed retrace entry | target={target_entry_price}"
        )
        setup["delayed_entry_target"] = target_entry_price
        setup["delayed_entry_started_at"] = datetime.utcnow()
        setup["expires_at"] = datetime.utcnow() + timedelta(minutes=expiry_minutes)

    def mark_wait_fvg_staged_entry(self, setup, stages, expiry_minutes):
        setup["state"] = "WAIT_FVG_STAGED_ENTRY"
        setup["wait_reason"] = "Waiting for FVG staged entries"
        setup["fvg_staged_entries"] = stages
        setup["fvg_staged_started_at"] = datetime.utcnow()
        setup["expires_at"] = datetime.utcnow() + timedelta(minutes=expiry_minutes)

    def get_wait_delayed_entry_setups(self):
        valid_setups = []

        for setup in self.active_setups:
            if setup.get("state") != "WAIT_DELAYED_ENTRY":
                continue

            if datetime.utcnow() > setup["expires_at"]:
                setup["state"] = "EXPIRED"
                setup["wait_reason"] = "Delayed entry setup expired"
                continue

            valid_setups.append(setup)

        return valid_setups
    
    def get_wait_fvg_staged_entry_setups(self):
        valid_setups = []

        for setup in self.active_setups:
            if setup.get("state") != "WAIT_FVG_STAGED_ENTRY":
                continue

            if datetime.utcnow() > setup["expires_at"]:
                setup["state"] = "EXPIRED"
                setup["wait_reason"] = "FVG staged entry setup expired"
                continue

            valid_setups.append(setup)

        return valid_setups

    def mark_executed(self, setup):
        setup["state"] = "EXECUTED"
        setup["wait_reason"] = None
        
    def mark_execution_failed(self, setup, reason):
        setup["state"] = "EXECUTION_FAILED"
        setup["wait_reason"] = reason