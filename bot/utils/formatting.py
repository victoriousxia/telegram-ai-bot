import re
import unicodedata

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
    table_lines = []

    for line in lines:
        # Flush accumulated table when we hit a non-table line
        if table_lines and not re.match(r"^\s*\|", line):
            rendered = _render_table(table_lines)
            if rendered:
                result.append(rendered)
            table_lines = []

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

        # Table rows: lines starting with |
        if re.match(r"^\s*\|", line):
            table_lines.append(line)
            continue

        # Headers → bold (only add extra newline if previous line isn't blank)
        header_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if header_match:
            prefix = "\n" if result and result[-1] != "" else ""
            result.append(f"{prefix}<b>{_convert_inline(header_match.group(2))}</b>")
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

    # Flush remaining table
    if table_lines:
        rendered = _render_table(table_lines)
        if rendered:
            result.append(rendered)

    # Unclosed code block
    if in_code_block and code_block_lines:
        code_content = "\n".join(code_block_lines)
        result.append(f"<pre>{_escape_html(code_content)}</pre>")

    return "\n".join(result).strip()


def _strip_inline_markdown(text: str) -> str:
    """Strip inline markdown markers that can't render inside <pre>."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text


def _render_table(table_lines: list[str]) -> str:
    """Convert markdown table lines to a <pre> block for monospace alignment."""
    rows = []
    for line in table_lines:
        stripped = line.strip().strip("|")
        cells = [_strip_inline_markdown(c.strip()) for c in stripped.split("|")]
        if all(re.match(r"^[-:]+$", c) for c in cells if c):
            continue
        rows.append(cells)

    if not rows:
        return ""

    col_count = max(len(r) for r in rows)
    col_widths = [0] * col_count
    for row in rows:
        for i, cell in enumerate(row):
            if i < col_count:
                col_widths[i] = max(col_widths[i], _display_width(cell))

    formatted = []
    for idx, row in enumerate(rows):
        padded = []
        for i in range(col_count):
            cell = row[i] if i < len(row) else ""
            pad = col_widths[i] - _display_width(cell)
            padded.append(cell + " " * pad)
        formatted.append("  ".join(padded))
        if idx == 0 and len(rows) > 1:
            formatted.append("  ".join("-" * w for w in col_widths))

    return f"<pre>{_escape_html(chr(10).join(formatted))}</pre>"


def _display_width(text: str) -> int:
    """Calculate display width accounting for wide (CJK) characters."""
    width = 0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


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
    Uses a conservative threshold (3600) to account for HTML tag expansion
    when the chunks are later converted via markdown_to_html.
    """
    # Conservative limit: HTML tags like <b>, <code>, <a href="..."> expand length
    effective_limit = min(max_length, 3600)

    if len(text) <= effective_limit:
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
        if current_len + line_len > effective_limit and not in_code and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_len = 0

        current_chunk.append(line)
        current_len += line_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    # If any chunk still exceeds effective_limit (e.g. a huge code block), force-split it
    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= effective_limit:
            final_chunks.append(chunk)
        else:
            # Force split at line boundaries
            sub_lines = chunk.split("\n")
            sub_chunk = []
            sub_len = 0
            for line in sub_lines:
                if sub_len + len(line) + 1 > effective_limit and sub_chunk:
                    final_chunks.append("\n".join(sub_chunk))
                    sub_chunk = []
                    sub_len = 0
                sub_chunk.append(line)
                sub_len += len(line) + 1
            if sub_chunk:
                final_chunks.append("\n".join(sub_chunk))

    return final_chunks if final_chunks else [text]
