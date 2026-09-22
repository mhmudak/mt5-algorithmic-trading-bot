from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.order_flow_features.rithmic_anti_fakeout import (
    FuturesSpotBasisTracker,
    RithmicAntiFakeoutEngine,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate one saved Rithmic state-cache snapshot with the "
            "observe-only anti-fakeout engine."
        )
    )
    parser.add_argument(
        "--snapshot",
        required=True,
        help="Path to a Rithmic state-cache JSON snapshot.",
    )
    parser.add_argument(
        "--signal",
        choices=("BUY", "SELL"),
        default=None,
    )
    parser.add_argument(
        "--session",
        default="UNSPECIFIED",
    )
    parser.add_argument(
        "--tick-size",
        type=float,
        default=0.1,
    )
    parser.add_argument(
        "--xau-mid",
        type=float,
        default=None,
        help=(
            "Optional XAUUSD mid for a one-sample basis observation. "
            "One sample is intentionally insufficient to mark basis stable."
        ),
    )
    args = parser.parse_args()

    snapshot_path = Path(args.snapshot)
    snapshot = json.loads(
        snapshot_path.read_text(
            encoding="utf-8",
        )
    )

    basis_state = None

    if args.xau_mid is not None:
        top_bid = (
            snapshot.get("order_book", {}).get("top_bid_price")
        )
        top_ask = (
            snapshot.get("order_book", {}).get("top_ask_price")
        )

        if (
            isinstance(top_bid, (int, float))
            and isinstance(top_ask, (int, float))
            and top_bid > 0
            and top_ask > 0
        ):
            futures_mid = (float(top_bid) + float(top_ask)) / 2.0
            tracker = FuturesSpotBasisTracker()
            basis_state = tracker.update(
                futures_mid=futures_mid,
                xauusd_mid=args.xau_mid,
            )

    engine = RithmicAntiFakeoutEngine(
        tick_size=args.tick_size,
    )
    result = engine.update(
        snapshot,
        signal=args.signal,
        session=args.session,
        basis_state=basis_state,
    )

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
