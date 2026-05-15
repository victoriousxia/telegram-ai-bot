import logging

from telegram import Update, Chat
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

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
from bot.services.ai_client import stream_chat, chat_once
from bot.utils.telegram import stream_and_send

logger = logging.getLogger(__name__)

TITLE_MAX_LEN = 10
TITLE_PLACEHOLDER = "..."
TITLE_PROMPT = (
    f"用{TITLE_MAX_LEN}字以内概括这段对话的主题，越短越好。"
    "不要加引号或标点，只输出标题：\n\n"
)


async def _generate_title(session_id: int, user_message: str, model: str,
                          chat: Chat, thread_id: int | None, topic_mode: int | None):
    """Background task: generate AI title and update session/topic."""
    title_model = config.TITLE_MODEL or model
    try:
        prompt_messages = [
            {"role": "user", "content": TITLE_PROMPT + user_message}
        ]
        title = await chat_once(prompt_messages, title_model)
        title = title.strip().strip('"\'""「」').strip()
        if not title:
            title = user_message[:TITLE_MAX_LEN].strip() or "Chat"
        else:
            title = title[:TITLE_MAX_LEN]

        await set_session_title(session_id, title)

        if topic_mode == 1 and thread_id:
            try:
                await chat.edit_forum_topic(
                    message_thread_id=thread_id, name=title
                )
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Auto-title generation failed: {e}")
        title = user_message[:TITLE_MAX_LEN].strip() or "Chat"
        await set_session_title(session_id, title)


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

    messages = await get_session_messages(session_id)
    bot_message = await update.message.reply_text("thinking...")

    await stream_and_send(
        stream_chat(messages, model),
        bot_message,
        update.message.chat,
        context,
        session_id,
    )

    # Auto-title: generate AI title after first response
    session = await get_session(session_id)
    if session and session["title"] == "New Chat":
        # Placeholder prevents duplicate triggers from rapid messages
        await set_session_title(session_id, TITLE_PLACEHOLDER)
        context.application.create_task(
            _generate_title(
                session_id, user_message, model,
                update.effective_chat,
                update.message.message_thread_id,
                user.get("topic_mode"),
            ),
            update=update,
        )
