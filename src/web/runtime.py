from __future__ import annotations

import asyncio
import inspect
import threading
from dataclasses import dataclass
from functools import partial
from typing import Any, Awaitable, Callable


async def run_web_action(
    step: str,
    payload: dict[str, Any],
    runner,
    *,
    create_job: Callable[..., dict[str, Any]],
    append_log: Callable[[str, str], None],
    update_job: Callable[..., dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    # Web 层统一的同步任务包装器：建 job、写日志、在线程里执行、回填结果。
    job = create_job(step=step, payload=payload)
    job_id = str(job["job_id"])
    append_log(job_id, f"web action start: {step}")

    try:
        def _call_runner():
            try:
                signature = inspect.signature(runner)
                if len(signature.parameters) >= 1:
                    return runner(job_id)
            except (TypeError, ValueError):
                pass
            return runner()

        result = await asyncio.to_thread(_call_runner)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, dict):
            result = {"data": result}
        append_log(job_id, "web action completed")
        update_job(job_id=job_id, status="completed", result=result)
        return job_id, result
    except Exception as exc:
        message = str(exc)
        append_log(job_id, f"web action failed: {message}")
        update_job(job_id=job_id, status="failed", error=message)
        raise


def spawn_background(func, **kwargs: Any) -> None:
    # 后台任务入口仍保留线程模式，但把启动细节从 app.py 拿走。
    worker = threading.Thread(target=func, kwargs=kwargs, daemon=True)
    worker.start()


@dataclass(frozen=True)
class WebRuntimeBuildDeps:
    # 这一层只做后台任务 callable 的依赖装配，不承载业务规则。
    create_job: Callable[..., dict[str, Any]]
    append_log: Callable[[str, str], None]
    update_job: Callable[..., dict[str, Any]]
    module_run_module1_detect_background: Callable[..., Any]
    update_detect_task: Callable[..., dict[str, Any]]
    run_detect: Callable[..., Any]
    normalize_detect_url_rows: Callable[[Any], list[dict[str, Any]]]
    read_detect_urls: Callable[[Any], list[str]]
    job_stop_requested: Callable[[str], bool]
    job_pause_requested: Callable[[str], bool]
    safe_str: Callable[[Any, str], str]
    to_int: Callable[[Any, int, int], int]
    module1_detect_job_step: str
    module_run_module2_project_sync_background: Callable[..., Any]
    run_project_sync: Callable[..., Any]
    normalize_proxy_server: Callable[[Any], str]
    domain_from_target_url: Callable[[str], str]
    sync_control_progress: Callable[..., dict[str, Any]]
    request_capture_job_control: Callable[[str, str], None]
    queue_request_capture: Callable[..., dict[str, Any]]
    read_job: Callable[[str], dict[str, Any]]
    normalize_sync_status: Callable[[Any], str]
    serialize_request_capture_job: Callable[..., dict[str, Any]]
    module2_request_default_concurrency: int
    select_auto_pipeline_js_api_path: Callable[..., dict[str, Any]]
    run_vue_api_auto_regex: Callable[..., dict[str, Any]]
    run_auto_request_pipeline: Callable[..., dict[str, Any]]
    resolve_scan_pattern: Callable[[str], str]
    save_vue_api_config: Callable[[str, str], None]
    run_api_extract: Callable[..., Any]
    load_api_endpoints: Callable[[str], list[Any]]
    normalize_endpoint_rows_for_infer: Callable[[Any], list[dict[str, Any]]]
    serialize_api_endpoint: Callable[[Any], dict[str, Any]]
    infer_request_base_from_endpoint_rows: Callable[[str, Any], dict[str, Any]]
    sync_vue_api_source_form: Callable[..., None]
    sync_vue_api_request_state: Callable[..., None]
    persist_project_request_config: Callable[..., Any]
    module2_sync_job_step: str
    module_run_module2_js_download_background: Callable[..., Any]
    cache_project_js_to_downchunk: Callable[..., Any]
    build_project_js_zip: Callable[..., Any]
    projects_dir: Any
    module2_js_download_job_step: str
    module_run_module2_request_capture_background: Callable[..., Any]
    read_lines: Callable[..., list[str]]
    dedupe_effective_js_urls: Callable[[list[Any]], list[str]]
    js_download_default_concurrency: int
    module2_request_capture_job_step: str
    module2_route_style_sample_size: int


@dataclass(frozen=True)
class WebRuntimeBundle:
    run_web_action: Callable[..., Awaitable[tuple[str, dict[str, Any]]]]
    spawn_background: Callable[..., None]
    run_module1_detect_background: Callable[..., Any]
    run_module2_project_sync_background: Callable[..., Any]
    run_module2_js_download_background: Callable[..., Any]
    run_module2_request_capture_background: Callable[..., Any]


def build_web_runtime_bundle(deps: WebRuntimeBuildDeps) -> WebRuntimeBundle:
    return WebRuntimeBundle(
        run_web_action=partial(
            run_web_action,
            create_job=deps.create_job,
            append_log=deps.append_log,
            update_job=deps.update_job,
        ),
        spawn_background=spawn_background,
        run_module1_detect_background=partial(
            deps.module_run_module1_detect_background,
            append_log=deps.append_log,
            update_job=deps.update_job,
            update_detect_task=deps.update_detect_task,
            run_detect=deps.run_detect,
            normalize_detect_url_rows=deps.normalize_detect_url_rows,
            read_detect_urls=deps.read_detect_urls,
            job_stop_requested=deps.job_stop_requested,
            job_pause_requested=deps.job_pause_requested,
            safe_str=deps.safe_str,
            to_int=deps.to_int,
            module1_detect_job_step=deps.module1_detect_job_step,
        ),
        run_module2_project_sync_background=partial(
            deps.module_run_module2_project_sync_background,
            append_log=deps.append_log,
            update_job=deps.update_job,
            run_project_sync=deps.run_project_sync,
            normalize_proxy_server=deps.normalize_proxy_server,
            safe_str=deps.safe_str,
            to_int=deps.to_int,
            domain_from_target_url=deps.domain_from_target_url,
            job_stop_requested=deps.job_stop_requested,
            job_pause_requested=deps.job_pause_requested,
            sync_control_progress=deps.sync_control_progress,
            request_capture_job_control=deps.request_capture_job_control,
            queue_request_capture=deps.queue_request_capture,
            read_job=deps.read_job,
            normalize_sync_status=deps.normalize_sync_status,
            serialize_request_capture_job=deps.serialize_request_capture_job,
            module2_request_default_concurrency=deps.module2_request_default_concurrency,
            select_auto_pipeline_js_api_path=deps.select_auto_pipeline_js_api_path,
            run_vue_api_auto_regex=deps.run_vue_api_auto_regex,
            run_auto_request_pipeline=deps.run_auto_request_pipeline,
            resolve_scan_pattern=deps.resolve_scan_pattern,
            save_vue_api_config=deps.save_vue_api_config,
            run_api_extract=deps.run_api_extract,
            load_api_endpoints=deps.load_api_endpoints,
            normalize_endpoint_rows_for_infer=deps.normalize_endpoint_rows_for_infer,
            serialize_api_endpoint=deps.serialize_api_endpoint,
            infer_request_base_from_endpoint_rows=deps.infer_request_base_from_endpoint_rows,
            sync_vue_api_source_form=deps.sync_vue_api_source_form,
            sync_vue_api_request_state=deps.sync_vue_api_request_state,
            persist_project_request_config=deps.persist_project_request_config,
            module2_sync_job_step=deps.module2_sync_job_step,
        ),
        run_module2_js_download_background=partial(
            deps.module_run_module2_js_download_background,
            append_log=deps.append_log,
            update_job=deps.update_job,
            cache_project_js_to_downchunk=deps.cache_project_js_to_downchunk,
            build_project_js_zip=deps.build_project_js_zip,
            safe_str=deps.safe_str,
            to_int=deps.to_int,
            projects_dir=deps.projects_dir,
            module2_js_download_job_step=deps.module2_js_download_job_step,
        ),
        run_module2_request_capture_background=partial(
            deps.module_run_module2_request_capture_background,
            append_log=deps.append_log,
            update_job=deps.update_job,
            normalize_proxy_server=deps.normalize_proxy_server,
            job_stop_requested=deps.job_stop_requested,
            job_pause_requested=deps.job_pause_requested,
            safe_str=deps.safe_str,
            to_int=deps.to_int,
            read_lines=deps.read_lines,
            dedupe_effective_js_urls=deps.dedupe_effective_js_urls,
            cache_project_js_to_downchunk=deps.cache_project_js_to_downchunk,
            js_download_default_concurrency=deps.js_download_default_concurrency,
            module2_request_capture_job_step=deps.module2_request_capture_job_step,
            module2_route_style_sample_size=deps.module2_route_style_sample_size,
        ),
    )
