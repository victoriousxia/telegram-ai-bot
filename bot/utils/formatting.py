import re

TELEGRAM_MAX_LENGTH = 4096


def markdown_to_html(text: str) -> str:
    """Convert standard Markdown to Telegram-compatible HTML."""
    lines = text.split("\n")
    result = []
    in_code_block = False
    code_block_lines = []

    for line in lines:
        # Code block toggle
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

        # Inline formatting
        line = _convert_inline(line)
        result.append(line)

    # Unclosed code block
    if in_code_block and code_block_lines:
        code_content = "\n".join(code_block_lines)
        result.append(f"<pre>{_escape_html(code_content)}</pre>")

    return "\n".join(result).strip()


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _convert_inline(line: str) -> str:
    """Convert inline Markdown to HTML, preserving code spans."""
    parts = re.split(r"(`[^`]+`)", line)
    converted = []
    for part in parts:
        if part.startswith("`") and part.endswith("`"):
            converted.append(f"<code>{_escape_html(part[1:-1])}</code>")
        else:
            text = _escape_html(part)
            # Bold: **text** or __text__
            text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
            text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
            # Italic: *text* or _text_ (but not inside words)
            text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"<i>\1</i>", text)
            text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", text)
            converted.append(text)
    return "".join(converted)


def split_message(text: str, max_length: int = TELEGRAM_MAX_LENGTH) -> list[str]:
    """Split text into chunks that fit Telegram's message limit."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        # Find a good split point: prefer paragraph break, then line break
        split_at = text.rfind("\n\n", 0, max_length)
        if split_at == -1 or split_at < max_length // 2:
            split_at = text.rfind("\n", 0, max_length)
        if split_at == -1 or split_at < max_length // 2:
            split_at = max_length

        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    return chunks
