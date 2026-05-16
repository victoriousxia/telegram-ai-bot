"""Markdown formatting utilities using telegramify-markdown."""

import telegramify_markdown
from telegramify_markdown import split_entities
from telegram import MessageEntity as TgEntity

TELEGRAM_MAX_LENGTH = 4096


def _convert_entities(lib_entities):
    """Convert telegramify-markdown entities to telegram.MessageEntity objects."""
    result = []
    for e in lib_entities:
        kwargs = {
            "type": e.type,
            "offset": e.offset,
            "length": e.length,
        }
        if e.url:
            kwargs["url"] = e.url
        if e.language:
            kwargs["language"] = e.language
        result.append(TgEntity(**kwargs))
    return result


def split_message(text: str) -> list[tuple[str, list]]:
    """Convert markdown to (plain_text, entities) chunks for Telegram.

    Returns a list of (text, telegram_entities) tuples ready to send.
    """
    plain_text, entities = telegramify_markdown.convert(text)
    chunks = split_entities(plain_text, entities, max_utf16_len=TELEGRAM_MAX_LENGTH)

    result = []
    for chunk_text, chunk_entities in chunks:
        tg_entities = _convert_entities(chunk_entities)
        result.append((chunk_text, tg_entities))

    return result if result else [(plain_text, _convert_entities(entities))]
