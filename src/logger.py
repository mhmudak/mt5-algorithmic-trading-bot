from pathlib import Path
from loguru import logger


LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logger.remove()

logger.add(
    LOG_DIR / "bot.log",
    rotation="1 MB",
    retention=5,
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
)

logger.add(
    lambda msg: print(msg, end=""),
    level="INFO",
    format="{time:HH:mm:ss} | {level} | {message}",
)