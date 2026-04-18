from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.web.sqlite_store import connect_web_sqlite, ensure_web_sqlite_schema


GLOBAL_SETTINGS_RECORD = "global_settings"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_settings_record(
    *,
    database_file: Path,
    settings_file: Path,
) -> dict[str, Any]:
    ensure_web_sqlite_schema(database_file)
    with connect_web_sqlite(database_file) as connection:
        row = connection.execute(
            "SELECT value_json FROM app_settings WHERE name = ?",
            (GLOBAL_SETTINGS_RECORD,),
        ).fetchone()
        if row:
            try:
                payload = json.loads(str(row["value_json"]))
            except Exception:
                payload = {}
            return payload if isinstance(payload, dict) else {}

    if not settings_file.is_file():
        return {}
    try:
        payload = json.loads(settings_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_settings_record(
    raw: Any,
    *,
    database_file: Path,
    settings_file: Path,
) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    ensure_web_sqlite_schema(database_file)
    with connect_web_sqlite(database_file) as connection:
        connection.execute(
            """
            INSERT INTO app_settings(name, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (
                GLOBAL_SETTINGS_RECORD,
                json.dumps(payload, ensure_ascii=False),
                _utc_now(),
            ),
        )
        connection.commit()

    # 保留 JSON 镜像，降低迁移风险。
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


__all__ = [
    "load_settings_record",
    "save_settings_record",
]
