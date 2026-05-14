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
