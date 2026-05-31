from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Callable


SIGNATURE_HINTS = (
    "sign",
    "token",
    "timestamp",
    "ts",
    "nonce",
    "mtgsig",
    "csec",
    "yoda",
)
PAGE_HINTS = (
    "page",
    "pageno",
    "pagesize",
    "current",
    "size",
    "limit",
    "offset",
)
AUTO_REQUEST_TIMEOUT_SECONDS = 20
AUTO_REQUEST_CONCURRENCY = 16
AUTO_REQUEST_POLL_INTERVAL_SECONDS = 0.75


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _coerce_int(raw: Any, default: int = 0, minimum: int = 0) -> int:
    text = _safe_text(raw)
    if not text:
        return max(default, minimum)
    try:
        value = int(text)
    except Exception:
        return max(default, minimum)
    return max(value, minimum)


def _normalize_method(value: Any, default: str = "GET") -> str:
    token = _safe_text(value, default).upper()
    return token or default


def _json_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        return _safe_text(value)


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    lower = _safe_text(text).lower()
    if not lower:
        return False
    return any(token in lower for token in hints)


def _score_query_row(row: dict[str, Any], preferred_request_url: str) -> int:
    query_string = _safe_text(row.get("query_string"))
    if not query_string:
        return -1
    score = 0
    if _safe_text(row.get("url")) == _safe_text(preferred_request_url):
        score += 80
    if _contains_any(query_string, SIGNATURE_HINTS):
        score += 40
    if _contains_any(query_string, PAGE_HINTS):
        score += 20
    score += min(_coerce_int(row.get("count"), default=1, minimum=1), 20)
    score += min(len(query_string), 60) // 6
    return score


def _score_json_row(row: dict[str, Any], preferred_request_url: str) -> int:
    body_json = row.get("body_json")
    if not isinstance(body_json, dict) or not body_json:
        return -1
    score = 0
    if _safe_text(row.get("url")) == _safe_text(preferred_request_url):
        score += 80
    content_type = _safe_text(row.get("content_type")).lower()
    if "application/json" in content_type:
        score += 40
    score += min(_coerce_int(row.get("count"), default=1, minimum=1), 20)
    score += min(len(body_json), 30)
    return score


def _pick_query_source(rows: list[dict[str, Any]], preferred_request_url: str) -> dict[str, Any]:
    best_row: dict[str, Any] = {}
    best_score = -1
    for row in rows:
        if not isinstance(row, dict):
            continue
        score = _score_query_row(row, preferred_request_url)
        if score > best_score:
            best_score = score
            best_row = row
    return best_row


def _pick_json_source(rows: list[dict[str, Any]], preferred_request_url: str) -> dict[str, Any]:
    best_row: dict[str, Any] = {}
    best_score = -1
    for row in rows:
        if not isinstance(row, dict):
            continue
        score = _score_json_row(row, preferred_request_url)
        if score > best_score:
            best_score = score
            best_row = row
    return best_row


def _pick_scalar(value: Any) -> Any:
    if isinstance(value, list):
        for item in value:
            text = _safe_text(item)
            if text:
                return text
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return _safe_text(value)


def _merge_param_source(target: dict[str, Any], payload: dict[str, Any]) -> None:
    for key, value in payload.items():
        name = _safe_text(key)
        if not name or name in target:
            continue
        picked = _pick_scalar(value)
        if picked == "":
            continue
        target[name] = picked


def _build_fallback_json_body(rows: list[dict[str, Any]]) -> dict[str, Any]:
    body_params: dict[str, Any] = {}
    all_params: dict[str, Any] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue
        body_json = row.get("body_json")
        if isinstance(body_json, dict):
            _merge_param_source(body_params, body_json)
            _merge_param_source(all_params, body_json)
        body_form = row.get("body_form")
        if isinstance(body_form, dict):
            _merge_param_source(all_params, body_form)
        query_params = row.get("query_params")
        if isinstance(query_params, dict):
            _merge_param_source(all_params, query_params)

    return body_params or all_params


def _normalize_headers(raw_headers: Any, *, force_json: bool = False) -> dict[str, str]:
    result: dict[str, str] = {}
    if isinstance(raw_headers, dict):
        for key, value in raw_headers.items():
            name = _safe_text(key)
            text = _safe_text(value)
            if not name or not text:
                continue
            result[name] = text

    if force_json:
        has_content_type = any(key.lower() == "content-type" for key in result)
        if not has_content_type:
            result["Content-Type"] = "application/json"
    return result


def build_auto_base_request_configs(
    *,
    captured_request_items: list[dict[str, Any]],
    preferred_request_url: str,
    baseurl: str,
    baseapi: str,
    total_rows: int,
) -> dict[str, dict[str, Any]]:
    # 自动化这里只负责尽量构造一份可跑的 GET / POST 基础请求包。
    query_source = _pick_query_source(captured_request_items, preferred_request_url)
    query_string = _safe_text(query_source.get("query_string"))
    get_headers = _normalize_headers(query_source.get("request_headers"))

    json_source = _pick_json_source(captured_request_items, preferred_request_url)
    json_body = json_source.get("body_json") if isinstance(json_source.get("body_json"), dict) else None
    if not isinstance(json_body, dict) or not json_body:
        json_body = _build_fallback_json_body(captured_request_items)
    post_headers = _normalize_headers(
        json_source.get("request_headers") or query_source.get("request_headers"),
        force_json=True,
    )

    get_request = {
        "method": "GET",
        "baseurl": _safe_text(baseurl),
        "baseapi": _safe_text(baseapi),
        "base_query": query_string,
        "headers": _json_text(get_headers) if get_headers else "",
        "body_type": "json",
        "body_text": "",
        "use_capture_template": False,
        "total": max(0, int(total_rows)),
    }
    post_request = {
        "method": "POST",
        "baseurl": _safe_text(baseurl),
        "baseapi": _safe_text(baseapi),
        "base_query": query_string,
        "headers": _json_text(post_headers) if post_headers else "",
        "body_type": "json",
        "body_text": _json_text(json_body) if json_body else "",
        "use_capture_template": False,
        "total": max(0, int(total_rows)),
    }
    return {
        "get": get_request,
        "post": post_request,
    }


def _build_request_rows(endpoints: list[dict[str, Any]], *, method: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in endpoints:
        if not isinstance(item, dict):
            continue
        endpoint_id = _coerce_int(item.get("id"), default=0, minimum=0)
        if endpoint_id <= 0:
            continue
        path = _safe_text(item.get("path") or item.get("url"))
        rows.append(
            {
                "row_key": f"endpoint:{endpoint_id}:{method}:{path}",
                "endpoint_id": endpoint_id,
                "method": method,
                "path": path,
            }
        )
    return rows


def _parse_request_headers(request_config: dict[str, Any]) -> dict[str, str] | None:
    headers_text = _safe_text(request_config.get("headers"))
    if not headers_text:
        return None
    try:
        payload = json.loads(headers_text)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return {
        str(key): str(value)
        for key, value in payload.items()
        if _safe_text(key) and _safe_text(value)
    }


def _parse_request_json_body(request_config: dict[str, Any]) -> tuple[object | None, bool]:
    body_type = _safe_text(request_config.get("body_type")).lower() or "json"
    body_text = _safe_text(request_config.get("body_text"))
    if body_type == "form" or not body_text:
        return None, False
    try:
        return json.loads(body_text), True
    except Exception:
        return None, False


def _parse_form_request_payload(request_config: dict[str, Any]) -> tuple[str, str]:
    body_type = _safe_text(request_config.get("body_type")).lower() or "json"
    if body_type != "form":
        return "", ""
    body_text = _safe_text(request_config.get("body_text"))
    if not body_text:
        return "", ""
    content_type = (
        _safe_text(request_config.get("content_type"))
        or "application/x-www-form-urlencoded; charset=utf-8"
    )
    return body_text, content_type


def _batch_job_status(raw_job: dict[str, Any]) -> str:
    return _safe_text(raw_job.get("status")).lower()


def _batch_job_result(raw_job: dict[str, Any]) -> dict[str, Any]:
    result = raw_job.get("result")
    return result if isinstance(result, dict) else {}


def _batch_job_rows(raw_job: dict[str, Any]) -> list[dict[str, Any]]:
    result = _batch_job_result(raw_job)
    row_results = result.get("row_results") if isinstance(result.get("row_results"), dict) else {}
    rows: list[dict[str, Any]] = []
    for item in row_results.values():
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "row_key": _safe_text(item.get("row_key")),
                "endpoint_id": _coerce_int(item.get("endpoint_id"), default=0, minimum=0),
                "method": _normalize_method(item.get("method")),
                "path": _safe_text(item.get("path")),
                "url": _safe_text(item.get("url")),
                "status_code": _coerce_int(item.get("status_code"), default=0, minimum=0),
                "ok": bool(item.get("ok")),
                "elapsed_ms": _coerce_int(item.get("elapsed_ms"), default=0, minimum=0),
                "error": _safe_text(item.get("error")),
                "response_path": _safe_text(item.get("response_path")),
                "requested_at": _safe_text(item.get("requested_at")),
                "response_length": _coerce_int(item.get("response_length"), default=0, minimum=0),
                "packet_length": _coerce_int(item.get("packet_length"), default=0, minimum=0),
            }
        )
    return rows


def _batch_job_summary(raw_job: dict[str, Any], *, total_fallback: int) -> dict[str, int]:
    result = _batch_job_result(raw_job)
    progress = result.get("progress") if isinstance(result.get("progress"), dict) else {}
    total = _coerce_int(
        result.get("total"),
        default=_coerce_int(progress.get("total"), default=total_fallback, minimum=0),
        minimum=0,
    ) or _coerce_int(progress.get("total"), default=total_fallback, minimum=0) or total_fallback
    done = _coerce_int(progress.get("done"), default=len(_batch_job_rows(raw_job)), minimum=0)
    ok_count = _coerce_int(progress.get("ok"), default=0, minimum=0)
    fail_count = _coerce_int(progress.get("failed"), default=max(0, done - ok_count), minimum=0)
    return {
        "total": total,
        "done": done,
        "ok": ok_count,
        "fail": fail_count,
    }


def _apply_batch_job_control(
    *,
    job_id: str,
    action: str,
    read_job: Callable[[str], dict[str, Any]],
    update_job: Callable[..., dict[str, Any]],
    append_log: Callable[[str, str], None],
) -> None:
    token = _safe_text(job_id)
    mode = _safe_text(action).lower()
    if not token or mode not in {"stop", "pause", "resume"}:
        return

    try:
        job = read_job(token)
    except Exception:
        return

    current_status = _batch_job_status(job)
    result = _batch_job_result(job)
    merged_result = dict(result)
    progress = merged_result.get("progress") if isinstance(merged_result.get("progress"), dict) else {}
    phase = _safe_text(progress.get("phase"), "running")

    if mode == "pause":
        if current_status != "running":
            return
        progress = dict(progress)
        progress["phase"] = phase
        progress["stop_requested"] = bool(merged_result.get("stop_requested"))
        merged_result["progress"] = progress
        update_job(job_id=token, status="paused", result=merged_result)
        append_log(token, "pause requested by parent auto pipeline")
        return

    if mode == "resume":
        if current_status != "paused":
            return
        progress = dict(progress)
        progress["phase"] = "running"
        progress["stop_requested"] = False
        merged_result["progress"] = progress
        merged_result["stop_requested"] = False
        update_job(job_id=token, status="running", result=merged_result)
        append_log(token, "resume requested by parent auto pipeline")
        return

    if current_status in {"completed", "done", "failed", "stopped", "cancelled", "canceled"}:
        return
    progress = dict(progress)
    progress["phase"] = "stopping" if current_status == "running" else phase or "stopped"
    progress["stop_requested"] = True
    merged_result["progress"] = progress
    merged_result["stop_requested"] = True
    if current_status in {"queued", "paused"}:
        update_job(job_id=token, status="stopped", result=merged_result)
    else:
        update_job(job_id=token, status="running", result=merged_result)
    append_log(token, "stop requested by parent auto pipeline")


def _wait_request_batch_job(
    *,
    child_job_id: str,
    parent_job_id: str,
    label: str,
    read_job: Callable[[str], dict[str, Any]],
    update_job: Callable[..., dict[str, Any]],
    append_log: Callable[[str, str], None],
    stop_check: Callable[[], bool] | None,
    pause_check: Callable[[], bool] | None,
    on_progress: Callable[[str, dict[str, int], str, str], None] | None = None,
) -> dict[str, Any]:
    last_done = -1
    last_status = ""
    child_paused = False

    while True:
        if callable(stop_check) and bool(stop_check()):
            _apply_batch_job_control(
                job_id=child_job_id,
                action="stop",
                read_job=read_job,
                update_job=update_job,
                append_log=append_log,
            )
            raise RuntimeError("__AUTO_REQUEST_STOPPED__")

        should_pause = callable(pause_check) and bool(pause_check())
        if should_pause and not child_paused:
            _apply_batch_job_control(
                job_id=child_job_id,
                action="pause",
                read_job=read_job,
                update_job=update_job,
                append_log=append_log,
            )
            child_paused = True
        elif not should_pause and child_paused:
            _apply_batch_job_control(
                job_id=child_job_id,
                action="resume",
                read_job=read_job,
                update_job=update_job,
                append_log=append_log,
            )
            child_paused = False

        try:
            raw_job = read_job(child_job_id)
        except FileNotFoundError as exc:
            raise RuntimeError(f"request batch job not found: {child_job_id}") from exc

        status = _batch_job_status(raw_job)
        summary = _batch_job_summary(raw_job, total_fallback=0)
        done = _coerce_int(summary.get("done"), default=0, minimum=0)
        total = _coerce_int(summary.get("total"), default=0, minimum=0)

        if done != last_done or status != last_status:
            append_log(parent_job_id, f"auto pipeline {label} progress {done}/{total}")
            if callable(on_progress):
                try:
                    on_progress(label, summary, status, child_job_id)
                except Exception:
                    pass
            last_done = done
            last_status = status

        if status in {"completed", "done"}:
            return raw_job
        if status in {"failed", "cancelled", "canceled"}:
            message = _safe_text(raw_job.get("error")) or f"{label} request batch failed"
            raise RuntimeError(message)
        if status == "stopped":
            raise RuntimeError("__AUTO_REQUEST_STOPPED__")

        time.sleep(AUTO_REQUEST_POLL_INTERVAL_SECONDS)


def run_auto_request_batch_snapshot(
    *,
    domain: str,
    request_config: dict[str, Any],
    endpoint_rows: list[dict[str, Any]],
    parent_job_id: str,
    label: str,
    queue_request_batch: Callable[..., dict[str, Any]],
    read_job: Callable[[str], dict[str, Any]],
    update_job: Callable[..., dict[str, Any]],
    save_request_run_snapshot: Callable[..., dict[str, object]],
    append_log: Callable[[str, str], None],
    stop_check: Callable[[], bool] | None = None,
    pause_check: Callable[[], bool] | None = None,
    concurrency: int = AUTO_REQUEST_CONCURRENCY,
    on_progress: Callable[[str, dict[str, int], str, str], None] | None = None,
) -> dict[str, Any]:
    method = _normalize_method(request_config.get("method"))
    headers_value = _parse_request_headers(request_config)
    json_body_value, json_body_provided = _parse_request_json_body(request_config)
    body_text, content_type = _parse_form_request_payload(request_config)

    append_log(parent_job_id, f"auto pipeline {label} request run start: total={len(endpoint_rows)}")
    job = queue_request_batch(
        domain=domain,
        request_rows=endpoint_rows,
        method=method,
        baseurl=_safe_text(request_config.get("baseurl")),
        baseapi=_safe_text(request_config.get("baseapi")),
        base_query=_safe_text(request_config.get("base_query")),
        timeout=AUTO_REQUEST_TIMEOUT_SECONDS,
        headers=headers_value,
        json_body=json_body_value,
        json_body_provided=json_body_provided,
        body_text=body_text,
        content_type=content_type,
        use_capture_template=False,
        concurrency=max(1, _coerce_int(concurrency, default=AUTO_REQUEST_CONCURRENCY, minimum=1)),
    )
    child_job_id = _safe_text(job.get("job_id"))
    if not child_job_id:
        raise RuntimeError(f"{label} request batch queue failed: empty job id")

    raw_job = _wait_request_batch_job(
        child_job_id=child_job_id,
        parent_job_id=parent_job_id,
        label=label,
        read_job=read_job,
        update_job=update_job,
        append_log=append_log,
        stop_check=stop_check,
        pause_check=pause_check,
        on_progress=on_progress,
    )
    rows = _batch_job_rows(raw_job)
    summary = _batch_job_summary(raw_job, total_fallback=len(endpoint_rows))
    snapshot = save_request_run_snapshot(
        domain=domain,
        job_id=child_job_id,
        status=_batch_job_status(raw_job),
        request=request_config,
        rows=rows,
    )
    append_log(
        parent_job_id,
        f"auto pipeline {label} request run completed: ok={summary.get('ok', 0)} fail={summary.get('fail', 0)}",
    )
    return {
        "job_id": child_job_id,
        "snapshot": snapshot,
        "summary": summary,
        "rows": rows,
    }


def run_auto_request_pipeline(
    *,
    domain: str,
    preferred_request_url: str,
    baseurl: str,
    baseapi: str,
    endpoints: list[dict[str, Any]],
    load_captured_request_items: Callable[[str], list[dict[str, Any]]],
    parent_job_id: str,
    queue_request_batch: Callable[..., dict[str, Any]],
    read_job: Callable[[str], dict[str, Any]],
    update_job: Callable[..., dict[str, Any]],
    save_request_run_snapshot: Callable[..., dict[str, object]],
    append_log: Callable[[str, str], None],
    stop_check: Callable[[], bool] | None = None,
    pause_check: Callable[[], bool] | None = None,
    concurrency: int = AUTO_REQUEST_CONCURRENCY,
    on_progress: Callable[[str, dict[str, int], str, str], None] | None = None,
) -> dict[str, Any]:
    rows_total = len(endpoints)
    captured_request_items = load_captured_request_items(domain)
    request_configs = build_auto_base_request_configs(
        captured_request_items=captured_request_items,
        preferred_request_url=preferred_request_url,
        baseurl=baseurl,
        baseapi=baseapi,
        total_rows=rows_total,
    )
    get_rows = _build_request_rows(endpoints, method="GET")
    post_rows = _build_request_rows(endpoints, method="POST")
    if not get_rows:
        raise ValueError("endpoint rows are empty")

    get_result = run_auto_request_batch_snapshot(
        domain=domain,
        request_config=request_configs["get"],
        endpoint_rows=get_rows,
        parent_job_id=parent_job_id,
        label="GET",
        queue_request_batch=queue_request_batch,
        read_job=read_job,
        update_job=update_job,
        save_request_run_snapshot=save_request_run_snapshot,
        append_log=append_log,
        stop_check=stop_check,
        pause_check=pause_check,
        concurrency=concurrency,
        on_progress=on_progress,
    )
    post_result = run_auto_request_batch_snapshot(
        domain=domain,
        request_config=request_configs["post"],
        endpoint_rows=post_rows,
        parent_job_id=parent_job_id,
        label="POST",
        queue_request_batch=queue_request_batch,
        read_job=read_job,
        update_job=update_job,
        save_request_run_snapshot=save_request_run_snapshot,
        append_log=append_log,
        stop_check=stop_check,
        pause_check=pause_check,
        concurrency=concurrency,
        on_progress=on_progress,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "endpoint_total": rows_total,
        "selected_endpoint_total": len(get_rows),
        "get_request": request_configs["get"],
        "post_request": request_configs["post"],
        "get_job_id": _safe_text(get_result.get("job_id")),
        "post_job_id": _safe_text(post_result.get("job_id")),
        "get_snapshot": get_result.get("snapshot"),
        "post_snapshot": post_result.get("snapshot"),
        "get_summary": get_result.get("summary"),
        "post_summary": post_result.get("summary"),
    }


__all__ = [
    "build_auto_base_request_configs",
    "run_auto_request_pipeline",
]
