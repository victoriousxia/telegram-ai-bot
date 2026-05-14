from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.config import config
from bot.services.session import (
    get_or_create_user,
    create_session,
    set_user_model,
)
from bot.services.ai_client import fetch_models


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
