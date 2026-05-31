from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Any, Callable


def queue_module2_project_sync_service(
    *,
    ui_state: dict[str, Any],
    target_url: str,
    source: str,
    concurrency: int,
    detect_routes: bool,
    detect_js: bool,
    detect_request: bool,
    queue_project_sync: Callable[..., tuple[dict[str, Any], dict[str, Any]]],
    safe_str: Callable[[Any, str], str],
    select_vue_api_domain: Callable[[str], str],
    proxy_server: str = "",
    auto_scan_pattern: str = "",
    task_id: str | None = None,
    auto_pipeline: bool = False,
    project_title: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    # 这里只做 Web UI 状态回写，真正的排队逻辑已经在 src/vue_chunk/job_queue.py。
    project, job = queue_project_sync(
        target_url=target_url,
        source=source,
        concurrency=concurrency,
        detect_routes=detect_routes,
        detect_js=detect_js,
        detect_request=detect_request,
        proxy_server=proxy_server,
        auto_scan_pattern=auto_scan_pattern,
        task_id=task_id,
        auto_pipeline=auto_pipeline,
        project_title=project_title,
    )
    selected_domain = safe_str(project.get("domain"))
    job_id = safe_str(job.get("job_id"))
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}

    select_vue_api_domain(selected_domain)
    ui_state["chunk_form"].update(
        {
            "target_url": safe_str(target_url),
            "concurrency": str(max(1, int(concurrency))),
            "detect_routes": "1" if detect_routes else "",
            "detect_js": "1" if detect_js else "",
            "detect_request": "1" if detect_request else "",
        }
    )
    ui_state["module2_sync_job_id"] = job_id
    ui_state["chunk_result"] = {
        "job_id": job_id,
        "status": "queued",
        "step": safe_str(job.get("step")),
        **payload,
    }
    return project, job


def queue_module2_js_download_service(
    *,
    ui_state: dict[str, Any],
    domain: str,
    concurrency: int,
    mode: str,
    queue_js_download: Callable[..., dict[str, Any]],
    set_selected_project_domain: Callable[[str], str],
    safe_str: Callable[[Any, str], str],
) -> dict[str, Any]:
    job = queue_js_download(domain=domain, concurrency=concurrency, mode=mode)
    job_id = safe_str(job.get("job_id"))
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}

    ui_state["module2_js_download_job_id"] = job_id
    set_selected_project_domain(domain)
    ui_state["chunk_result"] = {
        "job_id": job_id,
        "status": "queued",
        "step": safe_str(job.get("step")),
        **payload,
    }
    return job


def queue_module2_request_capture_service(
    *,
    ui_state: dict[str, Any],
    domain: str,
    concurrency: int,
    proxy_server: str,
    queue_request_capture: Callable[..., dict[str, Any]],
    set_selected_project_domain: Callable[[str], str],
    safe_str: Callable[[Any, str], str],
) -> dict[str, Any]:
    job = queue_request_capture(
        domain=domain,
        concurrency=concurrency,
        proxy_server=proxy_server,
    )
    ui_state["module2_request_capture_job_id"] = safe_str(job.get("job_id"))
    set_selected_project_domain(domain)
    return job


def resolve_module2_target_url_service(
    domain: str,
    preferred_target_url: str,
    *,
    resolve_target_url: Callable[..., str],
) -> str:
    return resolve_target_url(domain, preferred_target_url=preferred_target_url)


@dataclass(frozen=True)
class VueChunkRuntimeBuildDeps:
    # 这一层负责把 VueChunk 的排队入口和 UI 回写逻辑装配成可复用 callable。
    ui_state: dict[str, Any]
    safe_str: Callable[[Any, str], str]
    select_vue_api_domain: Callable[[str], str]
    set_selected_project_domain: Callable[[str], str]
    queue_project_sync_impl: Callable[..., tuple[dict[str, Any], dict[str, Any]]]
    upsert_project_from_url: Callable[..., dict[str, Any]]
    normalize_proxy_server: Callable[[Any], str]
    get_global_settings: Callable[..., dict[str, Any]]
    create_job: Callable[..., dict[str, Any]]
    append_log: Callable[[str, str], None]
    update_job: Callable[..., dict[str, Any]]
    module2_sync_job_step: str
    spawn_background: Callable[..., None]
    run_module2_project_sync_background: Callable[..., Any]
    queue_js_download_impl: Callable[..., dict[str, Any]]
    load_project_detail: Callable[[str], dict[str, Any]]
    read_lines: Callable[..., list[str]]
    dedupe_effective_js_urls: Callable[[list[Any]], list[str]]
    module2_js_download_job_step: str
    run_module2_js_download_background: Callable[..., Any]
    queue_request_capture_impl: Callable[..., dict[str, Any]]
    load_route_url_profile: Callable[[str], dict[str, Any]]
    module2_request_capture_job_step: str
    run_module2_request_capture_background: Callable[..., Any]
    resolve_target_url_impl: Callable[..., str]
    get_project: Callable[[str], dict[str, Any] | None]
    collect_sync_state_map: Callable[..., dict[str, dict[str, Any]]]


@dataclass(frozen=True)
class VueChunkRuntimeBundle:
    queue_project_sync: Callable[..., tuple[dict[str, Any], dict[str, Any]]]
    queue_js_download: Callable[..., dict[str, Any]]
    queue_request_capture: Callable[..., dict[str, Any]]
    resolve_target_url: Callable[[str, str], str]


def build_vue_chunk_runtime_bundle(deps: VueChunkRuntimeBuildDeps) -> VueChunkRuntimeBundle:
    queue_project_sync = partial(
        queue_module2_project_sync_service,
        ui_state=deps.ui_state,
        queue_project_sync=partial(
            deps.queue_project_sync_impl,
            upsert_project_from_url=deps.upsert_project_from_url,
            safe_str=deps.safe_str,
            normalize_proxy_server=deps.normalize_proxy_server,
            get_global_settings=deps.get_global_settings,
            create_job=deps.create_job,
            append_log=deps.append_log,
            update_job=deps.update_job,
            module2_sync_job_step=deps.module2_sync_job_step,
            on_queued=lambda project, job_id, payload: None,
            spawn_background=deps.spawn_background,
            run_background=deps.run_module2_project_sync_background,
        ),
        safe_str=deps.safe_str,
        select_vue_api_domain=deps.select_vue_api_domain,
    )

    queue_js_download = partial(
        queue_module2_js_download_service,
        ui_state=deps.ui_state,
        queue_js_download=partial(
            deps.queue_js_download_impl,
            load_project_detail=deps.load_project_detail,
            read_lines=deps.read_lines,
            dedupe_effective_js_urls=deps.dedupe_effective_js_urls,
            safe_str=deps.safe_str,
            create_job=deps.create_job,
            append_log=deps.append_log,
            update_job=deps.update_job,
            module2_js_download_job_step=deps.module2_js_download_job_step,
            on_queued=lambda job_id, queued_domain, payload: None,
            spawn_background=deps.spawn_background,
            run_background=deps.run_module2_js_download_background,
        ),
        set_selected_project_domain=deps.set_selected_project_domain,
        safe_str=deps.safe_str,
    )

    queue_request_capture = partial(
        queue_module2_request_capture_service,
        ui_state=deps.ui_state,
        queue_request_capture=partial(
            deps.queue_request_capture_impl,
            load_project_detail=deps.load_project_detail,
            read_lines=deps.read_lines,
            safe_str=deps.safe_str,
            load_route_url_profile=deps.load_route_url_profile,
            normalize_proxy_server=deps.normalize_proxy_server,
            get_global_settings=deps.get_global_settings,
            create_job=deps.create_job,
            append_log=deps.append_log,
            update_job=deps.update_job,
            module2_request_capture_job_step=deps.module2_request_capture_job_step,
            on_queued=lambda job_id, queued_domain: None,
            spawn_background=deps.spawn_background,
            run_background=deps.run_module2_request_capture_background,
        ),
        set_selected_project_domain=deps.set_selected_project_domain,
        safe_str=deps.safe_str,
    )

    resolve_target_url = partial(
        resolve_module2_target_url_service,
        resolve_target_url=partial(
            deps.resolve_target_url_impl,
            get_project=deps.get_project,
            collect_sync_state_map=deps.collect_sync_state_map,
            load_project_detail=deps.load_project_detail,
        ),
    )

    return VueChunkRuntimeBundle(
        queue_project_sync=queue_project_sync,
        queue_js_download=queue_js_download,
        queue_request_capture=queue_request_capture,
        resolve_target_url=resolve_target_url,
    )
