from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _flatten(obj: Any, prefix: str = "", result: dict[str, str] | None = None) -> dict[str, str]:
    if result is None:
        result = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else k
            _flatten(v, key, result)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _flatten(v, f"{prefix}.{i}" if prefix else str(i), result)
    else:
        result[prefix] = "" if obj is None else str(obj)
    return result


def extract_and_store_response_params(
    domain: str,
    *,
    database_file: Path,
    projects_dir: Path,
) -> dict[str, Any]:
    responses_dir = projects_dir / domain / "vueApi" / "responses"
    if not responses_dir.is_dir():
        return {"count": 0, "error": "responses dir not found"}

    rows: list[tuple[str, str, str, str, str, str]] = []
    now = _utc_now()

    for json_file in sorted(responses_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        method = str(data.get("method") or "GET").upper()
        url = str(data.get("url") or "")
        status_code = int(data.get("status_code") or 0)
        response_text = str(data.get("response_text") or "")

        # derive path from url
        try:
            from urllib.parse import urlparse
            path = urlparse(url).path or url
        except Exception:
            path = url

        # only parse JSON responses
        try:
            body = json.loads(response_text)
        except Exception:
            continue
        if not isinstance(body, (dict, list)):
            continue

        flat = _flatten(body)
        for field_key, field_value in flat.items():
            rows.append((domain, path, method, field_key, field_value, str(status_code), now))

    if not rows:
        return {"count": 0, "error": ""}

    with _connect(database_file) as conn:
        conn.executemany(
            """
            INSERT INTO api_response_params
                (domain, endpoint_path, method, field_key, field_value, status_code, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(domain, endpoint_path, method, field_key)
            DO UPDATE SET field_value=excluded.field_value,
                          status_code=excluded.status_code,
                          updated_at=excluded.updated_at
            """,
            rows,
        )

    return {"count": len(rows), "error": ""}


def load_param_keys(domain: str, *, database_file: Path) -> list[str]:
    with _connect(database_file) as conn:
        rows = conn.execute(
            "SELECT DISTINCT field_key FROM api_response_params WHERE domain = ? ORDER BY field_key",
            (domain,),
        ).fetchall()
    return [row[0] for row in rows]


def _connect(database_file: Path) -> sqlite3.Connection:
    database_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(database_file), timeout=10.0)
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


__all__ = [
    "extract_and_store_response_params",
    "load_param_keys",
]
