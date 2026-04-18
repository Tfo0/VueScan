from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.web.routes.vue_request import VueRequestRouteDeps, build_vue_request_routes
from src.web.routes.vue_request_actions import VueRequestActionRouteDeps, build_vue_request_action_routes


@dataclass(frozen=True)
class VueRequestRouteBundleDeps:
    # 统一装配 VueRequest 的 API 路由和表单动作路由，避免 app.py 直接堆两大段依赖清单。
    ui_state: dict[str, Any]
    safe_str: Callable[[Any, str], str]
    to_int: Callable[[Any, int, int], int]
    to_bool: Callable[[Any], bool]
    json_ok: Callable[..., Any]
    json_error: Callable[..., Any]
    clear_error: Callable[[], None]
    merge_project_domains: Callable[[list[Any]], list[str]]
    list_projects: Callable[..., list[Any]]
    load_project_request_config: Callable[[str], dict[str, Any]]
    persist_project_request_config: Callable[..., None]
    load_api_endpoints: Callable[[str], list[Any]]
    serialize_api_endpoint: Callable[[Any], dict[str, Any]]
    sync_vue_api_request_state: Callable[..., None]
    set_vue_api_request_result: Callable[[dict[str, Any]], None]
    load_captured_request_items: Callable[[str], list[dict[str, Any]]]
    load_captured_request_templates: Callable[[str], list[dict[str, Any]]]
    infer_request_base: Callable[..., dict[str, Any]]
    infer_request_base_from_paths: Callable[[str, Any], dict[str, Any]]
    parse_request_dispatch_inputs: Callable[[dict[str, object]], dict[str, object]]
    parse_request_payload_inputs: Callable[..., dict[str, object]]
    find_api_endpoint_by_id: Callable[[list[Any], int], Any | None]
    prepare_template_replay_request: Callable[..., dict[str, object]]
    run_web_action: Callable[..., Any]
    run_api_request: Callable[..., Any]
    queue_request_batch: Callable[..., dict[str, Any]]
    read_job: Callable[[str], dict[str, Any]]
    update_job: Callable[..., dict[str, Any]]
    append_log: Callable[[str, str], None]
    serialize_request_batch_job: Callable[[dict[str, Any]], dict[str, Any]]
    vue_request_batch_job_step: str
    load_saved_response_detail: Callable[[object], dict[str, object]]
    load_saved_request_results: Callable[[str], list[dict[str, object]]]
    save_saved_request_result: Callable[..., dict[str, object]]
    load_request_run_snapshots: Callable[[str], list[dict[str, object]]]
    save_request_run_snapshot: Callable[..., dict[str, object]]
    delete_request_run_snapshot: Callable[..., list[dict[str, object]]]
    format_request_payload_text: Callable[..., str]
    build_template_replay_summary: Callable[..., dict[str, object]]
    set_error: Callable[[str], None]
    redirect: Callable[[int], Any]
    apply_vue_api_request_form: Callable[[Any], None]
    select_vue_api_domain: Callable[[Any], str]
    parse_request_form_inputs: Callable[..., dict[str, object]]


@dataclass(frozen=True)
class VueRequestRouteBundle:
    api_routes: list[Any]
    action_routes: list[Any]


def build_vue_request_route_bundle(deps: VueRequestRouteBundleDeps) -> VueRequestRouteBundle:
    api_routes = build_vue_request_routes(
        VueRequestRouteDeps(
            ui_state=deps.ui_state,
            safe_str=deps.safe_str,
            to_int=deps.to_int,
            to_bool=deps.to_bool,
            json_ok=deps.json_ok,
            json_error=deps.json_error,
            clear_error=deps.clear_error,
            merge_project_domains=deps.merge_project_domains,
            list_projects=deps.list_projects,
            load_project_request_config=deps.load_project_request_config,
            persist_project_request_config=deps.persist_project_request_config,
            load_api_endpoints=deps.load_api_endpoints,
            serialize_api_endpoint=deps.serialize_api_endpoint,
            sync_vue_api_request_state=deps.sync_vue_api_request_state,
            set_vue_api_request_result=deps.set_vue_api_request_result,
            load_captured_request_items=deps.load_captured_request_items,
            load_captured_request_templates=deps.load_captured_request_templates,
            infer_request_base=deps.infer_request_base,
            infer_request_base_from_paths=deps.infer_request_base_from_paths,
            parse_request_dispatch_inputs=deps.parse_request_dispatch_inputs,
            parse_request_payload_inputs=deps.parse_request_payload_inputs,
            find_api_endpoint_by_id=deps.find_api_endpoint_by_id,
            prepare_template_replay_request=deps.prepare_template_replay_request,
            run_web_action=deps.run_web_action,
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
        )
    )

    action_routes = build_vue_request_action_routes(
        VueRequestActionRouteDeps(
            ui_state=deps.ui_state,
            safe_str=deps.safe_str,
            to_int=deps.to_int,
            set_error=deps.set_error,
            clear_error=deps.clear_error,
            redirect=deps.redirect,
            apply_vue_api_request_form=deps.apply_vue_api_request_form,
            select_vue_api_domain=deps.select_vue_api_domain,
            load_api_endpoints=deps.load_api_endpoints,
            load_project_request_config=deps.load_project_request_config,
            parse_request_dispatch_inputs=deps.parse_request_dispatch_inputs,
            parse_request_form_inputs=deps.parse_request_form_inputs,
            run_web_action=deps.run_web_action,
            run_api_request=deps.run_api_request,
            set_vue_api_request_result=deps.set_vue_api_request_result,
        )
    )

    return VueRequestRouteBundle(
        api_routes=api_routes,
        action_routes=action_routes,
    )
