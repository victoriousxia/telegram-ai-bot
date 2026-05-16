"""Shared Telegram message helpers — formatting, splitting, streaming."""
import time

from telegram.constants import ParseMode
from telegram.error import BadRequest

from bot.config import config
from bot.utils.formatting import markdown_to_telegramv2, split_message, TELEGRAM_MAX_LENGTH

_STREAM_OVERHEAD = len("… ") + len(" ▍")


async def send_formatted(bot_message, text, chat=None):
    """Send final response with MarkdownV2 formatting, split if too long.
    Uses telegramify-markdown to convert standard Markdown to Telegram MarkdownV2.
    """
    chunks = split_message(text)
    thread_id = getattr(bot_message, "message_thread_id", None)

    for i, chunk in enumerate(chunks):
        if i == 0:
            try:
                await bot_message.edit_text(chunk, parse_mode=ParseMode.MARKDOWN_V2)
            except BadRequest:
                try:
                    await bot_message.edit_text(text[:TELEGRAM_MAX_LENGTH])
                except BadRequest:
                    pass
        else:
            if chat:
                kwargs = {}
                if thread_id:
                    kwargs["message_thread_id"] = thread_id
                try:
                    await chat.send_message(chunk, parse_mode=ParseMode.MARKDOWN_V2, **kwargs)
                except BadRequest:
                    await chat.send_message(chunk, **kwargs)
            else:
                break

    if not chat and len(chunks) > 1:
        try:
            notice = "\n\n\\[… message truncated\\]"
            combined = chunks[0] + notice
            if len(combined) > TELEGRAM_MAX_LENGTH:
                combined = chunks[0][:TELEGRAM_MAX_LENGTH - len(notice)] + notice
            await bot_message.edit_text(combined, parse_mode=ParseMode.MARKDOWN_V2)
        except BadRequest:
            pass


async def stream_and_send(stream, bot_message, chat, context, session_id):
    """Shared streaming loop: stream chunks, update preview, send final formatted."""
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
