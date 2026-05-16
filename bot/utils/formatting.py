"""Markdown formatting utilities using telegramify-markdown."""

import telegramify_markdown
from telegramify_markdown import split_markdownv2

TELEGRAM_MAX_LENGTH = 4096


def markdown_to_telegramv2(text: str) -> str:
    """Convert standard Markdown to Telegram MarkdownV2 format."""
    return telegramify_markdown.markdownify(text)


def split_message(text: str) -> list[str]:
    """Split markdown text into MarkdownV2 chunks that fit Telegram's limit.

    Converts to MarkdownV2 first, then splits respecting formatting boundaries.
    Returns a list of MarkdownV2-formatted strings ready to send.
    """
    converted = telegramify_markdown.markdownify(text)
    chunks = split_markdownv2(converted, max_utf16_len=TELEGRAM_MAX_LENGTH)
    return chunks if chunks else [converted]
