from datetime import datetime, timedelta
from src.confirmation_engine import confirm_rejection_entry, confirm_breakout_hold


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

    def register_setup(self, signal_data, current_price, atr):
        if self._is_duplicate(signal_data):
            return

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
        }

        self.active_setups.append(setup)

    def process_setups(self, df, price, atr):
        executable = []

        for setup in self.active_setups:
            if setup["state"] in ["EXECUTED", "INVALIDATED", "EXPIRED"]:
                continue

            if datetime.utcnow() > setup["expires_at"]:
                setup["state"] = "EXPIRED"
                continue

            strategy = setup["strategy"]
            signal = setup["signal"]
            data = setup["data"]

            if strategy == "FVG":
                top = data.get("fvg_top")
                bottom = data.get("fvg_bottom")
                if top is None or bottom is None:
                    continue

                zone_low = min(bottom, top)
                zone_high = max(bottom, top)

                if confirm_rejection_entry(df, signal, zone_low, zone_high, atr):
                    setup["state"] = "READY"
                    executable.append(setup)
                else:
                    setup["state"] = "WAITING"

            elif strategy == "ORDER_BLOCK":
                # Order block strategy already confirms displacement + revisit.
                # Do not require a second zone rejection here, otherwise valid entries may be missed.
                setup["state"] = "READY"
                setup["wait_reason"] = None
                executable.append(setup)

            elif strategy == "ORB":
                orb_low = data.get("orb_low")
                orb_high = data.get("orb_high")
                entry_model = data.get("entry_model", "BREAKOUT")

                if orb_low is None or orb_high is None:
                    setup["state"] = "WAITING"
                    setup["wait_reason"] = "ORB levels missing"
                    continue

                if signal == "SELL":
                    if entry_model == "BREAKOUT":
                        if confirm_breakout_hold(df, signal, orb_low, atr):
                            setup["state"] = "READY"
                            setup["wait_reason"] = None
                            executable.append(setup)
                        else:
                            setup["state"] = "WAITING"
                            setup["wait_reason"] = (
                                f"ORB SELL breakout hold not confirmed | "
                                f"level={round(orb_low, 2)}"
                          )
                    else:
                        zone_low = orb_low
                        zone_high = orb_low + max(atr * 0.20, 2.0)
                        if confirm_rejection_entry(df, signal, zone_low, zone_high, atr):
                            setup["state"] = "READY"
                            executable.append(setup)
                        else:
                            setup["state"] = "WAITING"

                elif signal == "BUY":
                    if entry_model == "BREAKOUT":
                        if confirm_breakout_hold(df, signal, orb_high, atr):
                            setup["state"] = "READY"
                            setup["wait_reason"] = None
                            executable.append(setup)
                        else:
                            setup["state"] = "WAITING"
                            setup["wait_reason"] = (
                                f"ORB BUY breakout hold not confirmed | "
                                f"level={round(orb_high, 2)}"
                            )
                    else:
                        zone_low = orb_high - max(atr * 0.20, 2.0)
                        zone_high = orb_high
                        if confirm_rejection_entry(df, signal, zone_low, zone_high, atr):
                            setup["state"] = "READY"
                            executable.append(setup)
                        else:
                            setup["state"] = "WAITING"

            else:
                setup["state"] = "READY"
                executable.append(setup)

        return executable

    def mark_executed(self, setup):
        setup["state"] = "EXECUTED"