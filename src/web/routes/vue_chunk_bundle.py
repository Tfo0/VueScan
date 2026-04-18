from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.web.routes.vue_chunk import VueChunkRouteDeps, build_vue_chunk_routes
from src.web.routes.vue_chunk_actions import VueChunkActionRouteDeps, build_vue_chunk_action_routes


@dataclass(frozen=True)
class VueChunkRouteBundleDeps:
    # VueChunk 依赖最多，单独打成 bundle 后 app.py 就不需要维护两长段装配清单。
    ui_state: dict[str, Any]
    safe_str: Callable[[Any, str], str]
    to_int: Callable[[Any, int, int], int]
    to_bool: Callable[[Any], bool]
    json_ok: Callable[..., Any]
    json_error: Callable[..., Any]
    clear_error: Callable[[], None]
    merge_project_domains: Callable[[list[Any]], list[str]]
    list_projects: Callable[..., list[Any]]
    list_detect_tasks: Callable[..., list[Any]]
    get_project: Callable[[str], dict[str, Any] | None]
    upsert_project_from_url: Callable[..., dict[str, Any]]
    update_project_title: Callable[[str, str | None], dict[str, Any]]
    delete_project: Callable[..., dict[str, Any]]
    clear_selected_project_domain: Callable[[], None]
    select_vue_api_domain: Callable[[str], str]
    load_project_detail: Callable[..., dict[str, Any]]
    load_project_metrics: Callable[[str], dict[str, int]]
    serialize_project: Callable[[dict[str, Any]], dict[str, Any]]
    normalize_detect_url_rows: Callable[[Any], list[dict[str, Any]]]
    collect_sync_state_map: Callable[..., dict[str, dict[str, Any]]]
    collect_js_download_state_map: Callable[..., dict[str, dict[str, Any]]]
    collect_request_capture_state_map: Callable[..., dict[str, dict[str, Any]]]
    normalize_sync_status: Callable[[Any], str]
    resolve_scan_pattern: Callable[[str], str]
    get_global_settings: Callable[..., dict[str, Any]]
    normalize_proxy_server: Callable[[Any], str]
    domain_from_target_url: Callable[[str], str]
    resolve_target_url: Callable[[str, str], str]
    queue_project_sync: Callable[..., Any]
    queue_js_download: Callable[..., dict[str, Any]]
    queue_request_capture: Callable[..., dict[str, Any]]
    locate_request_in_chunks: Callable[..., dict[str, Any]]
    load_manual_request_items: Callable[[str], list[dict[str, Any]]]
    save_manual_request_items: Callable[[str, Any], list[dict[str, Any]]]
    load_route_url_profile: Callable[[str], dict[str, Any]]
    save_route_url_profile: Callable[..., dict[str, Any]]
    normalize_hash_style: Callable[[Any], str]
    normalize_basepath: Callable[[Any], str]
    default_route_url_profile: Callable[[], dict[str, Any]]
    read_job: Callable[[str], dict[str, Any]]
    update_job: Callable[..., dict[str, Any]]
    append_log: Callable[[str, str], None]
    sync_control_progress: Callable[..., dict[str, Any]]
    request_capture_job_control: Callable[[str, str], None]
    serialize_sync_job: Callable[..., dict[str, Any]]
    serialize_js_download_job: Callable[..., dict[str, Any]]
    serialize_request_capture_job: Callable[..., dict[str, Any]]
    module2_sync_job_step: str
    module2_js_download_job_step: str
    module2_request_capture_job_step: str
    js_download_default_concurrency: int
    module2_request_default_concurrency: int
    set_error: Callable[[str], None]
    redirect: Callable[[int], Any]
    run_web_action: Callable[..., Any]
    run_chunk_download: Callable[..., Any]
    set_selected_project_domain: Callable[[Any], str]
    dedupe_effective_js_urls: Callable[[list[Any]], list[str]]
    read_lines: Callable[..., list[str]]
    create_job: Callable[..., dict[str, Any]]
    spawn_background: Callable[..., None]
    run_module2_js_download_background: Callable[..., Any]
    safe_file_token: Callable[[str, str], str]


@dataclass(frozen=True)
class VueChunkRouteBundle:
    api_routes: list[Any]
    action_routes: list[Any]


def build_vue_chunk_route_bundle(deps: VueChunkRouteBundleDeps) -> VueChunkRouteBundle:
    api_routes = build_vue_chunk_routes(
        VueChunkRouteDeps(
            ui_state=deps.ui_state,
            safe_str=deps.safe_str,
            to_int=deps.to_int,
            to_bool=deps.to_bool,
            json_ok=deps.json_ok,
            json_error=deps.json_error,
            clear_error=deps.clear_error,
            merge_project_domains=deps.merge_project_domains,
            list_projects=deps.list_projects,
            list_detect_tasks=deps.list_detect_tasks,
            get_project=deps.get_project,
            upsert_project_from_url=deps.upsert_project_from_url,
            update_project_title=deps.update_project_title,
            delete_project=deps.delete_project,
            clear_selected_project_domain=deps.clear_selected_project_domain,
            select_vue_api_domain=deps.select_vue_api_domain,
            load_project_detail=deps.load_project_detail,
            load_project_metrics=deps.load_project_metrics,
            serialize_project=deps.serialize_project,
            normalize_detect_url_rows=deps.normalize_detect_url_rows,
            collect_sync_state_map=deps.collect_sync_state_map,
            collect_js_download_state_map=deps.collect_js_download_state_map,
            collect_request_capture_state_map=deps.collect_request_capture_state_map,
            normalize_sync_status=deps.normalize_sync_status,
            resolve_scan_pattern=deps.resolve_scan_pattern,
            get_global_settings=deps.get_global_settings,
            normalize_proxy_server=deps.normalize_proxy_server,
            domain_from_target_url=deps.domain_from_target_url,
            resolve_target_url=deps.resolve_target_url,
            queue_project_sync=deps.queue_project_sync,
            queue_js_download=deps.queue_js_download,
            queue_request_capture=deps.queue_request_capture,
            locate_request_in_chunks=deps.locate_request_in_chunks,
            load_manual_request_items=deps.load_manual_request_items,
            save_manual_request_items=deps.save_manual_request_items,
            load_route_url_profile=deps.load_route_url_profile,
            save_route_url_profile=deps.save_route_url_profile,
            normalize_hash_style=deps.normalize_hash_style,
            normalize_basepath=deps.normalize_basepath,
            default_route_url_profile=deps.default_route_url_profile,
            read_job=deps.read_job,
            update_job=deps.update_job,
            append_log=deps.append_log,
            sync_control_progress=deps.sync_control_progress,
            request_capture_job_control=deps.request_capture_job_control,
            serialize_sync_job=deps.serialize_sync_job,
            serialize_js_download_job=deps.serialize_js_download_job,
            serialize_request_capture_job=deps.serialize_request_capture_job,
            module2_sync_job_step=deps.module2_sync_job_step,
            module2_js_download_job_step=deps.module2_js_download_job_step,
            module2_request_capture_job_step=deps.module2_request_capture_job_step,
            js_download_default_concurrency=deps.js_download_default_concurrency,
            module2_request_default_concurrency=deps.module2_request_default_concurrency,
        )
    )

    action_routes = build_vue_chunk_action_routes(
        VueChunkActionRouteDeps(
            ui_state=deps.ui_state,
            safe_str=deps.safe_str,
            to_int=deps.to_int,
            to_bool=deps.to_bool,
            set_error=deps.set_error,
            clear_error=deps.clear_error,
            redirect=deps.redirect,
            run_web_action=deps.run_web_action,
            run_chunk_download=deps.run_chunk_download,
            upsert_project_from_url=deps.upsert_project_from_url,
            get_project=deps.get_project,
            queue_project_sync=deps.queue_project_sync,
            select_vue_api_domain=deps.select_vue_api_domain,
            set_selected_project_domain=deps.set_selected_project_domain,
            load_project_detail=deps.load_project_detail,
            dedupe_effective_js_urls=deps.dedupe_effective_js_urls,
            read_lines=deps.read_lines,
            create_job=deps.create_job,
            append_log=deps.append_log,
            spawn_background=deps.spawn_background,
            run_module2_js_download_background=deps.run_module2_js_download_background,
            read_job=deps.read_job,
            safe_file_token=deps.safe_file_token,
            module2_js_download_job_step=deps.module2_js_download_job_step,
            js_download_default_concurrency=deps.js_download_default_concurrency,
        )
    )

    return VueChunkRouteBundle(
        api_routes=api_routes,
        action_routes=action_routes,
    )
