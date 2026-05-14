import time

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction, ParseMode

from bot.config import config
from bot.handlers.commands import check_access
from bot.services.session import (
    get_or_create_user,
    add_message,
    get_session_messages,
    get_session_by_thread,
    set_session_title,
    get_session,
)
from bot.services.ai_client import stream_chat
from bot.utils.formatting import markdown_to_html, split_message, TELEGRAM_MAX_LENGTH


async def _send_formatted(bot_message, text, chat=None):
    """Send final response with HTML formatting, split if too long."""
    html = markdown_to_html(text)
    chunks = split_message(html)

    # First chunk: edit the existing "thinking..." message
    try:
        await bot_message.edit_text(chunks[0], parse_mode=ParseMode.HTML)
    except Exception:
        # HTML parse failed, try plain text
        plain_chunks = split_message(text)
        try:
            await bot_message.edit_text(plain_chunks[0])
        except Exception:
            await bot_message.edit_text(plain_chunks[0][:TELEGRAM_MAX_LENGTH])
        if chat:
            for chunk in plain_chunks[1:]:
                await chat.send_message(chunk)
        return

    # Remaining chunks: send as new messages
    if chat and len(chunks) > 1:
        for chunk in chunks[1:]:
            try:
                await chat.send_message(chunk, parse_mode=ParseMode.HTML)
            except Exception:
                await chat.send_message(chunk)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return

    user_message = update.message.text
    if not user_message:
        return

    user = await get_or_create_user(update.effective_user.id)
    session_id = user["current_session_id"]
    model = user["current_model"]

    # Topic routing: in native topic mode (1), route by thread_id
    if user.get("topic_mode") == 1 and update.message.message_thread_id:
        thread_session = await get_session_by_thread(
            update.effective_user.id, update.message.message_thread_id
        )
        if thread_session:
            session_id = thread_session["id"]

    await update.message.chat.send_action(ChatAction.TYPING)
    await add_message(session_id, "user", user_message)

    # Auto-title: set title from first user message
    session = await get_session(session_id)
    if session and session["title"] == "New Chat":
        title = user_message[:20].strip()
        await set_session_title(session_id, title)
        if user.get("topic_mode") == 1 and update.message.message_thread_id:
            try:
                await update.effective_chat.edit_forum_topic(
                    message_thread_id=update.message.message_thread_id,
                    name=title,
                )
            except Exception:
                pass

    messages = await get_session_messages(session_id)
    bot_message = await update.message.reply_text("thinking...")

    full_response = ""
    last_update = time.time()
    update_interval = config.STREAM_UPDATE_INTERVAL
    context.user_data["stop_flag"] = False

    try:
        async for chunk in stream_chat(messages, model):
            if context.user_data.get("stop_flag"):
                context.user_data["stop_flag"] = False
                break
            full_response += chunk
            now = time.time()
            if now - last_update >= update_interval:
                # Streaming preview: plain text, truncate if too long
                preview = full_response[-TELEGRAM_MAX_LENGTH + 10:] if len(full_response) > TELEGRAM_MAX_LENGTH else full_response
                try:
                    await bot_message.edit_text(preview + " ▍")
                except Exception:
                    pass
                last_update = now

        if full_response:
            await _send_formatted(bot_message, full_response, update.message.chat)
            await add_message(session_id, "assistant", full_response)
        else:
            await bot_message.edit_text("No response from the model.")

    except Exception as e:
        error_msg = f"Error: {type(e).__name__}: {str(e)[:200]}"
        await bot_message.edit_text(error_msg)
