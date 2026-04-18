from __future__ import annotations

from collections import Counter
from typing import Any, Callable


def run_module1_detect_background(
    *,
    job_id: str,
    task_id: str,
    input_path: str,
    concurrency: int,
    timeout: int,
    wait_ms: int,
    detect_limit: int | None,
    append_log: Callable[[str, str], None],
    update_job: Callable[..., dict[str, Any]],
    update_detect_task: Callable[..., dict[str, Any]],
    run_detect: Callable[..., Any],
    normalize_detect_url_rows: Callable[[Any], list[dict[str, Any]]],
    read_detect_urls: Callable[[Any], list[str]],
    job_stop_requested: Callable[[str], bool],
    job_pause_requested: Callable[[str], bool],
    safe_str: Callable[[Any, str], str],
    to_int: Callable[[Any, int, int], int],
    module1_detect_job_step: str,
) -> None:
    # VueDetect 后台任务已经下沉到领域模块，app.py 只保留入口转发。
    append_log(job_id, f"web action start: {module1_detect_job_step}")

    vue_item_map: dict[str, dict[str, Any]] = {}
    method_counter: Counter[str] = Counter()
    failed_sites = 0
    input_files = 0
    raw_candidates = 0

    def _progress_payload(done: int, total: int) -> dict[str, Any]:
        nonlocal input_files, raw_candidates
        vue_items = sorted(
            list(vue_item_map.values()),
            key=lambda item: (-to_int(item.get("route_count"), default=0, minimum=0), safe_str(item.get("url"))),
        )
        return {
            "input_files": to_int(input_files, default=0, minimum=0),
            "raw_candidates": to_int(raw_candidates, default=0, minimum=0),
            "total_urls": max(0, int(total)),
            "vue_sites": len(vue_items),
            "non_vue_sites": max(0, int(done) - len(vue_items)),
            "failed_sites": to_int(failed_sites, default=0, minimum=0),
            "methods": dict(method_counter),
            "vue_items": vue_items,
            "progress": {"done": max(0, int(done)), "total": max(0, int(total))},
        }

    def _on_detect_progress(item: dict[str, Any], done: int, total: int) -> None:
        nonlocal failed_sites

        if bool(item.get("error")):
            failed_sites += 1
        method_counter[safe_str(item.get("method"), "unknown")] += 1

        if bool(item.get("is_vue")):
            output_url = safe_str(item.get("final_url") or item.get("url"))
            route_count = to_int(item.get("route_count"), default=0, minimum=0)
            title = safe_str(item.get("title"))
            if output_url:
                existed = vue_item_map.get(output_url)
                if existed is None:
                    vue_item_map[output_url] = {
                        "url": output_url,
                        "title": title,
                        "route_count": route_count,
                    }
                else:
                    if route_count > to_int(existed.get("route_count"), default=0, minimum=0):
                        existed["route_count"] = route_count
                    if (not safe_str(existed.get("title"))) and title:
                        existed["title"] = title

        # 进度回调里同步刷新任务状态，这样 Web 页面可以持续看到增量结果。
        paused = job_pause_requested(job_id)
        progress_summary = _progress_payload(done, total)
        running_result = {
            "task_id": task_id,
            "job_id": job_id,
            "summary": progress_summary,
            "progress": progress_summary.get("progress", {"done": done, "total": total}),
        }

        try:
            update_detect_task(
                task_id,
                status="paused" if paused else "running",
                result=running_result,
                urls=progress_summary.get("vue_items"),
                error="",
            )
        except Exception:
            pass

        try:
            update_job(
                job_id=job_id,
                status="paused" if paused else "running",
                result=running_result,
            )
        except Exception:
            pass

    try:
        try:
            update_job(
                job_id=job_id,
                status="running",
                result={
                    "task_id": task_id,
                    "progress": {"done": 0, "total": 0},
                    "summary": {
                        "input_files": 0,
                        "raw_candidates": 0,
                        "total_urls": 0,
                        "vue_sites": 0,
                        "non_vue_sites": 0,
                        "failed_sites": 0,
                        "methods": {},
                        "vue_items": [],
                    },
                },
            )
        except Exception:
            pass

        result = run_detect(
            input_path=input_path,
            output_html=None,
            concurrency=concurrency,
            timeout=timeout,
            wait_ms=wait_ms,
            detect_limit=detect_limit,
            progress_callback=_on_detect_progress,
            stop_check=lambda: job_stop_requested(job_id),
            pause_check=lambda: job_pause_requested(job_id),
        )
        if not isinstance(result, dict):
            result = {"data": result}
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        input_files = to_int(summary.get("input_files"), default=input_files, minimum=0)
        raw_candidates = to_int(summary.get("raw_candidates"), default=raw_candidates, minimum=0)
        urls = normalize_detect_url_rows(summary.get("vue_items"))
        if not urls:
            urls = normalize_detect_url_rows(read_detect_urls(result.get("txt_path")))
        update_detect_task(
            task_id,
            status="completed",
            result=result,
            urls=urls,
            error="",
        )
        append_log(job_id, "web action completed")
        update_job(
            job_id=job_id,
            status="completed",
            result={"task_id": task_id, "url_count": len(urls), **result},
        )
    except Exception as exc:
        message = str(exc)
        try:
            update_detect_task(
                task_id,
                status="failed",
                result={},
                urls=[],
                error=message,
            )
        except Exception:
            pass
        append_log(job_id, f"web action failed: {message}")
        update_job(job_id=job_id, status="failed", error=message)
