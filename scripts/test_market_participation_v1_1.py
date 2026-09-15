from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.market_participation_context import (
    _reset_market_participation_state_for_tests,
    build_market_participation_context,
    build_mt5_tick_participation_context,
    format_market_participation_telegram_block,
    record_mt5_tick,
)


def _record_mid(epoch, mid):
    tick = {
        "time": int(epoch),
        "time_msc": int(epoch * 1000),
        "bid": mid - 0.10,
        "ask": mid + 0.10,
    }

    assert record_mt5_tick(
        tick,
        observed_at_epoch=epoch,
    )


def _seed_direction_bucket(
    *,
    epochs,
    mids,
):
    assert len(epochs) == len(mids)

    for epoch, mid in zip(
        epochs,
        mids,
    ):
        _record_mid(
            epoch,
            mid,
        )


def _seed_four_of_five_sell():
    _reset_market_participation_state_for_tests()

    # Oldest bucket: BUY.
    _seed_direction_bucket(
        epochs=[976.0, 978.0, 980.0],
        mids=[100.0, 100.2, 100.4],
    )

    # Four subsequent non-overlapping buckets: SELL.
    _seed_direction_bucket(
        epochs=[981.0, 983.0, 985.0],
        mids=[100.4, 100.2, 100.0],
    )
    _seed_direction_bucket(
        epochs=[986.0, 988.0, 990.0],
        mids=[100.0, 99.8, 99.6],
    )
    _seed_direction_bucket(
        epochs=[991.0, 993.0, 995.0],
        mids=[99.6, 99.4, 99.2],
    )
    _seed_direction_bucket(
        epochs=[996.0, 998.0, 1000.0],
        mids=[99.2, 99.0, 98.8],
    )


def test_real_five_bucket_persistence():
    _seed_four_of_five_sell()

    mt5 = build_mt5_tick_participation_context(
        now_epoch=1000.0,
    )

    persistence = mt5[
        "direction_persistence"
    ]

    assert persistence["bucket_count"] == 5
    assert persistence["sell_count"] == 4
    assert persistence["buy_count"] == 1
    assert persistence["unresolved_count"] == 0
    assert (
        persistence["dominant_direction"]
        == "SELL"
    )
    assert persistence["dominant_count"] == 4
    assert persistence["label"] == "4/5 SELL"

    assert persistence["decision_impact"] == "NONE"
    assert persistence["can_influence_decision"] is False
    assert persistence["safe_for_execution"] is False


def test_sparse_bucket_stays_unresolved():
    _reset_market_participation_state_for_tests()

    _record_mid(
        999.0,
        100.0,
    )
    _record_mid(
        1000.0,
        99.5,
    )

    mt5 = build_mt5_tick_participation_context(
        now_epoch=1000.0,
    )

    persistence = mt5[
        "direction_persistence"
    ]

    assert persistence["sell_count"] == 0
    assert persistence["buy_count"] == 0
    assert persistence["unresolved_count"] == 5
    assert persistence["label"] == "0/5 UNRESOLVED"


def test_formatter_explains_signed_values():
    _seed_four_of_five_sell()

    context = build_market_participation_context(
        symbol="XAUUSD",
        signal="SELL",
        now_epoch=1000.0,
    )

    block = (
        format_market_participation_telegram_block(
            context
        )
    )

    lines = block.splitlines()

    imbalance_line = next(
        line
        for line in lines
        if line.startswith(
            "5s Imbalance: "
        )
    )

    acceleration_line = next(
        line
        for line in lines
        if line.startswith(
            "Activity Acceleration: "
        )
    )

    persistence_line = next(
        line
        for line in lines
        if line.startswith(
            "Persistence: "
        )
    )

    assert imbalance_line.endswith(
        "| SELL"
    )

    assert acceleration_line.endswith(
        "x"
    )

    assert (
        persistence_line
        == "Persistence: 4/5 SELL"
    )

    assert "Mode: OBSERVE ONLY" in block

    assert context["decision_impact"] == "NONE"
    assert context["can_influence_decision"] is False
    assert context["safe_for_execution"] is False


def test_no_fake_atr_claim():
    _seed_four_of_five_sell()

    context = build_market_participation_context(
        symbol="XAUUSD",
        signal="SELL",
        now_epoch=1000.0,
    )

    block = (
        format_market_participation_telegram_block(
            context
        )
    )

    assert " ATR" not in block


def test_fixed_lot_unchanged():
    settings = (
        ROOT
        / "config"
        / "settings.py"
    ).read_text(
        encoding="utf-8",
    )

    assert "FIXED_LOT = 0.25" in settings


def test_source_remains_display_only():
    source = (
        ROOT
        / "src"
        / "market_participation_context.py"
    ).read_text(
        encoding="utf-8",
    )

    assert '"decision_impact": "NONE"' in source
    assert '"can_influence_decision": False' in source
    assert '"safe_for_execution": False' in source

    for relative_path in (
        "src/risk.py",
        "src/execution_engine.py",
        "src/candidate_rejection_recovery.py",
    ):
        text = (
            ROOT
            / relative_path
        ).read_text(
            encoding="utf-8",
        )

        assert "direction_persistence" not in text


if __name__ == "__main__":
    test_real_five_bucket_persistence()
    test_sparse_bucket_stays_unresolved()
    test_formatter_explains_signed_values()
    test_no_fake_atr_claim()
    test_fixed_lot_unchanged()
    test_source_remains_display_only()

    print("PASS: Market Participation V1.1")
    print("PASS: five non-overlapping 5s persistence buckets")
    print("PASS: imbalance direction label")
    print("PASS: acceleration ratio displayed with x")
    print("PASS: sparse buckets remain unresolved")
    print("PASS: no fake ATR normalization")
    print("PASS: observer remains DISPLAY_ONLY")
    print("PASS: FIXED_LOT remains 0.25")
