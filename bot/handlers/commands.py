import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction, ParseMode

from bot.config import config
from bot.services.session import (
    get_or_create_user,
    create_session,
    set_user_model,
    set_session_title,
    delete_last_exchange,
    delete_last_assistant_message,
    get_last_user_message,
    get_session_messages,
    replace_messages_with_summary,
)
from bot.services.ai_client import fetch_models, stream_chat, chat_once


def _shorten_model_name(model: str) -> str:
    """Remove claude- prefix only."""
    name = model
    if name.startswith("claude-"):
        name = name[len("claude-"):]
    return name


async def check_access(update: Update) -> bool:
    if config.ALLOWED_USER_IDS is None:
        return True
    return update.effective_user.id in config.ALLOWED_USER_IDS


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    user = await get_or_create_user(update.effective_user.id)
    await update.message.reply_text(
        f"Hi! I'm your AI assistant.\n\n"
        f"Current model: `{user['current_model']}`\n\n"
        f"Commands:\n"
        f"/new - Start a new conversation\n"
        f"/topic - Manage conversation topics\n"
        f"/model - Switch AI model\n"
        f"/retry - Regenerate last response\n"
        f"/undo - Remove last exchange\n"
        f"/title - Set conversation title\n"
        f"/stop - Stop generation\n"
        f"/compress - Compress context\n\n"
        f"Just send me a message to start chatting!",
        parse_mode="Markdown",
    )


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return

    user = await get_or_create_user(update.effective_user.id)
    await create_session(update.effective_user.id, user["current_model"])
    await update.message.reply_text(
        f"New conversation started with `{user['current_model']}`.",
        parse_mode="Markdown",
    )


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return

    user = await get_or_create_user(update.effective_user.id)
    text, markup = _build_provider_selection(user["current_model"])
    await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")


def _build_provider_selection(current_model: str):
    """Step 1: show provider list."""
    buttons = []
    for name, provider in config.providers.items():
        label = f"{provider.name} ({len(provider.models)})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"provider:{name}")])
    buttons.append([InlineKeyboardButton("Cancel", callback_data="model:cancel")])

    text = (
        f"Current model: `{current_model}`\n\n"
        f"Select provider:"
    )
    return text, InlineKeyboardMarkup(buttons)


def _build_model_selection(provider_name: str, current_model: str):
    """Step 2: show models for a specific provider."""
    provider = config.providers[provider_name]
    buttons = []
    row = []
    for model in provider.models:
        short = _shorten_model_name(model)
        label = f"✓ {short}" if model == current_model else short
        row.append(InlineKeyboardButton(label, callback_data=f"setmodel:{model}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("« Back", callback_data="provider:back"),
        InlineKeyboardButton("Cancel", callback_data="model:cancel"),
    ])

    text = (
        f"Current model: `{current_model}`\n"
        f"Provider: *{provider.name}*\n\n"
        f"Select model:"
    )
    return text, InlineKeyboardMarkup(buttons)


async def provider_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle provider selection (step 1 -> step 2)."""
    query = update.callback_query

    data = query.data.removeprefix("provider:")

    if data == "back":
        await query.answer()
        user = await get_or_create_user(query.from_user.id)
        text, markup = _build_provider_selection(user["current_model"])
        await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
        return

    provider_name = data
    provider = config.providers.get(provider_name)
    if not provider:
        await query.answer("Provider not found.", show_alert=True)
        return

    # Show loading state
    await query.answer()
    await query.edit_message_text(
        f"Loading models from *{provider.name}*...",
        parse_mode="Markdown",
    )

    # Refresh models if empty
    if not provider.models:
        try:
            provider.models = await fetch_models(provider)
        except Exception:
            await query.edit_message_text(
                f"Failed to fetch models from {provider.name}.",
            )
            return

    user = await get_or_create_user(query.from_user.id)
    text, markup = _build_model_selection(provider_name, user["current_model"])
    await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")


async def model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle model selection (step 2 confirm) or cancel."""
    query = update.callback_query
    await query.answer()

    data = query.data.removeprefix("model:")
    if data == "cancel":
        await query.edit_message_text("Model selection cancelled.")
        return


async def setmodel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle final model selection."""
    query = update.callback_query
    await query.answer()

    model = query.data.removeprefix("setmodel:")
    await set_user_model(query.from_user.id, model)
    await query.edit_message_text(
        f"Model switched to `{model}`.",
        parse_mode="Markdown",
    )


async def retry_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return

    user = await get_or_create_user(update.effective_user.id)
    session_id = user["current_session_id"]
    model = user["current_model"]

    last_msg = await get_last_user_message(session_id)
    if not last_msg:
        await update.message.reply_text("No message to retry.")
        return

    await delete_last_assistant_message(session_id)

    await update.message.chat.send_action(ChatAction.TYPING)
    messages = await get_session_messages(session_id)
    bot_message = await update.message.reply_text("thinking...")

    full_response = ""
    last_update = time.time()
    update_interval = config.STREAM_UPDATE_INTERVAL

    try:
        async for chunk in stream_chat(messages, model):
            if context.user_data.get("stop_flag"):
                context.user_data["stop_flag"] = False
                break
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
            from bot.services.session import add_message
            await add_message(session_id, "assistant", full_response)
        else:
            await bot_message.edit_text("No response from the model.")
    except Exception as e:
        error_msg = f"Error: {type(e).__name__}: {str(e)[:200]}"
        await bot_message.edit_text(error_msg)


async def undo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return

    user = await get_or_create_user(update.effective_user.id)
    session_id = user["current_session_id"]

    success = await delete_last_exchange(session_id)
    if success:
        await update.message.reply_text("Last exchange removed.")
    else:
        await update.message.reply_text("Nothing to undo.")


async def title_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return

    text = update.message.text.removeprefix("/title").strip()
    if not text:
        await update.message.reply_text("Usage: /title <new title>")
        return

    user = await get_or_create_user(update.effective_user.id)
    session_id = user["current_session_id"]
    await set_session_title(session_id, text)

    # Try to update native topic name
    if user.get("topic_mode") and update.message.message_thread_id:
        try:
            await update.effective_chat.edit_forum_topic(
                message_thread_id=update.message.message_thread_id,
                name=text[:128],
            )
        except Exception:
            pass

    await update.message.reply_text(f"Title set to: {text}")


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return

    context.user_data["stop_flag"] = True
    await update.message.reply_text("Generation stopped.")


async def compress_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return

    user = await get_or_create_user(update.effective_user.id)
    session_id = user["current_session_id"]
    model = user["current_model"]

    messages = await get_session_messages(session_id)
    if len(messages) < 4:
        await update.message.reply_text("Conversation too short to compress.")
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    conversation_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in messages if m["role"] != "system"
    )
    compress_messages = [
        {"role": "user", "content": (
            "请用 150 字以内总结以下对话的关键信息和上下文，"
            "用于后续对话的背景参考。只输出总结内容，不要加前缀：\n\n"
            f"{conversation_text}"
        )}
    ]

    try:
        summary = await chat_once(compress_messages, model)
        original_count = await replace_messages_with_summary(session_id, summary)
        await update.message.reply_text(
            f"Context compressed. ({original_count} messages → summary)\n\n"
            f"Summary: {summary[:200]}{'...' if len(summary) > 200 else ''}"
        )
    except Exception as e:
        await update.message.reply_text(f"Compress failed: {str(e)[:200]}")
