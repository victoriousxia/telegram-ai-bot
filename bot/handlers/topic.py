import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from bot.handlers.commands import check_access
from bot.services.session import (
    get_or_create_user,
    get_user_sessions,
    switch_session,
    create_session,
    set_user_topic_mode,
    set_session_topic_thread,
)

logger = logging.getLogger(__name__)


async def topic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return

    user = await get_or_create_user(update.effective_user.id)

    if user.get("topic_mode"):
        await _show_topic_list(update, user)
        return

    # Try to enable native forum topics
    try:
        topic = await update.effective_chat.create_forum_topic("New Chat")
        await set_user_topic_mode(update.effective_user.id, True)
        await set_session_topic_thread(user["current_session_id"], topic.message_thread_id)
        await update.message.reply_text(
            "Topic mode enabled! Each conversation will appear as a separate topic.\n"
            "Use /new to create a new topic, or /topic to see all topics."
        )
        logger.info(f"Native topic mode enabled for user {update.effective_user.id}")
    except (BadRequest, Exception) as e:
        logger.info(f"Native topics not supported, using inline mode: {e}")
        await set_user_topic_mode(update.effective_user.id, True)
        await _show_topic_list(update, user)


async def _show_topic_list(update: Update, user: dict):
    """Show session list as inline keyboard (fallback mode)."""
    sessions = await get_user_sessions(update.effective_user.id)
    current_id = user["current_session_id"]

    buttons = []
    for s in sessions:
        title = s["title"] or "New Chat"
        label = f"✓ {title}" if s["id"] == current_id else title
        # Truncate to fit callback_data limit
        callback = f"topic:switch:{s['id']}"
        buttons.append([InlineKeyboardButton(label, callback_data=callback)])

    buttons.append([InlineKeyboardButton("➕ New Chat", callback_data="topic:new")])

    text = f"Your conversations ({len(sessions)}):"
    reply_func = update.message.reply_text if update.message else update.callback_query.edit_message_text
    await reply_func(text, reply_markup=InlineKeyboardMarkup(buttons))


async def topic_switch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    session_id = int(query.data.removeprefix("topic:switch:"))
    await switch_session(query.from_user.id, session_id)

    user = await get_or_create_user(query.from_user.id)
    await _show_topic_list_edit(query, user)


async def topic_new_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = await get_or_create_user(query.from_user.id)
    model = user["current_model"]

    # Try native topic creation if supported
    if user.get("topic_mode"):
        try:
            topic = await query.message.chat.create_forum_topic("New Chat")
            session_id = await create_session(query.from_user.id, model)
            await set_session_topic_thread(session_id, topic.message_thread_id)
            await query.edit_message_text(f"New topic created with `{model}`.", parse_mode="Markdown")
            return
        except (BadRequest, Exception):
            pass

    # Fallback: just create a new session
    await create_session(query.from_user.id, model)
    user = await get_or_create_user(query.from_user.id)
    await _show_topic_list_edit(query, user)


async def _show_topic_list_edit(query, user: dict):
    """Edit existing message to show updated topic list."""
    sessions = await get_user_sessions(query.from_user.id)
    current_id = user["current_session_id"]

    buttons = []
    for s in sessions:
        title = s["title"] or "New Chat"
        label = f"✓ {title}" if s["id"] == current_id else title
        callback = f"topic:switch:{s['id']}"
        buttons.append([InlineKeyboardButton(label, callback_data=callback)])

    buttons.append([InlineKeyboardButton("➕ New Chat", callback_data="topic:new")])

    text = f"Your conversations ({len(sessions)}):"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
