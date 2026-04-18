from __future__ import annotations

import asyncio
from pathlib import Path
import time
from typing import Any, Callable

from src.services import run_route_hash_style_probe, run_route_request_capture
from src.vue_chunk.request_capture import normalize_basepath, normalize_hash_style, rewrite_route_urls
from src.vue_chunk.route_profile import save_route_url_profile


def _merge_recent_texts(existing: list[str], incoming: list[Any], *, limit: int = 3) -> list[str]:
    # 后台任务只保留少量最近活动项，既能给前端看进度，也避免结果文件无限膨胀。
    rows = [str(item).strip() for item in existing if str(item).strip()]
    for item in incoming:
        text = str(item).strip()
        if not text:
            continue
        rows = [row for row in rows if row != text]
        rows.append(text)
    return rows[-max(1, int(limit)) :]


def run_module2_project_sync_background(
    *,
    job_id: str,
    target_url: str,
    concurrency: int,
    proxy_server: str,
    detect_routes: bool,
    detect_js: bool,
    detect_request: bool,
    auto_scan_pattern: str,
    auto_pipeline: bool,
    append_log: Callable[[str, str], None],
    update_job: Callable[..., dict[str, Any]],
    run_project_sync: Callable[..., Any],
    normalize_proxy_server: Callable[[Any], str],
    safe_str: Callable[[Any, str], str],
    to_int: Callable[[Any, int, int], int],
    domain_from_target_url: Callable[[str], str],
    job_stop_requested: Callable[[str], bool],
    job_pause_requested: Callable[[str], bool],
    sync_control_progress: Callable[..., dict[str, Any]],
    request_capture_job_control: Callable[[str, str], None],
    queue_request_capture: Callable[..., dict[str, Any]],
    read_job: Callable[[str], dict[str, Any]],
    normalize_sync_status: Callable[[Any], str],
    serialize_request_capture_job: Callable[..., dict[str, Any]],
    module2_request_default_concurrency: int,
    select_auto_pipeline_js_api_path: Callable[..., dict[str, Any]],
    run_vue_api_auto_regex: Callable[..., dict[str, Any]],
    run_auto_request_pipeline: Callable[..., dict[str, Any]],
    resolve_scan_pattern: Callable[[str], str],
    save_vue_api_config: Callable[[str, str], None],
    run_api_extract: Callable[..., Any],
    load_api_endpoints: Callable[[str], list[Any]],
    normalize_endpoint_rows_for_infer: Callable[[Any], list[dict[str, Any]]],
    serialize_api_endpoint: Callable[[Any], dict[str, Any]],
    infer_request_base_from_endpoint_rows: Callable[[str, Any], dict[str, Any]],
    sync_vue_api_source_form: Callable[..., None],
    sync_vue_api_request_state: Callable[..., None],
    persist_project_request_config: Callable[..., Any],
    module2_sync_job_step: str,
) -> None:
    # 项目同步是整条自动流水线的后台编排入口，这里统一处理同步、抓包、提取和推断。
    append_log(job_id, f"web action start: {module2_sync_job_step}")
    scan_pattern = safe_str(auto_scan_pattern)
    auto_pipeline_enabled = bool(auto_pipeline)
    auto_scan_enabled = bool(scan_pattern) or auto_pipeline_enabled
    result: dict[str, Any] = {}
    capture_job_id = ""

    def _mark_stopped(phase: str, *, reason: str = "") -> None:
        nonlocal capture_job_id
        if capture_job_id:
            request_capture_job_control(capture_job_id, "stop")
        result["stop_requested"] = True
        result["progress"] = sync_control_progress(result, phase="stopped", stop_requested=True)
        if reason:
            result["stopped_reason"] = reason
        append_log(job_id, f"web action stopped: {phase}")
        update_job(job_id=job_id, status="stopped", result=result)

    def _update_phase(phase: str, *, prefer_status: str = "") -> None:
        status = safe_str(prefer_status).lower()
        if status not in {"running", "paused"}:
            status = "paused" if job_pause_requested(job_id) else "running"
        stop_requested = bool(job_stop_requested(job_id))
        result["stop_requested"] = stop_requested
        result["progress"] = sync_control_progress(result, phase=phase, stop_requested=stop_requested)
        update_job(job_id=job_id, status=status, result=result)

    def _checkpoint(phase: str) -> None:
        nonlocal capture_job_id
        if job_stop_requested(job_id):
            raise RuntimeError("__MODULE2_SYNC_STOPPED__")
        paused = False
        while job_pause_requested(job_id):
            paused = True
            _update_phase(phase, prefer_status="paused")
            if capture_job_id:
                request_capture_job_control(capture_job_id, "pause")
            if job_stop_requested(job_id):
                raise RuntimeError("__MODULE2_SYNC_STOPPED__")
            time.sleep(0.4)
        if paused:
            if capture_job_id:
                request_capture_job_control(capture_job_id, "resume")
            append_log(job_id, f"web action resumed: {phase}")
            _update_phase(phase, prefer_status="running")

    try:
        domain = domain_from_target_url(target_url)
        normalized_proxy_server = normalize_proxy_server(proxy_server)
        result = {
            "domain": domain,
            "target_url": target_url,
            "concurrency": max(1, int(concurrency)),
            "proxy_server": normalized_proxy_server,
            "detect_routes": bool(detect_routes),
            "detect_js": bool(detect_js),
            "detect_request": bool(detect_request),
            "auto_scan": auto_scan_enabled,
            "auto_pipeline": auto_pipeline_enabled,
            "stop_requested": False,
            "progress": {"phase": "running", "stop_requested": False},
        }
        update_job(job_id=job_id, status="running", result=result)

        _checkpoint("sync_project")
        sync_result = asyncio.run(
            run_project_sync(
                target_url=target_url,
                concurrency=concurrency,
                detect_routes=detect_routes,
                detect_js=detect_js,
                detect_request=detect_request,
                proxy_server=normalized_proxy_server,
                stop_check=lambda: job_stop_requested(job_id),
                pause_check=lambda: job_pause_requested(job_id),
            )
        )
        if isinstance(sync_result, dict):
            result.update(sync_result)
        else:
            result["sync_result"] = sync_result
        result["detect_request"] = bool(detect_request)
        result["auto_scan"] = auto_scan_enabled
        result["auto_pipeline"] = auto_pipeline_enabled
        result["proxy_server"] = normalized_proxy_server
        _update_phase("sync_completed")

        if detect_request:
            _checkpoint("queue_request_capture")
            capture_domain = safe_str(result.get("domain")) or domain_from_target_url(target_url)
            capture_error = ""
            try:
                capture_job = queue_request_capture(
                    domain=capture_domain,
                    concurrency=max(1, int(concurrency)),
                    proxy_server=normalized_proxy_server,
                )
                capture_job_id = safe_str(capture_job.get("job_id"))
            except Exception as capture_exc:
                capture_error = str(capture_exc)
                append_log(job_id, f"request capture queue failed: {capture_error}")

            if capture_job_id:
                result["request_capture_job_id"] = capture_job_id
                append_log(job_id, f"request capture queued: {capture_job_id}")
            if capture_error:
                result["request_capture_error"] = capture_error

            # 自动扫描模式需要等待抓包结束，再做接口提取和 base 推断。
            if auto_scan_enabled:
                _checkpoint("waiting_request_capture")
                if capture_error:
                    raise RuntimeError(f"request capture queue failed: {capture_error}")
                if not capture_job_id:
                    raise RuntimeError("request capture queue failed: empty job id")

                _update_phase("waiting_request_capture")
                append_log(job_id, f"auto scan waiting request capture: {capture_job_id}")

                wait_started_at = time.time()
                timeout_seconds = 7200
                capture_status = ""
                capture_payload: dict[str, Any] = {}
                while True:
                    _checkpoint("waiting_request_capture")
                    try:
                        capture_payload = read_job(capture_job_id)
                    except FileNotFoundError as capture_not_found:
                        raise RuntimeError(f"request capture job not found: {capture_job_id}") from capture_not_found

                    capture_status = normalize_sync_status(capture_payload.get("status"))
                    if capture_status in {"done", "failed", "stopped"}:
                        break

                    elapsed = time.time() - wait_started_at
                    if elapsed >= timeout_seconds:
                        raise TimeoutError(f"request capture timeout: {capture_job_id} ({int(elapsed)}s)")
                    time.sleep(1.0)

                capture_row = serialize_request_capture_job(
                    capture_payload,
                    fallback_domain=capture_domain,
                    default_concurrency=module2_request_default_concurrency,
                )
                result["request_capture_status"] = capture_status
                result["request_capture"] = {
                    "job_id": safe_str(capture_row.get("job_id")),
                    "status": safe_str(capture_row.get("status")),
                    "error": safe_str(capture_row.get("error")),
                    "visited_route_count": to_int(capture_row.get("visited_route_count"), default=0, minimum=0),
                    "failed_route_count": to_int(capture_row.get("failed_route_count"), default=0, minimum=0),
                    "request_total": to_int(capture_row.get("request_total"), default=0, minimum=0),
                }
                if capture_status != "done":
                    capture_message = safe_str(capture_row.get("error")) or f"request capture {capture_status}"
                    raise RuntimeError(capture_message)

                append_log(job_id, "auto scan api extract start")
                _checkpoint("extracting")
                _update_phase("extracting")
                selected_pattern = scan_pattern
                selected_js_api_path = ""

                if auto_pipeline_enabled:
                    append_log(job_id, "auto pipeline locate js start")
                    _checkpoint("locate_js")
                    _update_phase("locate_js")
                    selected_target = select_auto_pipeline_js_api_path(domain=capture_domain)
                    result["auto_pipeline_target"] = {
                        "selected": bool(selected_target.get("selected")),
                        "request_url": safe_str(selected_target.get("request_url")),
                        "method": safe_str(selected_target.get("method")),
                        "route_url": safe_str(selected_target.get("route_url")),
                        "keyword": safe_str(selected_target.get("keyword")),
                        "js_api_path": safe_str(selected_target.get("js_api_path")),
                        "matched_path": safe_str(selected_target.get("matched_path")),
                        "file_name": safe_str(selected_target.get("file_name")),
                        "line": to_int(selected_target.get("line"), default=0, minimum=0),
                        "chunk_url": safe_str(selected_target.get("chunk_url")),
                        "hit_total": to_int(selected_target.get("hit_total"), default=0, minimum=0),
                        "scanned_api_count": to_int(
                            selected_target.get("scanned_api_count"),
                            default=0,
                            minimum=0,
                        ),
                        "error": safe_str(selected_target.get("error")),
                    }
                    _update_phase("locate_js")
                    selected_js_api_path = safe_str(selected_target.get("js_api_path"))
                    if not selected_js_api_path:
                        raise RuntimeError(
                            safe_str(selected_target.get("error"))
                            or "auto pipeline locate js candidate not found"
                        )
                    append_log(
                        job_id,
                        "auto pipeline locate js matched: "
                        f"{safe_str(selected_target.get('keyword'))} "
                        f"{safe_str(selected_target.get('request_url'))}",
                    )

                    append_log(job_id, "auto pipeline regex infer start")
                    _checkpoint("auto_regex")
                    _update_phase("auto_regex")
                    try:
                        auto_regex_result = run_vue_api_auto_regex(
                            domain=capture_domain,
                            js_api_path=selected_js_api_path,
                            target_api="",
                            js_file="",
                            max_candidates=3,
                        )
                    except Exception as auto_regex_exc:
                        auto_regex_result = {
                            "domain": capture_domain,
                            "candidate_count": 0,
                            "selected_pattern": "",
                            "error": str(auto_regex_exc),
                        }
                    result["auto_regex"] = {
                        "candidate_count": to_int(auto_regex_result.get("candidate_count"), default=0, minimum=0),
                        "selected_pattern": safe_str(auto_regex_result.get("selected_pattern")),
                        "error": safe_str(auto_regex_result.get("error")),
                    }
                    selected_pattern = safe_str(auto_regex_result.get("selected_pattern")) or selected_pattern
                    _update_phase("auto_regex")

                if not selected_pattern:
                    selected_pattern = resolve_scan_pattern("")
                if not selected_pattern:
                    raise RuntimeError("auto extract pattern is empty")

                _checkpoint("extracting")
                save_vue_api_config(capture_domain, selected_pattern)
                extract_result = run_api_extract(
                    domain=capture_domain,
                    pattern=selected_pattern,
                    baseurl="",
                    baseapi="",
                )
                result["extract_result"] = (
                    extract_result if isinstance(extract_result, dict) else {"data": extract_result}
                )
                result["extract_pattern"] = selected_pattern
                _update_phase("extracting")

                endpoints = load_api_endpoints(capture_domain)
                serialized_endpoints = [serialize_api_endpoint(item) for item in endpoints]
                endpoint_rows = normalize_endpoint_rows_for_infer(serialized_endpoints)
                if not endpoint_rows:
                    infer_result: dict[str, Any] = {
                        "domain": capture_domain,
                        "inferred": False,
                        "baseurl": "",
                        "baseapi": "",
                        "captured_request_count": to_int(
                            result["request_capture"].get("request_total"),
                            default=0,
                            minimum=0,
                        ),
                        "endpoint_count": 0,
                        "matched": {},
                        "compose_preview": [],
                        "error": "api endpoint list is empty after extract",
                    }
                else:
                    infer_result = infer_request_base_from_endpoint_rows(capture_domain, endpoint_rows)

                compose_preview_raw = (
                    infer_result.get("compose_preview")
                    if isinstance(infer_result.get("compose_preview"), list)
                    else []
                )
                result["infer_result"] = {
                    "domain": safe_str(infer_result.get("domain")),
                    "inferred": bool(infer_result.get("inferred")),
                    "baseurl": safe_str(infer_result.get("baseurl")),
                    "baseapi": safe_str(infer_result.get("baseapi")),
                    "captured_request_count": to_int(
                        infer_result.get("captured_request_count"),
                        default=0,
                        minimum=0,
                    ),
                    "endpoint_count": to_int(infer_result.get("endpoint_count"), default=0, minimum=0),
                    "matched": infer_result.get("matched") if isinstance(infer_result.get("matched"), dict) else {},
                    "error": safe_str(infer_result.get("error")),
                    "compose_preview_total": len(compose_preview_raw),
                    "compose_preview": compose_preview_raw[:120],
                }
                _update_phase("infer_base")

                if bool(infer_result.get("inferred")):
                    append_log(
                        job_id,
                        "auto pipeline infer base matched: "
                        f"{safe_str(infer_result.get('baseurl'))}{safe_str(infer_result.get('baseapi'))}",
                    )
                    sync_vue_api_source_form(domain=capture_domain, pattern=selected_pattern)
                    sync_vue_api_request_state(
                        domain=capture_domain,
                        baseurl=safe_str(infer_result.get("baseurl")),
                        baseapi=safe_str(infer_result.get("baseapi")),
                    )
                    persist_project_request_config(
                        capture_domain,
                        baseurl=safe_str(infer_result.get("baseurl")),
                        baseapi=safe_str(infer_result.get("baseapi")),
                    )

                    matched = infer_result.get("matched") if isinstance(infer_result.get("matched"), dict) else {}
                    endpoint_id = safe_str(matched.get("endpoint_id"))
                    endpoint_method = safe_str(matched.get("endpoint_method"))
                    if endpoint_id:
                        sync_vue_api_request_state(api_id=endpoint_id)
                    if endpoint_method:
                        sync_vue_api_request_state(method=endpoint_method)

                    append_log(job_id, "auto pipeline request run start")
                    _checkpoint("auto_request")
                    _update_phase("auto_request")

                    def _report_auto_request_progress(
                        label: str,
                        summary: dict[str, int],
                        child_status: str,
                        child_job_id: str,
                    ) -> None:
                        total_value = to_int(summary.get("total"), default=0, minimum=0)
                        done_value = to_int(summary.get("done"), default=0, minimum=0)
                        ok_value = to_int(summary.get("ok"), default=0, minimum=0)
                        fail_value = to_int(summary.get("fail"), default=0, minimum=0)
                        result["auto_request_progress"] = {
                            "label": safe_str(label),
                            "child_job_id": safe_str(child_job_id),
                            "status": safe_str(child_status),
                            "done": done_value,
                            "total": total_value,
                            "ok": ok_value,
                            "fail": fail_value,
                        }
                        progress = sync_control_progress(result, phase="auto_request", stop_requested=bool(job_stop_requested(job_id)))
                        progress["done"] = done_value
                        progress["total"] = total_value
                        progress["ok"] = ok_value
                        progress["failed"] = fail_value
                        progress["phase"] = "auto_request"
                        result["progress"] = progress
                        update_job(job_id=job_id, status="paused" if job_pause_requested(job_id) else "running", result=result)

                    auto_request_result = run_auto_request_pipeline(
                        domain=capture_domain,
                        preferred_request_url=safe_str(result.get("auto_pipeline_target", {}).get("request_url")),
                        baseurl=safe_str(infer_result.get("baseurl")),
                        baseapi=safe_str(infer_result.get("baseapi")),
                        endpoints=serialized_endpoints,
                        parent_job_id=job_id,
                        stop_check=lambda: job_stop_requested(job_id),
                        pause_check=lambda: job_pause_requested(job_id),
                        on_progress=_report_auto_request_progress,
                    )
                    result["auto_request"] = auto_request_result
                    _update_phase("auto_request")
                else:
                    append_log(
                        job_id,
                        "auto pipeline infer base failed: "
                        f"{safe_str(result.get('infer_result', {}).get('error')) or 'baseurl/baseapi not inferred'}",
                    )

                append_log(
                    job_id,
                    f"auto scan completed: endpoints={to_int(result.get('infer_result', {}).get('endpoint_count'), default=0, minimum=0)}",
                )
                _update_phase("auto_pipeline_done")

        _checkpoint("finalize")
        result["stop_requested"] = False
        result["progress"] = sync_control_progress(result, phase="completed", stop_requested=False)
        append_log(job_id, "web action completed")
        update_job(job_id=job_id, status="completed", result=result)
    except Exception as exc:
        message = str(exc)
        if message == "__MODULE2_SYNC_STOPPED__" or job_stop_requested(job_id):
            _mark_stopped("sync", reason="stop requested")
            return
        append_log(job_id, f"web action failed: {message}")
        update_job(job_id=job_id, status="failed", result=result or None, error=message)


def run_module2_js_download_background(
    *,
    job_id: str,
    domain: str,
    js_urls: list[str],
    concurrency: int,
    mode: str,
    append_log: Callable[[str, str], None],
    update_job: Callable[..., dict[str, Any]],
    cache_project_js_to_downchunk: Callable[..., dict[str, Any]],
    build_project_js_zip: Callable[..., tuple[Path, int, int]],
    safe_str: Callable[[Any, str], str],
    to_int: Callable[[Any, int, int], int],
    projects_dir: Path,
    module2_js_download_job_step: str,
) -> None:
    # 这里只保留 JS 下载后台任务的具体实现，app.py 只负责把入口和依赖接进来。
    mode_token = safe_str(mode, "zip").lower()
    if mode_token not in {"zip", "local"}:
        mode_token = "zip"
    append_log(job_id, f"web action start: {module2_js_download_job_step} ({mode_token})")
    total = len(js_urls)
    report_span = max(1, total // 12) if total > 0 else 1
    last_progress_logged = 0
    recent_js_urls: list[str] = []

    try:
        update_job(
            job_id=job_id,
            status="running",
            result={
                "domain": domain,
                "mode": mode_token,
                "progress": {"done": 0, "total": total, "downloaded": 0, "skipped": 0, "failed": 0},
                "concurrency": concurrency,
                "current_js_url": "",
                "current_file_name": "",
                "recent_js_urls": [],
            },
        )

        def _report_zip(
            done: int,
            total_count: int,
            success_count: int,
            failed_count: int,
            **context: Any,
        ) -> None:
            nonlocal last_progress_logged, recent_js_urls
            try:
                current_js_url = safe_str(context.get("current_js_url"))
                current_file_name = safe_str(context.get("current_file_name"))
                if current_js_url:
                    recent_js_urls = _merge_recent_texts(recent_js_urls, [current_js_url], limit=3)
                update_job(
                    job_id=job_id,
                    status="running",
                    result={
                        "domain": domain,
                        "mode": mode_token,
                        "progress": {
                            "done": int(done),
                            "total": int(total_count),
                            "downloaded": int(success_count),
                            "skipped": 0,
                            "failed": int(failed_count),
                        },
                        "concurrency": concurrency,
                        "current_js_url": current_js_url,
                        "current_file_name": current_file_name,
                        "recent_js_urls": recent_js_urls,
                    },
                )
                if done == 1 or done == total_count or done - last_progress_logged >= report_span:
                    last_progress_logged = int(done)
                    if current_js_url:
                        append_log(job_id, f"js download progress {done}/{total_count}: {current_js_url}")
                    else:
                        append_log(job_id, f"js download progress {done}/{total_count}")
            except Exception:
                pass

        if mode_token == "local":

            def _report_local(
                done: int,
                total_count: int,
                downloaded_count: int,
                skipped_count: int,
                failed_count: int,
                **context: Any,
            ) -> None:
                nonlocal last_progress_logged, recent_js_urls
                try:
                    current_js_url = safe_str(context.get("current_js_url"))
                    current_file_name = safe_str(context.get("current_file_name"))
                    if current_js_url:
                        recent_js_urls = _merge_recent_texts(recent_js_urls, [current_js_url], limit=3)
                    update_job(
                        job_id=job_id,
                        status="running",
                        result={
                            "domain": domain,
                            "mode": mode_token,
                            "progress": {
                                "done": int(done),
                                "total": int(total_count),
                                "downloaded": int(downloaded_count),
                                "skipped": int(skipped_count),
                                "failed": int(failed_count),
                            },
                            "concurrency": concurrency,
                            "current_js_url": current_js_url,
                            "current_file_name": current_file_name,
                            "recent_js_urls": recent_js_urls,
                        },
                    )
                    if done == 1 or done == total_count or done - last_progress_logged >= report_span:
                        last_progress_logged = int(done)
                        if current_js_url:
                            append_log(job_id, f"js download progress {done}/{total_count}: {current_js_url}")
                        else:
                            append_log(job_id, f"js download progress {done}/{total_count}")
                except Exception:
                    pass

            cache_stats = cache_project_js_to_downchunk(
                domain=domain,
                js_urls=js_urls,
                concurrency=concurrency,
                progress_callback=_report_local,
            )
            result = {
                "domain": domain,
                "mode": mode_token,
                "local_dir": str(projects_dir / domain / "downChunk"),
                "downloaded_count": to_int(cache_stats.get("downloaded"), default=0, minimum=0),
                "skipped_count": to_int(cache_stats.get("skipped"), default=0, minimum=0),
                "failed_count": to_int(cache_stats.get("failed"), default=0, minimum=0),
                "total": to_int(cache_stats.get("total"), default=total, minimum=0),
                "concurrency": int(concurrency),
                "progress": {
                    "done": to_int(cache_stats.get("total"), default=total, minimum=0),
                    "total": to_int(cache_stats.get("total"), default=total, minimum=0),
                    "downloaded": to_int(cache_stats.get("downloaded"), default=0, minimum=0),
                    "skipped": to_int(cache_stats.get("skipped"), default=0, minimum=0),
                    "failed": to_int(cache_stats.get("failed"), default=0, minimum=0),
                },
                "current_js_url": "",
                "current_file_name": "",
                "recent_js_urls": recent_js_urls,
            }
        else:
            zip_path, success_count, failed_count = build_project_js_zip(
                domain,
                js_urls,
                concurrency=concurrency,
                progress_callback=_report_zip,
            )
            result = {
                "domain": domain,
                "mode": mode_token,
                "zip_path": str(zip_path),
                "downloaded_count": int(success_count),
                "skipped_count": 0,
                "failed_count": int(failed_count),
                "total": int(total),
                "concurrency": int(concurrency),
                "progress": {
                    "done": int(total),
                    "total": int(total),
                    "downloaded": int(success_count),
                    "skipped": 0,
                    "failed": int(failed_count),
                },
                "current_js_url": "",
                "current_file_name": "",
                "recent_js_urls": recent_js_urls,
            }

        append_log(job_id, "web action completed")
        update_job(job_id=job_id, status="completed", result=result)
    except Exception as exc:
        message = str(exc)
        append_log(job_id, f"web action failed: {message}")
        update_job(job_id=job_id, status="failed", error=message)


def run_module2_request_capture_background(
    *,
    job_id: str,
    domain: str,
    route_urls: list[str],
    concurrency: int,
    proxy_server: str,
    preferred_hash_style: str,
    preferred_basepath_override: str,
    manual_lock: bool,
    append_log: Callable[[str, str], None],
    update_job: Callable[..., dict[str, Any]],
    normalize_proxy_server: Callable[[Any], str],
    job_stop_requested: Callable[[str], bool],
    job_pause_requested: Callable[[str], bool],
    safe_str: Callable[[Any, str], str],
    to_int: Callable[[Any, int, int], int],
    read_lines: Callable[[Path, int], list[str]],
    dedupe_effective_js_urls: Callable[[list[Any]], list[str]],
    cache_project_js_to_downchunk: Callable[..., dict[str, Any]],
    js_download_default_concurrency: int,
    module2_request_capture_job_step: str,
    module2_route_style_sample_size: int,
) -> None:
    append_log(job_id, f"web action start: {module2_request_capture_job_step}")
    total = len(route_urls)
    selected_hash_style = normalize_hash_style(preferred_hash_style)
    selected_basepath_override = normalize_basepath(preferred_basepath_override)
    probe_result: dict[str, Any] = {}
    report_span = max(1, total // 12) if total > 0 else 1
    last_progress_logged = 0
    recent_chunks: list[str] = []
    recent_requests: list[str] = []

    try:
        if job_stop_requested(job_id):
            append_log(job_id, "web action stopped before start")
            update_job(
                job_id=job_id,
                status="stopped",
                result={
                    "domain": domain,
                    "concurrency": int(concurrency),
                    "proxy_server": normalize_proxy_server(proxy_server),
                    "hash_style": selected_hash_style,
                    "basepath_override": selected_basepath_override,
                    "manual_lock": bool(manual_lock),
                    "stop_requested": True,
                    "current_route_url": "",
                    "recent_chunks": [],
                    "recent_requests": [],
                    "progress": {
                        "done": 0,
                        "total": int(total),
                        "visited_route_count": 0,
                        "failed_route_count": 0,
                        "request_total": 0,
                        "phase": "stopped",
                    },
                },
            )
            return

        if not manual_lock:
            update_job(
                job_id=job_id,
                status="running",
                result={
                    "domain": domain,
                    "concurrency": int(concurrency),
                    "proxy_server": normalize_proxy_server(proxy_server),
                    "hash_style": selected_hash_style,
                    "basepath_override": selected_basepath_override,
                    "manual_lock": False,
                    "stop_requested": False,
                    "current_route_url": "",
                    "recent_chunks": [],
                    "recent_requests": [],
                    "progress": {
                        "done": 0,
                        "total": int(total),
                        "visited_route_count": 0,
                        "failed_route_count": 0,
                        "request_total": 0,
                        "phase": "probing",
                    },
                },
            )
            append_log(job_id, f"route style probe start (sample={module2_route_style_sample_size})")
            try:
                probe_payload = asyncio.run(
                    run_route_hash_style_probe(
                        route_urls=route_urls,
                        sample_size=module2_route_style_sample_size,
                        basepath_override=selected_basepath_override,
                        preferred_style=selected_hash_style,
                        proxy_server=normalize_proxy_server(proxy_server),
                    )
                )
                if isinstance(probe_payload, dict):
                    probe_result = probe_payload
                    selected_hash_style = normalize_hash_style(probe_result.get("picked_style"))
                    selected_basepath_override = normalize_basepath(
                        probe_result.get("basepath_override") or selected_basepath_override
                    )
                    append_log(job_id, f"route style probe selected: {selected_hash_style}")
            except Exception as probe_exc:
                append_log(
                    job_id,
                    f"route style probe failed, fallback to {selected_hash_style}: {probe_exc}",
                )

            if job_stop_requested(job_id):
                append_log(job_id, "web action stopped during route style probe")
                update_job(
                    job_id=job_id,
                    status="stopped",
                    result={
                        "domain": domain,
                        "concurrency": int(concurrency),
                        "proxy_server": normalize_proxy_server(proxy_server),
                        "hash_style": selected_hash_style,
                        "basepath_override": selected_basepath_override,
                        "manual_lock": False,
                        "probe": probe_result,
                        "stop_requested": True,
                        "current_route_url": "",
                        "recent_chunks": [],
                        "recent_requests": [],
                        "progress": {
                            "done": 0,
                            "total": int(total),
                            "visited_route_count": 0,
                            "failed_route_count": 0,
                            "request_total": 0,
                            "phase": "probing",
                        },
                    },
                )
                return

            save_route_url_profile(
                domain,
                hash_style=selected_hash_style,
                basepath_override=selected_basepath_override,
                manual_lock=False,
                source="auto_probe",
                probe=probe_result,
            )
        else:
            append_log(job_id, f"route style manual lock enabled: {selected_hash_style}")

        effective_route_urls = rewrite_route_urls(
            route_urls,
            hash_style=selected_hash_style,
            basepath_override=selected_basepath_override,
        )
        total = len(effective_route_urls)
        if total <= 0:
            raise ValueError("no route urls found for request capture")

        update_job(
            job_id=job_id,
            status="running",
            result={
                "domain": domain,
                "concurrency": int(concurrency),
                "proxy_server": normalize_proxy_server(proxy_server),
                "hash_style": selected_hash_style,
                "basepath_override": selected_basepath_override,
                "manual_lock": bool(manual_lock),
                "probe": probe_result,
                "stop_requested": False,
                "current_route_url": "",
                "recent_chunks": [],
                "recent_requests": [],
                "progress": {
                    "done": 0,
                    "total": int(total),
                    "visited_route_count": 0,
                    "failed_route_count": 0,
                    "request_total": 0,
                    "phase": "capturing",
                },
            },
        )

        def _report(
            done: int,
            total_count: int,
            visited_route_count: int,
            failed_route_count: int,
            request_total: int,
            **context: Any,
        ) -> None:
            nonlocal last_progress_logged, recent_chunks, recent_requests
            try:
                stop_requested = job_stop_requested(job_id)
                paused = job_pause_requested(job_id)
                route_status = safe_str(context.get("route_status")).lower()
                current_route_url = safe_str(context.get("current_route_url"))
                route_error = safe_str(context.get("route_error"))
                fresh_chunks = (
                    context.get("recent_chunks") if isinstance(context.get("recent_chunks"), list) else []
                )
                fresh_requests = (
                    context.get("recent_requests") if isinstance(context.get("recent_requests"), list) else []
                )
                recent_chunks = _merge_recent_texts(
                    recent_chunks,
                    fresh_chunks,
                    limit=3,
                )
                recent_requests = _merge_recent_texts(
                    recent_requests,
                    fresh_requests,
                    limit=3,
                )
                update_job(
                    job_id=job_id,
                    status="paused" if paused else "running",
                    result={
                        "domain": domain,
                        "concurrency": int(concurrency),
                        "proxy_server": normalize_proxy_server(proxy_server),
                        "hash_style": selected_hash_style,
                        "basepath_override": selected_basepath_override,
                        "manual_lock": bool(manual_lock),
                        "probe": probe_result,
                        "stop_requested": stop_requested,
                        "current_route_url": current_route_url,
                        "recent_chunks": recent_chunks,
                        "recent_requests": recent_requests,
                        "progress": {
                            "done": int(done),
                            "total": int(total_count),
                            "visited_route_count": int(visited_route_count),
                            "failed_route_count": int(failed_route_count),
                            "request_total": int(request_total),
                            "phase": "capturing",
                        },
                    },
                )
                should_log = (
                    done == 1
                    or done == total_count
                    or done - last_progress_logged >= report_span
                    or (route_status == "done" and bool(fresh_chunks or fresh_requests))
                    or (route_status == "failed" and bool(route_error))
                )
                if should_log:
                    last_progress_logged = int(done)
                    summary = f"capture progress {done}/{total_count}"
                    if current_route_url:
                        summary = f"{summary}: {current_route_url}"
                    if recent_chunks or recent_requests:
                        summary = (
                            f"{summary} | chunk={len(recent_chunks)} api={len(recent_requests)}"
                        )
                    append_log(job_id, summary)
            except Exception:
                pass

        result = asyncio.run(
            run_route_request_capture(
                domain=domain,
                route_urls=effective_route_urls,
                concurrency=concurrency,
                hash_style=selected_hash_style,
                basepath_override=selected_basepath_override,
                proxy_server=normalize_proxy_server(proxy_server),
                progress_callback=_report,
                stop_check=lambda: job_stop_requested(job_id),
                pause_check=lambda: job_pause_requested(job_id),
            )
        )
        if not isinstance(result, dict):
            result = {"data": result}

        # 抓包完成后顺手把 JS 缓存到本地 downChunk，减少后续提取流程重复拉取网络资源。
        try:
            js_file = Path(safe_str(result.get("js_file")))
            js_urls = dedupe_effective_js_urls(read_lines(js_file, limit=300000))
            if js_urls:
                cache_stats = cache_project_js_to_downchunk(
                    domain=domain,
                    js_urls=js_urls,
                    concurrency=js_download_default_concurrency,
                )
            else:
                cache_stats = {
                    "total": 0,
                    "downloaded": 0,
                    "skipped": 0,
                    "failed": 0,
                    "concurrency": int(js_download_default_concurrency),
                }
            result["chunk_cache"] = cache_stats
            append_log(
                job_id,
                "chunk cache done: "
                f"total={to_int(cache_stats.get('total'), default=0, minimum=0)}, "
                f"downloaded={to_int(cache_stats.get('downloaded'), default=0, minimum=0)}, "
                f"skipped={to_int(cache_stats.get('skipped'), default=0, minimum=0)}, "
                f"failed={to_int(cache_stats.get('failed'), default=0, minimum=0)}",
            )
        except Exception as cache_exc:
            result["chunk_cache"] = {
                "total": 0,
                "downloaded": 0,
                "skipped": 0,
                "failed": 0,
                "error": str(cache_exc),
            }
            append_log(job_id, f"chunk cache failed: {cache_exc}")

        result["concurrency"] = int(concurrency)
        result["hash_style"] = selected_hash_style
        result["basepath_override"] = selected_basepath_override
        result["manual_lock"] = bool(manual_lock)
        result["proxy_server"] = normalize_proxy_server(proxy_server)
        result["probe"] = probe_result
        result["current_route_url"] = ""
        result["recent_chunks"] = recent_chunks
        result["recent_requests"] = recent_requests
        stopped = bool(job_stop_requested(job_id) or result.get("stop_requested"))
        result["stop_requested"] = stopped
        result["progress"] = {
            "done": to_int(
                (result.get("progress") if isinstance(result.get("progress"), dict) else {}).get("done"),
                default=(0 if stopped else int(total)),
                minimum=0,
            ),
            "total": int(total),
            "visited_route_count": to_int(result.get("visited_route_count"), default=0, minimum=0),
            "failed_route_count": to_int(result.get("failed_route_count"), default=0, minimum=0),
            "request_total": to_int(result.get("request_total"), default=0, minimum=0),
            "phase": "capturing",
        }

        if stopped:
            append_log(job_id, "web action stopped")
            update_job(job_id=job_id, status="stopped", result=result)
        else:
            append_log(job_id, "web action completed")
            update_job(job_id=job_id, status="completed", result=result)
    except Exception as exc:
        message = str(exc)
        if job_stop_requested(job_id):
            append_log(job_id, "web action stopped")
            update_job(
                job_id=job_id,
                status="stopped",
                result={
                    "domain": domain,
                    "concurrency": int(concurrency),
                    "proxy_server": normalize_proxy_server(proxy_server),
                    "hash_style": selected_hash_style,
                    "basepath_override": selected_basepath_override,
                    "manual_lock": bool(manual_lock),
                    "probe": probe_result,
                    "stop_requested": True,
                    "current_route_url": "",
                    "recent_chunks": recent_chunks,
                    "recent_requests": recent_requests,
                    "progress": {
                        "done": 0,
                        "total": int(total),
                        "visited_route_count": 0,
                        "failed_route_count": 0,
                        "request_total": 0,
                        "phase": "stopped",
                    },
                },
            )
            return
        append_log(job_id, f"web action failed: {message}")
        update_job(job_id=job_id, status="failed", error=message)
