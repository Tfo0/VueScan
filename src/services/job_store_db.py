from __future__ import annotations

import sqlite3
from pathlib import Path

from config import OUTPUTS_DIR


JOB_DB_FILE = OUTPUTS_DIR / "web" / "app.sqlite3"


def connect_job_store(database_file: Path = JOB_DB_FILE) -> sqlite3.Connection:
    database_file.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_file), timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def ensure_job_store_schema(database_file: Path = JOB_DB_FILE) -> None:
    # job 元数据进 SQLite，原始大结果和镜像 JSON 继续保留在文件系统里。
    with connect_job_store(database_file) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                step TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                finished_at TEXT,
                payload_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                error_text TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS job_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                message TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_job_logs_job_id
            ON job_logs(job_id, id);

            CREATE INDEX IF NOT EXISTS idx_jobs_step_updated_at
            ON jobs(step, updated_at DESC);
            """
        )


__all__ = [
    "JOB_DB_FILE",
    "connect_job_store",
    "ensure_job_store_schema",
]
