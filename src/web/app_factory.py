from __future__ import annotations

from functools import partial
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware

from src.services import (
    append_log,
    create_job,
    load_api_endpoints,
    read_job,
    run_api_extract,
    run_api_request,
    run_chunk_download,
    run_detect,
    run_project_sync,
    update_job,
)
from src.vue_detection.background import (
    run_module1_detect_background as _module_run_module1_detect_background,
)
from src.vue_detection.task_state import (
    find_detect_task_by_job_id as _module_find_detect_task_by_job_id,
    normalize_detect_url_rows as _module_normalize_detect_url_rows,
    serialize_detect_task as _module_serialize_detect_task,
    serialize_module1_detect_job as _module_serialize_module1_detect_job,
    task_status_is_running as _module_task_status_is_running,
)
from src.vue_api.extractor import (
    list_project_js_files,
    preview_endpoints_from_all_chunks,
    preview_endpoints_from_chunks,
    preview_endpoints_from_js,
    preview_endpoints_from_text,
)
from src.vue_api.auto_regex_runner import run_vue_api_auto_regex as _module_run_vue_api_auto_regex
from src.vue_api.automation_gate import (
    select_auto_pipeline_js_api_path as _module_select_auto_pipeline_js_api_path,
)
from src.vue_api.automation_request import (
    run_auto_request_pipeline as _module_run_auto_request_pipeline,
)
from src.vue_api.models import serialize_api_endpoint as _module_serialize_api_endpoint
from src.vue_api.project_store import (
    load_project_extract_config as _module_load_project_extract_config,
    load_project_extract_result as _module_load_project_extract_result,
    load_project_request_config as _module_load_project_request_config,
    persist_project_preview_extract as _module_persist_project_preview_extract,
    persist_project_request_config as _module_persist_project_request_config,
)
from src.vue_api.saved_results import (
    load_saved_request_results as _module_load_saved_request_results,
    save_saved_request_result as _module_save_saved_request_result,
)
from src.vue_api.request_snapshots import (
    delete_request_run_snapshot as _module_delete_request_run_snapshot,
    load_request_run_snapshots as _module_load_request_run_snapshots,
    save_request_run_snapshot as _module_save_request_run_snapshot,
)
from src.vue_api.request_infer import (
    infer_request_base as _module_infer_request_base,
    infer_request_base_from_paths as _module_infer_request_base_from_paths,
    infer_request_base_from_endpoint_rows as _module_infer_request_base_from_endpoint_rows,
    normalize_endpoint_rows_for_infer as _module_normalize_endpoint_rows_for_infer,
    normalize_url_path as _module_normalize_url_path,
    path_is_suffix_by_segments as _module_path_is_suffix_by_segments,
)
from src.vue_api.requester import (
    build_template_replay_summary as _module_build_template_replay_summary,
    find_api_endpoint_by_id as _module_find_api_endpoint_by_id,
    format_request_payload_text as _module_format_request_payload_text,
    load_saved_response_detail as _module_load_saved_response_detail,
    parse_request_dispatch_inputs as _module_parse_request_dispatch_inputs,
    parse_request_form_inputs as _module_parse_request_form_inputs,
    parse_request_payload_inputs as _module_parse_request_payload_inputs,
    prepare_template_replay_request as _module_prepare_template_replay_request,
)
from src.vue_api.request_batch import (
    queue_request_batch as _module_queue_request_batch,
    run_request_batch_background as _module_run_request_batch_background,
    serialize_request_batch_job as _module_serialize_request_batch_job,
)
from src.vue_api.js_tools import (
    beautify_js_code as _module_beautify_js_code,
    fetch_text_from_url as _module_fetch_text_from_url,
)
from src.vue_api.source_preview import (
    module3_js_source_name_from_url as _module3_js_source_name_from_url,
    module3_source_preview_payload as _module3_source_preview_payload,
)
from src.vue_api.source_loader import (
    list_project_js_urls as _module_list_project_js_urls,
    load_project_js_source as _module_load_project_js_source,
)
from src.vue_chunk.request_capture import (
    load_captured_request_items as _chunk_load_captured_request_items,
    load_captured_request_templates as _chunk_load_captured_request_templates,
    load_manual_request_items as _chunk_load_manual_request_items,
    normalize_basepath,
    normalize_hash_style,
    save_manual_request_items as _chunk_save_manual_request_items,
)
from src.vue_chunk.job_state import (
    collect_js_download_state_map as _module_collect_js_download_state_map,
    collect_request_capture_state_map as _module_collect_request_capture_state_map,
    collect_sync_state_map as _module_collect_sync_state_map,
    domain_from_target_url as _module_domain_from_target_url,
    normalize_sync_status as _module_normalize_sync_status,
    serialize_js_download_job as _module_serialize_js_download_job,
    serialize_request_capture_job as _module_serialize_request_capture_job,
    serialize_sync_job as _module_serialize_sync_job,
)
from src.vue_chunk.background import (
    run_module2_project_sync_background as _module_run_module2_project_sync_background,
    run_module2_js_download_background as _module_run_module2_js_download_background,
    run_module2_request_capture_background as _module_run_module2_request_capture_background,
)
from src.vue_chunk.js_archive import (
    build_project_js_zip as _module_build_project_js_zip,
    cache_project_js_to_downchunk as _module_cache_project_js_to_downchunk,
)
from src.vue_chunk.route_profile import (
    default_route_url_profile as _module_default_route_url_profile,
    load_route_url_profile as _module_load_route_url_profile,
    save_route_url_profile as _module_save_route_url_profile,
)
from src.vue_chunk.job_queue import (
    queue_js_download as _module_queue_js_download,
    queue_project_sync as _module_queue_project_sync,
    queue_request_capture as _module_queue_request_capture,
    resolve_target_url as _module_resolve_target_url,
)
from src.vue_chunk.project_detail import (
    load_project_detail as _module_load_project_detail,
    load_project_metrics as _module_load_project_metrics,
)
from src.vue_chunk.request_locator import locate_request_in_chunks
from src.web.state_store import (
    create_detect_task,
    delete_detect_task,
    delete_project,
    get_detect_task,
    get_project,
    list_detect_tasks,
    list_projects,
    upsert_project_from_url,
    update_project_title,
    update_detect_task,
)
from src.web.app_wiring import WebAppRouteWiringDeps as _WebAppRouteWiringDeps, build_web_app_routes as _build_web_app_routes
from src.web.bootstrap_config import (
    WebBootstrapConfig as _WebBootstrapConfig,
    build_web_bootstrap_config as _build_web_bootstrap_config,
)
from src.web.auth_middleware import ApiAuthMiddleware as _ApiAuthMiddleware
from src.web.sqlite_store import ensure_web_sqlite_schema as _ensure_web_sqlite_schema
from src.web.common import (
    dedupe_effective_js_urls as _dedupe_effective_js_urls,
    normalize_proxy_server as _normalize_proxy_server,
    read_detect_urls as _read_detect_urls,
    read_lines as _read_lines,
    safe_file_token as _safe_file_token,
    safe_str as _safe_str,
    to_bool as _to_bool,
    to_int as _to_int,
)
from src.web.global_settings import (
    get_global_settings as _web_get_global_settings,
    resolve_scan_pattern as _web_resolve_scan_pattern,
    save_global_settings_file as _web_save_global_settings_file,
)
from src.web.http_helpers import (
    json_error as _web_json_error,
    json_ok as _web_json_ok,
    redirect as _web_redirect,
    redirect_detect_task as _web_redirect_detect_task,
)
from src.web.job_control import (
    job_pause_requested as _web_job_pause_requested,
    job_stop_requested as _web_job_stop_requested,
    request_capture_job_control as _web_request_capture_job_control,
    sync_control_progress as _web_sync_control_progress,
)
from src.web.project_view import (
    merge_project_domains as _web_merge_project_domains,
    serialize_project as _web_serialize_project,
)
from src.web.runtime import (
    WebRuntimeBuildDeps as _WebRuntimeBuildDeps,
    build_web_runtime_bundle as _build_web_runtime_bundle,
    spawn_background as _runtime_spawn_background,
)
from src.web.shared_bundle import WebSharedBundleDeps as _WebSharedBundleDeps, build_web_shared_bundle as _build_web_shared_bundle
from src.web.ui_defaults import (
    build_default_ui_state as _build_default_ui_state,
)
from src.web.ui_feedback import clear_error as _web_clear_error, set_error as _web_set_error
from src.web.uploads import save_uploaded_file as _web_save_uploaded_file
from src.web.vue_chunk_runtime import (
    VueChunkRuntimeBuildDeps as _VueChunkRuntimeBuildDeps,
    build_vue_chunk_runtime_bundle as _build_vue_chunk_runtime_bundle,
)
from src.web.vue_api_state import (
    apply_vue_api_form as _web_apply_vue_api_form,
    apply_vue_api_request_form as _web_apply_vue_api_request_form,
    clear_selected_project_domain as _web_clear_selected_project_domain,
    get_vue_api_config_for_domain as _web_get_vue_api_config_for_domain,
    prepare_vue_api_context_state as _web_prepare_vue_api_context_state,
    reset_vue_api_runtime_outputs as _web_reset_vue_api_runtime_outputs,
    resolve_vue_api_pattern_config as _web_resolve_vue_api_pattern_config,
    save_vue_api_config as _web_save_vue_api_config,
    select_vue_api_domain as _web_select_vue_api_domain,
    set_selected_project_domain as _web_set_selected_project_domain,
    set_vue_api_beautify_result as _web_set_vue_api_beautify_result,
    set_vue_api_extract_result as _web_set_vue_api_extract_result,
    set_vue_api_preview_result as _web_set_vue_api_preview_result,
    set_vue_api_request_result as _web_set_vue_api_request_result,
    sync_vue_api_request_state as _web_sync_vue_api_request_state,
    sync_vue_api_source_form as _web_sync_vue_api_source_form,
)


BOOTSTRAP_CONFIG: _WebBootstrapConfig = _build_web_bootstrap_config()
_ensure_web_sqlite_schema(BOOTSTRAP_CONFIG.sqlite_db_file)


UI_STATE: dict[str, Any] = _build_default_ui_state(
    detect_default_concurrency=BOOTSTRAP_CONFIG.detect_default_concurrency,
    auto_scan_pattern=BOOTSTRAP_CONFIG.module2_auto_scan_pattern,
)

WEB_SHARED_BUNDLE = _build_web_shared_bundle(
    _WebSharedBundleDeps(
        ui_state=UI_STATE,
        database_file=BOOTSTRAP_CONFIG.sqlite_db_file,
        settings_file=BOOTSTRAP_CONFIG.global_settings_file,
        auto_scan_pattern=BOOTSTRAP_CONFIG.module2_auto_scan_pattern,
        upload_dir=BOOTSTRAP_CONFIG.web_upload_dir,
        upload_extensions=BOOTSTRAP_CONFIG.upload_extensions,
        projects_dir=BOOTSTRAP_CONFIG.projects_dir,
        safe_str=_safe_str,
        to_int=_to_int,
        web_get_global_settings=_web_get_global_settings,
        web_save_global_settings_file=_web_save_global_settings_file,
        web_resolve_scan_pattern=_web_resolve_scan_pattern,
        web_save_uploaded_file=_web_save_uploaded_file,
        web_merge_project_domains=_web_merge_project_domains,
        web_serialize_project=_web_serialize_project,
        module_run_vue_api_auto_regex=_module_run_vue_api_auto_regex,
        list_project_js_files=list_project_js_files,
        load_request_capture_items=_chunk_load_captured_request_items,
        normalize_target_path=_module_normalize_url_path,
        locate_request_in_chunks=locate_request_in_chunks,
        preview_endpoints_from_all_chunks=preview_endpoints_from_all_chunks,
        max_scan_files=BOOTSTRAP_CONFIG.module3_auto_regex_max_scan_files,
        web_job_stop_requested=_web_job_stop_requested,
        web_job_pause_requested=_web_job_pause_requested,
        web_sync_control_progress=_web_sync_control_progress,
        web_request_capture_job_control=_web_request_capture_job_control,
        read_job=read_job,
        update_job=update_job,
        append_log=append_log,
        normalize_sync_status=_module_normalize_sync_status,
        module2_request_capture_job_step=BOOTSTRAP_CONFIG.module2_request_capture_job_step,
        web_set_error=_web_set_error,
        web_clear_error=_web_clear_error,
        web_redirect=_web_redirect,
        web_redirect_detect_task=_web_redirect_detect_task,
        web_json_error=_web_json_error,
        web_json_ok=_web_json_ok,
    )
)

GET_GLOBAL_SETTINGS = WEB_SHARED_BUNDLE.get_global_settings
SAVE_GLOBAL_SETTINGS_FILE = WEB_SHARED_BUNDLE.save_global_settings_file
RESOLVE_SCAN_PATTERN = WEB_SHARED_BUNDLE.resolve_scan_pattern
SAVE_UPLOADED_FILE = WEB_SHARED_BUNDLE.save_uploaded_file
MERGE_PROJECT_DOMAINS = WEB_SHARED_BUNDLE.merge_project_domains
SERIALIZE_PROJECT = WEB_SHARED_BUNDLE.serialize_project
RUN_VUE_API_AUTO_REGEX = WEB_SHARED_BUNDLE.run_vue_api_auto_regex
CACHE_PROJECT_JS_TO_DOWNCHUNK = _module_cache_project_js_to_downchunk
BUILD_PROJECT_JS_ZIP = _module_build_project_js_zip
JOB_STOP_REQUESTED = WEB_SHARED_BUNDLE.job_stop_requested
JOB_PAUSE_REQUESTED = WEB_SHARED_BUNDLE.job_pause_requested
SYNC_CONTROL_PROGRESS = WEB_SHARED_BUNDLE.sync_control_progress
REQUEST_CAPTURE_JOB_CONTROL = WEB_SHARED_BUNDLE.request_capture_job_control
SET_ERROR = WEB_SHARED_BUNDLE.set_error
CLEAR_ERROR = WEB_SHARED_BUNDLE.clear_error
REDIRECT = WEB_SHARED_BUNDLE.redirect
REDIRECT_DETECT_TASK = WEB_SHARED_BUNDLE.redirect_detect_task
JSON_ERROR = WEB_SHARED_BUNDLE.json_error
JSON_OK = WEB_SHARED_BUNDLE.json_ok

RUN_VUE_REQUEST_BATCH_BACKGROUND = partial(
    _module_run_request_batch_background,
    job_step=BOOTSTRAP_CONFIG.vue_request_batch_job_step,
    load_api_endpoints=load_api_endpoints,
    find_api_endpoint_by_id=_module_find_api_endpoint_by_id,
    prepare_template_replay_request=_module_prepare_template_replay_request,
    run_api_request=run_api_request,
    load_saved_response_detail=_module_load_saved_response_detail,
    build_template_replay_summary=_module_build_template_replay_summary,
    append_log=append_log,
    update_job=update_job,
    job_stop_requested=JOB_STOP_REQUESTED,
    job_pause_requested=JOB_PAUSE_REQUESTED,
)
QUEUE_REQUEST_BATCH = partial(
    _module_queue_request_batch,
    job_step=BOOTSTRAP_CONFIG.vue_request_batch_job_step,
    create_job=create_job,
    append_log=append_log,
    update_job=update_job,
    spawn_background=_runtime_spawn_background,
    run_background=RUN_VUE_REQUEST_BATCH_BACKGROUND,
)

# Web 层统一在这里绑定后台任务和 VueChunk 排队服务，避免 app.py 再保留大段 partial 装配。
WEB_RUNTIME_BUNDLE = _build_web_runtime_bundle(
    _WebRuntimeBuildDeps(
        create_job=create_job,
        append_log=append_log,
        update_job=update_job,
        module_run_module1_detect_background=_module_run_module1_detect_background,
        update_detect_task=update_detect_task,
        run_detect=run_detect,
        normalize_detect_url_rows=_module_normalize_detect_url_rows,
        read_detect_urls=_read_detect_urls,
        job_stop_requested=JOB_STOP_REQUESTED,
        job_pause_requested=JOB_PAUSE_REQUESTED,
        safe_str=_safe_str,
        to_int=_to_int,
        module1_detect_job_step=BOOTSTRAP_CONFIG.module1_detect_job_step,
        module_run_module2_project_sync_background=_module_run_module2_project_sync_background,
        run_project_sync=run_project_sync,
        normalize_proxy_server=_normalize_proxy_server,
        domain_from_target_url=_module_domain_from_target_url,
        sync_control_progress=SYNC_CONTROL_PROGRESS,
        request_capture_job_control=REQUEST_CAPTURE_JOB_CONTROL,
        queue_request_capture=lambda **kwargs: MODULE2_QUEUE_REQUEST_CAPTURE(**kwargs),
        read_job=read_job,
        normalize_sync_status=_module_normalize_sync_status,
        serialize_request_capture_job=lambda job, fallback_domain, default_concurrency: _module_serialize_request_capture_job(
            job,
            fallback_domain=fallback_domain,
            default_concurrency=default_concurrency,
        ),
        module2_request_default_concurrency=BOOTSTRAP_CONFIG.module2_request_default_concurrency,
        select_auto_pipeline_js_api_path=partial(
            _module_select_auto_pipeline_js_api_path,
            load_captured_request_items=_chunk_load_captured_request_items,
            locate_request_in_chunks=locate_request_in_chunks,
        ),
        run_vue_api_auto_regex=RUN_VUE_API_AUTO_REGEX,
        run_auto_request_pipeline=partial(
            _module_run_auto_request_pipeline,
            load_captured_request_items=_chunk_load_captured_request_items,
            queue_request_batch=QUEUE_REQUEST_BATCH,
            read_job=read_job,
            update_job=update_job,
            save_request_run_snapshot=_module_save_request_run_snapshot,
            append_log=append_log,
            concurrency=BOOTSTRAP_CONFIG.module2_request_default_concurrency,
        ),
        resolve_scan_pattern=RESOLVE_SCAN_PATTERN,
        save_vue_api_config=lambda domain, pattern: _web_save_vue_api_config(
            UI_STATE,
            domain,
            pattern,
            safe_str=_safe_str,
        ),
        run_api_extract=run_api_extract,
        load_api_endpoints=load_api_endpoints,
        normalize_endpoint_rows_for_infer=_module_normalize_endpoint_rows_for_infer,
        serialize_api_endpoint=_module_serialize_api_endpoint,
        infer_request_base_from_endpoint_rows=_module_infer_request_base_from_endpoint_rows,
        sync_vue_api_source_form=lambda **kwargs: _web_sync_vue_api_source_form(
            UI_STATE,
            safe_str=_safe_str,
            **kwargs,
        ),
        sync_vue_api_request_state=lambda **kwargs: _web_sync_vue_api_request_state(
            UI_STATE,
            safe_str=_safe_str,
            **kwargs,
        ),
        persist_project_request_config=_module_persist_project_request_config,
        module2_sync_job_step=BOOTSTRAP_CONFIG.module2_sync_job_step,
        module_run_module2_js_download_background=_module_run_module2_js_download_background,
        cache_project_js_to_downchunk=CACHE_PROJECT_JS_TO_DOWNCHUNK,
        build_project_js_zip=BUILD_PROJECT_JS_ZIP,
        projects_dir=BOOTSTRAP_CONFIG.projects_dir,
        module2_js_download_job_step=BOOTSTRAP_CONFIG.module2_js_download_job_step,
        module_run_module2_request_capture_background=_module_run_module2_request_capture_background,
        read_lines=_read_lines,
        dedupe_effective_js_urls=_dedupe_effective_js_urls,
        js_download_default_concurrency=BOOTSTRAP_CONFIG.js_download_default_concurrency,
        module2_request_capture_job_step=BOOTSTRAP_CONFIG.module2_request_capture_job_step,
        module2_route_style_sample_size=BOOTSTRAP_CONFIG.module2_route_style_sample_size,
    )
)

WEB_RUN_ACTION = WEB_RUNTIME_BUNDLE.run_web_action
SPAWN_BACKGROUND = WEB_RUNTIME_BUNDLE.spawn_background
RUN_MODULE1_DETECT_BACKGROUND = WEB_RUNTIME_BUNDLE.run_module1_detect_background
RUN_MODULE2_PROJECT_SYNC_BACKGROUND = WEB_RUNTIME_BUNDLE.run_module2_project_sync_background
RUN_MODULE2_JS_DOWNLOAD_BACKGROUND = WEB_RUNTIME_BUNDLE.run_module2_js_download_background
RUN_MODULE2_REQUEST_CAPTURE_BACKGROUND = WEB_RUNTIME_BUNDLE.run_module2_request_capture_background

VUE_CHUNK_RUNTIME_BUNDLE = _build_vue_chunk_runtime_bundle(
    _VueChunkRuntimeBuildDeps(
        ui_state=UI_STATE,
        safe_str=_safe_str,
        select_vue_api_domain=partial(_web_select_vue_api_domain, UI_STATE, safe_str=_safe_str),
        set_selected_project_domain=partial(_web_set_selected_project_domain, UI_STATE, safe_str=_safe_str),
        queue_project_sync_impl=_module_queue_project_sync,
        upsert_project_from_url=upsert_project_from_url,
        normalize_proxy_server=_normalize_proxy_server,
        get_global_settings=GET_GLOBAL_SETTINGS,
        create_job=create_job,
        append_log=append_log,
        update_job=update_job,
        module2_sync_job_step=BOOTSTRAP_CONFIG.module2_sync_job_step,
        spawn_background=SPAWN_BACKGROUND,
        run_module2_project_sync_background=RUN_MODULE2_PROJECT_SYNC_BACKGROUND,
        queue_js_download_impl=_module_queue_js_download,
        load_project_detail=_module_load_project_detail,
        read_lines=_read_lines,
        dedupe_effective_js_urls=_dedupe_effective_js_urls,
        module2_js_download_job_step=BOOTSTRAP_CONFIG.module2_js_download_job_step,
        run_module2_js_download_background=RUN_MODULE2_JS_DOWNLOAD_BACKGROUND,
        queue_request_capture_impl=_module_queue_request_capture,
        load_route_url_profile=_module_load_route_url_profile,
        module2_request_capture_job_step=BOOTSTRAP_CONFIG.module2_request_capture_job_step,
        run_module2_request_capture_background=RUN_MODULE2_REQUEST_CAPTURE_BACKGROUND,
        resolve_target_url_impl=_module_resolve_target_url,
        get_project=get_project,
        collect_sync_state_map=lambda limit=600: _module_collect_sync_state_map(
            jobs_dir=BOOTSTRAP_CONFIG.jobs_dir,
            module2_sync_job_step=BOOTSTRAP_CONFIG.module2_sync_job_step,
            limit=limit,
        ),
    )
)

MODULE2_QUEUE_PROJECT_SYNC = VUE_CHUNK_RUNTIME_BUNDLE.queue_project_sync
MODULE2_QUEUE_JS_DOWNLOAD = VUE_CHUNK_RUNTIME_BUNDLE.queue_js_download
MODULE2_QUEUE_REQUEST_CAPTURE = VUE_CHUNK_RUNTIME_BUNDLE.queue_request_capture
MODULE2_RESOLVE_TARGET_URL = VUE_CHUNK_RUNTIME_BUNDLE.resolve_target_url

APP_ROUTE_WIRING = _build_web_app_routes(
    _WebAppRouteWiringDeps(
        ui_state=UI_STATE,
        templates=BOOTSTRAP_CONFIG.templates,
        frontend_dir=BOOTSTRAP_CONFIG.frontend_dir,
        frontend_dist_dir=BOOTSTRAP_CONFIG.frontend_dist_dir,
        static_dir=BOOTSTRAP_CONFIG.static_dir,
        jobs_dir=BOOTSTRAP_CONFIG.jobs_dir,
        shared_bundle=WEB_SHARED_BUNDLE,
        web_runtime_bundle=WEB_RUNTIME_BUNDLE,
        vue_chunk_runtime_bundle=VUE_CHUNK_RUNTIME_BUNDLE,
        safe_str=_safe_str,
        to_int=_to_int,
        to_bool=_to_bool,
        normalize_detect_url_rows=_module_normalize_detect_url_rows,
        read_detect_urls=_read_detect_urls,
        list_detect_tasks=list_detect_tasks,
        list_projects=list_projects,
        get_project=get_project,
        get_detect_task=get_detect_task,
        read_job=read_job,
        update_job=update_job,
        append_log=append_log,
        create_job=create_job,
        create_detect_task=create_detect_task,
        update_detect_task=update_detect_task,
        delete_detect_task=delete_detect_task,
        delete_project=delete_project,
        upsert_project_from_url=upsert_project_from_url,
        update_project_title=update_project_title,
        load_project_detail=_module_load_project_detail,
        load_project_metrics=_module_load_project_metrics,
        load_project_extract_config=_module_load_project_extract_config,
        load_project_request_config=_module_load_project_request_config,
        persist_project_preview_extract=_module_persist_project_preview_extract,
        persist_project_request_config=_module_persist_project_request_config,
        list_project_js_files=list_project_js_files,
        list_project_js_urls=_module_list_project_js_urls,
        load_project_extract_result=_module_load_project_extract_result,
        load_api_endpoints=load_api_endpoints,
        prepare_vue_api_context_state=_web_prepare_vue_api_context_state,
        load_project_js_source=_module_load_project_js_source,
        fetch_text_from_url=_module_fetch_text_from_url,
        build_source_preview_payload=_module3_source_preview_payload,
        beautify_js_code=_module_beautify_js_code,
        js_source_name_from_url=_module3_js_source_name_from_url,
        preview_endpoints_from_js=preview_endpoints_from_js,
        preview_endpoints_from_text=preview_endpoints_from_text,
        preview_endpoints_from_all_chunks=preview_endpoints_from_all_chunks,
        serialize_api_endpoint=_module_serialize_api_endpoint,
        run_api_extract=run_api_extract,
        run_api_request=run_api_request,
        run_chunk_download=run_chunk_download,
        web_select_vue_api_domain=_web_select_vue_api_domain,
        web_set_selected_project_domain=_web_set_selected_project_domain,
        web_clear_selected_project_domain=_web_clear_selected_project_domain,
        web_get_vue_api_config_for_domain=_web_get_vue_api_config_for_domain,
        web_save_vue_api_config=_web_save_vue_api_config,
        web_sync_vue_api_source_form=_web_sync_vue_api_source_form,
        web_set_vue_api_beautify_result=_web_set_vue_api_beautify_result,
        web_set_vue_api_preview_result=_web_set_vue_api_preview_result,
        web_set_vue_api_extract_result=_web_set_vue_api_extract_result,
        web_reset_vue_api_runtime_outputs=_web_reset_vue_api_runtime_outputs,
        web_apply_vue_api_form=_web_apply_vue_api_form,
        web_resolve_vue_api_pattern_config=_web_resolve_vue_api_pattern_config,
        web_apply_vue_api_request_form=_web_apply_vue_api_request_form,
        web_sync_vue_api_request_state=_web_sync_vue_api_request_state,
        web_set_vue_api_request_result=_web_set_vue_api_request_result,
        load_captured_request_items=_chunk_load_captured_request_items,
        load_captured_request_templates=_chunk_load_captured_request_templates,
        load_manual_request_items=_chunk_load_manual_request_items,
        save_manual_request_items=_chunk_save_manual_request_items,
        infer_request_base=_module_infer_request_base,
        infer_request_base_from_paths=_module_infer_request_base_from_paths,
        parse_request_dispatch_inputs=_module_parse_request_dispatch_inputs,
        parse_request_payload_inputs=_module_parse_request_payload_inputs,
        parse_request_form_inputs=_module_parse_request_form_inputs,
        find_api_endpoint_by_id=_module_find_api_endpoint_by_id,
        prepare_template_replay_request=_module_prepare_template_replay_request,
        queue_request_batch=QUEUE_REQUEST_BATCH,
        load_saved_response_detail=_module_load_saved_response_detail,
        load_saved_request_results=_module_load_saved_request_results,
        save_saved_request_result=_module_save_saved_request_result,
        load_request_run_snapshots=_module_load_request_run_snapshots,
        save_request_run_snapshot=_module_save_request_run_snapshot,
        delete_request_run_snapshot=_module_delete_request_run_snapshot,
        format_request_payload_text=_module_format_request_payload_text,
        build_template_replay_summary=_module_build_template_replay_summary,
        locate_request_in_chunks=locate_request_in_chunks,
        load_route_url_profile=_module_load_route_url_profile,
        save_route_url_profile=_module_save_route_url_profile,
        normalize_hash_style=normalize_hash_style,
        normalize_basepath=normalize_basepath,
        default_route_url_profile=_module_default_route_url_profile,
        normalize_proxy_server=_normalize_proxy_server,
        dedupe_effective_js_urls=_dedupe_effective_js_urls,
        read_lines=_read_lines,
        safe_file_token=_safe_file_token,
        collect_sync_state_map=_module_collect_sync_state_map,
        collect_js_download_state_map=_module_collect_js_download_state_map,
        collect_request_capture_state_map=_module_collect_request_capture_state_map,
        normalize_sync_status=_module_normalize_sync_status,
        domain_from_target_url=_module_domain_from_target_url,
        serialize_sync_job=_module_serialize_sync_job,
        serialize_js_download_job=_module_serialize_js_download_job,
        serialize_request_capture_job=_module_serialize_request_capture_job,
        serialize_request_batch_job=_module_serialize_request_batch_job,
        serialize_detect_task=_module_serialize_detect_task,
        serialize_module1_detect_job=_module_serialize_module1_detect_job,
        find_detect_task_by_job_id=_module_find_detect_task_by_job_id,
        task_status_is_running=_module_task_status_is_running,
        module1_detect_job_step=BOOTSTRAP_CONFIG.module1_detect_job_step,
        module2_sync_job_step=BOOTSTRAP_CONFIG.module2_sync_job_step,
        module2_js_download_job_step=BOOTSTRAP_CONFIG.module2_js_download_job_step,
        module2_request_capture_job_step=BOOTSTRAP_CONFIG.module2_request_capture_job_step,
        vue_request_batch_job_step=BOOTSTRAP_CONFIG.vue_request_batch_job_step,
        detect_default_concurrency=BOOTSTRAP_CONFIG.detect_default_concurrency,
        detect_default_timeout=BOOTSTRAP_CONFIG.detect_default_timeout,
        detect_default_wait_ms=BOOTSTRAP_CONFIG.detect_default_wait_ms,
        js_download_default_concurrency=BOOTSTRAP_CONFIG.js_download_default_concurrency,
        module2_request_default_concurrency=BOOTSTRAP_CONFIG.module2_request_default_concurrency,
        module3_js_max_display_chars=BOOTSTRAP_CONFIG.module3_js_max_display_chars,
    )
)

routes = APP_ROUTE_WIRING.routes

app = Starlette(
    debug=False,
    routes=routes,
    middleware=[
        Middleware(
            _ApiAuthMiddleware,
            database_file=BOOTSTRAP_CONFIG.sqlite_db_file,
        )
    ],
)


