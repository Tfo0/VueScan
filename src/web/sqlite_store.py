from __future__ import annotations

import sqlite3
from pathlib import Path


def connect_web_sqlite(database_file: Path) -> sqlite3.Connection:
    database_file.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_file), timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def ensure_web_sqlite_schema(database_file: Path) -> None:
    # 这里只建系统表，不接管项目原始文件目录。
    with connect_web_sqlite(database_file) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                name TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                disabled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS projects (
                domain TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                seed_urls_json TEXT NOT NULL,
                task_ids_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_projects_updated_at
            ON projects(updated_at DESC);

            CREATE TABLE IF NOT EXISTS detect_tasks (
                task_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                job_id TEXT NOT NULL,
                input_path TEXT NOT NULL,
                params_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                urls_json TEXT NOT NULL,
                error_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_detect_tasks_updated_at
            ON detect_tasks(updated_at DESC);
            """
        )


__all__ = [
    "connect_web_sqlite",
    "ensure_web_sqlite_schema",
]
