import re

TELEGRAM_MAX_LENGTH = 4096


def markdown_to_html(text: str) -> str:
    """Convert standard Markdown to Telegram-compatible HTML.
    Known limitation: nested inline formatting (e.g. ***bold italic***) is not
    reliably supported — only single-level bold/italic is converted.
    """
    lines = text.split("\n")
    result = []
    in_code_block = False
    code_block_lines = []

    for line in lines:
        if line.strip().startswith("```"):
            if in_code_block:
                code_content = "\n".join(code_block_lines)
                result.append(f"<pre>{_escape_html(code_content)}</pre>")
                code_block_lines = []
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_block_lines.append(line)
            continue

        # Headers → bold
        header_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if header_match:
            result.append(f"\n<b>{_escape_html(header_match.group(2))}</b>")
            continue

        # Unordered list items: "* text" or "- text" → "• text" (skip inline conversion for the marker)
        list_match = re.match(r"^(\s*)[*\-]\s+(.+)$", line)
        if list_match:
            indent = list_match.group(1)
            content = _convert_inline(list_match.group(2))
            result.append(f"{_escape_html(indent)}• {content}")
            continue

        # Regular line: inline formatting
        line = _convert_inline(line)
        result.append(line)

    # Unclosed code block
    if in_code_block and code_block_lines:
        code_content = "\n".join(code_block_lines)
        result.append(f"<pre>{_escape_html(code_content)}</pre>")

    return "\n".join(result).strip()


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _convert_inline(line: str) -> str:
    """Convert inline MarML, preserving code spans and links."""
    # Split on code spans and links to protect them from other transformations
    parts = re.split(r"(`[^`]+`|\[(?:[^\]]+)\]\((?:[^)]+)\))", line)
    converted = []
    for part in parts:
        if not part:
            continue
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            converted.append(f"<code>{_escape_html(part[1:-1])}</code>")
        elif part.startswith("[") and "](" in part:
            # Markdown link [text](url)
            m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", part)
            if m:
                link_text = _escape_html(m.group(1))
                url = _escape_html(m.group(2))
                converted.append(f'<a href="{url}">{link_text}</a>')
            else:
                converted.append(_escape_html(part))
        else:
            text = _escape_html(part)
            # Bold: **text** or __text__
            text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
            text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
            # Italic: *text* or _text_ (not at line start to avoid list confusion)
            text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"<i>\1</i>", text)
            text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", text)
            converted.append(text)
    return "".join(converted)


def split_message(text: str, max_length: int = TELEGRAM_MAX_LENGTH) -> list[str]:
    """Split text into chunks that fit Telegram's message limit.
    Respects code block boundaries — never splits inside a ``` block.
    Uses a segment-based approach: first splits text into code/non-code segments,
    then only subdivides non-code segments when they exceed max_length.
    """
    if len(text) <= max_length:
        return [text]

    # Split by lines, group into chunks respecting code blocks
    lines = text.split("\n")
    chunks = []
    current_chunk = []
    current_len = 0
    in_code = False

    for line in lines:
        line_len = len(line) + 1  # +1 for the \n

        if line.strip().startswith("```"):
            in_code = not in_code

        # If adding this line would exceed limit and we're not in a code block
        if current_len + line_len > max_length and not in_code and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_len = 0

        current_chunk.append(line)
        current_len += line_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    # If any chunk still exceeds max_length (e.g. a huge code block), force-split it
    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= max_length:
            final_chunks.append(chunk)
        else:
            # Force split at line boundaries
            sub_lines = chunk.split("\n")
            sub_chunk = []
            sub_len = 0
            for line in sub_lines:
                if sub_len + len(line) + 1 > max_length and sub_chunk:
                    final_chunks.append("\n".join(sub_chunk))
                    sub_chunk = []
                    sub_len = 0
                sub_chunk.append(line)
                sub_len += len(line) + 1
            if sub_chunk:
                final_chunks.append("\n".join(sub_chunk))

    return final_chunks if final_chunks else [text]
