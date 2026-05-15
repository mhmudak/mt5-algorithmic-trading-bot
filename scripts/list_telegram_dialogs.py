import sys
from pathlib import Path
import asyncio

sys.path.append(str(Path(__file__).resolve().parents[1]))

from telethon import TelegramClient
from telethon.tl.types import Channel, Chat

from config.settings import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_USER_SESSION,
)


async def main():
    client = TelegramClient(
        TELEGRAM_USER_SESSION,
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH,
    )

    await client.start()

    print("\nChannels / Groups:\n")

    async for dialog in client.iter_dialogs():
        entity = dialog.entity

        if not isinstance(entity, (Channel, Chat)):
            continue

        title = getattr(entity, "title", "NO_TITLE")
        username = getattr(entity, "username", None)
        entity_id = getattr(entity, "id", None)

        print(
            f"title={title} | "
            f"id={entity_id} | "
            f"username={username} | "
            f"type={type(entity).__name__}"
        )

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())