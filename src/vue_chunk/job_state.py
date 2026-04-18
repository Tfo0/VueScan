from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from src.services.job_store import iter_job_payloads
from src.vue_chunk.request_capture import normalize_basepath, normalize_hash_style


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


def _coerce_bool(raw: Any) -> bool:
    return _safe_text(raw).lower() in {"1", "true", "yes", "on"}


def normalize_proxy_server(raw_proxy: Any) -> str:
    value = _safe_text(raw_proxy)
    if not value:
        return ""
    if "://" not in value:
        return f"http://{value}"
    return value


def normalize_sync_status(raw_status: Any) -> str:
    value = _safe_text(raw_status).lower()
    if value in {"completed", "done"}:
        return "done"
    if value in {"failed", "error"}:
        return "failed"
    if value in {"stopped", "cancelled", "canceled"}:
        return "stopped"
    if value in {"paused", "pause"}:
        return "paused"
    if value in {"queued", "pending"}:
        return "queued"
    if value in {"running", "started"}:
        return "running"
    return "idle"


def domain_from_target_url(target_url: str) -> str:
    parsed = urlsplit(_safe_text(target_url))
    return _safe_text(parsed.hostname)


def serialize_sync_job(job: dict[str, Any], fallback_domain: str = "") -> dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    target_url = _safe_text(result.get("target_url") or payload.get("target_url"))
    domain = _safe_text(
        result.get("domain") or payload.get("domain") or fallback_domain or domain_from_target_url(target_url)
    )
    has_detect_routes = isinstance(payload, dict) and "detect_routes" in payload
    has_detect_js = isinstance(payload, dict) and "detect_js" in payload
    has_detect_request = isinstance(payload, dict) and "detect_request" in payload
    has_auto_pipeline = isinstance(payload, dict) and "auto_pipeline" in payload
    return {
        "job_id": _safe_text(job.get("job_id")),
        "step": _safe_text(job.get("step")),
        "status": normalize_sync_status(job.get("status")),
        "error": _safe_text(job.get("error")),
        "created_at": _safe_text(job.get("created_at")),
        "updated_at": _safe_text(job.get("updated_at")),
        "finished_at": _safe_text(job.get("finished_at")),
        "domain": domain,
        "target_url": target_url,
        "concurrency": _coerce_int(payload.get("concurrency"), default=5, minimum=1),
        "proxy_server": normalize_proxy_server(result.get("proxy_server") or payload.get("proxy_server")),
        "detect_routes": _coerce_bool(payload.get("detect_routes")) if has_detect_routes else True,
        "detect_js": _coerce_bool(payload.get("detect_js")) if has_detect_js else True,
        "detect_request": _coerce_bool(payload.get("detect_request")) if has_detect_request else False,
        "auto_pipeline": _coerce_bool(payload.get("auto_pipeline")) if has_auto_pipeline else False,
        "result": result,
    }


def serialize_js_download_job(
    job: dict[str, Any],
    *,
    fallback_domain: str = "",
    default_concurrency: int = 1,
) -> dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    job_id = _safe_text(job.get("job_id"))
    domain = _safe_text(result.get("domain") or payload.get("domain") or fallback_domain)
    mode = _safe_text(result.get("mode") or payload.get("mode"), "zip").lower()
    if mode not in {"zip", "local"}:
        mode = "zip"
    progress_raw = result.get("progress") if isinstance(result.get("progress"), dict) else {}
    total = _coerce_int(
        progress_raw.get("total"),
        default=_coerce_int(payload.get("total"), default=0, minimum=0),
        minimum=0,
    )
    done = _coerce_int(progress_raw.get("done"), default=0, minimum=0)
    downloaded = _coerce_int(
        progress_raw.get("downloaded"),
        default=_coerce_int(result.get("downloaded_count"), default=0, minimum=0),
        minimum=0,
    )
    failed = _coerce_int(
        progress_raw.get("failed"),
        default=_coerce_int(result.get("failed_count"), default=0, minimum=0),
        minimum=0,
    )
    skipped = _coerce_int(
        progress_raw.get("skipped"),
        default=_coerce_int(result.get("skipped_count"), default=0, minimum=0),
        minimum=0,
    )
    status = normalize_sync_status(job.get("status"))
    zip_path = _safe_text(result.get("zip_path"))
    download_url = ""
    if mode == "zip" and status == "done" and zip_path:
        download_url = f"/downloads/vueChunk/jszip/{quote(job_id, safe='')}"
    return {
        "job_id": job_id,
        "step": _safe_text(job.get("step")),
        "status": status,
        "error": _safe_text(job.get("error")),
        "created_at": _safe_text(job.get("created_at")),
        "updated_at": _safe_text(job.get("updated_at")),
        "finished_at": _safe_text(job.get("finished_at")),
        "domain": domain,
        "mode": mode,
        "concurrency": _coerce_int(
            result.get("concurrency"),
            default=_coerce_int(payload.get("concurrency"), default=default_concurrency, minimum=1),
            minimum=1,
        ),
        "total": total,
        "downloaded_count": _coerce_int(result.get("downloaded_count"), default=downloaded, minimum=0),
        "skipped_count": _coerce_int(result.get("skipped_count"), default=skipped, minimum=0),
        "failed_count": _coerce_int(result.get("failed_count"), default=failed, minimum=0),
        "progress": {
            "done": done,
            "total": total,
            "downloaded": downloaded,
            "skipped": skipped,
            "failed": failed,
        },
        "zip_path": zip_path,
        "local_dir": _safe_text(result.get("local_dir")),
        "download_url": download_url,
        "result": result,
    }


def serialize_request_capture_job(
    job: dict[str, Any],
    *,
    fallback_domain: str = "",
    default_concurrency: int = 1,
) -> dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    status = normalize_sync_status(job.get("status"))
    progress_raw = result.get("progress") if isinstance(result.get("progress"), dict) else {}
    total = _coerce_int(
        progress_raw.get("total"),
        default=_coerce_int(payload.get("total"), default=0, minimum=0),
        minimum=0,
    )
    done_default = total if status == "done" else 0
    done = _coerce_int(progress_raw.get("done"), default=done_default, minimum=0)
    visited_route_count = _coerce_int(
        progress_raw.get("visited_route_count"),
        default=_coerce_int(result.get("visited_route_count"), default=0, minimum=0),
        minimum=0,
    )
    failed_route_count = _coerce_int(
        progress_raw.get("failed_route_count"),
        default=_coerce_int(result.get("failed_route_count"), default=0, minimum=0),
        minimum=0,
    )
    request_total = _coerce_int(
        progress_raw.get("request_total"),
        default=_coerce_int(result.get("request_total"), default=0, minimum=0),
        minimum=0,
    )
    hash_style = normalize_hash_style(result.get("hash_style") or payload.get("hash_style"))
    basepath_override = normalize_basepath(result.get("basepath_override") or payload.get("basepath_override"))
    manual_lock = bool(_coerce_bool(result.get("manual_lock") if "manual_lock" in result else payload.get("manual_lock")))
    phase = _safe_text(progress_raw.get("phase"), "capturing")
    probe = result.get("probe") if isinstance(result.get("probe"), dict) else {}
    stop_requested = bool(result.get("stop_requested"))
    return {
        "job_id": _safe_text(job.get("job_id")),
        "step": _safe_text(job.get("step")),
        "status": status,
        "error": _safe_text(job.get("error")),
        "created_at": _safe_text(job.get("created_at")),
        "updated_at": _safe_text(job.get("updated_at")),
        "finished_at": _safe_text(job.get("finished_at")),
        "domain": _safe_text(result.get("domain") or payload.get("domain") or fallback_domain),
        "concurrency": _coerce_int(
            result.get("concurrency"),
            default=_coerce_int(payload.get("concurrency"), default=default_concurrency, minimum=1),
            minimum=1,
        ),
        "proxy_server": normalize_proxy_server(result.get("proxy_server") or payload.get("proxy_server")),
        "total": total,
        "visited_route_count": visited_route_count,
        "failed_route_count": failed_route_count,
        "request_total": request_total,
        "hash_style": hash_style,
        "basepath_override": basepath_override,
        "manual_lock": manual_lock,
        "probe": probe,
        "stop_requested": stop_requested,
        "capture_file": _safe_text(result.get("capture_file")),
        "progress": {
            "done": done,
            "total": total,
            "visited_route_count": visited_route_count,
            "failed_route_count": failed_route_count,
            "request_total": request_total,
            "phase": phase,
            "stop_requested": stop_requested,
        },
        "result": result,
    }


def describe_vue_chunk_job_phase(
    job: dict[str, Any],
    *,
    sync_step: str,
    js_download_step: str,
    request_capture_step: str,
) -> dict[str, str]:
    step = _safe_text(job.get("step"))
    status = normalize_sync_status(job.get("status"))
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    progress = result.get("progress") if isinstance(result.get("progress"), dict) else {}
    phase = _safe_text(progress.get("phase"))

    # 用统一中文名称描述自动化或抓包阶段，便于项目列表直接展示。
    phase_labels = {
        "running": "运行",
        "sync_project": "项目同步",
        "sync_completed": "项目同步完成",
        "queue_request_capture": "请求捕获排队",
        "waiting_request_capture": "等待请求捕获",
        "extracting": "批量提取",
        "locate_js": "定位 JS",
        "auto_regex": "自动正则",
        "infer_base": "基址推断",
        "auto_request": "自动请求",
        "auto_pipeline_done": "自动化完成",
        "probing": "路由探测",
        "capturing": "请求捕获",
        "downloading": "下载 JS",
        "queued": "排队",
        "completed": "已完成",
        "stopping": "停止中",
        "stopped": "已停止",
    }
    step_labels = {
        _safe_text(sync_step): "项目同步",
        _safe_text(js_download_step): "下载 JS",
        _safe_text(request_capture_step): "请求捕获",
    }

    if not phase:
        if step == _safe_text(js_download_step):
            phase = "downloading"
        elif step == _safe_text(request_capture_step):
            phase = "capturing"
        elif step == _safe_text(sync_step):
            phase = "running"

    base_text = phase_labels.get(phase) or step_labels.get(step) or ""
    if not base_text or status == "idle":
        return {"phase": phase, "phase_text": ""}

    if status == "done":
        if phase in {"sync_completed", "auto_pipeline_done", "completed"}:
            return {"phase": phase, "phase_text": base_text}
        return {"phase": phase, "phase_text": f"{base_text}已完成"}
    if status == "failed":
        return {"phase": phase, "phase_text": f"{base_text}失败"}
    if status == "stopped":
        return {"phase": phase, "phase_text": f"{base_text}已停止"}
    if status == "paused":
        return {"phase": phase, "phase_text": f"{base_text}已暂停"}
    if status == "queued":
        return {"phase": phase, "phase_text": f"{base_text}排队中"}
    if status == "running":
        if phase in {"queue_request_capture", "waiting_request_capture", "stopping"}:
            return {"phase": phase, "phase_text": base_text}
        return {"phase": phase, "phase_text": f"{base_text}中"}
    return {"phase": phase, "phase_text": base_text}


def _iter_latest_job_payloads(jobs_dir: Path, *, limit: int, step: str) -> list[dict[str, Any]]:
    try:
        rows = iter_job_payloads(limit=max(1, int(limit)), step=step)
    except Exception:
        rows = []
    if rows:
        return rows
    if not jobs_dir.is_dir():
        return []
    files = sorted(jobs_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    fallback_rows: list[dict[str, Any]] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if _safe_text(payload.get("step")) != step:
            continue
        fallback_rows.append(payload)
        if len(fallback_rows) >= max(1, int(limit)):
            break
    return fallback_rows


def collect_sync_state_map(
    *,
    jobs_dir: Path,
    module2_sync_job_step: str,
    limit: int = 600,
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for payload in _iter_latest_job_payloads(jobs_dir, limit=limit, step=module2_sync_job_step):
        job_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        result_payload = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        target_url = _safe_text(result_payload.get("target_url") or job_payload.get("target_url"))
        domain = _safe_text(
            result_payload.get("domain") or job_payload.get("domain") or domain_from_target_url(target_url)
        )
        if not domain:
            continue
        updated_at = _safe_text(payload.get("updated_at") or payload.get("created_at"))
        existing = records.get(domain)
        if existing and _safe_text(existing.get("updated_at")) >= updated_at:
            continue
        row = serialize_sync_job(payload)
        row["updated_at"] = updated_at
        records[domain] = row
    return records


def collect_js_download_state_map(
    *,
    jobs_dir: Path,
    module2_js_download_job_step: str,
    default_concurrency: int,
    limit: int = 600,
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for payload in _iter_latest_job_payloads(jobs_dir, limit=limit, step=module2_js_download_job_step):
        row = serialize_js_download_job(payload, default_concurrency=default_concurrency)
        domain = _safe_text(row.get("domain"))
        if not domain:
            continue
        updated_at = _safe_text(row.get("updated_at") or row.get("created_at"))
        existing = records.get(domain)
        if existing and _safe_text(existing.get("updated_at")) >= updated_at:
            continue
        records[domain] = row
    return records


def collect_request_capture_state_map(
    *,
    jobs_dir: Path,
    module2_request_capture_job_step: str,
    default_concurrency: int,
    limit: int = 600,
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for payload in _iter_latest_job_payloads(jobs_dir, limit=limit, step=module2_request_capture_job_step):
        row = serialize_request_capture_job(payload, default_concurrency=default_concurrency)
        domain = _safe_text(row.get("domain"))
        if not domain:
            continue
        updated_at = _safe_text(row.get("updated_at") or row.get("created_at"))
        existing = records.get(domain)
        if existing and _safe_text(existing.get("updated_at")) >= updated_at:
            continue
        records[domain] = row
    return records
