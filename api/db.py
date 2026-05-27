"""SQLite database layer using aiosqlite."""

from __future__ import annotations

import aiosqlite
import pathlib

DB_PATH = pathlib.Path("api_data.db")


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                key_hash TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                tier TEXT NOT NULL DEFAULT 'free',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                api_key_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                file_path TEXT,
                source_url TEXT,
                result_json TEXT,
                error_code TEXT,
                error_message TEXT,
                audio_minutes REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (api_key_id) REFERENCES api_keys(id)
            );

            CREATE TABLE IF NOT EXISTS usage (
                id TEXT PRIMARY KEY,
                api_key_id TEXT NOT NULL,
                job_id TEXT,
                audio_minutes REAL NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (api_key_id) REFERENCES api_keys(id)
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_api_key ON jobs(api_key_id);
            CREATE INDEX IF NOT EXISTS idx_usage_api_key ON usage(api_key_id);
        """)
        await db.commit()
