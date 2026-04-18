from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.web.page_context import PageContextBuildDeps, build_page_context, build_page_context_deps
from src.web.route_table import WebRouteTableDeps, build_web_routes
from src.web.routes.core_bundle import CoreRouteBundleDeps, build_core_route_bundle
from src.web.routes.vue_api_bundle import VueApiRouteBundleDeps, build_vue_api_route_bundle
from src.web.routes.vue_chunk_bundle import VueChunkRouteBundleDeps, build_vue_chunk_route_bundle
from src.web.routes.vue_detect_bundle import VueDetectRouteBundleDeps, build_vue_detect_route_bundle
from src.web.routes.vue_request_bundle import VueRequestRouteBundleDeps, build_vue_request_route_bundle


@dataclass(frozen=True)
class WebAppRouteWiringDeps:
    # 这一层专门负责把页面上下文、各业务路由 bundle 和最终路由表串起来。
    ui_state: dict[str, Any]
    templates: Any
    frontend_dir: Path
    frontend_dist_dir: Path
    static_dir: Path
    jobs_dir: Path
    shared_bundle: Any
    web_runtime_bundle: Any
    vue_chunk_runtime_bundle: Any
    safe_str: Any
    to_int: Any
    to_bool: Any
    normalize_detect_url_rows: Any
    read_detect_urls: Any
    list_detect_tasks: Any
    list_projects: Any
    get_project: Any
    get_detect_task: Any
    read_job: Any
    update_job: Any
    append_log: Any
    create_job: Any
    create_detect_task: Any
    update_detect_task: Any
    delete_detect_task: Any
    delete_project: Any
    upsert_project_from_url: Any
    update_project_title: Any
    load_project_detail: Any
    load_project_metrics: Any
    load_project_extract_config: Any
    load_project_request_config: Any
    persist_project_request_config: Any
    persist_project_preview_extract: Any
    list_project_js_files: Any
    list_project_js_urls: Any
    load_project_extract_result: Any
    load_api_endpoints: Any
    prepare_vue_api_context_state: Any
    load_project_js_source: Any
    fetch_text_from_url: Any
    build_source_preview_payload: Any
    beautify_js_code: Any
    js_source_name_from_url: Any
    preview_endpoints_from_js: Any
    preview_endpoints_from_text: Any
    preview_endpoints_from_all_chunks: Any
    serialize_api_endpoint: Any
    run_api_extract: Any
    run_api_request: Any
    run_chunk_download: Any
    web_select_vue_api_domain: Any
    web_set_selected_project_domain: Any
    web_clear_selected_project_domain: Any
    web_get_vue_api_config_for_domain: Any
    web_save_vue_api_config: Any
    web_sync_vue_api_source_form: Any
    web_set_vue_api_beautify_result: Any
    web_set_vue_api_preview_result: Any
    web_set_vue_api_extract_result: Any
    web_reset_vue_api_runtime_outputs: Any
    web_apply_vue_api_form: Any
    web_resolve_vue_api_pattern_config: Any
    web_apply_vue_api_request_form: Any
    web_sync_vue_api_request_state: Any
    web_set_vue_api_request_result: Any
    load_captured_request_items: Any
    load_captured_request_templates: Any
    load_manual_request_items: Any
    save_manual_request_items: Any
    infer_request_base: Any
    infer_request_base_from_paths: Any
    parse_request_dispatch_inputs: Any
    parse_request_payload_inputs: Any
    parse_request_form_inputs: Any
    find_api_endpoint_by_id: Any
    prepare_template_replay_request: Any
    queue_request_batch: Any
    load_saved_response_detail: Any
    load_saved_request_results: Any
    save_saved_request_result: Any
    load_request_run_snapshots: Any
    save_request_run_snapshot: Any
    delete_request_run_snapshot: Any
    format_request_payload_text: Any
    build_template_replay_summary: Any
    locate_request_in_chunks: Any
    load_route_url_profile: Any
    save_route_url_profile: Any
    normalize_hash_style: Any
    normalize_basepath: Any
    default_route_url_profile: Any
    normalize_proxy_server: Any
    dedupe_effective_js_urls: Any
    read_lines: Any
    safe_file_token: Any
    collect_sync_state_map: Any
    collect_js_download_state_map: Any
    collect_request_capture_state_map: Any
    normalize_sync_status: Any
    domain_from_target_url: Any
    serialize_sync_job: Any
    serialize_js_download_job: Any
    serialize_request_capture_job: Any
    serialize_request_batch_job: Any
    serialize_detect_task: Any
    serialize_module1_detect_job: Any
    find_detect_task_by_job_id: Any
    task_status_is_running: Any
    module1_detect_job_step: str
    module2_sync_job_step: str
    module2_js_download_job_step: str
    module2_request_capture_job_step: str
    vue_request_batch_job_step: str
    detect_default_concurrency: int
    detect_default_timeout: int
    detect_default_wait_ms: int
    js_download_default_concurrency: int
    module2_request_default_concurrency: int
    module3_js_max_display_chars: int


@dataclass(frozen=True)
class WebAppRouteWiringBundle:
    routes: list[Any]


def build_web_app_routes(deps: WebAppRouteWiringDeps) -> WebAppRouteWiringBundle:
    page_context_deps = build_page_context_deps(
        PageContextBuildDeps(
            ui_state=deps.ui_state,
            safe_str=deps.safe_str,
            to_int=deps.to_int,
            normalize_detect_url_rows=deps.normalize_detect_url_rows,
            read_detect_urls=deps.read_detect_urls,
            list_detect_tasks=deps.list_detect_tasks,
            list_projects=deps.list_projects,
            merge_project_domains=deps.shared_bundle.merge_project_domains,
            load_project_metrics=deps.load_project_metrics,
            set_selected_project_domain=lambda domain: deps.web_set_selected_project_domain(
                deps.ui_state,
                domain,
                safe_str=deps.safe_str,
            ),
            get_project=deps.get_project,
            load_project_detail=deps.load_project_detail,
            prepare_vue_api_context_state=deps.prepare_vue_api_context_state,
            load_project_extract_config=deps.load_project_extract_config,
            load_project_request_config=deps.load_project_request_config,
            list_project_js_files=deps.list_project_js_files,
            load_api_endpoints=deps.load_api_endpoints,
            read_job=deps.read_job,
        )
    )

    core_route_bundle = build_core_route_bundle(
        CoreRouteBundleDeps(
            ui_state=deps.ui_state,
            templates=deps.templates,
            frontend_dir=deps.frontend_dir,
            frontend_dist_dir=deps.frontend_dist_dir,
            safe_str=deps.safe_str,
            set_error=deps.shared_bundle.set_error,
            clear_error=deps.shared_bundle.clear_error,
            redirect=deps.shared_bundle.redirect,
            json_error=deps.shared_bundle.json_error,
            json_ok=deps.shared_bundle.json_ok,
            select_vue_api_domain=lambda domain: deps.web_select_vue_api_domain(
                deps.ui_state,
                domain,
                safe_str=deps.safe_str,
            ),
            load_project_detail=deps.load_project_detail,
            get_detect_task=deps.get_detect_task,
            build_page_context=build_page_context,
            page_context_deps=page_context_deps,
            get_global_settings=deps.shared_bundle.get_global_settings,
            save_global_settings_file=deps.shared_bundle.save_global_settings_file,
            database_file=deps.shared_bundle.database_file,
        )
    )

    vue_detect_route_bundle = build_vue_detect_route_bundle(
        VueDetectRouteBundleDeps(
            ui_state=deps.ui_state,
            safe_str=deps.safe_str,
            to_int=deps.to_int,
            to_bool=deps.to_bool,
            json_ok=deps.shared_bundle.json_ok,
            json_error=deps.shared_bundle.json_error,
            clear_error=deps.shared_bundle.clear_error,
            save_uploaded_file=deps.shared_bundle.save_uploaded_file,
            create_job=deps.create_job,
            append_log=deps.append_log,
            create_detect_task=deps.create_detect_task,
            spawn_background=deps.web_runtime_bundle.spawn_background,
            run_module1_detect_background=deps.web_runtime_bundle.run_module1_detect_background,
            update_detect_task=deps.update_detect_task,
            update_job=deps.update_job,
            read_job=deps.read_job,
            get_detect_task=deps.get_detect_task,
            delete_detect_task=deps.delete_detect_task,
            list_detect_tasks=deps.list_detect_tasks,
            serialize_detect_task=deps.serialize_detect_task,
            serialize_module1_detect_job=deps.serialize_module1_detect_job,
            find_detect_task_by_job_id=lambda job_id: deps.find_detect_task_by_job_id(
                job_id,
                list_detect_tasks=deps.list_detect_tasks,
            ),
            task_status_is_running=deps.task_status_is_running,
            queue_project_sync=deps.vue_chunk_runtime_bundle.queue_project_sync,
            serialize_project=deps.shared_bundle.serialize_project,
            serialize_sync_job=lambda job, fallback_domain="": deps.serialize_sync_job(
                job,
                fallback_domain=fallback_domain,
            ),
            detect_default_concurrency=deps.detect_default_concurrency,
            detect_default_timeout=deps.detect_default_timeout,
            detect_default_wait_ms=deps.detect_default_wait_ms,
            module1_detect_job_step=deps.module1_detect_job_step,
            set_error=deps.shared_bundle.set_error,
            redirect=deps.shared_bundle.redirect,
            redirect_detect_task=deps.shared_bundle.redirect_detect_task,
            upsert_project_from_url=deps.upsert_project_from_url,
            select_vue_api_domain=lambda domain: deps.web_select_vue_api_domain(
                deps.ui_state,
                domain,
                safe_str=deps.safe_str,
            ),
        )
    )

    vue_chunk_route_bundle = build_vue_chunk_route_bundle(
        VueChunkRouteBundleDeps(
            ui_state=deps.ui_state,
            safe_str=deps.safe_str,
            to_int=deps.to_int,
            to_bool=deps.to_bool,
            json_ok=deps.shared_bundle.json_ok,
            json_error=deps.shared_bundle.json_error,
            clear_error=deps.shared_bundle.clear_error,
            merge_project_domains=deps.shared_bundle.merge_project_domains,
            list_projects=deps.list_projects,
            list_detect_tasks=deps.list_detect_tasks,
            get_project=deps.get_project,
            upsert_project_from_url=deps.upsert_project_from_url,
            update_project_title=deps.update_project_title,
            delete_project=deps.delete_project,
            clear_selected_project_domain=lambda: deps.web_clear_selected_project_domain(deps.ui_state),
            select_vue_api_domain=lambda domain: deps.web_select_vue_api_domain(
                deps.ui_state,
                domain,
                safe_str=deps.safe_str,
            ),
            load_project_detail=deps.load_project_detail,
            load_project_metrics=deps.load_project_metrics,
            serialize_project=deps.shared_bundle.serialize_project,
            normalize_detect_url_rows=deps.normalize_detect_url_rows,
            collect_sync_state_map=lambda limit=600: deps.collect_sync_state_map(
                jobs_dir=deps.jobs_dir,
                module2_sync_job_step=deps.module2_sync_job_step,
                limit=limit,
            ),
            collect_js_download_state_map=lambda limit=600: deps.collect_js_download_state_map(
                jobs_dir=deps.jobs_dir,
                module2_js_download_job_step=deps.module2_js_download_job_step,
                default_concurrency=deps.js_download_default_concurrency,
                limit=limit,
            ),
            collect_request_capture_state_map=lambda limit=600: deps.collect_request_capture_state_map(
                jobs_dir=deps.jobs_dir,
                module2_request_capture_job_step=deps.module2_request_capture_job_step,
                default_concurrency=deps.module2_request_default_concurrency,
                limit=limit,
            ),
            normalize_sync_status=deps.normalize_sync_status,
            resolve_scan_pattern=deps.shared_bundle.resolve_scan_pattern,
            get_global_settings=deps.shared_bundle.get_global_settings,
            normalize_proxy_server=deps.normalize_proxy_server,
            domain_from_target_url=deps.domain_from_target_url,
            resolve_target_url=deps.vue_chunk_runtime_bundle.resolve_target_url,
            queue_project_sync=deps.vue_chunk_runtime_bundle.queue_project_sync,
            queue_js_download=deps.vue_chunk_runtime_bundle.queue_js_download,
            queue_request_capture=deps.vue_chunk_runtime_bundle.queue_request_capture,
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
            sync_control_progress=deps.shared_bundle.sync_control_progress,
            request_capture_job_control=deps.shared_bundle.request_capture_job_control,
            serialize_sync_job=lambda job, fallback_domain="": deps.serialize_sync_job(
                job,
                fallback_domain=fallback_domain,
            ),
            serialize_js_download_job=lambda job, fallback_domain="": deps.serialize_js_download_job(
                job,
                fallback_domain=fallback_domain,
                default_concurrency=deps.js_download_default_concurrency,
            ),
            serialize_request_capture_job=lambda job, fallback_domain="": deps.serialize_request_capture_job(
                job,
                fallback_domain=fallback_domain,
                default_concurrency=deps.module2_request_default_concurrency,
            ),
            module2_sync_job_step=deps.module2_sync_job_step,
            module2_js_download_job_step=deps.module2_js_download_job_step,
            module2_request_capture_job_step=deps.module2_request_capture_job_step,
            js_download_default_concurrency=deps.js_download_default_concurrency,
            module2_request_default_concurrency=deps.module2_request_default_concurrency,
            set_error=deps.shared_bundle.set_error,
            redirect=deps.shared_bundle.redirect,
            run_web_action=deps.web_runtime_bundle.run_web_action,
            run_chunk_download=deps.run_chunk_download,
            set_selected_project_domain=lambda domain: deps.web_set_selected_project_domain(
                deps.ui_state,
                domain,
                safe_str=deps.safe_str,
            ),
            dedupe_effective_js_urls=deps.dedupe_effective_js_urls,
            read_lines=deps.read_lines,
            create_job=deps.create_job,
            spawn_background=deps.web_runtime_bundle.spawn_background,
            run_module2_js_download_background=deps.web_runtime_bundle.run_module2_js_download_background,
            safe_file_token=deps.safe_file_token,
        )
    )

    vue_api_route_bundle = build_vue_api_route_bundle(
        VueApiRouteBundleDeps(
            ui_state=deps.ui_state,
            safe_str=deps.safe_str,
            to_int=deps.to_int,
            json_ok=deps.shared_bundle.json_ok,
            json_error=deps.shared_bundle.json_error,
            clear_error=deps.shared_bundle.clear_error,
            merge_project_domains=deps.shared_bundle.merge_project_domains,
            list_projects=deps.list_projects,
            list_project_js_files=deps.list_project_js_files,
            list_project_js_urls=deps.list_project_js_urls,
            get_vue_api_config_for_domain=lambda domain: deps.web_get_vue_api_config_for_domain(
                deps.ui_state,
                domain,
                safe_str=deps.safe_str,
                load_project_extract_config=deps.load_project_extract_config,
            ),
            load_project_extract_result=deps.load_project_extract_result,
            save_vue_api_config=lambda domain, pattern: deps.web_save_vue_api_config(
                deps.ui_state,
                domain,
                pattern,
                safe_str=deps.safe_str,
            ),
            sync_vue_api_source_form=lambda **kwargs: deps.web_sync_vue_api_source_form(
                deps.ui_state,
                safe_str=deps.safe_str,
                **kwargs,
            ),
            set_vue_api_beautify_result=lambda payload: deps.web_set_vue_api_beautify_result(deps.ui_state, payload),
            set_vue_api_preview_result=lambda payload: deps.web_set_vue_api_preview_result(deps.ui_state, payload),
            set_vue_api_extract_result=lambda payload: deps.web_set_vue_api_extract_result(deps.ui_state, payload),
            load_project_js_source=lambda *, domain, js_file, js_url: deps.load_project_js_source(
                domain=domain,
                js_file=js_file,
                js_url=js_url,
                fetch_text_from_url=deps.fetch_text_from_url,
            ),
            build_source_preview_payload=deps.build_source_preview_payload,
            beautify_js_code=deps.beautify_js_code,
            js_source_name_from_url=deps.js_source_name_from_url,
            module3_js_max_display_chars=deps.module3_js_max_display_chars,
            preview_endpoints_from_js=deps.preview_endpoints_from_js,
            preview_endpoints_from_text=deps.preview_endpoints_from_text,
            preview_endpoints_from_all_chunks=deps.preview_endpoints_from_all_chunks,
            run_vue_api_auto_regex=deps.shared_bundle.run_vue_api_auto_regex,
            run_web_action=deps.web_runtime_bundle.run_web_action,
            run_api_extract=deps.run_api_extract,
            load_api_endpoints=deps.load_api_endpoints,
            serialize_api_endpoint=deps.serialize_api_endpoint,
            persist_project_preview_extract=deps.persist_project_preview_extract,
            set_error=deps.shared_bundle.set_error,
            redirect=deps.shared_bundle.redirect,
            select_vue_api_domain=lambda domain: deps.web_select_vue_api_domain(
                deps.ui_state,
                domain,
                safe_str=deps.safe_str,
            ),
            reset_vue_api_runtime_outputs=lambda: deps.web_reset_vue_api_runtime_outputs(deps.ui_state),
            apply_vue_api_form=lambda form: deps.web_apply_vue_api_form(deps.ui_state, form, safe_str=deps.safe_str),
            resolve_vue_api_pattern_config=lambda module3_form: deps.web_resolve_vue_api_pattern_config(
                module3_form,
                safe_str=deps.safe_str,
            ),
        )
    )

    vue_request_route_bundle = build_vue_request_route_bundle(
        VueRequestRouteBundleDeps(
            ui_state=deps.ui_state,
            safe_str=deps.safe_str,
            to_int=deps.to_int,
            to_bool=deps.to_bool,
            json_ok=deps.shared_bundle.json_ok,
            json_error=deps.shared_bundle.json_error,
            clear_error=deps.shared_bundle.clear_error,
            merge_project_domains=deps.shared_bundle.merge_project_domains,
            list_projects=deps.list_projects,
            load_project_request_config=deps.load_project_request_config,
            persist_project_request_config=deps.persist_project_request_config,
            load_api_endpoints=deps.load_api_endpoints,
            serialize_api_endpoint=deps.serialize_api_endpoint,
            sync_vue_api_request_state=lambda **kwargs: deps.web_sync_vue_api_request_state(
                deps.ui_state,
                safe_str=deps.safe_str,
                **kwargs,
            ),
            set_vue_api_request_result=lambda payload: deps.web_set_vue_api_request_result(deps.ui_state, payload),
            load_captured_request_items=deps.load_captured_request_items,
            load_captured_request_templates=deps.load_captured_request_templates,
            infer_request_base=deps.infer_request_base,
            infer_request_base_from_paths=deps.infer_request_base_from_paths,
            parse_request_dispatch_inputs=deps.parse_request_dispatch_inputs,
            parse_request_payload_inputs=deps.parse_request_payload_inputs,
            find_api_endpoint_by_id=deps.find_api_endpoint_by_id,
            prepare_template_replay_request=deps.prepare_template_replay_request,
            run_web_action=deps.web_runtime_bundle.run_web_action,
            run_api_request=deps.run_api_request,
            queue_request_batch=deps.queue_request_batch,
            read_job=deps.read_job,
            update_job=deps.update_job,
            append_log=deps.append_log,
            serialize_request_batch_job=deps.serialize_request_batch_job,
            vue_request_batch_job_step=deps.vue_request_batch_job_step,
            load_saved_response_detail=deps.load_saved_response_detail,
            load_saved_request_results=deps.load_saved_request_results,
            save_saved_request_result=deps.save_saved_request_result,
            load_request_run_snapshots=deps.load_request_run_snapshots,
            save_request_run_snapshot=deps.save_request_run_snapshot,
            delete_request_run_snapshot=deps.delete_request_run_snapshot,
            format_request_payload_text=deps.format_request_payload_text,
            build_template_replay_summary=deps.build_template_replay_summary,
            set_error=deps.shared_bundle.set_error,
            redirect=deps.shared_bundle.redirect,
            apply_vue_api_request_form=lambda form: deps.web_apply_vue_api_request_form(
                deps.ui_state,
                form,
                safe_str=deps.safe_str,
            ),
            select_vue_api_domain=lambda domain: deps.web_select_vue_api_domain(
                deps.ui_state,
                domain,
                safe_str=deps.safe_str,
            ),
            parse_request_form_inputs=deps.parse_request_form_inputs,
        )
    )

    routes = build_web_routes(
        WebRouteTableDeps(
            frontend_routes=core_route_bundle.frontend_routes,
            page_routes=core_route_bundle.page_routes,
            system_routes=core_route_bundle.system_routes,
            vue_detect_routes=vue_detect_route_bundle.api_routes,
            vue_chunk_routes=vue_chunk_route_bundle.api_routes,
            vue_api_routes=vue_api_route_bundle.api_routes,
            vue_request_routes=vue_request_route_bundle.api_routes,
            vue_detect_action_routes=vue_detect_route_bundle.action_routes,
            vue_chunk_action_routes=vue_chunk_route_bundle.action_routes,
            vue_api_action_routes=vue_api_route_bundle.action_routes,
            vue_request_action_routes=vue_request_route_bundle.action_routes,
            static_dir=deps.static_dir,
        )
    )

    return WebAppRouteWiringBundle(routes=routes)
