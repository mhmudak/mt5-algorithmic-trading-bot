import json
import logging
from pathlib import Path

from src.account_context import get_account_file

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
INTELLIGENCE_ROOT = ROOT / "data" / "strategy_intelligence"
POLICY_FILENAME = "strategy_advisory_policy.json"

_POLICY_CACHE = {
    "path": None,
    "mtime": None,
    "policy": {},
}


def safe_upper(value, default="UNKNOWN"):
    if value is None:
        return default

    value = str(value).strip()

    if not value:
        return default

    return value.upper()


def get_current_account_name(default=None):
    try:
        account_dir = get_account_file("trades.json").parent
        account_name = account_dir.name

        if account_name and account_name != "NEW_ACCOUNT_FOLDER":
            return account_name
    except Exception as exc:
        logger.warning(f"[STRATEGY ADVISORY] Could not detect current account: {exc}")

    return default


def find_latest_policy_file(account_name=None):
    account_name = account_name or get_current_account_name()

    if not account_name:
        logger.warning("[STRATEGY ADVISORY] No account name detected; policy load skipped.")
        return None

    path = INTELLIGENCE_ROOT / account_name / POLICY_FILENAME

    if path.exists():
        return path

    logger.warning(f"[STRATEGY ADVISORY] No policy found for account={account_name} path={path}")
    return None


def load_strategy_advisory_policy(account_name=None):
    policy_path = find_latest_policy_file(account_name)

    if not policy_path:
        logger.warning("[STRATEGY ADVISORY] No advisory policy file found.")
        return {}

    mtime = policy_path.stat().st_mtime

    if (
        _POLICY_CACHE["path"] == policy_path
        and _POLICY_CACHE["mtime"] == mtime
        and _POLICY_CACHE["policy"]
    ):
        return _POLICY_CACHE["policy"]

    try:
        with open(policy_path, "r", encoding="utf-8") as file:
            policy = json.load(file)
    except Exception as exc:
        logger.warning(f"[STRATEGY ADVISORY] Failed to load policy: {exc}")
        return {}

    _POLICY_CACHE["path"] = policy_path
    _POLICY_CACHE["mtime"] = mtime
    _POLICY_CACHE["policy"] = policy

    logger.info(f"[STRATEGY ADVISORY] Loaded policy from {policy_path}")

    return policy


def get_strategy_advisory(strategy, setup_source_bucket="NORMAL_OR_TRACKED", account_name=None):
    policy = load_strategy_advisory_policy(account_name=account_name)

    if not policy:
        return None

    strategy = safe_upper(strategy)
    setup_source_bucket = safe_upper(setup_source_bucket, default="NORMAL_OR_TRACKED")

    candidate_keys = [
        f"{strategy}|{setup_source_bucket}",
        f"{strategy}|NORMAL_OR_TRACKED",
    ]

    for key in candidate_keys:
        advisory = policy.get(key)

        if advisory:
            result = dict(advisory)
            result["policy_key"] = key
            result["strategy"] = strategy
            result["setup_source_bucket"] = setup_source_bucket
            return result

    return None


def format_strategy_advisory(advisory):
    if not advisory:
        return "[STRATEGY ADVISORY] No advisory found."

    return (
        "[STRATEGY ADVISORY] "
        f"key={advisory.get('policy_key')} | "
        f"decision={advisory.get('decision')} | "
        f"samples={advisory.get('sample_count')} | "
        f"w10={advisory.get('w10_rate')} | "
        f"tp={advisory.get('tp_rate')} | "
        f"sl={advisory.get('sl_rate')} | "
        f"expectancy={advisory.get('synthetic_expectancy')} | "
        f"reason={advisory.get('decision_reason')}"
    )


def is_advisory_risky(advisory):
    if not advisory:
        return False

    return advisory.get("decision") in [
        "BLOCK_TEMPORARILY",
        "DISABLE_STRATEGY",
        "TRACK_ONLY",
    ]