from __future__ import annotations

from pathlib import Path
import re

import src.setup_quality_grade as setup_quality


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "config" / "settings.py"


def main():
    v2_result = {
        "setup_quality_version": "V2",
        "grade": "F",
        "v1_grade": "A+",
        "score_10": 10.0,
        "full_rr": 0.97,
        "grade_blockers": [
            "RR 0.97R < 1.50R A+",
            "Exact-cohort historical edge unavailable",
        ],
        "historical_edge": {
            "trade_sample": 0,
            "path_sample": 0,
            "trade_win_rate": None,
            "hit_plus_10_rate": None,
        },
    }

    text = setup_quality.format_setup_quality_block(
        v2_result
    )

    assert "STRUCTURAL QUALITY: A+" in text
    assert "Raw Score: 10.0/10" in text
    assert "ELIGIBILITY GRADE: F" in text
    assert "Quality RR: 0.97R" in text
    assert "A+ Eligibility: FAIL" in text
    assert "History Scope: EXACT COHORT" in text
    assert (
        "Exact-cohort historical edge unavailable"
        in text
    )

    # V1 must remain byte-for-byte behaviorally delegated
    # to the preserved V1 formatter alias.
    legacy_result = {
        "grade": "A+",
        "score_10": 9.4,
        "confirmations": ["Legacy confirmation"],
    }

    assert (
        setup_quality.format_setup_quality_block(
            legacy_result
        )
        == setup_quality._format_setup_quality_block_v1(
            legacy_result
        )
    )

    source = (
        ROOT
        / "src"
        / "setup_quality_grade.py"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert (
        "hard_f = bool(rr is not None and rr < SQ2_F_RR_THRESHOLD)"
        in source
    )
    assert (
        'and history.get("history_pass", False)'
        in source
    )

    settings = SETTINGS.read_text(
        encoding="utf-8",
        errors="replace",
    )
    fixed = re.search(
        r"(?m)^FIXED_LOT\s*=\s*([0-9.]+)\s*$",
        settings,
    )
    assert fixed
    assert float(fixed.group(1)) == 0.25

    print("PASS: V2 structural quality is explicit")
    print("PASS: V2 eligibility grade is explicit")
    print("PASS: V2 quality RR is labeled separately")
    print("PASS: V2 exact-cohort history scope is explicit")
    print("PASS: legacy V1 formatter path is unchanged")
    print("PASS: low-RR hard-F grading logic is unchanged")
    print("PASS: A+ historical gate is unchanged")
    print("PASS: FIXED_LOT remains exactly 0.25")


if __name__ == "__main__":
    main()
