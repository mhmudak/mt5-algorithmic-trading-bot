from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import (
    PROP_FIRM_PROFILE,
    PROP_FIRM_PROFILES,
)
from src.prop_firm_news_guard import (
    evaluate_prop_firm_news_restriction,
)


def main() -> int:
    now = datetime.now()
    profile_name = str(PROP_FIRM_PROFILE).strip().upper()
    profile = PROP_FIRM_PROFILES.get(profile_name)

    synthetic_event = {
        "name": "SYNTHETIC HIGH-IMPACT TEST",
        "time": now,
        "currency": "USD",
        "impact": "High",
        "source": "SYNTHETIC_TEST",
    }

    decision = evaluate_prop_firm_news_restriction(
        enabled=True,
        profile_name=profile_name,
        profile=profile,
        calendar_snapshot={
            "available": True,
            "provider": "SYNTHETIC_TEST",
            "events": [synthetic_event],
            "error": None,
        },
        action="OPEN_POSITION",
        now=now,
        fail_closed=True,
    )

    print(
        "STATUS: "
        + (
            "ALLOWED"
            if decision.get("allowed")
            else "BLOCKED"
        )
    )
    print(f"Reason: {decision.get('reason')}")
    print(f"Profile: {profile_name}")
    print(
        "Restricted event: "
        f"{decision.get('snapshot', {}).get('restricted_event')}"
    )
    print("Orders sent: 0")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
