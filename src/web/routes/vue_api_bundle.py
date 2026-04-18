from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.web.routes.vue_api import VueApiRouteDeps, build_vue_api_routes
from src.web.routes.vue_api_actions import VueApiActionRouteDeps, build_vue_api_action_routes


@dataclass(frozen=True)
class VueApiRouteBundleDeps:
    # VueApi 的 API 路由和表单动作路由共用很多依赖，统一在这里装配更容易维护。
    ui_state: dict[str, Any]
    safe_str: Callable[[Any, str], str]
    to_int: Callable[[Any, int, int], int]
    json_ok: Callable[..., Any]
    json_error: Callable[..., Any]
    clear_error: Callable[[], None]
    merge_project_domains: Callable[[list[Any]], list[str]]
    list_projects: Callable[..., list[Any]]
    list_project_js_files: Callable[[str], list[Any]]
    list_project_js_urls: Callable[[str], list[Any]]
    get_vue_api_config_for_domain: Callable[[str], dict[str, str]]
    load_project_extract_result: Callable[[str], dict[str, Any]]
    save_vue_api_config: Callable[[str, str], None]
    sync_vue_api_source_form: Callable[..., None]
    set_vue_api_beautify_result: Callable[[dict[str, Any]], None]
    set_vue_api_preview_result: Callable[[dict[str, Any]], None]
    set_vue_api_extract_result: Callable[[dict[str, Any]], None]
    load_project_js_source: Callable[..., tuple[str, str, str]]
    build_source_preview_payload: Callable[..., dict[str, Any]]
    beautify_js_code: Callable[[str], str]
    js_source_name_from_url: Callable[[str], str]
    module3_js_max_display_chars: int
    preview_endpoints_from_js: Callable[..., list[Any]]
    preview_endpoints_from_text: Callable[..., list[Any]]
    preview_endpoints_from_all_chunks: Callable[..., list[Any]]
    run_vue_api_auto_regex: Callable[..., dict[str, Any]]
    run_web_action: Callable[..., Any]
    run_api_extract: Callable[..., Any]
    load_api_endpoints: Callable[[str], list[Any]]
    serialize_api_endpoint: Callable[[Any], dict[str, Any]]
    persist_project_preview_extract: Callable[..., str]
    set_error: Callable[[str], None]
    redirect: Callable[[int], Any]
    select_vue_api_domain: Callable[[Any], str]
    reset_vue_api_runtime_outputs: Callable[[], None]
    apply_vue_api_form: Callable[[Any], None]
    resolve_vue_api_pattern_config: Callable[[dict[str, Any]], tuple[str, str, str]]


@dataclass(frozen=True)
class VueApiRouteBundle:
    api_routes: list[Any]
    action_routes: list[Any]


def build_vue_api_route_bundle(deps: VueApiRouteBundleDeps) -> VueApiRouteBundle:
    api_routes = build_vue_api_routes(
        VueApiRouteDeps(
            ui_state=deps.ui_state,
            safe_str=deps.safe_str,
            to_int=deps.to_int,
            json_ok=deps.json_ok,
            json_error=deps.json_error,
            clear_error=deps.clear_error,
            merge_project_domains=deps.merge_project_domains,
            list_projects=deps.list_projects,
            list_project_js_files=deps.list_project_js_files,
            list_project_js_urls=deps.list_project_js_urls,
            get_vue_api_config_for_domain=deps.get_vue_api_config_for_domain,
            load_project_extract_result=deps.load_project_extract_result,
            save_vue_api_config=deps.save_vue_api_config,
            sync_vue_api_source_form=deps.sync_vue_api_source_form,
            set_vue_api_beautify_result=deps.set_vue_api_beautify_result,
            set_vue_api_preview_result=deps.set_vue_api_preview_result,
            set_vue_api_extract_result=deps.set_vue_api_extract_result,
            load_project_js_source=deps.load_project_js_source,
            build_source_preview_payload=deps.build_source_preview_payload,
            beautify_js_code=deps.beautify_js_code,
            js_source_name_from_url=deps.js_source_name_from_url,
            module3_js_max_display_chars=deps.module3_js_max_display_chars,
            preview_endpoints_from_js=deps.preview_endpoints_from_js,
            preview_endpoints_from_text=deps.preview_endpoints_from_text,
            preview_endpoints_from_all_chunks=deps.preview_endpoints_from_all_chunks,
            run_vue_api_auto_regex=deps.run_vue_api_auto_regex,
            run_web_action=deps.run_web_action,
            run_api_extract=deps.run_api_extract,
            load_api_endpoints=deps.load_api_endpoints,
            serialize_api_endpoint=deps.serialize_api_endpoint,
            persist_project_preview_extract=deps.persist_project_preview_extract,
        )
    )

    action_routes = build_vue_api_action_routes(
        VueApiActionRouteDeps(
            ui_state=deps.ui_state,
            safe_str=deps.safe_str,
            set_error=deps.set_error,
            clear_error=deps.clear_error,
            redirect=deps.redirect,
            list_project_js_files=deps.list_project_js_files,
            get_vue_api_config_for_domain=deps.get_vue_api_config_for_domain,
            select_vue_api_domain=deps.select_vue_api_domain,
            reset_vue_api_runtime_outputs=deps.reset_vue_api_runtime_outputs,
            apply_vue_api_form=deps.apply_vue_api_form,
            save_vue_api_config=deps.save_vue_api_config,
            load_project_js_source=deps.load_project_js_source,
            beautify_js_code=deps.beautify_js_code,
            js_source_name_from_url=deps.js_source_name_from_url,
            module3_js_max_display_chars=deps.module3_js_max_display_chars,
            set_vue_api_beautify_result=deps.set_vue_api_beautify_result,
            resolve_vue_api_pattern_config=deps.resolve_vue_api_pattern_config,
            preview_endpoints_from_js=deps.preview_endpoints_from_js,
            preview_endpoints_from_text=deps.preview_endpoints_from_text,
            set_vue_api_preview_result=deps.set_vue_api_preview_result,
            run_web_action=deps.run_web_action,
            run_api_extract=deps.run_api_extract,
            set_vue_api_extract_result=deps.set_vue_api_extract_result,
        )
    )

    return VueApiRouteBundle(
        api_routes=api_routes,
        action_routes=action_routes,
    )
