from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
from pathlib import Path


# Direct execution:
#
#   python scripts/test_phase5ac_basis_promotion_v1.py
#
# puts scripts/ at sys.path[0]. Explicitly add the repository
# root so scripts.*, src.*, and config.* imports resolve exactly
# as they do from the project root.
ROOT = Path(__file__).resolve().parents[1]

root_text = str(ROOT)

if root_text not in sys.path:
    sys.path.insert(
        0,
        root_text,
    )


from scripts.run_phase5ac_xauusd_rithmic_basis_calibration import (
    promote_candidate_basis_if_ready,
)


SOURCE_PATH = (
    ROOT
    / "scripts"
    / "run_phase5ac_xauusd_rithmic_basis_calibration.py"
)


def payload(
    *,
    status="COMPLETED",
    ready=True,
    basis=-32.4,
):
    return {
        "phase": (
            "PHASE_5AC_XAUUSD_RITHMIC_BASIS_CALIBRATION"
        ),
        "session_status": status,
        "mt5_symbol": "XAUUSD",
        "rithmic_symbol": "GCZ6",
        "exchange": "COMEX",
        "summary": {
            "sample_count": 32,
            "valid_pair_count": 31,
            "valid_pair_rate": 0.9688,
            "avg_basis": basis,
            "basis_std": 0.2,
            "basis_ready_observe_only": ready,
            "decision_grade_ready": False,
            "automation_allowed": False,
        },
        "mode": "OBSERVE_ONLY",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "trade_action": "NO_AUTO_TRADE",
    }


def write_payload(
    path: Path,
    value,
):
    path.write_text(
        json.dumps(
            value,
            indent=2,
        ),
        encoding="utf-8",
    )


def read_payload(
    path: Path,
):
    return json.loads(
        path.read_text(
            encoding="utf-8",
        )
    )


def test_low_quality_candidate_preserves_canonical():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        candidate = root / "candidate.json"
        canonical = root / "canonical.json"

        old = payload(
            ready=True,
            basis=-32.1,
        )

        bad = payload(
            ready=False,
            basis=-99.0,
        )

        write_payload(
            canonical,
            old,
        )

        old_epoch = 1_700_000_000

        os.utime(
            canonical,
            (
                old_epoch,
                old_epoch,
            ),
        )

        write_payload(
            candidate,
            bad,
        )

        promoted = (
            promote_candidate_basis_if_ready(
                candidate_path=candidate,
                canonical_path=canonical,
                session_status="COMPLETED",
                summary=bad["summary"],
            )
        )

        assert promoted is False
        assert read_payload(canonical) == old

        assert int(
            canonical.stat().st_mtime
        ) == old_epoch

    print(
        "PASS: low-quality candidate preserves "
        "last good canonical and mtime"
    )


def test_partial_session_preserves_canonical():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        candidate = root / "candidate.json"
        canonical = root / "canonical.json"

        old = payload(
            ready=True,
            basis=-32.2,
        )

        partial = payload(
            status="RUNNING",
            ready=True,
            basis=-32.3,
        )

        write_payload(
            canonical,
            old,
        )

        write_payload(
            candidate,
            partial,
        )

        promoted = (
            promote_candidate_basis_if_ready(
                candidate_path=candidate,
                canonical_path=canonical,
                session_status="RUNNING",
                summary=partial["summary"],
            )
        )

        assert promoted is False
        assert read_payload(canonical) == old

    print(
        "PASS: partial session cannot replace canonical"
    )


def test_candidate_payload_must_also_be_ready():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        candidate = root / "candidate.json"
        canonical = root / "canonical.json"

        old = payload(
            ready=True,
            basis=-32.2,
        )

        bad_candidate = payload(
            ready=False,
            basis=-88.0,
        )

        caller_summary = payload(
            ready=True,
            basis=-32.3,
        )["summary"]

        write_payload(
            canonical,
            old,
        )

        write_payload(
            candidate,
            bad_candidate,
        )

        promoted = (
            promote_candidate_basis_if_ready(
                candidate_path=candidate,
                canonical_path=canonical,
                session_status="COMPLETED",
                summary=caller_summary,
            )
        )

        assert promoted is False
        assert read_payload(canonical) == old

    print(
        "PASS: candidate payload readiness is "
        "independently required"
    )


def test_ready_completed_candidate_promotes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        candidate = root / "candidate.json"
        canonical = root / "canonical.json"

        old = payload(
            ready=True,
            basis=-31.0,
        )

        good = payload(
            ready=True,
            basis=-32.45,
        )

        write_payload(
            canonical,
            old,
        )

        old_epoch = 1_700_000_000

        os.utime(
            canonical,
            (
                old_epoch,
                old_epoch,
            ),
        )

        write_payload(
            candidate,
            good,
        )

        promoted = (
            promote_candidate_basis_if_ready(
                candidate_path=candidate,
                canonical_path=canonical,
                session_status="COMPLETED",
                summary=good["summary"],
            )
        )

        assert promoted is True
        assert read_payload(canonical) == good

        assert (
            canonical.stat().st_mtime
            > old_epoch
        )

    print(
        "PASS: completed observe-ready candidate "
        "is promoted atomically"
    )


def test_live_script_wiring():
    source = SOURCE_PATH.read_text(
        encoding="utf-8-sig",
    )

    tree = ast.parse(
        source
    )

    assert "CANDIDATE_JSON" in source

    assert (
        "promote_candidate_basis_if_ready"
        in source
    )

    write_progress = None

    for node in ast.walk(tree):
        if (
            isinstance(
                node,
                ast.FunctionDef,
            )
            and node.name == "write_progress"
        ):
            write_progress = node
            break

    assert write_progress is not None

    progress_source = ast.get_source_segment(
        source,
        write_progress,
    )

    assert progress_source is not None

    assert (
        "CANDIDATE_JSON"
        in progress_source
    )

    assert (
        "OUT_JSON"
        not in progress_source
    )

    assert (
        "canonical_promoted"
        in source
    )

    print(
        "PASS: live calibration progress writes "
        "candidate only"
    )


def main():
    test_low_quality_candidate_preserves_canonical()
    test_partial_session_preserves_canonical()
    test_candidate_payload_must_also_be_ready()
    test_ready_completed_candidate_promotes()
    test_live_script_wiring()

    print()

    print(
        "[PASS] Phase5AC safe basis promotion "
        "contract verified."
    )


if __name__ == "__main__":
    main()
