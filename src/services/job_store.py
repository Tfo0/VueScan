from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from config import OUTPUTS_DIR
from src.vue_api.models import utc_now_iso

from .job_store_db import JOB_DB_FILE, connect_job_store, ensure_job_store_schema


JOBS_DIR = OUTPUTS_DIR / "jobs"
_JOB_IO_LOCK = threading.RLock()


def _job_path(job_id: str) -> Path:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    return JOBS_DIR / f"{job_id}.json"


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(raw: object, default: object) -> object:
    text = str(raw or "").strip()
    if not text:
        return default
    try:
        data = json.loads(text)
    except Exception:
        return default
    return data


def _normalize_job_payload(payload: dict) -> dict:
    logs = payload.get("logs") if isinstance(payload.get("logs"), list) else []
    return {
        "job_id": str(payload.get("job_id") or "").strip(),
        "step": str(payload.get("step") or "").strip(),
        "status": str(payload.get("status") or "").strip(),
        "created_at": str(payload.get("created_at") or "").strip(),
        "updated_at": str(payload.get("updated_at") or "").strip(),
        "finished_at": payload.get("finished_at"),
        "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
        "result": payload.get("result") if isinstance(payload.get("result"), dict) else {},
        "error": str(payload.get("error") or ""),
        "logs": [
            {
                "time": str(item.get("time") or "").strip(),
                "message": str(item.get("message") or "").strip(),
            }
            for item in logs
            if isinstance(item, dict)
        ],
    }


def _write_job_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    with NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=str(path.parent), suffix=".tmp") as fp:
        fp.write(text)
        fp.flush()
        temp_path = Path(fp.name)
    last_exc: Exception | None = None
    for _ in range(12):
        try:
            temp_path.replace(path)
            return
        except PermissionError as exc:
            last_exc = exc
            time.sleep(0.03)
    try:
        if temp_path.exists():
            temp_path.unlink()
    except Exception:
        pass
    if last_exc is not None:
        raise last_exc
    raise PermissionError(f"failed to replace job file: {path.name}")


def _read_job_file(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"job not found: {path.stem}")
    last_exc: Exception | None = None
    for _ in range(6):
        try:
            text = path.read_text(encoding="utf-8")
            if not text.strip():
                raise json.JSONDecodeError("empty json text", "", 0)
            payload = json.loads(text)
            if isinstance(payload, dict):
                return _normalize_job_payload(payload)
            raise ValueError(f"invalid job payload type: {type(payload).__name__}")
        except (json.JSONDecodeError, ValueError) as exc:
            last_exc = exc
            time.sleep(0.03)
    if last_exc is not None:
        raise last_exc
    raise ValueError(f"failed to read job: {path.stem}")


def _job_payload_from_row(connection, row) -> dict:
    logs = [
        {
            "time": str(log_row["created_at"] or "").strip(),
            "message": str(log_row["message"] or "").strip(),
        }
        for log_row in connection.execute(
            """
            SELECT created_at, message
            FROM job_logs
            WHERE job_id = ?
            ORDER BY id ASC
            """,
            (str(row["job_id"]),),
        ).fetchall()
    ]
    return _normalize_job_payload(
        {
            "job_id": row["job_id"],
            "step": row["step"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "finished_at": row["finished_at"],
            "payload": _json_loads(row["payload_json"], {}),
            "result": _json_loads(row["result_json"], {}),
            "error": row["error_text"],
            "logs": logs,
        }
    )


def _mirror_job_file(payload: dict) -> None:
    _write_job_file(_job_path(str(payload.get("job_id") or "")), _normalize_job_payload(payload))


def _save_job_payload(payload: dict, *, database_file: Path = JOB_DB_FILE) -> dict:
    ensure_job_store_schema(database_file)
    normalized = _normalize_job_payload(payload)
    with connect_job_store(database_file) as connection:
        connection.execute(
            """
            INSERT INTO jobs (
                job_id,
                step,
                status,
                created_at,
                updated_at,
                finished_at,
                payload_json,
                result_json,
                error_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                step = excluded.step,
                status = excluded.status,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                finished_at = excluded.finished_at,
                payload_json = excluded.payload_json,
                result_json = excluded.result_json,
                error_text = excluded.error_text
            """,
            (
                normalized["job_id"],
                normalized["step"],
                normalized["status"],
                normalized["created_at"],
                normalized["updated_at"],
                normalized.get("finished_at"),
                _json_dumps(normalized["payload"]),
                _json_dumps(normalized["result"]),
                normalized["error"],
            ),
        )
        connection.execute("DELETE FROM job_logs WHERE job_id = ?", (normalized["job_id"],))
        if normalized["logs"]:
            connection.executemany(
                """
                INSERT INTO job_logs (job_id, created_at, message)
                VALUES (?, ?, ?)
                """,
                [
                    (
                        normalized["job_id"],
                        str(item.get("time") or "").strip(),
                        str(item.get("message") or "").strip(),
                    )
                    for item in normalized["logs"]
                ],
            )
        connection.commit()
    _mirror_job_file(normalized)
    return normalized


def _read_job_from_db(job_id: str, *, database_file: Path = JOB_DB_FILE) -> dict:
    ensure_job_store_schema(database_file)
    with connect_job_store(database_file) as connection:
        row = connection.execute(
            """
            SELECT job_id, step, status, created_at, updated_at, finished_at, payload_json, result_json, error_text
            FROM jobs
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"job not found: {job_id}")
        return _job_payload_from_row(connection, row)


def _load_or_import_job(job_id: str, *, database_file: Path = JOB_DB_FILE) -> dict:
    try:
        return _read_job_from_db(job_id, database_file=database_file)
    except FileNotFoundError:
        path = _job_path(job_id)
        payload = _read_job_file(path)
        return _save_job_payload(payload, database_file=database_file)


def create_job(step: str, payload: dict | None = None) -> dict:
    with _JOB_IO_LOCK:
        now = utc_now_iso()
        data = {
            "job_id": f"{now.replace(':', '').replace('-', '')}_{uuid4().hex[:8]}",
            "step": step,
            "status": "running",
            "created_at": now,
            "updated_at": now,
            "finished_at": None,
            "payload": payload or {},
            "result": {},
            "error": "",
            "logs": [],
        }
        return _save_job_payload(data)


def append_log(job_id: str, message: str) -> dict:
    with _JOB_IO_LOCK:
        data = _load_or_import_job(job_id)
        timestamp = utc_now_iso()
        text = str(message)
        data["logs"].append({"time": timestamp, "message": text})
        data["updated_at"] = utc_now_iso()
        updated = _save_job_payload(data)
    try:
        print(f"[{timestamp}] [job:{job_id}] {text}", flush=True)
    except Exception:
        pass
    return updated


def update_job(
    job_id: str,
    status: str,
    result: dict | None = None,
    error: str | None = None,
) -> dict:
    with _JOB_IO_LOCK:
        data = _load_or_import_job(job_id)
        data["status"] = status
        data["updated_at"] = utc_now_iso()
        if result is not None:
            data["result"] = result
        if error is not None:
            data["error"] = str(error)
        if status in {"completed", "failed", "stopped", "cancelled", "canceled"}:
            data["finished_at"] = utc_now_iso()
        return _save_job_payload(data)


def read_job(job_id: str) -> dict:
    with _JOB_IO_LOCK:
        return _load_or_import_job(job_id)


def list_jobs(limit: int = 30) -> list[dict]:
    with _JOB_IO_LOCK:
        ensure_job_store_schema()
        with connect_job_store() as connection:
            rows = connection.execute(
                """
                SELECT job_id, step, status, created_at, updated_at
                FROM jobs
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
            if rows:
                return [
                    {
                        "job_id": str(row["job_id"] or "").strip(),
                        "step": str(row["step"] or "").strip(),
                        "status": str(row["status"] or "").strip(),
                        "created_at": str(row["created_at"] or "").strip(),
                        "updated_at": str(row["updated_at"] or "").strip(),
                    }
                    for row in rows
                ]

        if not JOBS_DIR.is_dir():
            return []
        files = sorted(JOBS_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        records: list[dict] = []
        for path in files[: max(1, int(limit))]:
            try:
                payload = _read_job_file(path)
                _save_job_payload(payload)
            except Exception:
                continue
            records.append(
                {
                    "job_id": payload.get("job_id"),
                    "step": payload.get("step"),
                    "status": payload.get("status"),
                    "created_at": payload.get("created_at"),
                    "updated_at": payload.get("updated_at"),
                }
            )
        return records


def iter_job_payloads(limit: int = 30, *, step: str | None = None) -> list[dict]:
    with _JOB_IO_LOCK:
        ensure_job_store_schema()
        query = """
            SELECT job_id, step, status, created_at, updated_at, finished_at, payload_json, result_json, error_text
            FROM jobs
        """
        params: list[object] = []
        if step:
            query += " WHERE step = ?"
            params.append(step)
        query += " ORDER BY updated_at DESC, created_at DESC LIMIT ?"
        params.append(max(1, int(limit)))

        with connect_job_store() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
            if rows:
                return [_job_payload_from_row(connection, row) for row in rows]

        if not JOBS_DIR.is_dir():
            return []
        files = sorted(JOBS_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        records: list[dict] = []
        for path in files:
            try:
                payload = _read_job_file(path)
            except Exception:
                continue
            if step and str(payload.get("step") or "").strip() != step:
                continue
            records.append(payload)
            _save_job_payload(payload)
            if len(records) >= max(1, int(limit)):
                break
        return records


__all__ = [
    "append_log",
    "create_job",
    "iter_job_payloads",
    "list_jobs",
    "read_job",
    "update_job",
]
