"""Markdown formatting utilities using telegramify-markdown."""

import re

import telegramify_markdown
from telegramify_markdown import split_entities
from telegramify_markdown.config import get_runtime_config
from telegramify_markdown.converter import EventWalker
from telegramify_markdown.entity import MessageEntity
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
_cfg.markdown_symbol.horizontal_rule = "⸻" * 9

# Make all headings bold only, no underline
EventWalker._HEADING_ENTITIES = {
    "H1": ["bold"],
    "H2": ["bold"],
    "H3": ["bold"],
    "H4": ["bold"],
    "H5": ["bold"],
    "H6": ["bold"],
}


def _is_list_line(line):
    """Check if a line is any kind of list item."""
    s = line.strip()
    return (s.startswith("⦁") or s.startswith("✔") or
            s.startswith("☐") or bool(re.match(r"^\d+\. ", s)))


def _adjust_spacing(text, entities):
    """Adjust spacing based on block-level semantics.

    Rules:
    - Remove blank line between paragraph and sub-item list
    - Add blank line after last list item before non-list non-empty content
    - Add blank line after last sub-item before next numbered item
    """
    lines = text.split("\n")
    if len(lines) <= 1:
        return text, entities

    removals = set()
    insertions = set()

    for i in range(len(lines)):
        # Remove blank line between paragraph and sub-item list
        if (i > 0 and i < len(lines) - 1
            and lines[i].strip() == ""
            and not _is_list_line(lines[i - 1])
            and lines[i - 1].strip() != ""
            and lines[i + 1].strip().startswith("⦁")):
            removals.add(i)

        # Add blank line after last list item before non-list non-empty content
        if (i < len(lines) - 1
            and _is_list_line(lines[i])
            and not _is_list_line(lines[i + 1])
            and lines[i + 1].strip() != ""):
            insertions.add(i)

        # Add blank line after last sub-item before next numbered item
        if (i < len(lines) - 1
            and lines[i].strip().startswith("⦁")
            and not lines[i + 1].strip().startswith("⦁")
            and bool(re.match(r"^\d+\. ", lines[i + 1].strip()))):
            insertions.add(i)

    if not removals and not insertions:
        return text, entities

    # Calculate UTF-16 line end offsets
    utf16_offset = 0
    line_end_offsets = []
    for i, line in enumerate(lines):
        line_utf16_len = len(line.encode("utf-16-le")) // 2
        utf16_offset += line_utf16_len
        if i < len(lines) - 1:
            utf16_offset += 1  # newline character
        line_end_offsets.append(utf16_offset)

    # Collect offset adjustments
    offset_adjustments = []
    for i in sorted(removals):
        if i > 0:
            offset_adjustments.append((line_end_offsets[i - 1], -1))
    for i in sorted(insertions):
        offset_adjustments.append((line_end_offsets[i], +1))

    # Build new text
    new_lines = []
    for i, line in enumerate(lines):
        if i in removals:
            continue
        new_lines.append(line)
        if i in insertions:
            new_lines.append("")

    new_text = "\n".join(new_lines)

    # Apply offset adjustments to entities
    offset_adjustments.sort(key=lambda x: x[0])
    for adj_pos, delta in offset_adjustments:
        for e in entities:
            if e.offset >= adj_pos:
                e.offset += delta

    return new_text, entities


def _safe_split(text, entities, max_len=TELEGRAM_MAX_LENGTH):
    """Split text+entities into chunks without cutting through pre (code block) entities."""
    utf16_len = len(text.encode("utf-16-le")) // 2
    if utf16_len <= max_len:
        return [(text, entities)]

    # Build protected ranges from "pre" entities (code blocks)
    protected = []
    for e in entities:
        if e.type == "pre":
            protected.append((e.offset, e.offset + e.length))

    # Find safe split points: positions of \n\n that are NOT inside protected ranges
    split_candidates = []
    utf16_pos = 0
    for i, ch in enumerate(text):
        if ch == "\n" and i + 1 < len(text) and text[i + 1] == "\n":
            pos = utf16_pos + 1  # after the first \n
            inside_protected = any(start <= pos < end for start, end in protected)
            if not inside_protected:
                split_candidates.append((pos + 1, i + 2))  # utf16 pos, str index (after \n\n)
        utf16_pos += 2 if ord(ch) > 0xFFFF else 1

    # Greedy algorithm: for each chunk, find the last split point that fits within max_len
    chunks = []
    chunk_start_utf16 = 0
    chunk_start_str = 0
    last_good_utf16 = 0
    last_good_str = 0

    for utf16_pos, str_idx in split_candidates:
        if utf16_pos - chunk_start_utf16 <= max_len:
            last_good_utf16 = utf16_pos
            last_good_str = str_idx
        else:
            # Emit chunk up to last_good
            if last_good_str > chunk_start_str:
                chunks.append(text[chunk_start_str:last_good_str].rstrip("\n"))
                chunk_start_utf16 = last_good_utf16
                chunk_start_str = last_good_str
                last_good_utf16 = utf16_pos
                last_good_str = str_idx
            else:
                # No safe split found, fall back to split_entities from the library
                return split_entities(text, entities, max_utf16_len=max_len)

    # Remaining text
    remaining = text[chunk_start_str:]
    if remaining.strip():
        rem_utf16 = len(remaining.encode("utf-16-le")) // 2
        if rem_utf16 > max_len:
            # Still too long, use library split for this remainder
            last_chunks = split_entities(remaining, [], max_utf16_len=max_len)
            chunks.extend([ct for ct, _ in last_chunks])
        else:
            chunks.append(remaining.rstrip("\n"))

    if not chunks:
        return split_entities(text, entities, max_utf16_len=max_len)

    # Assign entities to chunks by checking if entity offset falls within chunk range
    result = []
    chunk_start_utf16 = 0
    for chunk_text in chunks:
        chunk_utf16_len = len(chunk_text.encode("utf-16-le")) // 2
        chunk_end_utf16 = chunk_start_utf16 + chunk_utf16_len
        chunk_ents = []
        for e in entities:
            # Entity belongs to this chunk if it starts within it
            if chunk_start_utf16 <= e.offset < chunk_end_utf16:
                new_e = MessageEntity(
                    type=e.type,
                    offset=e.offset - chunk_start_utf16,
                    length=min(e.length, chunk_utf16_len - (e.offset - chunk_start_utf16)),
                    url=e.url,
                    language=e.language,
                )
                chunk_ents.append(new_e)
        result.append((chunk_text, chunk_ents))
        # Advance chunk_start_utf16 by chunk_utf16_len + 2 (for the \n\n separator)
        chunk_start_utf16 = chunk_end_utf16 + 2

    return result


def _convert_entities(lib_entities):
    """Convert telegramify-markdown MessageEntity to telegram.MessageEntity objects."""
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
    chunks = _safe_split(plain_text, entities)

    result = []
    for chunk_text, chunk_entities in chunks:
        tg_entities = _convert_entities(chunk_entities)
        result.append((chunk_text, tg_entities))

    return result if result else [(plain_text, _convert_entities(entities))]
