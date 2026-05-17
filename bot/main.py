import logging

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from bot.config import config
from bot.database.models import init_db
from bot.handlers.commands import (
    start_command, new_command, model_command,
    model_callback, provider_callback, setmodel_callback,
    retry_command, undo_command, title_command, stop_command, compress_command,
)
from bot.handlers.topic import topic_command, topic_switch_callback, topic_new_callback
from bot.handlers.chat import handle_message

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application):
    await init_db()

    from bot.services.ai_client import fetch_models
    for provider in config.providers.values():
        if not provider.models:
            try:
                provider.models = await fetch_models(provider)
                logger.info(f"Fetched {len(provider.models)} models from {provider.name}")
            except Exception as e:
                logger.error(f"Failed to fetch models from {provider.name}: {e}")

    if not config.DEFAULT_MODEL and config.all_models:
        config.DEFAULT_MODEL = config.all_models[0]

    await application.bot.set_my_commands([
        ("new", "Start new conversation"),
        ("topic", "Manage conversation topics"),
        ("model", "Switch AI model"),
        ("retry", "Regenerate last response"),
        ("undo", "Remove last exchange"),
        ("title", "Set conversation title"),
        ("stop", "Stop generation"),
        ("compress", "Compress conversation context"),
    ])


def main():
    app = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("new", new_command))
    app.add_handler(CommandHandler("topic", topic_command))
    app.add_handler(CommandHandler("model", model_command))
    app.add_handler(CommandHandler("retry", retry_command))
    app.add_handler(CommandHandler("undo", undo_command))
    app.add_handler(CommandHandler("title", title_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("compress", compress_command))
    app.add_handler(CallbackQueryHandler(provider_callback, pattern=r"^provider:"))
    app.add_handler(CallbackQueryHandler(setmodel_callback, pattern=r"^setmodel:"))
    app.add_handler(CallbackQueryHandler(model_callback, pattern=r"^model:"))
    app.add_handler(CallbackQueryHandler(topic_switch_callback, pattern=r"^topic:switch:"))
    app.add_handler(CallbackQueryHandler(topic_new_callback, pattern=r"^topic:new$"))
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND,
        handle_message,
    ))

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
