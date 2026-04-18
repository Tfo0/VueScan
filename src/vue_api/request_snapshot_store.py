from __future__ import annotations

import sqlite3
from pathlib import Path

from config import OUTPUTS_DIR


REQUEST_DB_FILE = OUTPUTS_DIR / "web" / "app.sqlite3"


def connect_request_store(database_file: Path = REQUEST_DB_FILE) -> sqlite3.Connection:
    database_file.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_file), timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def ensure_request_snapshot_schema(database_file: Path = REQUEST_DB_FILE) -> None:
    # 请求快照和项目级分析摘要进 SQLite，原始镜像 JSON 继续保留在项目目录里。
    with connect_request_store(database_file) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS request_snapshots (
                domain TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                run_index INTEGER NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                request_json TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                rows_json TEXT NOT NULL,
                PRIMARY KEY(domain, snapshot_id)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_request_snapshots_domain_job_id
            ON request_snapshots(domain, job_id);

            CREATE INDEX IF NOT EXISTS idx_request_snapshots_domain_run_index
            ON request_snapshots(domain, run_index ASC);

            CREATE TABLE IF NOT EXISTS request_analysis_summary (
                domain TEXT PRIMARY KEY,
                value_level TEXT NOT NULL,
                value_label TEXT NOT NULL,
                value_reason TEXT NOT NULL,
                value_score INTEGER NOT NULL,
                snapshot_count INTEGER NOT NULL,
                sample_count INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                summary_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS saved_request_results (
                domain TEXT NOT NULL,
                match_key TEXT NOT NULL,
                row_key TEXT NOT NULL,
                endpoint_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                request_method TEXT NOT NULL,
                url TEXT NOT NULL,
                baseurl TEXT NOT NULL,
                baseapi TEXT NOT NULL,
                base_query TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                ok INTEGER NOT NULL,
                elapsed_ms INTEGER NOT NULL,
                response_path TEXT NOT NULL,
                response_length INTEGER NOT NULL,
                packet_length INTEGER NOT NULL,
                requested_at TEXT NOT NULL,
                saved_at TEXT NOT NULL,
                error_text TEXT NOT NULL,
                PRIMARY KEY(domain, match_key)
            );

            CREATE INDEX IF NOT EXISTS idx_saved_request_results_domain_saved_at
            ON saved_request_results(domain, saved_at DESC);
            """
        )


__all__ = [
    "REQUEST_DB_FILE",
    "connect_request_store",
    "ensure_request_snapshot_schema",
]
