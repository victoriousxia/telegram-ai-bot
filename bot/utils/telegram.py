"""Shared Telegram message helpers — formatting, splitting, streaming."""
import time

from telegram.constants import ParseMode

from bot.config import config
from bot.utils.formatting import markdown_to_html, split_message, TELEGRAM_MAX_LENGTH

# Overhead for streaming cursor: "… " prefix (2 chars) + " ▍" suffix (2 chars)
_STREAM_OVERHEAD = len("… ") + len(" ▍")


async def send_formatted(bot_message, text, chat=None):
    """Send final response with HTML formatting, split if too long.
    Splits raw Markdown first, then converts each chunk to HTML separately
    to avoid cutting HTML tags in half.
    If chat is None and message is multi-chunk, appends truncation notice.
    """
    chunks = split_message(text)

    for i, chunk in enumerate(chunks):
        html = markdown_to_html(chunk)
        if i == 0:
            try:
                await bot_message.edit_text(html, parse_mode=ParseMode.HTML)
            except Exception:
                try:
                    await bot_message.edit_text(chunk)
                except Exception:
                    await bot_message.edit_text(chunk[:TELEGRAM_MAX_LENGTH])
        else:
            if chat:
                try:
                    await chat.send_message(html, parse_mode=ParseMode.HTML)
                except Exception:
                    await chat.send_message(chunk)
            else:
                break

    # No chat object but multiple chunks — notify user of truncation
    if not chat and len(chunks) > 1:
        try:
            notice = "\n\n[… message truncated]"
            await bot_message.edit_text(
                markdown_to_html(chunks[0]) + notice,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass


async def stream_and_send(stream, bot_message, chat, context, session_id):
    """Shared streaming loop: stream chunks, update preview, send final formatted.
    Returns the full response text, or empty string if nothing was generated.
    """
    from bot.services.session import add_message

    full_response = ""
    last_update = time.time()
    update_interval = config.STREAM_UPDATE_INTERVAL
    context.user_data["stop_flag"] = False

    try:
        async for chunk in stream:
            if context.user_data.get("stop_flag"):
                context.user_data["stop_flag"] = False
                break
            full_response += chunk
            now = time.time()
            if now - last_update >= update_interval:
                if len(full_response) > TELEGRAM_MAX_LENGTH - _STREAM_OVERHEAD:
                    preview = "… " + full_response[-(TELEGRAM_MAX_LENGTH - _STREAM_OVERHEAD):]
                else:
                    preview = full_response
                try:
                    await bot_message.edit_text(preview + " ▍")
                except Exception:
                    pass
                last_update = now

        if full_response:
            await send_formatted(bot_message, full_response, chat)
            await add_message(session_id, "assistant", full_response)
        else:
            await bot_message.edit_text("No response from the model.")

    except Exception as e:
        error_msg = f"Error: {type(e).__name__}: {str(e)[:200]}"
        await bot_message.edit_text(error_msg)

    return full_response
