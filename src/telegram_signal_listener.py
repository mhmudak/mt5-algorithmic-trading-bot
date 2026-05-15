import asyncio
import hashlib

import MetaTrader5 as mt5
from telethon import TelegramClient, events

from config.settings import (
    ENABLE_TELEGRAM_SIGNAL_LISTENER,
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_USER_SESSION,
    TELEGRAM_SIGNAL_SOURCES,
)
from src.logger import logger
from src.notifier import send_telegram_message
from src.telegram_signal_parser import parse_telegram_signal
from src.telegram_signal_executor import handle_parsed_telegram_signal


SOURCE_BY_ENTITY_ID = {}


def _enabled_sources():
    return [
        source for source in TELEGRAM_SIGNAL_SOURCES
        if source.get("enabled", True)
    ]


def _message_hash(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:10]


async def resolve_signal_sources(client):
    """
    Resolve configured Telegram source channels/groups from the account dialogs.

    This works better for private channels than direct string resolution,
    because Telethon needs the entity access hash from the user's dialogs.
    """
    enabled_sources = _enabled_sources()
    resolved_entities = []

    async for dialog in client.iter_dialogs():
        entity = dialog.entity

        entity_id = getattr(entity, "id", None)
        title = getattr(entity, "title", None)
        username = getattr(entity, "username", None)

        for source in enabled_sources:
            configured_chat = str(source.get("chat"))

            matches = (
                configured_chat == str(entity_id)
                or (title and configured_chat == str(title))
                or (username and configured_chat == str(username))
                or (username and configured_chat == f"@{username}")
            )

            if matches:
                resolved_entities.append(entity)
                SOURCE_BY_ENTITY_ID[entity_id] = source

                logger.info(
                    f"[TELEGRAM LISTENER] Resolved source "
                    f"name={source.get('name')} title={title} id={entity_id}"
                )

    if not resolved_entities:
        raise RuntimeError("No configured Telegram signal sources were resolved")

    return resolved_entities


def get_source_from_chat(chat):
    chat_id = getattr(chat, "id", None)
    return SOURCE_BY_ENTITY_ID.get(chat_id, {})


async def handle_signal_message(event, event_type):
    message = event.message
    text = message.message or ""

    if not text.strip():
        logger.info("[TELEGRAM LISTENER] Empty/non-text message ignored")
        return

    chat = await event.get_chat()

    chat_title = getattr(chat, "title", None)
    chat_username = getattr(chat, "username", None)
    chat_id = getattr(chat, "id", "UNKNOWN")

    source = get_source_from_chat(chat)

    source_name = source.get("name", str(chat_title or chat_username or chat_id))
    parser_profile = source.get("parser_profile", "DEFAULT")

    chat_identifier = chat_username or chat_title or chat_id

    parsed = parse_telegram_signal(text)

    parsed["source_name"] = source_name
    parsed["parser_profile"] = parser_profile
    parsed["telegram_setup_id"] = f"TG-{source_name}-{message.id}"
    parsed["source_chat"] = str(chat_identifier)
    parsed["source_message_id"] = message.id
    parsed["source_event_type"] = event_type
    parsed["message_hash"] = _message_hash(text)

    logger.info(
        f"[TELEGRAM LISTENER] {event_type} | "
        f"source={source_name} message_id={message.id} parsed={parsed}"
    )

    send_telegram_message(
        f"📩 Telegram Source Message\n"
        f"Source: {source_name}\n"
        f"Type: {event_type}\n"
        f"Parsed Type: {parsed.get('type')}\n"
        f"Direction: {parsed.get('direction')}\n"
        f"Message ID: {message.id}"
    )

    handle_parsed_telegram_signal(parsed)


async def main():
    if not ENABLE_TELEGRAM_SIGNAL_LISTENER:
        logger.info("[TELEGRAM LISTENER] Disabled in settings")
        return

    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        raise RuntimeError("TELEGRAM_API_ID / TELEGRAM_API_HASH missing")

    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    client = TelegramClient(
        TELEGRAM_USER_SESSION,
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH,
    )

    await client.start()

    resolved_chats = await resolve_signal_sources(client)

    @client.on(events.NewMessage(chats=resolved_chats))
    async def on_new_message(event):
        await handle_signal_message(event, "NEW_MESSAGE")

    @client.on(events.MessageEdited(chats=resolved_chats))
    async def on_edited_message(event):
        await handle_signal_message(event, "EDITED_MESSAGE")

    logger.info("[TELEGRAM LISTENER] Starting for resolved sources")

    try:
        await client.run_until_disconnected()
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[TELEGRAM LISTENER] Stopped manually")