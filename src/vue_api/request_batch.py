from __future__ import annotations

import json
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _coerce_int(raw: object, default: int, minimum: int = 0) -> int:
    text = _safe_text(raw)
    if not text:
        return max(default, minimum)
    try:
        value = int(text)
    except (TypeError, ValueError):
        return max(default, minimum)
    return max(value, minimum)


def _normalize_method(value: object, default: str = "GET") -> str:
    token = _safe_text(value, default).upper()
    return token or default


def _utf8_length(value: object) -> int:
    return len(_safe_text(value).encode("utf-8"))


def _response_lengths(detail: dict[str, object]) -> tuple[int, int]:
    body_text = _safe_text(detail.get("response_text"))
    header_text = json.dumps(
        detail.get("response_headers") if isinstance(detail.get("response_headers"), dict) else {},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    body_length = _utf8_length(body_text)
    packet_length = body_length + len(header_text.encode("utf-8"))
    return body_length, packet_length


def _normalize_request_rows(raw_rows: list[object]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    seen_keys: set[str] = set()

    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        endpoint_id = _coerce_int(item.get("endpoint_id") or item.get("api_id"), default=0, minimum=0)
        if endpoint_id <= 0:
            continue
        path = _safe_text(item.get("path") or item.get("url"))
        row_key = _safe_text(item.get("row_key"))
        if not row_key:
            row_key = f"endpoint:{endpoint_id}:{_normalize_method(item.get('method'))}:{path}"
        if row_key in seen_keys:
            continue
        seen_keys.add(row_key)
        normalized.append(
            {
                "row_key": row_key,
                "endpoint_id": endpoint_id,
                "method": _normalize_method(item.get("method")),
                "path": path,
            }
        )
    return normalized


def _job_logs(raw_job: dict[str, Any], *, log_limit: int = 12) -> list[dict[str, str]]:
    logs = raw_job.get("logs") if isinstance(raw_job.get("logs"), list) else []
    rows: list[dict[str, str]] = []
    for item in logs[-max(1, int(log_limit)) :]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "time": _safe_text(item.get("time")),
                "message": _safe_text(item.get("message")),
            }
        )
    return rows


def serialize_request_batch_job(
    raw_job: dict[str, Any],
    *,
    default_concurrency: int = 16,
    log_limit: int = 12,
) -> dict[str, Any]:
    # 统一把后端 job 转成前端可直接轮询消费的结构。
    result = raw_job.get("result") if isinstance(raw_job.get("result"), dict) else {}
    payload = raw_job.get("payload") if isinstance(raw_job.get("payload"), dict) else {}
    progress = result.get("progress") if isinstance(result.get("progress"), dict) else {}
    row_results_raw = result.get("row_results") if isinstance(result.get("row_results"), dict) else {}

    row_results: dict[str, dict[str, Any]] = {}
    for row_key, payload in row_results_raw.items():
        if not isinstance(payload, dict):
            continue
        token = _safe_text(row_key)
        if not token:
            continue
        row_results[token] = {
            "row_key": token,
            "endpoint_id": _coerce_int(payload.get("endpoint_id"), default=0, minimum=0),
            "method": _normalize_method(payload.get("method")),
            "path": _safe_text(payload.get("path")),
            "url": _safe_text(payload.get("url")),
            "status_code": _coerce_int(payload.get("status_code"), default=0, minimum=0),
            "ok": bool(payload.get("ok")),
            "elapsed_ms": _coerce_int(payload.get("elapsed_ms"), default=0, minimum=0),
            "error": _safe_text(payload.get("error")),
            "response_path": _safe_text(payload.get("response_path")),
            "requested_at": _safe_text(payload.get("requested_at")),
            "response_length": _coerce_int(payload.get("response_length"), default=0, minimum=0),
            "packet_length": _coerce_int(payload.get("packet_length"), default=0, minimum=0),
            "template_replay": payload.get("template_replay") if isinstance(payload.get("template_replay"), dict) else {},
        }

    total = _coerce_int(result.get("total"), default=len(row_results), minimum=0)
    done = _coerce_int(progress.get("done"), default=len(row_results), minimum=0)
    ok_count = _coerce_int(progress.get("ok"), default=0, minimum=0)
    fail_count = _coerce_int(progress.get("failed"), default=0, minimum=0)

    return {
        "job_id": _safe_text(raw_job.get("job_id")),
        "step": _safe_text(raw_job.get("step")),
        "status": _safe_text(raw_job.get("status")),
        "error": _safe_text(raw_job.get("error")),
        "created_at": _safe_text(raw_job.get("created_at")),
        "updated_at": _safe_text(raw_job.get("updated_at")),
        "finished_at": _safe_text(raw_job.get("finished_at")),
        "domain": _safe_text(result.get("domain") or payload.get("domain")),
        "method": _normalize_method(result.get("method")),
        "baseurl": _safe_text(result.get("baseurl")),
        "baseapi": _safe_text(result.get("baseapi")),
        "base_query": _safe_text(result.get("base_query")),
        "timeout": _coerce_int(result.get("timeout"), default=20, minimum=1),
        "concurrency": _coerce_int(result.get("concurrency"), default=default_concurrency, minimum=1),
        "use_capture_template": bool(result.get("use_capture_template")),
        "total": total,
        "done_count": done,
        "ok_count": ok_count,
        "fail_count": fail_count,
        "current_row_key": _safe_text(result.get("current_row_key")),
        "current_path": _safe_text(result.get("current_path")),
        "row_results": row_results,
        "row_result_total": len(row_results),
        "progress": {
            "done": done,
            "total": total,
            "ok": ok_count,
            "failed": fail_count,
            "phase": _safe_text(progress.get("phase"), "running"),
            "stop_requested": bool(progress.get("stop_requested") or result.get("stop_requested")),
        },
        "logs": _job_logs(raw_job, log_limit=log_limit),
        "log_count": len(raw_job.get("logs")) if isinstance(raw_job.get("logs"), list) else 0,
        "result": result,
    }


def queue_request_batch(
    *,
    domain: str,
    request_rows: list[object],
    method: str,
    baseurl: str,
    baseapi: str,
    base_query: str,
    timeout: int,
    headers: dict[str, str] | None,
    json_body: object | None,
    json_body_provided: bool,
    body_text: str,
    content_type: str,
    use_capture_template: bool,
    concurrency: int,
    job_step: str,
    create_job: Callable[..., dict[str, Any]],
    append_log: Callable[[str, str], None],
    update_job: Callable[..., dict[str, Any]],
    spawn_background: Callable[..., None],
    run_background: Callable[..., Any],
) -> dict[str, Any]:
    normalized_rows = _normalize_request_rows(request_rows)
    if not normalized_rows:
        raise ValueError("request rows are empty")

    worker_count = max(1, min(_coerce_int(concurrency, default=16, minimum=1), len(normalized_rows)))
    method_token = _normalize_method(method)
    domain_token = _safe_text(domain)
    if not domain_token:
        raise ValueError("domain is required")

    payload = {
        "domain": domain_token,
        "method": method_token,
        "baseurl": _safe_text(baseurl),
        "baseapi": _safe_text(baseapi),
        "base_query": _safe_text(base_query),
        "timeout": _coerce_int(timeout, default=20, minimum=1),
        "concurrency": worker_count,
        "total": len(normalized_rows),
        "use_capture_template": bool(use_capture_template),
    }
    job = create_job(step=job_step, payload=payload)
    job_id = _safe_text(job.get("job_id"))
    if not job_id:
        raise ValueError("failed to create vue request batch job")

    append_log(job_id, f"web action queued: {job_step}")
    job = update_job(
        job_id=job_id,
        status="queued",
        result={
            **payload,
            "json_body_provided": bool(json_body_provided),
            "stop_requested": False,
            "current_row_key": "",
            "current_path": "",
            "row_results": {},
            "progress": {
                "done": 0,
                "total": len(normalized_rows),
                "ok": 0,
                "failed": 0,
                "phase": "queued",
                "stop_requested": False,
            },
        },
    )

    spawn_background(
        run_background,
        job_id=job_id,
        domain=domain_token,
        request_rows=normalized_rows,
        method=method_token,
        baseurl=_safe_text(baseurl),
        baseapi=_safe_text(baseapi),
        base_query=_safe_text(base_query),
        timeout=_coerce_int(timeout, default=20, minimum=1),
        headers=dict(headers) if isinstance(headers, dict) else None,
        json_body=json_body,
        json_body_provided=bool(json_body_provided),
        body_text=_safe_text(body_text),
        content_type=_safe_text(content_type),
        use_capture_template=bool(use_capture_template),
        concurrency=worker_count,
    )
    return job


def run_request_batch_background(
    *,
    job_id: str,
    domain: str,
    request_rows: list[dict[str, object]],
    method: str,
    baseurl: str,
    baseapi: str,
    base_query: str,
    timeout: int,
    headers: dict[str, str] | None,
    json_body: object | None,
    json_body_provided: bool,
    body_text: str,
    content_type: str,
    use_capture_template: bool,
    concurrency: int,
    job_step: str,
    load_api_endpoints: Callable[[str], list[Any]],
    find_api_endpoint_by_id: Callable[[list[Any], int], Any | None],
    prepare_template_replay_request: Callable[..., dict[str, object]],
    run_api_request: Callable[..., dict[str, Any]],
    load_saved_response_detail: Callable[[object], dict[str, object]],
    build_template_replay_summary: Callable[..., dict[str, object]],
    append_log: Callable[[str, str], None],
    update_job: Callable[..., dict[str, Any]],
    job_stop_requested: Callable[[str], bool],
    job_pause_requested: Callable[[str], bool],
) -> None:
    # 后端线程里真正跑批量请求，页面离开后任务仍继续。
    job_token = _safe_text(job_id)
    if not job_token:
        return

    domain_token = _safe_text(domain)
    if not domain_token:
        update_job(job_id=job_token, status="failed", error="domain is required")
        return

    normalized_rows = _normalize_request_rows(request_rows)
    if not normalized_rows:
        update_job(job_id=job_token, status="failed", error="request rows are empty")
        return

    append_log(job_token, f"web action start: {job_step}")
    worker_count = max(1, min(_coerce_int(concurrency, default=16, minimum=1), len(normalized_rows)))
    timeout_value = _coerce_int(timeout, default=20, minimum=1)
    method_token = _normalize_method(method)

    state_lock = threading.Lock()
    cursor = 0
    total = len(normalized_rows)
    report_span = max(1, total // 12)
    last_progress_logged = 0
    pause_announced = False

    state: dict[str, Any] = {
        "domain": domain_token,
        "method": method_token,
        "baseurl": _safe_text(baseurl),
        "baseapi": _safe_text(baseapi),
        "base_query": _safe_text(base_query),
        "timeout": timeout_value,
        "concurrency": worker_count,
        "use_capture_template": bool(use_capture_template),
        "json_body_provided": bool(json_body_provided),
        "body_text": _safe_text(body_text),
        "content_type": _safe_text(content_type),
        "stop_requested": False,
        "current_row_key": "",
        "current_path": "",
        "row_results": {},
        "progress": {
            "done": 0,
            "total": total,
            "ok": 0,
            "failed": 0,
            "phase": "running",
            "stop_requested": False,
        },
    }

    def _snapshot() -> dict[str, Any]:
        progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
        row_results = state.get("row_results") if isinstance(state.get("row_results"), dict) else {}
        return {
            **state,
            "progress": dict(progress),
            "row_results": {str(key): dict(value) for key, value in row_results.items() if isinstance(value, dict)},
        }

    def _sync_job_state(status: str) -> None:
        update_job(job_id=job_token, status=status, result=_snapshot())

    def _announce_progress(row_result: dict[str, Any]) -> None:
        nonlocal last_progress_logged
        progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
        done = _coerce_int(progress.get("done"), default=0, minimum=0)
        failed = not bool(row_result.get("ok"))
        if done == 1 or done == total or done - last_progress_logged >= report_span or failed:
            last_progress_logged = done
            summary = (
                f"request batch progress {done}/{total}: "
                f"{_normalize_method(row_result.get('method'))} {_safe_text(row_result.get('path'))}"
            )
            if failed:
                summary = f"{summary} | failed: {_safe_text(row_result.get('error')) or 'request failed'}"
            append_log(job_token, summary)

    def _wait_if_paused() -> bool:
        nonlocal pause_announced
        while job_pause_requested(job_token):
            if not pause_announced:
                pause_announced = True
                with state_lock:
                    progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
                    progress["phase"] = "paused"
                    progress["stop_requested"] = bool(job_stop_requested(job_token))
                    state["progress"] = progress
                    _sync_job_state("paused")
                append_log(job_token, "request batch paused")
            if job_stop_requested(job_token):
                return False
            time.sleep(0.25)
        if pause_announced:
            pause_announced = False
            with state_lock:
                progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
                progress["phase"] = "running"
                progress["stop_requested"] = bool(job_stop_requested(job_token))
                state["progress"] = progress
                _sync_job_state("running")
            append_log(job_token, "request batch resumed")
        return not job_stop_requested(job_token)

    def _build_row_result(row: dict[str, object]) -> dict[str, Any]:
        endpoint_id = _coerce_int(row.get("endpoint_id"), default=0, minimum=0)
        endpoint = find_api_endpoint_by_id(endpoints, endpoint_id)
        if endpoint is None:
            return {
                "row_key": _safe_text(row.get("row_key")),
                "endpoint_id": endpoint_id,
                "method": method_token,
                "path": _safe_text(row.get("path")),
                "url": "",
                "status_code": 0,
                "ok": False,
                "elapsed_ms": 0,
                "error": f"api id not found: {endpoint_id}",
                "response_path": "",
                "requested_at": "",
                "response_length": 0,
                "packet_length": 0,
                "template_replay": {},
            }

        endpoint_path = _safe_text(row.get("path") or getattr(endpoint, "path", "") or getattr(endpoint, "url", ""))
        endpoint_method = _normalize_method(
            method_token or row.get("method") or getattr(endpoint, "method", "GET"),
        )

        template_runtime = prepare_template_replay_request(
            domain=domain_token,
            endpoint_path=endpoint_path,
            endpoint_method=endpoint_method,
            baseurl=_safe_text(baseurl),
            baseapi=_safe_text(baseapi),
            use_capture_template=bool(use_capture_template),
            headers=dict(headers) if isinstance(headers, dict) else None,
            json_body=json_body,
            json_body_provided=bool(json_body_provided),
        )
        template_replay = (
            template_runtime.get("template_replay")
            if isinstance(template_runtime.get("template_replay"), dict)
            else {}
        )
        request_headers = template_runtime.get("headers") if isinstance(template_runtime.get("headers"), dict) else None
        request_json_body = template_runtime.get("json_body")
        request_url_override = _safe_text(template_runtime.get("request_url_override"))
        request_body_text = _safe_text(body_text) or _safe_text(template_runtime.get("body_text"))
        request_content_type = _safe_text(content_type) or _safe_text(template_runtime.get("content_type"))
        used_template_url = bool(template_runtime.get("used_template_url"))
        used_template_headers = bool(template_runtime.get("used_template_headers"))
        used_template_body = bool(template_runtime.get("used_template_body"))

        request_result = run_api_request(
            domain=domain_token,
            api_id=endpoint_id,
            method=endpoint_method,
            baseurl=_safe_text(baseurl),
            baseapi=_safe_text(baseapi),
            base_query=_safe_text(base_query),
            json_body=request_json_body,
            headers=request_headers,
            timeout=timeout_value,
            request_url_override=request_url_override or None,
            body_text=request_body_text or None,
            content_type=request_content_type or None,
        )
        detail = load_saved_response_detail(request_result.get("response_path"))
        response_length, packet_length = _response_lengths(detail)

        return {
            "row_key": _safe_text(row.get("row_key")),
            "endpoint_id": endpoint_id,
            "method": _normalize_method(request_result.get("method"), endpoint_method),
            "path": endpoint_path,
            "url": _safe_text(request_result.get("url")),
            "status_code": _coerce_int(request_result.get("status_code"), default=0, minimum=0),
            "ok": bool(request_result.get("ok")),
            "elapsed_ms": _coerce_int(request_result.get("elapsed_ms"), default=0, minimum=0),
            "error": _safe_text(request_result.get("error")),
            "response_path": _safe_text(request_result.get("response_path")),
            "requested_at": _safe_text(detail.get("requested_at")),
            "response_length": response_length,
            "packet_length": packet_length,
            "template_replay": build_template_replay_summary(
                use_capture_template=bool(use_capture_template),
                template_replay=template_replay,
                used_template_url=used_template_url,
                used_template_headers=used_template_headers,
                used_template_body=used_template_body,
            ),
        }

    def _worker() -> None:
        nonlocal cursor
        while True:
            if not _wait_if_paused():
                return

            with state_lock:
                if job_stop_requested(job_token):
                    return
                index = cursor
                cursor += 1
                if index >= total:
                    return
                row = normalized_rows[index]
                state["current_row_key"] = _safe_text(row.get("row_key"))
                state["current_path"] = _safe_text(row.get("path"))
                progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
                progress["phase"] = "running"
                progress["stop_requested"] = False
                state["progress"] = progress
                _sync_job_state("running")

            row_result = _build_row_result(row)

            with state_lock:
                row_key = _safe_text(row_result.get("row_key"))
                row_results = state.get("row_results") if isinstance(state.get("row_results"), dict) else {}
                row_results[row_key] = row_result
                state["row_results"] = row_results
                progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
                progress["done"] = _coerce_int(progress.get("done"), default=0, minimum=0) + 1
                if bool(row_result.get("ok")):
                    progress["ok"] = _coerce_int(progress.get("ok"), default=0, minimum=0) + 1
                else:
                    progress["failed"] = _coerce_int(progress.get("failed"), default=0, minimum=0) + 1
                progress["phase"] = "running"
                progress["stop_requested"] = bool(job_stop_requested(job_token))
                state["progress"] = progress
                state["current_row_key"] = ""
                state["current_path"] = ""
                _sync_job_state("running")
                _announce_progress(row_result)

    try:
        endpoints = load_api_endpoints(domain_token)
        if not endpoints:
            raise ValueError(f"api endpoint list is empty: {domain_token}")

        with state_lock:
            _sync_job_state("running")

        futures: list[Future[None]] = []
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            for _ in range(worker_count):
                futures.append(executor.submit(_worker))
            for future in futures:
                future.result()

        stopped = bool(job_stop_requested(job_token))
        with state_lock:
            progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
            progress["stop_requested"] = stopped
            progress["phase"] = "stopped" if stopped else "completed"
            state["progress"] = progress
            state["stop_requested"] = stopped
            state["current_row_key"] = ""
            state["current_path"] = ""
            if stopped:
                append_log(job_token, "request batch stopped")
                _sync_job_state("stopped")
            else:
                append_log(job_token, "request batch completed")
                _sync_job_state("completed")
    except Exception as exc:
        message = str(exc)
        with state_lock:
            progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
            progress["phase"] = "failed"
            progress["stop_requested"] = bool(job_stop_requested(job_token))
            state["progress"] = progress
            state["stop_requested"] = bool(job_stop_requested(job_token))
            state["current_row_key"] = ""
            state["current_path"] = ""
        append_log(job_token, f"request batch failed: {message}")
        update_job(job_id=job_token, status="failed", result=_snapshot(), error=message)
