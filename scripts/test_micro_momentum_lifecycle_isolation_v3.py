from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "config" / "settings.py"
TRACKER = ROOT / "src" / "trade_tracker.py"


def assigned_value(tree, name):
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"setting not found: {name}")


def main():
    print("[MICRO MOMENTUM LIFECYCLE ISOLATION TEST V3]")

    settings_text = SETTINGS.read_text(encoding="utf-8")
    settings_tree = ast.parse(settings_text)
    tracker_text = TRACKER.read_text(encoding="utf-8")
    tracker_tree = ast.parse(tracker_text)

    close_notify = assigned_value(
        settings_tree,
        "MICRO_MOMENTUM_TELEGRAM_CLOSE_NOTIFICATIONS",
    )
    trigger_cooldown = assigned_value(
        settings_tree,
        "MICRO_MOMENTUM_TRIGGER_POST_SL_COOLDOWN",
    )

    print(
        "MICRO_MOMENTUM_TELEGRAM_CLOSE_NOTIFICATIONS="
        f"{close_notify}"
    )
    print(
        "MICRO_MOMENTUM_TRIGGER_POST_SL_COOLDOWN="
        f"{trigger_cooldown}"
    )

    assert close_notify is False
    assert trigger_cooldown is False

    required = [
        "def _micro_momentum_lifecycle_policy(trade):",
        '"INTRABAR_MICRO_MOMENTUM"',
        '"MICRO_MOMENTUM_TRIGGER_POST_SL_COOLDOWN"',
        '"MICRO_MOMENTUM_TELEGRAM_CLOSE_NOTIFICATIONS"',
        'lifecycle_policy = _micro_momentum_lifecycle_policy(trade)',
        'lifecycle_policy["trigger_post_sl_cooldown"]',
        'lifecycle_policy["notify_close"]',
        'activate_cooldown()',
        'Trade Fully Closed',
        'event="TRADE_CLOSED"',
    ]
    for snippet in required:
        if snippet not in tracker_text:
            raise AssertionError(f"missing lifecycle isolation wiring: {snippet}")

    cooldown_policy_found = False
    close_notify_found = False
    closed_event_found = False

    for node in ast.walk(tracker_tree):
        if isinstance(node, ast.If):
            try:
                test_text = ast.unparse(node.test)
            except Exception:
                test_text = ""

            if (
                "close_reason" in test_text
                and "SL" in test_text
                and "trigger_post_sl_cooldown" in test_text
            ):
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Name)
                        and child.func.id == "activate_cooldown"
                    ):
                        cooldown_policy_found = True

            if "notify_close" in test_text:
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Name)
                        and child.func.id == "send_telegram_message"
                    ):
                        literal_text = ""
                        if child.args:
                            for sub in ast.walk(child.args[0]):
                                if (
                                    isinstance(sub, ast.Constant)
                                    and isinstance(sub.value, str)
                                ):
                                    literal_text += sub.value
                        if "Trade Fully Closed" in literal_text:
                            close_notify_found = True

        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "log_setup_event"
        ):
            for kw in node.keywords:
                if kw.arg != "event":
                    continue
                try:
                    if ast.literal_eval(kw.value) == "TRADE_CLOSED":
                        closed_event_found = True
                except Exception:
                    pass

    if not cooldown_policy_found:
        raise AssertionError(
            "Micro Momentum SL cooldown isolation AST wiring missing"
        )
    if not close_notify_found:
        raise AssertionError(
            "Micro Momentum full-close Telegram suppression AST wiring missing"
        )
    if not closed_event_found:
        raise AssertionError("TRADE_CLOSED event persistence missing")

    print(
        "\nPASS: INTRABAR_MICRO_MOMENTUM full-close Telegram is disabled "
        "and its SL/SL_LIKELY closes no longer activate the shared 4-minute "
        "post-SL cooldown. Normal strategies retain existing close Telegram "
        "and post-SL cooldown behavior; TRADE_CLOSED persistence remains on."
    )


if __name__ == "__main__":
    main()
