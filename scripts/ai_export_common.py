import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.account_context import get_account_file
from src.logger import logger
from src.memory_decision_report import load_memory_decision_reports
from src.setup_outcome_tracker import load_setup_outcomes


def add_account_argument(parser):
    parser.add_argument(
        "--account",
        default=None,
        help="Account folder name under data/accounts, for example JustMarkets-Live_123456",
    )


def get_ai_account_file(filename, account=None):
    if account:
        return ROOT_DIR / "data" / "accounts" / account / filename

    return get_account_file(filename)


def load_json_file(path, default):
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[AI EXPORT] Failed to load {path}: {e}")
        return default


def load_memory_reports(account=None):
    if account:
        return load_json_file(
            get_ai_account_file("memory_decision_reports.json", account),
            [],
        )

    return load_memory_decision_reports()


def load_outcomes(account=None):
    if account:
        return load_json_file(
            get_ai_account_file("setup_outcomes.json", account),
            {},
        )

    return load_setup_outcomes()