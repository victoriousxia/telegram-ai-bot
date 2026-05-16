"""Markdown formatting utilities using telegramify-markdown."""

import telegramify_markdown
from telegramify_markdown import split_entities
from telegramify_markdown.config import get_runtime_config
from telegram import MessageEntity as TgEntity

TELEGRAM_MAX_LENGTH = 4096

# Configure: remove emoji symbols from headings
_cfg = get_runtime_config()
_cfg.markdown_symbol.heading_level_1 = ""
_cfg.markdown_symbol.heading_level_2 = ""
_cfg.markdown_symbol.heading_level_3 = ""
_cfg.markdown_symbol.heading_level_4 = ""


def _utf16_to_str_index(s, utf16_off):
    """Convert UTF-16 code unit offset to Python string index."""
    count = 0
    for i, ch in enumerate(s):
        if count >= utf16_off:
            return i
        count += 2 if ord(ch) > 0xFFFF else 1
    return len(s)


def _ensure_heading_spacing(text, entities):
    """Insert blank line before headings that only have a single newline."""
    heading_offsets = set()
    underlines = {(e.offset, e.length) for e in entities if e.type == "underline"}
    for e in entities:
        if e.type == "bold" and (e.offset, e.length) in underlines:
            heading_offsets.add(e.offset)

    insertions = []
    for offset in sorted(heading_offsets, reverse=True):
        if offset == 0:
            continue
        idx = _utf16_to_str_index(text, offset)
        if idx >= 2 and text[idx - 2:idx] == "\n\n":
            continue
        if idx >= 1 and text[idx - 1] == "\n":
            insertions.append((idx, offset))

    for idx, utf16_off in insertions:
        text = text[:idx] + "\n" + text[idx:]
        for e in entities:
            if e.offset >= utf16_off:
                e.offset += 1

    return text, entities


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
    plain_text, entities = _ensure_heading_spacing(plain_text, entities)
    chunks = split_entities(plain_text, entities, max_utf16_len=TELEGRAM_MAX_LENGTH)

    result = []
    for chunk_text, chunk_entities in chunks:
        tg_entities = _convert_entities(chunk_entities)
        result.append((chunk_text, tg_entities))

    return result if result else [(plain_text, _convert_entities(entities))]
