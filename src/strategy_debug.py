from config.settings import ENABLE_STRATEGY_REJECTION_DEBUG
from src.logger import logger


def reject_strategy(strategy_name, reason, **context):
    if ENABLE_STRATEGY_REJECTION_DEBUG:
        details = " ".join(
            f"{key}={value}"
            for key, value in context.items()
            if value is not None
        )

        logger.info(
            f"[STRATEGY REJECTED] {strategy_name} | "
            f"reason={reason} {details}"
        )

    return None