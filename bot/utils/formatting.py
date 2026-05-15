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
    """Split text into chunks that fit Telegram's message limit.
    Respects code block boundaries — never splits inside a ``` block.
    """
    if len(text) <= max_length:
        return [text]

    # Identify code block regions to avoid splitting inside them
    code_block_ranges = []
    for m in re.finditer(r"^```.*$", text, re.MULTILINE):
        code_block_ranges.append(m.start())

    # Pair up opening/closing ``` markers
    code_regions = []
    i = 0
    while i + 1 < len(code_block_ranges):
        code_regions.append((code_block_ranges[i], code_block_ranges[i + 1]))
        i += 2

    def _in_code_block(pos: int) -> bool:
        for start, end in code_regions:
            if start < pos < end:
                return True
        return False

    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        # Try paragraph break, then line break, avoiding code block inters
        split_at = -1
        for sep in ("\n\n", "\n"):
            candidate = text.rfind(sep, 0, max_length)
            while candidate > max_length // 4:
                # Calculate absolute position to check code block membership
                abs_pos = sum(len(c) for c in chunks) + candidate
                if not _in_code_block(abs_pos):
                    split_at = candidate
                    break
                candidate = text.rfind(sep, 0, candidate)
            if split_at > 0:
                break

        if split_at <= 0:
            split_at = max_length

        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    return chunks
