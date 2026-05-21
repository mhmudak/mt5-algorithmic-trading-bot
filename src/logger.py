from pathlib import Path
from loguru import logger


LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "bot.log"

logger.remove()

# Windows-safe file logging.
# No rotation here, because rotation renames bot.log and Windows may block it
# if the file is open in VS Code or watched by Get-Content -Wait.
logger.add(
    LOG_FILE,
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    encoding="utf-8",
    enqueue=True,
    catch=True,
)

logger.add(
    lambda msg: print(msg, end=""),
    level="INFO",
    format="{time:HH:mm:ss} | {level} | {message}",
    enqueue=True,
    catch=True,
)