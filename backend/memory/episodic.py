"""
Episodic memory: persistent conversation storage (PostgreSQL).

Stores chat sessions and their messages so the sidebar can list past
conversations and reload them. Pure storage — no AI calls here.
"""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import asyncpg

# config.py lives at the project root, one level above backend/. Make it
# importable regardless of the working directory uvicorn is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import DATABASE_URL  # noqa: E402


class EpisodicMemory:
    """PostgreSQL-backed store for chat sessions and messages."""

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or DATABASE_URL
        self._pool: Optional[asyncpg.Pool] = None

    async def init_db(self) -> None:
        if not self.dsn:
            raise RuntimeError(
                "DATABASE_URL is not configured. Set it in .env to your "
                "Postgres connection string (e.g. from Neon)."
            )

        self._pool = await asyncpg.create_pool(
            self.dsn, min_size=1, max_size=5, timeout=10, command_timeout=30
        )

        async with self._pool.acquire() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT,
                    created_at TEXT,
                    summary TEXT
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)"
            )
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    created_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
            """)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()

    async def create_session(self, session_id: str, user_id: str) -> None:
        async with self._pool.acquire() as db:
            await db.execute(
                "INSERT INTO sessions (id, user_id, title, created_at, summary) VALUES ($1, $2, $3, $4, $5)",
                session_id, user_id, "New Chat", datetime.now(timezone.utc).isoformat(), None,
            )

    async def get_sessions(self, user_id: str, only_with_messages: bool = False) -> list[dict]:
        async with self._pool.acquire() as db:
            if only_with_messages:
                sql = """
                    SELECT s.id, s.title, s.created_at
                    FROM sessions s
                    WHERE s.user_id = $1
                      AND EXISTS (
                        SELECT 1 FROM messages m WHERE m.session_id = s.id
                      )
                    ORDER BY s.created_at DESC
                """
            else:
                sql = "SELECT id, title, created_at FROM sessions WHERE user_id = $1 ORDER BY created_at DESC"
            rows = await db.fetch(sql, user_id)
            return [dict(row) for row in rows]

    async def get_session_owner(self, session_id: str) -> str | None:
        """Return the user_id that owns this session, or None if it doesn't exist."""
        async with self._pool.acquire() as db:
            return await db.fetchval("SELECT user_id FROM sessions WHERE id = $1", session_id)

    async def get_messages(self, session_id: str) -> list[dict]:
        async with self._pool.acquire() as db:
            rows = await db.fetch(
                "SELECT role, content FROM messages WHERE session_id = $1 ORDER BY created_at ASC",
                session_id,
            )
            return [dict(row) for row in rows]

    async def get_recent_messages(self, session_id: str, limit: int = 15) -> list[dict]:
        async with self._pool.acquire() as db:
            rows = await db.fetch(
                """SELECT role, content FROM messages
                   WHERE session_id = $1
                   ORDER BY created_at DESC
                   LIMIT $2""",
                session_id, limit,
            )
            return list(reversed([dict(row) for row in rows]))

    async def get_old_messages(self, session_id: str, exclude_last: int = 15) -> list[dict]:
        async with self._pool.acquire() as db:
            rows = await db.fetch(
                """SELECT role, content FROM messages
                   WHERE session_id = $1
                     AND id NOT IN (
                         SELECT id FROM messages
                         WHERE session_id = $1
                         ORDER BY created_at DESC
                         LIMIT $2
                     )
                   ORDER BY created_at ASC""",
                session_id, exclude_last,
            )
            return [dict(row) for row in rows]

    async def get_message_count(self, session_id: str) -> int:
        async with self._pool.acquire() as db:
            return await db.fetchval(
                "SELECT COUNT(*) FROM messages WHERE session_id = $1", session_id
            )

    async def save_message(self, session_id: str, role: str, content: str) -> None:
        async with self._pool.acquire() as db:
            await db.execute(
                "INSERT INTO messages (id, session_id, role, content, created_at) VALUES ($1, $2, $3, $4, $5)",
                str(uuid.uuid4()), session_id, role, content, datetime.now(timezone.utc).isoformat(),
            )

    async def get_summary(self, session_id: str) -> str | None:
        async with self._pool.acquire() as db:
            return await db.fetchval("SELECT summary FROM sessions WHERE id = $1", session_id)

    async def update_summary(self, session_id: str, summary: str) -> None:
        async with self._pool.acquire() as db:
            await db.execute("UPDATE sessions SET summary = $1 WHERE id = $2", summary, session_id)

    async def update_title(self, session_id: str, title: str) -> None:
        async with self._pool.acquire() as db:
            await db.execute("UPDATE sessions SET title = $1 WHERE id = $2", title, session_id)

    async def delete_session(self, session_id: str) -> None:
        async with self._pool.acquire() as db:
            await db.execute("DELETE FROM messages WHERE session_id = $1", session_id)
            await db.execute("DELETE FROM sessions WHERE id = $1", session_id)
