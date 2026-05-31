from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Any, Callable


@dataclass(frozen=True)
class WebSharedBundleDeps:
    # 这一层统一装配 app.py 会反复复用的轻量 helper callable。
    ui_state: dict[str, Any]
    database_file: Any
    settings_file: Any
    auto_scan_pattern: str
    upload_dir: Any
    upload_extensions: set[str]
    projects_dir: Any
    safe_str: Callable[[Any, str], str]
    to_int: Callable[[Any, int, int], int]
    web_get_global_settings: Callable[..., dict[str, Any]]
    web_save_global_settings_file: Callable[..., dict[str, Any]]
    web_resolve_scan_pattern: Callable[..., str]
    web_save_uploaded_file: Callable[..., Any]
    web_merge_project_domains: Callable[..., list[str]]
    web_serialize_project: Callable[..., dict[str, Any]]
    module_run_vue_api_auto_regex: Callable[..., dict[str, Any]]
    list_project_js_files: Callable[[str], list[Any]]
    load_request_capture_items: Callable[[str], list[dict[str, Any]]]
    normalize_target_path: Callable[[str], str]
    locate_request_in_chunks: Callable[..., dict[str, Any]]
    preview_endpoints_from_all_chunks: Callable[..., list[Any]]
    max_scan_files: int
    web_job_stop_requested: Callable[..., bool]
    web_job_pause_requested: Callable[..., bool]
    web_sync_control_progress: Callable[..., dict[str, Any]]
    web_request_capture_job_control: Callable[..., None]
    read_job: Callable[[str], dict[str, Any]]
    update_job: Callable[..., dict[str, Any]]
    append_log: Callable[[str, str], None]
    normalize_sync_status: Callable[[Any], str]
    module2_request_capture_job_step: str
    web_set_error: Callable[[dict[str, Any], str], None]
    web_clear_error: Callable[[dict[str, Any]], None]
    web_redirect: Callable[[int], Any]
    web_redirect_detect_task: Callable[..., Any]
    web_json_error: Callable[..., Any]
    web_json_ok: Callable[..., Any]


@dataclass(frozen=True)
class WebSharedBundle:
    database_file: Any
    get_global_settings: Callable[..., dict[str, Any]]
    save_global_settings_file: Callable[[Any], dict[str, Any]]
    resolve_scan_pattern: Callable[[str], str]
    save_uploaded_file: Callable[..., Any]
    merge_project_domains: Callable[[list[dict[str, Any]]], list[str]]
    serialize_project: Callable[[dict[str, Any]], dict[str, Any]]
    run_vue_api_auto_regex: Callable[..., dict[str, Any]]
    job_stop_requested: Callable[[str], bool]
    job_pause_requested: Callable[[str], bool]
    sync_control_progress: Callable[..., dict[str, Any]]
    request_capture_job_control: Callable[[str, str], None]
    set_error: Callable[[str], None]
    clear_error: Callable[[], None]
    redirect: Callable[[int], Any]
    redirect_detect_task: Callable[[str], Any]
    json_error: Callable[..., Any]
    json_ok: Callable[..., Any]


def build_web_shared_bundle(deps: WebSharedBundleDeps) -> WebSharedBundle:
    get_global_settings = partial(
        deps.web_get_global_settings,
        ui_state=deps.ui_state,
        database_file=deps.database_file,
        settings_file=deps.settings_file,
        auto_scan_pattern=deps.auto_scan_pattern,
    )
    sync_control_progress = partial(
        deps.web_sync_control_progress,
        safe_str=deps.safe_str,
    )
    return WebSharedBundle(
        database_file=deps.database_file,
        get_global_settings=get_global_settings,
        save_global_settings_file=partial(
            deps.web_save_global_settings_file,
            database_file=deps.database_file,
            settings_file=deps.settings_file,
            ui_state=deps.ui_state,
            auto_scan_pattern=deps.auto_scan_pattern,
        ),
        resolve_scan_pattern=partial(
            deps.web_resolve_scan_pattern,
            get_global_settings=get_global_settings,
            auto_scan_pattern=deps.auto_scan_pattern,
        ),
        save_uploaded_file=partial(
            deps.web_save_uploaded_file,
            upload_dir=deps.upload_dir,
            upload_extensions=deps.upload_extensions,
            safe_str=deps.safe_str,
        ),
        merge_project_domains=partial(
            deps.web_merge_project_domains,
            projects_dir=deps.projects_dir,
            safe_str=deps.safe_str,
        ),
        serialize_project=partial(
            deps.web_serialize_project,
            safe_str=deps.safe_str,
        ),
        run_vue_api_auto_regex=partial(
            deps.module_run_vue_api_auto_regex,
            auto_scan_pattern=deps.auto_scan_pattern,
            get_global_settings=get_global_settings,
            safe_str=deps.safe_str,
            to_int=deps.to_int,
            list_project_js_files=deps.list_project_js_files,
            load_request_capture_items=deps.load_request_capture_items,
            normalize_target_path=deps.normalize_target_path,
            locate_request_in_chunks=deps.locate_request_in_chunks,
            preview_endpoints_from_all_chunks=deps.preview_endpoints_from_all_chunks,
            max_scan_files=deps.max_scan_files,
        ),
        job_stop_requested=partial(
            deps.web_job_stop_requested,
            read_job=deps.read_job,
            safe_str=deps.safe_str,
        ),
        job_pause_requested=partial(
            deps.web_job_pause_requested,
            read_job=deps.read_job,
            safe_str=deps.safe_str,
        ),
        sync_control_progress=sync_control_progress,
        request_capture_job_control=partial(
            deps.web_request_capture_job_control,
            read_job=deps.read_job,
            update_job=deps.update_job,
            append_log=deps.append_log,
            safe_str=deps.safe_str,
            normalize_sync_status=deps.normalize_sync_status,
            module2_request_capture_job_step=deps.module2_request_capture_job_step,
            sync_control_progress=sync_control_progress,
        ),
        set_error=partial(deps.web_set_error, deps.ui_state),
        clear_error=partial(deps.web_clear_error, deps.ui_state),
        redirect=deps.web_redirect,
        redirect_detect_task=partial(
            deps.web_redirect_detect_task,
            safe_str=deps.safe_str,
        ),
        json_error=partial(
            deps.web_json_error,
            safe_str=deps.safe_str,
        ),
        json_ok=deps.web_json_ok,
    )
