from bot.config import config
from bot.database.models import get_db


async def get_or_create_user(telegram_id: int) -> dict:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        user = await cursor.fetchone()
        if user:
            return dict(user)

        await db.execute(
            "INSERT INTO users (telegram_id, current_model) VALUES (?, ?)",
            (telegram_id, config.DEFAULT_MODEL),
        )
        await db.commit()

        session_id = await create_session(telegram_id, config.DEFAULT_MODEL)
        await db.execute(
            "UPDATE users SET current_session_id = ? WHERE telegram_id = ?",
            (session_id, telegram_id),
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        return dict(await cursor.fetchone())
    finally:
        await db.close()


async def create_session(user_id: int, model: str) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO sessions (user_id, model) VALUES (?, ?)",
            (user_id, model),
        )
        await db.commit()
        session_id = cursor.lastrowid

        await db.execute(
            "UPDATE users SET current_session_id = ? WHERE telegram_id = ?",
            (session_id, user_id),
        )
        await db.commit()
        return session_id
    finally:
        await db.close()


async def set_user_model(telegram_id: int, model: str):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET current_model = ? WHERE telegram_id = ?",
            (model, telegram_id),
        )
        await db.commit()
    finally:
        await db.close()


async def add_message(session_id: int, role: str, content: str):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        await db.execute(
            "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )
        await db.commit()
    finally:
        await db.close()


async def get_session_messages(session_id: int) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]
    finally:
        await db.close()


async def get_user_sessions(user_id: int, limit: int = 20) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, title, model, topic_thread_id, updated_at "
            "FROM sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def switch_session(user_id: int, session_id: int):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET current_session_id = ? WHERE telegram_id = ?",
            (session_id, user_id),
        )
        await db.commit()
    finally:
        await db.close()


async def set_session_title(session_id: int, title: str):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE sessions SET title = ? WHERE id = ?",
            (title, session_id),
        )
        await db.commit()
    finally:
        await db.close()


async def set_session_topic_thread(session_id: int, thread_id: int):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE sessions SET topic_thread_id = ? WHERE id = ?",
            (thread_id, session_id),
        )
        await db.commit()
    finally:
        await db.close()


async def get_session_by_thread(user_id: int, thread_id: int) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM sessions WHERE user_id = ? AND topic_thread_id = ?",
            (user_id, thread_id),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def delete_last_exchange(session_id: int) -> bool:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, role FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT 2",
            (session_id,),
        )
        rows = await cursor.fetchall()
        if len(rows) < 2:
            return False
        ids = [row["id"] for row in rows]
        await db.execute(
            f"DELETE FROM messages WHERE id IN ({','.join('?' * len(ids))})", ids
        )
        await db.commit()
        return True
    finally:
        await db.close()


async def delete_last_assistant_message(session_id: int) -> bool:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id FROM messages WHERE session_id = ? AND role = 'assistant' "
            "ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return False
        await db.execute("DELETE FROM messages WHERE id = ?", (row["id"],))
        await db.commit()
        return True
    finally:
        await db.close()


async def get_last_user_message(session_id: int) -> str | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT content FROM messages WHERE session_id = ? AND role = 'user' "
            "ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        )
        row = await cursor.fetchone()
        return row["content"] if row else None
    finally:
        await db.close()


async def set_user_topic_mode(user_id: int, enabled: bool):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET topic_mode = ? WHERE telegram_id = ?",
            (1 if enabled else 0, user_id),
        )
        await db.commit()
    finally:
        await db.close()


async def replace_messages_with_summary(session_id: int, summary: str) -> int:
    """Delete all messages and insert a system summary. Returns original message count."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        count = row["cnt"]

        await db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        await db.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, 'system', ?)",
            (session_id, summary),
        )
        await db.commit()
        return count
    finally:
        await db.close()


async def get_session(session_id: int) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()
