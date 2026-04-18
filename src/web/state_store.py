from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from config import OUTPUTS_DIR, PROJECTS_DIR
from src.vue_api.models import utc_now_iso
from src.web.sqlite_store import connect_web_sqlite, ensure_web_sqlite_schema


WEB_STATE_DIR = OUTPUTS_DIR / "web"
DETECT_TASKS_FILE = WEB_STATE_DIR / "detect_tasks.json"
PROJECTS_FILE = WEB_STATE_DIR / "projects.json"
SQLITE_DB_FILE = WEB_STATE_DIR / "app.sqlite3"


def _ensure_state_dir() -> None:
    WEB_STATE_DIR.mkdir(parents=True, exist_ok=True)


def _read_list(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _write_list(path: Path, records: list[dict]) -> None:
    _ensure_state_dir()
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_project_record(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "domain": str(raw.get("domain", "")).strip(),
        "title": str(raw.get("title", "")).strip(),
        "source": str(raw.get("source", "manual") or "manual"),
        "seed_urls": _dedupe_keep_order(
            [str(url).strip() for url in raw.get("seed_urls", []) if str(url).strip()]
        ),
        "task_ids": _dedupe_keep_order(
            [str(task_id).strip() for task_id in raw.get("task_ids", []) if str(task_id).strip()]
        ),
        "created_at": str(raw.get("created_at", "")),
        "updated_at": str(raw.get("updated_at", "")),
    }


def _project_records_from_db() -> list[dict[str, Any]]:
    ensure_web_sqlite_schema(SQLITE_DB_FILE)
    with connect_web_sqlite(SQLITE_DB_FILE) as connection:
        rows = connection.execute(
            """
            SELECT domain, title, source, seed_urls_json, task_ids_json, created_at, updated_at
            FROM projects
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
    records: list[dict[str, Any]] = []
    for row in rows:
        try:
            seed_urls = json.loads(str(row["seed_urls_json"] or "[]"))
        except Exception:
            seed_urls = []
        try:
            task_ids = json.loads(str(row["task_ids_json"] or "[]"))
        except Exception:
            task_ids = []
        records.append(
            _normalize_project_record(
                {
                    "domain": row["domain"],
                    "title": row["title"],
                    "source": row["source"],
                    "seed_urls": seed_urls,
                    "task_ids": task_ids,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        )
    return [item for item in records if item["domain"]]


def _save_project_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [_normalize_project_record(item) for item in records if str(item.get("domain", "")).strip()]
    ensure_web_sqlite_schema(SQLITE_DB_FILE)
    with connect_web_sqlite(SQLITE_DB_FILE) as connection:
        connection.execute("DELETE FROM projects")
        connection.executemany(
            """
            INSERT INTO projects (
                domain,
                title,
                source,
                seed_urls_json,
                task_ids_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item["domain"],
                    item["title"],
                    item["source"],
                    json.dumps(item["seed_urls"], ensure_ascii=False),
                    json.dumps(item["task_ids"], ensure_ascii=False),
                    item["created_at"],
                    item["updated_at"],
                )
                for item in normalized
            ],
        )
        connection.commit()
    _write_list(PROJECTS_FILE, normalized)
    return normalized


def _load_project_records() -> list[dict[str, Any]]:
    records = _project_records_from_db()
    if records:
        return records
    records = [_normalize_project_record(item) for item in _read_list(PROJECTS_FILE)]
    if records:
        _save_project_records(records)
    return records


def _next_detect_title(records: list[dict]) -> str:
    max_index = 0
    for item in records:
        title = str(item.get("title", ""))
        match = re.search(r"(\d+)$", title)
        if match:
            max_index = max(max_index, int(match.group(1)))
    return f"\u68c0\u6d4b\u4efb\u52a1{max_index + 1}"


def _to_non_negative_int(raw: Any, default: int = 0) -> int:
    try:
        value = int(raw)
    except Exception:
        return max(0, int(default))
    return max(0, value)


def _normalize_detect_url_entries(values: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in values:
        if isinstance(raw, dict):
            url = str(raw.get("url") or raw.get("final_url") or "").strip()
            title = str(raw.get("title") or "").strip()
            route_count = _to_non_negative_int(raw.get("route_count", raw.get("routeCount", 0)))
        else:
            url = str(raw or "").strip()
            title = ""
            route_count = 0

        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            continue
        if url in seen:
            continue
        seen.add(url)
        rows.append(
            {
                "url": url,
                "title": title,
                "route_count": route_count,
            }
        )
    rows.sort(key=lambda item: (-_to_non_negative_int(item.get("route_count"), default=0), str(item.get("url") or "")))
    return rows


def _normalize_detect_task_record(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": str(raw.get("task_id", "")).strip(),
        "title": str(raw.get("title", "")).strip(),
        "status": str(raw.get("status", "")).strip(),
        "job_id": str(raw.get("job_id", "")).strip(),
        "input_path": str(raw.get("input_path", "")).strip(),
        "params": raw.get("params") if isinstance(raw.get("params"), dict) else {},
        "result": raw.get("result") if isinstance(raw.get("result"), dict) else {},
        "urls": _normalize_detect_url_entries(raw.get("urls") if isinstance(raw.get("urls"), list) else []),
        "error": str(raw.get("error", "")).strip(),
        "created_at": str(raw.get("created_at", "")).strip(),
        "updated_at": str(raw.get("updated_at", "")).strip(),
    }


def _detect_task_records_from_db() -> list[dict[str, Any]]:
    ensure_web_sqlite_schema(SQLITE_DB_FILE)
    with connect_web_sqlite(SQLITE_DB_FILE) as connection:
        rows = connection.execute(
            """
            SELECT
                task_id,
                title,
                status,
                job_id,
                input_path,
                params_json,
                result_json,
                urls_json,
                error_text,
                created_at,
                updated_at
            FROM detect_tasks
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
    records: list[dict[str, Any]] = []
    for row in rows:
        try:
            params = json.loads(str(row["params_json"] or "{}"))
        except Exception:
            params = {}
        try:
            result = json.loads(str(row["result_json"] or "{}"))
        except Exception:
            result = {}
        try:
            urls = json.loads(str(row["urls_json"] or "[]"))
        except Exception:
            urls = []
        records.append(
            _normalize_detect_task_record(
                {
                    "task_id": row["task_id"],
                    "title": row["title"],
                    "status": row["status"],
                    "job_id": row["job_id"],
                    "input_path": row["input_path"],
                    "params": params,
                    "result": result,
                    "urls": urls,
                    "error": row["error_text"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        )
    return [item for item in records if item["task_id"]]


def _save_detect_task_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [_normalize_detect_task_record(item) for item in records if str(item.get("task_id", "")).strip()]
    ensure_web_sqlite_schema(SQLITE_DB_FILE)
    with connect_web_sqlite(SQLITE_DB_FILE) as connection:
        connection.execute("DELETE FROM detect_tasks")
        connection.executemany(
            """
            INSERT INTO detect_tasks (
                task_id,
                title,
                status,
                job_id,
                input_path,
                params_json,
                result_json,
                urls_json,
                error_text,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item["task_id"],
                    item["title"],
                    item["status"],
                    item["job_id"],
                    item["input_path"],
                    json.dumps(item["params"], ensure_ascii=False),
                    json.dumps(item["result"], ensure_ascii=False),
                    json.dumps(item["urls"], ensure_ascii=False),
                    item["error"],
                    item["created_at"],
                    item["updated_at"],
                )
                for item in normalized
            ],
        )
        connection.commit()
    _write_list(DETECT_TASKS_FILE, normalized)
    return normalized


def _load_detect_task_records() -> list[dict[str, Any]]:
    records = _detect_task_records_from_db()
    if records:
        return records
    records = [_normalize_detect_task_record(item) for item in _read_list(DETECT_TASKS_FILE)]
    if records:
        _save_detect_task_records(records)
    return records


def list_detect_tasks(limit: int = 80) -> list[dict]:
    records = _load_detect_task_records()
    records.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return records[: max(1, int(limit))]


def get_detect_task(task_id: str) -> dict | None:
    needle = str(task_id).strip()
    if not needle:
        return None
    records = _load_detect_task_records()
    return next((item for item in records if str(item.get("task_id")) == needle), None)


def create_detect_task(job_id: str, input_path: str, params: dict | None = None, title: str | None = None) -> dict:
    records = _load_detect_task_records()
    now = utc_now_iso()
    task_title = str(title or "").strip() or _next_detect_title(records)
    record = {
        "task_id": f"detect_{now.replace(':', '').replace('-', '')}_{uuid4().hex[:8]}",
        "title": task_title,
        "status": "running",
        "job_id": str(job_id),
        "input_path": str(input_path),
        "params": params or {},
        "result": {},
        "urls": [],
        "error": "",
        "created_at": now,
        "updated_at": now,
    }
    records.insert(0, record)
    _save_detect_task_records(records)
    return _normalize_detect_task_record(record)


def update_detect_task(
    task_id: str,
    *,
    status: str | None = None,
    result: dict | None = None,
    urls: list[Any] | None = None,
    error: str | None = None,
) -> dict:
    records = _load_detect_task_records()
    now = utc_now_iso()
    for item in records:
        if str(item.get("task_id")) != str(task_id):
            continue
        if status is not None:
            item["status"] = str(status)
        if result is not None:
            item["result"] = result
        if urls is not None:
            item["urls"] = _normalize_detect_url_entries(list(urls))
        if error is not None:
            item["error"] = str(error)
        item["updated_at"] = now
        _save_detect_task_records(records)
        return _normalize_detect_task_record(item)
    raise FileNotFoundError(f"detection task not found: {task_id}")


def delete_detect_task(task_id: str) -> dict:
    needle = str(task_id).strip()
    if not needle:
        raise ValueError("task_id is required")

    records = _load_detect_task_records()
    removed: dict | None = None
    kept_records: list[dict] = []
    for item in records:
        if str(item.get("task_id")) == needle and removed is None:
            removed = item
            continue
        kept_records.append(item)

    if removed is None:
        raise FileNotFoundError(f"detection task not found: {task_id}")

    _save_detect_task_records(kept_records)

    # Keep project linkage clean after deleting a detect task.
    project_records = _load_project_records()
    changed = False
    for item in project_records:
        task_ids = [str(v).strip() for v in item.get("task_ids", []) if str(v).strip()]
        new_task_ids = [task for task in task_ids if task != needle]
        if new_task_ids != task_ids:
            item["task_ids"] = _dedupe_keep_order(new_task_ids)
            changed = True
    if changed:
        _save_project_records(project_records)

    return removed


def _normalize_url(url: str) -> str:
    text = str(url).strip()
    parsed = urlsplit(text)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid url: {url}")
    host = parsed.netloc.strip()
    path = parsed.path or ""
    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return f"{scheme}://{host}{path}{query}{fragment}"


def _domain_from_url(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.hostname:
        raise ValueError(f"cannot resolve domain from url: {url}")
    return parsed.hostname


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = str(value).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _ensure_project_scaffold(domain: str, seed_url: str | None = None) -> None:
    base_dir = PROJECTS_DIR / domain
    router_dir = base_dir / "vueRouter"
    down_chunk_dir = base_dir / "downChunk"
    router_dir.mkdir(parents=True, exist_ok=True)
    down_chunk_dir.mkdir(parents=True, exist_ok=True)

    if not seed_url:
        return

    seed_file = router_dir / "seed_urls.txt"
    existing = []
    if seed_file.is_file():
        existing = [line.strip() for line in seed_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    values = _dedupe_keep_order(existing + [seed_url])
    seed_file.write_text("\n".join(values), encoding="utf-8")

    urls_file = router_dir / "urls.txt"
    if not urls_file.is_file():
        urls_file.write_text(seed_url, encoding="utf-8")


def list_projects(limit: int = 300) -> list[dict]:
    records = _load_project_records()
    records.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return records[: max(1, int(limit))]


def get_project(domain: str) -> dict | None:
    needle = str(domain).strip()
    if not needle:
        return None
    records = list_projects(limit=5000)
    return next((item for item in records if item["domain"] == needle), None)


def upsert_project_from_url(
    url: str,
    source: str,
    task_id: str | None = None,
    title: str | None = None,
    resolve_title: bool = False,
) -> dict:
    normalized_url = _normalize_url(url)
    domain = _domain_from_url(normalized_url)
    now = utc_now_iso()
    project_title = str(title or "").strip()

    records = _load_project_records()
    existing = next((item for item in records if str(item.get("domain")) == domain), None)
    existing_title = str(existing.get("title", "")).strip() if isinstance(existing, dict) else ""
    if not project_title and not existing_title:
        if resolve_title:
            from src.web.page_title import resolve_page_title

            project_title = resolve_page_title(normalized_url)
        if not project_title:
            # 创建项目不阻塞，先用域名占位，后续可手动补标题。
            project_title = domain

    if existing is None:
        existing = {
            "domain": domain,
            "title": project_title,
            "source": str(source or "manual"),
            "seed_urls": [],
            "task_ids": [],
            "created_at": now,
            "updated_at": now,
        }
        records.append(existing)

    existing["source"] = str(existing.get("source") or source or "manual")
    if project_title:
        existing["title"] = project_title
    else:
        existing["title"] = str(existing.get("title", "")).strip()
    seeds = [str(v).strip() for v in existing.get("seed_urls", []) if str(v).strip()]
    if normalized_url not in seeds:
        seeds.append(normalized_url)
    existing["seed_urls"] = _dedupe_keep_order(seeds)

    task_ids = [str(v).strip() for v in existing.get("task_ids", []) if str(v).strip()]
    if task_id:
        task_ids.append(str(task_id).strip())
    existing["task_ids"] = _dedupe_keep_order(task_ids)
    if not existing.get("created_at"):
        existing["created_at"] = now
    existing["updated_at"] = now

    _save_project_records(records)
    _ensure_project_scaffold(domain, normalized_url)
    return _normalize_project_record(existing)


def update_project_title(domain: str, title: str | None) -> dict:
    needle = str(domain).strip()
    if not needle:
        raise ValueError("domain is required")

    now = utc_now_iso()
    project_title = str(title or "").strip()
    records = _load_project_records()
    existing = next((item for item in records if str(item.get("domain")).strip() == needle), None)

    if existing is None:
        base_dir = PROJECTS_DIR / needle
        if not base_dir.exists():
            raise FileNotFoundError(f"project not found: {domain}")
        existing = {
            "domain": needle,
            "title": project_title,
            "source": "filesystem",
            "seed_urls": [],
            "task_ids": [],
            "created_at": now,
            "updated_at": now,
        }
        records.append(existing)

    existing["title"] = project_title
    if not existing.get("created_at"):
        existing["created_at"] = now
    existing["updated_at"] = now
    _save_project_records(records)
    return _normalize_project_record(existing)


def delete_project(domain: str, *, remove_files: bool = True) -> dict:
    needle = str(domain).strip()
    if not needle:
        raise ValueError("domain is required")

    records = _load_project_records()
    removed: dict | None = None
    kept_records: list[dict] = []
    for item in records:
        if str(item.get("domain")).strip() == needle and removed is None:
            removed = item
            continue
        kept_records.append(item)

    if removed is not None:
        _save_project_records(kept_records)

    base_dir = PROJECTS_DIR / needle
    base_dir_exists = base_dir.exists()
    if remove_files and base_dir_exists:
        shutil.rmtree(base_dir, ignore_errors=True)

    if removed is None and not base_dir_exists:
        raise FileNotFoundError(f"project not found: {domain}")

    return _normalize_project_record(
        {
            "domain": needle,
            "title": str((removed or {}).get("title") or ""),
            "source": str((removed or {}).get("source") or "filesystem"),
            "seed_urls": _dedupe_keep_order(
                [str(v).strip() for v in (removed or {}).get("seed_urls", []) if str(v).strip()]
            ),
            "task_ids": _dedupe_keep_order(
                [str(v).strip() for v in (removed or {}).get("task_ids", []) if str(v).strip()]
            ),
            "created_at": str((removed or {}).get("created_at") or ""),
            "updated_at": str((removed or {}).get("updated_at") or ""),
        }
    )
