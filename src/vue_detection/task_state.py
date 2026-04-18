from __future__ import annotations

from typing import Any, Callable
from urllib.parse import urlsplit


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _coerce_int(raw: Any, default: int, minimum: int = 0) -> int:
    text = _safe_text(raw)
    if not text:
        return max(default, minimum)
    try:
        value = int(text)
    except ValueError:
        return max(default, minimum)
    return max(value, minimum)


def normalize_detect_url_rows(raw_values: Any) -> list[dict[str, Any]]:
    # VueDetect 的 URL 样本可能来自任务结果或 txt 文件，这里统一整理成稳定结构。
    values = raw_values if isinstance(raw_values, list) else []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in values:
        if isinstance(raw, dict):
            url = _safe_text(raw.get("url") or raw.get("final_url"))
            title = _safe_text(raw.get("title"))
            route_count = _coerce_int(raw.get("route_count", raw.get("routeCount")), default=0, minimum=0)
        else:
            url = _safe_text(raw)
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
                "route_count": int(route_count),
            }
        )
    rows.sort(key=lambda item: (-_coerce_int(item.get("route_count"), default=0, minimum=0), _safe_text(item.get("url"))))
    return rows


def task_status_is_running(status: Any) -> bool:
    return _safe_text(status).lower() in {"running", "queued", "paused"}


def serialize_detect_task(item: dict[str, Any]) -> dict[str, Any]:
    urls = normalize_detect_url_rows(item.get("urls"))
    return {
        "task_id": _safe_text(item.get("task_id")),
        "title": _safe_text(item.get("title")),
        "status": _safe_text(item.get("status")),
        "job_id": _safe_text(item.get("job_id")),
        "input_path": _safe_text(item.get("input_path")),
        "params": item.get("params") if isinstance(item.get("params"), dict) else {},
        "result": item.get("result") if isinstance(item.get("result"), dict) else {},
        "urls": urls,
        "url_count": len(urls),
        "error": _safe_text(item.get("error")),
        "created_at": _safe_text(item.get("created_at")),
        "updated_at": _safe_text(item.get("updated_at")),
    }


def serialize_module1_detect_job(job: dict[str, Any]) -> dict[str, Any]:
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    return {
        "job_id": _safe_text(job.get("job_id")),
        "step": _safe_text(job.get("step")),
        "status": _safe_text(job.get("status")),
        "error": _safe_text(job.get("error")),
        "created_at": _safe_text(job.get("created_at")),
        "updated_at": _safe_text(job.get("updated_at")),
        "finished_at": _safe_text(job.get("finished_at")),
        "result": result,
    }


def find_detect_task_by_job_id(
    job_id: str,
    *,
    list_detect_tasks: Callable[..., list[dict[str, Any]]],
) -> dict[str, Any] | None:
    token = _safe_text(job_id)
    if not token:
        return None
    records = list_detect_tasks(limit=5000)
    for item in records:
        if _safe_text(item.get("job_id")) == token:
            return item
    return None
