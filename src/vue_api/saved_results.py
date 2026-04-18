from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from config import PROJECTS_DIR

from .request_snapshot_store import REQUEST_DB_FILE, connect_request_store, ensure_request_snapshot_schema


_SAVED_RESULTS_LOCK = threading.RLock()


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _coerce_int(value: Any, default: int = 0, minimum: int | None = None) -> int:
    try:
        number = int(value)
    except Exception:
        number = default
    if minimum is not None and number < minimum:
        return minimum
    return number


def _saved_results_path(domain: str) -> Path:
    token = _safe_text(domain)
    if not token:
        raise ValueError("domain is required")
    return PROJECTS_DIR / token / "vueApi" / "saved_results.json"


def _atomic_write_json(target: Path, payload: list[dict[str, object]]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    with NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False, suffix=".tmp") as handle:
        handle.write(raw)
        temp_name = handle.name
    os.replace(temp_name, target)


def _normalize_match_key(endpoint_id: int, row_key: str, path: str, url: str) -> str:
    if endpoint_id > 0:
        return f"endpoint:{endpoint_id}"
    if row_key:
        return f"row:{row_key}"
    if path:
        return f"path:{path}"
    return f"url:{url}"


def _normalize_saved_item(raw: dict[str, Any]) -> dict[str, object]:
    endpoint_id = _coerce_int(raw.get("endpoint_id"), default=0, minimum=0)
    row_key = _safe_text(raw.get("row_key"))
    path = _safe_text(raw.get("path"))
    url = _safe_text(raw.get("url"))
    return {
        "match_key": _safe_text(raw.get("match_key")) or _normalize_match_key(endpoint_id, row_key, path, url),
        "row_key": row_key,
        "endpoint_id": endpoint_id,
        "path": path,
        "request_method": _safe_text(raw.get("request_method")).upper() or "GET",
        "url": url,
        "baseurl": _safe_text(raw.get("baseurl")),
        "baseapi": _safe_text(raw.get("baseapi")),
        "base_query": _safe_text(raw.get("base_query")),
        "status_code": _coerce_int(raw.get("status_code"), default=0, minimum=0),
        "ok": bool(raw.get("ok")),
        "elapsed_ms": _coerce_int(raw.get("elapsed_ms"), default=0, minimum=0),
        "response_path": _safe_text(raw.get("response_path")),
        "response_length": _coerce_int(raw.get("response_length"), default=0, minimum=0),
        "packet_length": _coerce_int(raw.get("packet_length"), default=0, minimum=0),
        "requested_at": _safe_text(raw.get("requested_at")),
        "saved_at": _safe_text(raw.get("saved_at")),
        "error": _safe_text(raw.get("error")),
    }


def _saved_item_from_row(row) -> dict[str, object]:
    return _normalize_saved_item(
        {
            "match_key": row["match_key"],
            "row_key": row["row_key"],
            "endpoint_id": row["endpoint_id"],
            "path": row["path"],
            "request_method": row["request_method"],
            "url": row["url"],
            "baseurl": row["baseurl"],
            "baseapi": row["baseapi"],
            "base_query": row["base_query"],
            "status_code": row["status_code"],
            "ok": bool(row["ok"]),
            "elapsed_ms": row["elapsed_ms"],
            "response_path": row["response_path"],
            "response_length": row["response_length"],
            "packet_length": row["packet_length"],
            "requested_at": row["requested_at"],
            "saved_at": row["saved_at"],
            "error": row["error_text"],
        }
    )


def _load_saved_items_from_db(domain: str) -> list[dict[str, object]]:
    ensure_request_snapshot_schema(REQUEST_DB_FILE)
    token = _safe_text(domain)
    with connect_request_store(REQUEST_DB_FILE) as connection:
        rows = connection.execute(
            """
            SELECT
                match_key,
                row_key,
                endpoint_id,
                path,
                request_method,
                url,
                baseurl,
                baseapi,
                base_query,
                status_code,
                ok,
                elapsed_ms,
                response_path,
                response_length,
                packet_length,
                requested_at,
                saved_at,
                error_text
            FROM saved_request_results
            WHERE domain = ?
            ORDER BY saved_at DESC, requested_at DESC
            """,
            (token,),
        ).fetchall()
    return [_saved_item_from_row(row) for row in rows]


def _load_saved_items_from_file(domain: str) -> list[dict[str, object]]:
    target = _saved_results_path(domain)
    if not target.is_file():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    rows = [_normalize_saved_item(item) for item in payload if isinstance(item, dict)]
    rows.sort(key=lambda item: (_safe_text(item.get("saved_at")), _safe_text(item.get("requested_at"))), reverse=True)
    return rows


def _save_saved_items(domain: str, rows: list[dict[str, object]]) -> None:
    ensure_request_snapshot_schema(REQUEST_DB_FILE)
    token = _safe_text(domain)
    normalized_rows = [_normalize_saved_item(item) for item in rows if isinstance(item, dict)]
    normalized_rows.sort(
        key=lambda item: (_safe_text(item.get("saved_at")), _safe_text(item.get("requested_at"))),
        reverse=True,
    )
    with connect_request_store(REQUEST_DB_FILE) as connection:
        connection.execute("DELETE FROM saved_request_results WHERE domain = ?", (token,))
        connection.executemany(
            """
            INSERT INTO saved_request_results (
                domain,
                match_key,
                row_key,
                endpoint_id,
                path,
                request_method,
                url,
                baseurl,
                baseapi,
                base_query,
                status_code,
                ok,
                elapsed_ms,
                response_path,
                response_length,
                packet_length,
                requested_at,
                saved_at,
                error_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    token,
                    _safe_text(item.get("match_key")),
                    _safe_text(item.get("row_key")),
                    _coerce_int(item.get("endpoint_id"), default=0, minimum=0),
                    _safe_text(item.get("path")),
                    _safe_text(item.get("request_method")).upper() or "GET",
                    _safe_text(item.get("url")),
                    _safe_text(item.get("baseurl")),
                    _safe_text(item.get("baseapi")),
                    _safe_text(item.get("base_query")),
                    _coerce_int(item.get("status_code"), default=0, minimum=0),
                    1 if bool(item.get("ok")) else 0,
                    _coerce_int(item.get("elapsed_ms"), default=0, minimum=0),
                    _safe_text(item.get("response_path")),
                    _coerce_int(item.get("response_length"), default=0, minimum=0),
                    _coerce_int(item.get("packet_length"), default=0, minimum=0),
                    _safe_text(item.get("requested_at")),
                    _safe_text(item.get("saved_at")),
                    _safe_text(item.get("error")),
                )
                for item in normalized_rows
            ],
        )
        connection.commit()
    _atomic_write_json(_saved_results_path(token), normalized_rows)


def load_saved_request_results(domain: str) -> list[dict[str, object]]:
    with _SAVED_RESULTS_LOCK:
        rows = _load_saved_items_from_db(domain)
        if rows:
            return rows
        rows = _load_saved_items_from_file(domain)
        if rows:
            _save_saved_items(domain, rows)
        return rows


def save_saved_request_result(
    *,
    domain: str,
    row_key: str,
    endpoint_id: int,
    path: str,
    request_result: dict[str, Any],
    response_detail: dict[str, Any] | None = None,
    response_length: int = 0,
    packet_length: int = 0,
) -> dict[str, object]:
    # 只把用户明确保存的结果建立索引，避免每次请求都把结果列表刷得很乱。
    with _SAVED_RESULTS_LOCK:
        current_items = load_saved_request_results(domain)
        normalized_request = request_result if isinstance(request_result, dict) else {}
        normalized_detail = response_detail if isinstance(response_detail, dict) else {}

        endpoint_id_value = _coerce_int(endpoint_id or normalized_request.get("api_id"), default=0, minimum=0)
        row_key_value = _safe_text(row_key)
        path_value = _safe_text(path)
        url_value = _safe_text(normalized_request.get("url"))
        item = _normalize_saved_item(
            {
                "match_key": _normalize_match_key(endpoint_id_value, row_key_value, path_value, url_value),
                "row_key": row_key_value,
                "endpoint_id": endpoint_id_value,
                "path": path_value,
                "request_method": _safe_text(normalized_request.get("method")),
                "url": url_value,
                "baseurl": _safe_text(normalized_request.get("baseurl")),
                "baseapi": _safe_text(normalized_request.get("baseapi")),
                "base_query": _safe_text(normalized_request.get("base_query")),
                "status_code": normalized_request.get("status_code"),
                "ok": normalized_request.get("ok"),
                "elapsed_ms": normalized_request.get("elapsed_ms"),
                "response_path": _safe_text(normalized_request.get("response_path")),
                "response_length": response_length,
                "packet_length": packet_length,
                "requested_at": _safe_text(normalized_detail.get("requested_at")),
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "error": _safe_text(normalized_request.get("error") or normalized_detail.get("error")),
            }
        )

        merged = [row for row in current_items if _safe_text(row.get("match_key")) != _safe_text(item.get("match_key"))]
        merged.append(item)
        merged.sort(key=lambda row: _safe_text(row.get("saved_at")), reverse=True)
        _save_saved_items(domain, merged)
        return item


__all__ = [
    "load_saved_request_results",
    "save_saved_request_result",
]
