from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.config import config
from bot.services.session import (
    get_or_create_user,
    create_session,
    set_user_model,
)


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
        f"/model - Switch AI model\n\n"
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
    buttons = []

    for provider in config.providers.values():
        buttons.append([
            InlineKeyboardButton(
                f"── {provider.name} ({provider.api_type}) ──",
                callback_data="model:noop",
            )
        ])
        row = []
        for model in provider.models:
            label = f"✓ {model}" if model == user["current_model"] else model
            row.append(InlineKeyboardButton(label, callback_data=f"model:{model}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

    buttons.append([InlineKeyboardButton("Cancel", callback_data="model:cancel")])

    await update.message.reply_text(
        f"Current model: `{user['current_model']}`\n\nSelect a model:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.removeprefix("model:")
    if data == "cancel":
        await query.edit_message_text("Model selection cancelled.")
        return
    if data == "noop":
        return

    await set_user_model(query.from_user.id, data)
    await query.edit_message_text(
        f"Model switched to `{data}`.\n\nNew messages will use this model.",
        parse_mode="Markdown",
    )
