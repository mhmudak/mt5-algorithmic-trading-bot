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


def _enabled_sources():
    return [
        source for source in TELEGRAM_SIGNAL_SOURCES
        if source.get("enabled", True)
    ]


def _source_chats():
    return [
        source["chat"] for source in _enabled_sources()
        if source.get("chat")
    ]


def _source_name(chat_identifier, chat_title=None, chat_id=None):
    for source in _enabled_sources():
        configured_chat = str(source.get("chat"))

        if configured_chat == str(chat_identifier):
            return source.get("name", configured_chat)

        if chat_title and configured_chat == str(chat_title):
            return source.get("name", configured_chat)

        if chat_id and configured_chat == str(chat_id):
            return source.get("name", configured_chat)

    return str(chat_title or chat_identifier)

def _source_config(chat_identifier, chat_title=None, chat_id=None):
    for source in _enabled_sources():
        configured_chat = str(source.get("chat"))

        if configured_chat == str(chat_identifier):
            return source

        if chat_title and configured_chat == str(chat_title):
            return source

        if chat_id and configured_chat == str(chat_id):
            return source

    return {}


def _message_hash(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:10]


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

    chat_identifier = chat_username or chat_title or chat_id
    source_name = _source_name(
        chat_identifier=chat_identifier,
        chat_title=chat_title,
        chat_id=chat_id,
    )
    
    source_config = _source_config(
        chat_identifier=chat_identifier,
        chat_title=chat_title,
        chat_id=chat_id,
    )

    parser_profile = source_config.get("parser_profile", "DEFAULT")

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

    chats = _source_chats()

    if not chats:
        raise RuntimeError("No Telegram signal sources configured")

    @client.on(events.NewMessage(chats=chats))
    async def on_new_message(event):
        await handle_signal_message(event, "NEW_MESSAGE")

    @client.on(events.MessageEdited(chats=chats))
    async def on_edited_message(event):
        await handle_signal_message(event, "EDITED_MESSAGE")

    logger.info(f"[TELEGRAM LISTENER] Starting for chats={chats}")

    await client.start()
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())