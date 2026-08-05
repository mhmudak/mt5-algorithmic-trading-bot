
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


PHASE = "PHASE_6S10_EVIDENCE_COLLECTION_HEALTH"


BOOL_SETTING_NAMES = (
    "ENABLE_PHASE6S_RUNTIME_OUTLOOK_ADVISORY",
    "SEND_PHASE6S_RUNTIME_OUTLOOK_ADVISORY_TELEGRAM",
    "PHASE6S_RUNTIME_OUTLOOK_ADVISORY_FORCE_SEND",
    "ENABLE_PHASE6S_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION",
)


def _parse_bool_setting(settings_text: str, name: str) -> Optional[bool]:
    match = re.search(rf"^\s*{re.escape(name)}\s*=\s*(True|False)\s*$", settings_text, re.MULTILINE)

    if not match:
        return None

    return match.group(1) == "True"


def read_phase6s_evidence_settings(settings_path: str | Path = "config/settings.py") -> Dict[str, Optional[bool]]:
    path = Path(settings_path)

    if not path.exists():
        return {name: None for name in BOOL_SETTING_NAMES}

    text = path.read_text(encoding="utf-8")

    return {
        name: _parse_bool_setting(text, name)
        for name in BOOL_SETTING_NAMES
    }


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []

    if not path.exists():
        return rows

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line:
            continue

        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue

        if isinstance(row, dict):
            rows.append(row)

    return rows


def scan_phase6s_execution_annotations(
    annotation_dir: str | Path = "data/reports/market_outlook/execution_annotations",
) -> Dict[str, Any]:
    target = Path(annotation_dir)

    if not target.exists():
        return {
            "annotation_dir": str(target),
            "exists": False,
            "files": 0,
            "annotations": 0,
            "tags": {},
            "strategies": {},
            "latest": None,
        }

    files = sorted(target.glob("*.jsonl"))
    rows = []

    for path in files:
        for row in _read_jsonl(path):
            if row.get("phase") == "PHASE_6S8_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION":
                row = dict(row)
                row["_source_file"] = str(path)
                rows.append(row)

    rows_sorted = sorted(
        rows,
        key=lambda item: str(item.get("created_at_utc") or ""),
    )

    latest = rows_sorted[-1] if rows_sorted else None

    return {
        "annotation_dir": str(target),
        "exists": True,
        "files": len(files),
        "annotations": len(rows),
        "tags": dict(Counter(str(row.get("tag") or "UNKNOWN") for row in rows)),
        "strategies": dict(Counter(str(row.get("strategy") or "UNKNOWN") for row in rows)),
        "latest": latest,
    }


def read_latest_attribution_report(
    latest_report_path: str | Path = "data/reports/market_outlook/outcome_attribution/phase6s_outcome_attribution_latest.json",
) -> Dict[str, Any]:
    path = Path(latest_report_path)

    if not path.exists():
        return {
            "exists": False,
            "path": str(path),
            "counts": None,
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "exists": True,
            "path": str(path),
            "error": str(exc),
            "counts": None,
        }

    return {
        "exists": True,
        "path": str(path),
        "counts": data.get("counts"),
        "created_at_utc": data.get("created_at_utc"),
    }


def classify_phase6s_evidence_health(settings: Dict[str, Optional[bool]], annotation_scan: Dict[str, Any]) -> str:
    advisory_enabled = settings.get("ENABLE_PHASE6S_RUNTIME_OUTLOOK_ADVISORY")
    telegram_enabled = settings.get("SEND_PHASE6S_RUNTIME_OUTLOOK_ADVISORY_TELEGRAM")
    force_send = settings.get("PHASE6S_RUNTIME_OUTLOOK_ADVISORY_FORCE_SEND")
    annotation_enabled = settings.get("ENABLE_PHASE6S_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION")

    if telegram_enabled is True or force_send is True:
        return "REVIEW_TELEGRAM_OR_FORCE_SEND_ENABLED"

    if advisory_enabled is not True and annotation_enabled is True:
        return "WEAK_EVIDENCE_MODE_ADVISORY_DISABLED"

    if advisory_enabled is True and annotation_enabled is not True:
        return "ADVISORY_ONLY_NO_EXECUTION_ANNOTATION"

    if advisory_enabled is True and annotation_enabled is True:
        if int(annotation_scan.get("annotations") or 0) > 0:
            return "EVIDENCE_COLLECTION_ACTIVE_WITH_DATA"

        return "EVIDENCE_COLLECTION_READY_WAITING_FOR_EXECUTIONS"

    return "EVIDENCE_COLLECTION_DISABLED"


def build_phase6s_evidence_health_report(
    *,
    settings_path: str | Path = "config/settings.py",
    annotation_dir: str | Path = "data/reports/market_outlook/execution_annotations",
    latest_attribution_path: str | Path = "data/reports/market_outlook/outcome_attribution/phase6s_outcome_attribution_latest.json",
) -> Dict[str, Any]:
    settings = read_phase6s_evidence_settings(settings_path)
    annotation_scan = scan_phase6s_execution_annotations(annotation_dir)
    latest_attribution = read_latest_attribution_report(latest_attribution_path)

    health_status = classify_phase6s_evidence_health(settings, annotation_scan)

    return {
        "phase": PHASE,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "health_status": health_status,

        # Safety contract
        "decision_impact": "REPORT_ONLY",
        "auto_trade_allowed": False,
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_risk": False,
        "can_modify_entry_sl_tp": False,

        "settings": settings,
        "annotations": annotation_scan,
        "latest_attribution": latest_attribution,
    }


def write_phase6s_evidence_health_report(
    report: Dict[str, Any],
    *,
    output_dir: str | Path = "data/reports/market_outlook/evidence_health",
) -> Dict[str, str]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = target / f"phase6s_evidence_health_{timestamp}.json"
    latest_path = target / "phase6s_evidence_health_latest.json"

    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)

    json_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")

    return {
        "json": str(json_path),
        "latest_json": str(latest_path),
    }
