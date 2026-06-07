import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ai_export_common import add_account_argument
from export_ai_memory_dataset import export_ai_memory_dataset
from evaluate_ai_shadow_advisor import evaluate_ai_shadow_advisor
from export_ai_shadow_advisor_report import export_ai_shadow_advisor_report
from src.logger import logger


def run_ai_shadow_pipeline(account=None):
    logger.info(
        f"[AI SHADOW PIPELINE] Starting | account={account or 'active_context'}"
    )

    print("Step 1/3: Exporting AI memory dataset...")
    export_ai_memory_dataset(account=account)

    print("Step 2/3: Evaluating AI shadow advisor...")
    evaluate_ai_shadow_advisor(account=account)

    print("Step 3/3: Exporting AI shadow advisor report...")
    export_ai_shadow_advisor_report(account=account)

    logger.info(
        f"[AI SHADOW PIPELINE] Completed | account={account or 'active_context'}"
    )

    print("AI shadow advisor pipeline completed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    add_account_argument(parser)
    args = parser.parse_args()

    run_ai_shadow_pipeline(account=args.account)