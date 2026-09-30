from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIVE_BOT = ROOT / "src" / "live_bot.py"


def main() -> None:
    source = LIVE_BOT.read_text(
        encoding="utf-8-sig"
    )

    start_token = (
        'rejected_signal_data["recovery_source"] = '
        '"intrabar_price_event_low_rr"'
    )
    end_token = (
        'logger.info(\n'
        '            f"[INTRABAR ORB] Guard blocked | "'
    )

    start = source.find(start_token)
    assert start >= 0, "intrabar LOW_RR branch start not found"

    end = source.find(end_token, start)
    assert end > start, "intrabar LOW_RR branch end not found"

    branch = source[start:end]

    assert (
        "_directional_alert_context_blocks_fail_open("
        in branch
    )
    assert "intrabar_rithmic_block" in branch
    assert "intrabar_participation_block" in branch

    assert (
        "_market_participation_telegram_block_fail_open("
        not in branch
    )

    expected_prefix = (
        'if intrabar_rithmic_block:\n'
        '                intrabar_rejected_message = (\n'
        '                    intrabar_rithmic_block\n'
        '                    + "\\n--------------------------------\\n\\n"\n'
        '                    + intrabar_rejected_message\n'
        '                )'
    )

    assert expected_prefix in branch

    # Existing rejection/recovery behavior must still be present.
    assert (
        "register_rejected_candidate_for_recovery("
        in branch
    )
    assert 'reason_type="LOW_RR"' in branch
    assert (
        "TELEGRAM_NOTIFY_CANDIDATE_REJECTED_LOW_RR"
        in branch
    )
    assert "return False" in branch

    # Rithmic integration is presentation-only in this branch.
    rithmic_use = branch[
        branch.find(
            "_directional_alert_context_blocks_fail_open("
        ):
    ]

    assert "execute_trade(" not in rithmic_use
    assert "order_send(" not in rithmic_use

    print(
        "PASS: intrabar LOW_RR alert reuses the "
        "directional Rithmic/participation helper"
    )
    print(
        "PASS: Rithmic block is Telegram presentation only"
    )
    print(
        "PASS: rejection and recovery path remains present"
    )
    print()
    print(
        "[PASS] Intrabar LOW_RR Rithmic display "
        "integration verified."
    )


if __name__ == "__main__":
    main()
