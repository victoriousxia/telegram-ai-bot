import base64
import io
import json
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

TITLE_MAX_LEN = 15
TITLE_PROMPT = (
    f"用{TITLE_MAX_LEN}字以内概括这段对话的主题，越短越好，宁可精简也不要截断。"
    "不要加引号或标点，只输出标题：\n\n"
)

IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

TEXT_MIME_TYPES = {
    "text/plain", "text/markdown", "text/html", "text/css",
    "text/javascript", "text/x-python", "text/x-c", "text/x-csrc",
    "text/x-c++src", "text/x-java", "text/x-swift", "text/csv",
    "application/json", "application/xml", "application/javascript",
    "application/x-yaml", "application/x-sh",
}

TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".md",
    ".txt", ".json", ".yaml", ".yml", ".toml", ".xml", ".csv",
    ".sh", ".bash", ".zsh", ".fish",
    ".m", ".mm", ".h", ".swift",  # iOS
    ".c", ".cpp", ".cc", ".cxx", ".hpp", ".hxx",  # C/C++
    ".java", ".kt", ".kts",  # JVM
    ".go", ".rs", ".rb", ".php", ".lua", ".sql",
    ".env", ".gitignore", ".dockerfile",
    ".vue", ".svelte", ".astro",
}

MAX_FILE_TEXT_LENGTH = 100_000  # ~100KB text limit


def _is_text_file(mime_type: str, file_name: str | None) -> bool:
    if mime_type in TEXT_MIME_TYPES:
        return True
    if file_name:
        ext = "." + file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        if ext in TEXT_EXTENSIONS:
            return True
    return False


async def _extract_text_from_file(file_obj, file_name: str | None) -> str | None:
    """Download and extract text content from a text/code file."""
    tg_file = await file_obj.get_file()
    data = await tg_file.download_as_bytearray()
    try:
        text = bytes(data).decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = bytes(data).decode("gbk")
        except UnicodeDecodeError:
            return None
    if len(text) > MAX_FILE_TEXT_LENGTH:
        text = text[:MAX_FILE_TEXT_LENGTH] + "\n\n... [文件过长，已截断]"
    ext = ""
    if file_name and "." in file_name:
        ext = file_name.rsplit(".", 1)[-1].lower()
    return f"```{ext}\n{text}\n```"


async def _extract_text_from_pdf(file_obj) -> str | None:
    """Download and extract text from a PDF file."""
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        return None
    tg_file = await file_obj.get_file()
    data = await tg_file.download_as_bytearray()
    reader = PdfReader(io.BytesIO(bytes(data)))
    pages = []
    for i, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(f"[第{i+1}页]\n{page_text}")
    if not pages:
        return None
    text = "\n\n".join(pages)
    if len(text) > MAX_FILE_TEXT_LENGTH:
        text = text[:MAX_FILE_TEXT_LENGTH] + "\n\n... [PDF 过长，已截断]"
    return text


async def _download_file_as_base64(file_obj, context: ContextTypes.DEFAULT_TYPE) -> tuple[str, str]:
    """Download a Telegram file and return (base64_data, mime_type)."""
    tg_file = await file_obj.get_file()
    data = await tg_file.download_as_bytearray()
    b64 = base64.b64encode(bytes(data)).decode("utf-8")
    mime = getattr(file_obj, "mime_type", None) or "image/jpeg"
    return b64, mime


def _build_multimodal_content(text: str | None, images: list[dict]) -> str:
    """Build JSON content array for storage. images: [{"base64": ..., "mime_type": ...}]"""
    parts = []
    for img in images:
        parts.append({
            "type": "image",
            "base64": img["base64"],
            "mime_type": img["mime_type"],
        })
    if text:
        parts.append({"type": "text", "text": text})
    else:
        parts.append({"type": "text", "text": "请描述这张图片"})
    return json.dumps(parts, ensure_ascii=False)


async def _generate_title(session_id: int, user_message: str, model: str,
                          chat: Chat, thread_id: int | None, topic_mode: int | None):
    """Background task: generate AI title and update session/topic."""
    title_model = config.TITLE_MODEL or model
    logger.info(f"Auto-title: generating with model={title_model}, session={session_id}")
    try:
        prompt_messages = [
            {"role": "user", "content": TITLE_PROMPT + user_message}
        ]
        title = await chat_once(prompt_messages, title_model)
        logger.info(f"Auto-title: raw result={title!r}")
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
            except Exception as e:
                logger.warning(f"Auto-title: edit_forum_topic failed: {e}")
    except Exception as e:
        logger.warning(f"Auto-title generation failed: {e}")
        title = user_message[:TITLE_MAX_LEN].strip() or "Chat"
        await set_session_title(session_id, title)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return

    msg = update.message
    user_text = msg.text or msg.caption or ""
    images: list[dict] = []

    if msg.photo:
        photo = msg.photo[-1]
        b64, mime = await _download_file_as_base64(photo, context)
        images.append({"base64": b64, "mime_type": mime})

    if msg.document:
        doc = msg.document
        mime_type = doc.mime_type or ""
        file_name = doc.file_name or ""
        if mime_type in IMAGE_MIME_TYPES:
            b64, mime = await _download_file_as_base64(doc, context)
            images.append({"base64": b64, "mime_type": mime})
        elif mime_type == "application/pdf":
            extracted = await _extract_text_from_pdf(doc)
            if extracted:
                user_text = (user_text + "\n\n" + extracted).strip() if user_text else extracted
            else:
                await msg.reply_text("无法提取 PDF 文本内容（可能是扫描件）")
                return
        elif _is_text_file(mime_type, file_name):
            extracted = await _extract_text_from_file(doc, file_name)
            if extracted:
                user_text = (user_text + "\n\n" + extracted).strip() if user_text else extracted
            else:
                await msg.reply_text("无法读取该文件内容（编码不支持）")
                return
        elif not user_text:
            await msg.reply_text(f"暂不支持处理该文件类型: {mime_type or file_name}")
            return

    if not user_text and not images:
        return

    if images:
        content = _build_multimodal_content(user_text, images)
    else:
        content = user_text

    user = await get_or_create_user(update.effective_user.id)
    session_id = user["current_session_id"]
    model = user["current_model"]

    if user.get("topic_mode") == 1 and msg.message_thread_id:
        thread_session = await get_session_by_thread(
            update.effective_user.id, msg.message_thread_id
        )
        if thread_session:
            session_id = thread_session["id"]

    await msg.chat.send_action(ChatAction.TYPING)
    await add_message(session_id, "user", content)

    messages = await get_session_messages(session_id)
    bot_message = await msg.reply_text("thinking...")

    logger.info(f"[handle_message] session_id={session_id}, model={model}")

    await stream_and_send(
        stream_chat(messages, model),
        bot_message,
        msg.chat,
        context,
        session_id,
    )

    logger.info("[handle_message] stream_and_send done, checking auto-title")

    # Auto-title: generate AI title after first response
    title_text = user_text or "图片对话"
    session = await get_session(session_id)
    needs_title = session and (
        session["title"] == "New Chat"
        or session["title"].startswith("/")
    )
    if needs_title:
        placeholder = title_text[:TITLE_MAX_LEN].strip() or "Chat"
        await set_session_title(session_id, placeholder)
        context.application.create_task(
            _generate_title(
                session_id, title_text, model,
                update.effective_chat,
                msg.message_thread_id,
                user.get("topic_mode"),
            ),
            update=update,
        )
    else:
        logger.info(
            f"Auto-title skipped: session_id={session_id}, "
            f"title={session['title'] if session else 'N/A'}"
        )
