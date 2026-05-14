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
)
from bot.services.ai_client import stream_chat


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return

    user_message = update.message.text
    if not user_message:
        return

    user = await get_or_create_user(update.effective_user.id)
    session_id = user["current_session_id"]
    model = user["current_model"]

    await update.message.chat.send_action(ChatAction.TYPING)

    await add_message(session_id, "user", user_message)

    messages = await get_session_messages(session_id)

    bot_message = await update.message.reply_text("thinking...")

    full_response = ""
    last_update = time.time()
    update_interval = config.STREAM_UPDATE_INTERVAL

    try:
        async for chunk in stream_chat(messages, model):
            full_response += chunk
            now = time.time()
            if now - last_update >= update_interval:
                try:
                    await bot_message.edit_text(full_response + " ▍")
                except Exception:
                    pass
                last_update = now

        if full_response:
            try:
                await bot_message.edit_text(full_response, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                await bot_message.edit_text(full_response)
            await add_message(session_id, "assistant", full_response)
        else:
            await bot_message.edit_text("No response from the model.")

    except Exception as e:
        error_msg = f"Error: {type(e).__name__}: {str(e)[:200]}"
        await bot_message.edit_text(error_msg)
