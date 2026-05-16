"""Markdown formatting utilities using telegramify-markdown."""

import re

import telegramify_markdown
from telegramify_markdown import split_entities
from telegramify_markdown.config import get_runtime_config
from telegramify_markdown.converter import EventWalker
from telegram import MessageEntity as TgEntity

TELEGRAM_MAX_LENGTH = 4096

# Configure symbols
_cfg = get_runtime_config()
_cfg.markdown_symbol.heading_level_1 = ""
_cfg.markdown_symbol.heading_level_2 = ""
_cfg.markdown_symbol.heading_level_3 = ""
_cfg.markdown_symbol.heading_level_4 = ""
_cfg.markdown_symbol.task_completed = "✔"
_cfg.markdown_symbol.task_uncompleted = "☐"
_cfg.markdown_symbol.horizontal_rule = "⸻⸻⸻⸻⸻⸻⸻⸻⸻⸻"

# Make h3 headings also use underline+bold (default is bold only)
EventWalker._HEADING_ENTITIES = {
    "H1": ["bold", "underline"],
    "H2": ["bold", "underline"],
    "H3": ["bold", "underline"],
    "H4": ["bold"],
    "H5": ["bold"],
    "H6": ["bold"],
}


def _is_list_line(line):
    """Check if a line is any kind of list item."""
    s = line.strip()
    return (s.startswith("⦁") or s.startswith("✔") or
            s.startswith("☐") or bool(re.match(r"^\d+\.", s)))


def _adjust_spacing(text, entities):
    """Adjust spacing: add blank line after list blocks, remove extra blank before bullets."""
    lines = text.split("\n")
    if len(lines) <= 1:
        return text, entities

    # First pass: determine which blank lines to remove and where to insert
    removals = set()  # indices of blank lines to remove
    insertions = set()  # indices after which to insert blank line

    for i in range(len(lines)):
        # Remove blank line between paragraph and ⦁ sub-item list only
        if (i < len(lines) - 2
            and lines[i].strip() != ""
            and not _is_list_line(lines[i])
            and lines[i + 1].strip() == ""
            and lines[i + 2].strip().startswith("⦁")):
            removals.add(i + 1)

        # Add blank line after list items followed by non-list non-empty content
        if (i < len(lines) - 1
            and _is_list_line(lines[i])
            and lines[i + 1].strip() != ""
            and not _is_list_line(lines[i + 1])):
            insertions.add(i)

    # Build new lines and track UTF-16 offset changes
    utf16_offset = 0
    offset_adjustments = []  # (utf16_position, delta) where delta is +1 or -1

    line_end_offsets = []
    for i, line in enumerate(lines):
        line_utf16_len = len(line.encode("utf-16-le")) // 2
        utf16_offset += line_utf16_len
        if i < len(lines) - 1:
            utf16_offset += 1  # the \n
        line_end_offsets.append(utf16_offset)

    # Calculate adjustments
    for i in sorted(removals):
        if i > 0:
            offset_adjustments.append((line_end_offsets[i - 1], -1))

    for i in sorted(insertions):
        adj_pos = line_end_offsets[i]
        # Account for prior removals that shift this position
        offset_adjustments.append((adj_pos, +1))

    # Build new text
    new_lines = []
    for i, line in enumerate(lines):
        if i in removals:
            continue
        new_lines.append(line)
        if i in insertions:
            new_lines.append("")

    new_text = "\n".join(new_lines)

    # Apply offset adjustments to entities (sort by position)
    offset_adjustments.sort(key=lambda x: x[0])
    for adj_pos, delta in offset_adjustments:
        for e in entities:
            if e.offset >= adj_pos:
                e.offset += delta

    return new_text, entities


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


def split_message(text):
    """Convert markdown to (plain_text, entities) chunks for Telegram."""
    plain_text, entities = telegramify_markdown.convert(text)
    plain_text, entities = _adjust_spacing(plain_text, entities)
    chunks = split_entities(plain_text, entities, max_utf16_len=TELEGRAM_MAX_LENGTH)

    result = []
    for chunk_text, chunk_entities in chunks:
        tg_entities = _convert_entities(chunk_entities)
        result.append((chunk_text, tg_entities))

    return result if result else [(plain_text, _convert_entities(entities))]
