from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass
class UserTask:
    user_id: int
    source_text: str
    context: str | None
    tone: str | None
    stage: str
    created_at: datetime


class Storage:
    def __init__(self, path: Path, ttl_hours: int = 24) -> None:
        self.path = path
        self.ttl_hours = ttl_hours
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        async with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        user_id INTEGER PRIMARY KEY,
                        source_text TEXT NOT NULL,
                        context TEXT,
                        tone TEXT,
                        stage TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS generations (
                        user_id INTEGER NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )

    async def save_task(
        self,
        user_id: int,
        source_text: str,
        stage: str = "tone",
        context: str | None = None,
        tone: str | None = None,
    ) -> None:
        async with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO tasks(user_id, source_text, context, tone, stage, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        source_text=excluded.source_text,
                        context=excluded.context,
                        tone=excluded.tone,
                        stage=excluded.stage,
                        created_at=excluded.created_at
                    """,
                    (user_id, source_text, context, tone, stage, _now().isoformat()),
                )

    async def update_task(self, user_id: int, *, stage: str | None = None, context: str | None = None, tone: str | None = None) -> None:
        task = await self.get_task(user_id)
        if not task:
            return
        await self.save_task(
            user_id=user_id,
            source_text=task.source_text,
            stage=stage or task.stage,
            context=context if context is not None else task.context,
            tone=tone if tone is not None else task.tone,
        )

    async def get_task(self, user_id: int) -> UserTask | None:
        await self.cleanup()
        async with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT user_id, source_text, context, tone, stage, created_at FROM tasks WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
        if not row:
            return None
        return UserTask(
            user_id=row["user_id"],
            source_text=row["source_text"],
            context=row["context"],
            tone=row["tone"],
            stage=row["stage"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    async def clear_task(self, user_id: int) -> None:
        async with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM tasks WHERE user_id = ?", (user_id,))

    async def record_generation(self, user_id: int) -> None:
        async with self._lock:
            with self._connect() as conn:
                conn.execute("INSERT INTO generations(user_id, created_at) VALUES (?, ?)", (user_id, _now().isoformat()))

    async def count_recent_generations(self, user_id: int, hours: int = 1) -> int:
        threshold = (_now() - timedelta(hours=hours)).isoformat()
        async with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) AS total FROM generations WHERE user_id = ? AND created_at >= ?",
                    (user_id, threshold),
                ).fetchone()
        return int(row["total"])

    async def cleanup(self) -> None:
        threshold = (_now() - timedelta(hours=self.ttl_hours)).isoformat()
        async with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM tasks WHERE created_at < ?", (threshold,))
                conn.execute("DELETE FROM generations WHERE created_at < ?", (threshold,))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn


def _now() -> datetime:
    return datetime.now(UTC)

