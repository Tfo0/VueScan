from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from config import PROJECTS_DIR
from .saved_results import load_saved_request_results

from .request_snapshot_store import REQUEST_DB_FILE, connect_request_store, ensure_request_snapshot_schema


_SNAPSHOT_IO_LOCK = threading.RLock()


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


def _snapshot_path(domain: str) -> Path:
    token = _safe_text(domain)
    if not token:
        raise ValueError("domain is required")
    return PROJECTS_DIR / token / "vueApi" / "request_snapshots.json"


def _atomic_write_json(target: Path, payload: list[dict[str, object]]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    with NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False, suffix=".tmp") as handle:
        handle.write(raw)
        temp_name = handle.name
    os.replace(temp_name, target)


def _normalize_request_config(raw: dict[str, Any]) -> dict[str, object]:
    return {
        "method": _safe_text(raw.get("method")).upper() or "GET",
        "baseurl": _safe_text(raw.get("baseurl")),
        "baseapi": _safe_text(raw.get("baseapi")),
        "base_query": _safe_text(raw.get("base_query")),
        "headers": _safe_text(raw.get("headers")),
        "body_type": _safe_text(raw.get("body_type")).lower() or "json",
        "body_text": _safe_text(raw.get("body_text")),
        "use_capture_template": bool(raw.get("use_capture_template")),
        "total": _coerce_int(raw.get("total"), default=0, minimum=0),
    }


def _normalize_row(raw: dict[str, Any]) -> dict[str, object]:
    return {
        "row_key": _safe_text(raw.get("row_key")),
        "endpoint_id": _coerce_int(raw.get("endpoint_id"), default=0, minimum=0),
        "method": _safe_text(raw.get("method")).upper() or "GET",
        "path": _safe_text(raw.get("path")),
        "url": _safe_text(raw.get("url")),
        "status_code": _coerce_int(raw.get("status_code"), default=0, minimum=0),
        "ok": bool(raw.get("ok")),
        "elapsed_ms": _coerce_int(raw.get("elapsed_ms"), default=0, minimum=0),
        "error": _safe_text(raw.get("error")),
        "response_path": _safe_text(raw.get("response_path")),
        "requested_at": _safe_text(raw.get("requested_at")),
        "response_length": _coerce_int(raw.get("response_length"), default=0, minimum=0),
        "packet_length": _coerce_int(raw.get("packet_length"), default=0, minimum=0),
    }


def _normalize_rows(raw_rows: list[Any]) -> list[dict[str, object]]:
    rows = [_normalize_row(item) for item in raw_rows if isinstance(item, dict)]
    rows.sort(
        key=lambda row: (
            _coerce_int(row.get("status_code"), default=0, minimum=0) != 200,
            -_coerce_int(row.get("packet_length"), default=0, minimum=0),
            -_coerce_int(row.get("status_code"), default=0, minimum=0),
            _safe_text(row.get("path")),
        )
    )
    return rows


def _snapshot_response_paths(snapshot: dict[str, object]) -> set[str]:
    rows = snapshot.get("rows") if isinstance(snapshot.get("rows"), list) else []
    return {
        _safe_text(item.get("response_path"))
        for item in rows
        if isinstance(item, dict) and _safe_text(item.get("response_path"))
    }


def _saved_result_response_paths(domain: str) -> set[str]:
    try:
        rows = load_saved_request_results(domain)
    except Exception:
        return set()
    return {
        _safe_text(item.get("response_path"))
        for item in rows
        if isinstance(item, dict) and _safe_text(item.get("response_path"))
    }


def _delete_response_files(paths: set[str]) -> None:
    for raw_path in paths:
        try:
            path = Path(_safe_text(raw_path))
            if path.is_file():
                path.unlink()
        except Exception:
            continue


def _build_summary(rows: list[dict[str, object]], raw_summary: dict[str, Any] | None = None) -> dict[str, object]:
    ok_count = sum(1 for row in rows if bool(row.get("ok")))
    total = len(rows)
    fail_count = max(0, total - ok_count)
    return {
        "total": _coerce_int((raw_summary or {}).get("total"), default=total, minimum=0) or total,
        "done": _coerce_int((raw_summary or {}).get("done"), default=total, minimum=0) or total,
        "ok": _coerce_int((raw_summary or {}).get("ok"), default=ok_count, minimum=0) or ok_count,
        "fail": _coerce_int((raw_summary or {}).get("fail"), default=fail_count, minimum=0) or fail_count,
    }


def _normalize_snapshot(raw: dict[str, Any]) -> dict[str, object]:
    rows = _normalize_rows(raw.get("rows") if isinstance(raw.get("rows"), list) else [])
    run_index = _coerce_int(raw.get("run_index"), default=0, minimum=0)
    return {
        "snapshot_id": _safe_text(raw.get("snapshot_id")) or _safe_text(raw.get("job_id")),
        "job_id": _safe_text(raw.get("job_id")),
        "run_index": run_index,
        "title": _safe_text(raw.get("title")) or (f"第{run_index}次" if run_index > 0 else "未命名"),
        "status": _safe_text(raw.get("status")).lower() or "completed",
        "created_at": _safe_text(raw.get("created_at")),
        "updated_at": _safe_text(raw.get("updated_at")),
        "request": _normalize_request_config(raw.get("request") if isinstance(raw.get("request"), dict) else {}),
        "summary": _build_summary(rows, raw.get("summary") if isinstance(raw.get("summary"), dict) else None),
        "rows": rows,
    }


def _snapshot_from_row(row) -> dict[str, object]:
    return _normalize_snapshot(
        {
            "snapshot_id": row["snapshot_id"],
            "job_id": row["job_id"],
            "run_index": row["run_index"],
            "title": row["title"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "request": json.loads(str(row["request_json"] or "{}")),
            "summary": json.loads(str(row["summary_json"] or "{}")),
            "rows": json.loads(str(row["rows_json"] or "[]")),
        }
    )


def _save_snapshot_rows(domain: str, snapshots: list[dict[str, object]], *, database_file: Path = REQUEST_DB_FILE) -> None:
    ensure_request_snapshot_schema(database_file)
    token = _safe_text(domain)
    with connect_request_store(database_file) as connection:
        connection.execute("DELETE FROM request_snapshots WHERE domain = ?", (token,))
        connection.executemany(
            """
            INSERT INTO request_snapshots (
                domain,
                snapshot_id,
                job_id,
                run_index,
                title,
                status,
                created_at,
                updated_at,
                request_json,
                summary_json,
                rows_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    token,
                    _safe_text(item.get("snapshot_id")),
                    _safe_text(item.get("job_id")),
                    _coerce_int(item.get("run_index"), default=0, minimum=0),
                    _safe_text(item.get("title")),
                    _safe_text(item.get("status")).lower() or "completed",
                    _safe_text(item.get("created_at")),
                    _safe_text(item.get("updated_at")),
                    json.dumps(item.get("request") or {}, ensure_ascii=False),
                    json.dumps(item.get("summary") or {}, ensure_ascii=False),
                    json.dumps(item.get("rows") or [], ensure_ascii=False),
                )
                for item in snapshots
            ],
        )
        connection.commit()
    _atomic_write_json(_snapshot_path(token), snapshots)


def _load_snapshot_rows_from_db(domain: str, *, database_file: Path = REQUEST_DB_FILE) -> list[dict[str, object]]:
    ensure_request_snapshot_schema(database_file)
    token = _safe_text(domain)
    with connect_request_store(database_file) as connection:
        rows = connection.execute(
            """
            SELECT snapshot_id, job_id, run_index, title, status, created_at, updated_at, request_json, summary_json, rows_json
            FROM request_snapshots
            WHERE domain = ?
            ORDER BY run_index ASC
            """,
            (token,),
        ).fetchall()
    return [_snapshot_from_row(row) for row in rows]


def _load_snapshot_rows_from_file(domain: str) -> list[dict[str, object]]:
    target = _snapshot_path(domain)
    if not target.is_file():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    snapshots = [_normalize_snapshot(item) for item in payload if isinstance(item, dict)]
    snapshots.sort(key=lambda item: _coerce_int(item.get("run_index"), default=0, minimum=0))
    return snapshots


def load_request_run_snapshots(domain: str) -> list[dict[str, object]]:
    with _SNAPSHOT_IO_LOCK:
        snapshots = _load_snapshot_rows_from_db(domain)
        if snapshots:
            return snapshots
        snapshots = _load_snapshot_rows_from_file(domain)
        if snapshots:
            _save_snapshot_rows(domain, snapshots)
        return snapshots


def save_request_run_snapshot(
    *,
    domain: str,
    job_id: str,
    status: str,
    request: dict[str, Any] | None,
    rows: list[dict[str, Any]] | None,
) -> dict[str, object]:
    with _SNAPSHOT_IO_LOCK:
        snapshots = load_request_run_snapshots(domain)
        job_token = _safe_text(job_id)
        if not job_token:
            raise ValueError("job_id is required")

        existing = next((item for item in snapshots if _safe_text(item.get("job_id")) == job_token), None)
        run_index = _coerce_int(existing.get("run_index"), default=0, minimum=0) if isinstance(existing, dict) else 0
        if run_index <= 0:
            run_index = max((_coerce_int(item.get("run_index"), default=0, minimum=0) for item in snapshots), default=0) + 1

        now = datetime.now(timezone.utc).isoformat()
        snapshot = _normalize_snapshot(
            {
                "snapshot_id": _safe_text(existing.get("snapshot_id")) if isinstance(existing, dict) else job_token,
                "job_id": job_token,
                "run_index": run_index,
                "title": f"第{run_index}次",
                "status": _safe_text(status).lower() or "completed",
                "created_at": _safe_text(existing.get("created_at")) if isinstance(existing, dict) else now,
                "updated_at": now,
                "request": request or {},
                "summary": {},
                "rows": rows or [],
            }
        )

        merged = [item for item in snapshots if _safe_text(item.get("job_id")) != job_token]
        merged.append(snapshot)
        merged.sort(key=lambda item: _coerce_int(item.get("run_index"), default=0, minimum=0))
        _save_snapshot_rows(domain, merged)

    try:
        from .request_analysis import refresh_request_analysis_summary

        refresh_request_analysis_summary(domain)
    except Exception:
        pass

    return snapshot


def delete_request_run_snapshot(*, domain: str, snapshot_id: str) -> list[dict[str, object]]:
    with _SNAPSHOT_IO_LOCK:
        token = _safe_text(domain)
        snapshot_token = _safe_text(snapshot_id)
        if not token:
            raise ValueError("domain is required")
        if not snapshot_token:
            raise ValueError("snapshot_id is required")

        snapshots = load_request_run_snapshots(token)
        if not snapshots:
            raise FileNotFoundError(f"snapshot not found: {snapshot_token}")

        removed = [item for item in snapshots if _safe_text(item.get("snapshot_id")) == snapshot_token]
        kept = [item for item in snapshots if _safe_text(item.get("snapshot_id")) != snapshot_token]
        if len(kept) == len(snapshots):
            raise FileNotFoundError(f"snapshot not found: {snapshot_token}")

        removed_response_paths: set[str] = set()
        for item in removed:
            removed_response_paths.update(_snapshot_response_paths(item))

        for index, item in enumerate(kept, start=1):
            item["run_index"] = index
            item["title"] = f"绗?{index}娆?"
        _save_snapshot_rows(token, kept)

        remaining_response_paths: set[str] = set()
        for item in kept:
            remaining_response_paths.update(_snapshot_response_paths(item))
        remaining_response_paths.update(_saved_result_response_paths(token))
        _delete_response_files(removed_response_paths - remaining_response_paths)

    try:
        from .request_analysis import refresh_request_analysis_summary

        refresh_request_analysis_summary(token)
    except Exception:
        pass

    return kept


__all__ = [
    "delete_request_run_snapshot",
    "load_request_run_snapshots",
    "save_request_run_snapshot",
]
