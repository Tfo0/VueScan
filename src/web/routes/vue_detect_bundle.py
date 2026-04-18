from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.web.routes.vue_detect import VueDetectRouteDeps, build_vue_detect_routes
from src.web.routes.vue_detect_actions import VueDetectActionRouteDeps, build_vue_detect_action_routes


@dataclass(frozen=True)
class VueDetectRouteBundleDeps:
    # 统一装配 VueDetect 的 API 路由与表单动作，减少 app.py 里的依赖清单噪音。
    ui_state: dict[str, Any]
    safe_str: Callable[[Any, str], str]
    to_int: Callable[[Any, int, int], int]
    to_bool: Callable[[Any], bool]
    json_ok: Callable[..., Any]
    json_error: Callable[..., Any]
    clear_error: Callable[[], None]
    save_uploaded_file: Callable[..., Any]
    create_job: Callable[..., dict[str, Any]]
    append_log: Callable[[str, str], None]
    create_detect_task: Callable[..., dict[str, Any]]
    spawn_background: Callable[..., None]
    run_module1_detect_background: Callable[..., Any]
    update_detect_task: Callable[..., dict[str, Any]]
    update_job: Callable[..., dict[str, Any]]
    read_job: Callable[[str], dict[str, Any]]
    get_detect_task: Callable[[str], dict[str, Any] | None]
    delete_detect_task: Callable[[str], Any]
    list_detect_tasks: Callable[..., list[dict[str, Any]]]
    serialize_detect_task: Callable[[dict[str, Any]], dict[str, Any]]
    serialize_module1_detect_job: Callable[[dict[str, Any]], dict[str, Any]]
    find_detect_task_by_job_id: Callable[[str], dict[str, Any] | None]
    task_status_is_running: Callable[[str], bool]
    queue_project_sync: Callable[..., Any]
    serialize_project: Callable[[dict[str, Any]], dict[str, Any]]
    serialize_sync_job: Callable[..., dict[str, Any]]
    detect_default_concurrency: int
    detect_default_timeout: int
    detect_default_wait_ms: int
    module1_detect_job_step: str
    set_error: Callable[[str], None]
    redirect: Callable[[int], Any]
    redirect_detect_task: Callable[[str], Any]
    upsert_project_from_url: Callable[..., dict[str, Any]]
    select_vue_api_domain: Callable[[Any], str]


@dataclass(frozen=True)
class VueDetectRouteBundle:
    api_routes: list[Any]
    action_routes: list[Any]


def build_vue_detect_route_bundle(deps: VueDetectRouteBundleDeps) -> VueDetectRouteBundle:
    api_routes = build_vue_detect_routes(
        VueDetectRouteDeps(
            ui_state=deps.ui_state,
            safe_str=deps.safe_str,
            to_int=deps.to_int,
            to_bool=deps.to_bool,
            json_ok=deps.json_ok,
            json_error=deps.json_error,
            clear_error=deps.clear_error,
            save_uploaded_file=deps.save_uploaded_file,
            create_job=deps.create_job,
            append_log=deps.append_log,
            create_detect_task=deps.create_detect_task,
            spawn_background=deps.spawn_background,
            run_module1_detect_background=deps.run_module1_detect_background,
            update_detect_task=deps.update_detect_task,
            update_job=deps.update_job,
            read_job=deps.read_job,
            get_detect_task=deps.get_detect_task,
            delete_detect_task=deps.delete_detect_task,
            list_detect_tasks=deps.list_detect_tasks,
            serialize_detect_task=deps.serialize_detect_task,
            serialize_module1_detect_job=deps.serialize_module1_detect_job,
            find_detect_task_by_job_id=deps.find_detect_task_by_job_id,
            task_status_is_running=deps.task_status_is_running,
            queue_project_sync=deps.queue_project_sync,
            serialize_project=deps.serialize_project,
            serialize_sync_job=deps.serialize_sync_job,
            detect_default_concurrency=deps.detect_default_concurrency,
            detect_default_timeout=deps.detect_default_timeout,
            detect_default_wait_ms=deps.detect_default_wait_ms,
            module1_detect_job_step=deps.module1_detect_job_step,
        )
    )

    action_routes = build_vue_detect_action_routes(
        VueDetectActionRouteDeps(
            ui_state=deps.ui_state,
            safe_str=deps.safe_str,
            to_int=deps.to_int,
            set_error=deps.set_error,
            clear_error=deps.clear_error,
            redirect=deps.redirect,
            redirect_detect_task=deps.redirect_detect_task,
            save_uploaded_file=deps.save_uploaded_file,
            create_job=deps.create_job,
            append_log=deps.append_log,
            create_detect_task=deps.create_detect_task,
            spawn_background=deps.spawn_background,
            run_module1_detect_background=deps.run_module1_detect_background,
            update_detect_task=deps.update_detect_task,
            update_job=deps.update_job,
            get_detect_task=deps.get_detect_task,
            delete_detect_task=deps.delete_detect_task,
            upsert_project_from_url=deps.upsert_project_from_url,
            select_vue_api_domain=deps.select_vue_api_domain,
            detect_default_concurrency=deps.detect_default_concurrency,
            detect_default_timeout=deps.detect_default_timeout,
            detect_default_wait_ms=deps.detect_default_wait_ms,
            module1_detect_job_step=deps.module1_detect_job_step,
        )
    )

    return VueDetectRouteBundle(
        api_routes=api_routes,
        action_routes=action_routes,
    )
