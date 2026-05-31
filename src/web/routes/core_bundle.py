from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from starlette.requests import Request
from starlette.routing import Route

from src.web.routes.auth import AuthRouteDeps, build_auth_routes
from src.web.routes.frontend import FrontendRouteDeps, build_frontend_app_handler, build_frontend_routes
from src.web.routes.pages import PageRouteDeps, build_page_routes
from src.web.routes.system import SystemRouteDeps, build_system_routes


@dataclass(frozen=True)
class CoreRouteBundleDeps:
    # 这一层只负责把 frontend/page/system 三组路由装配起来，不承载业务逻辑。
    ui_state: dict[str, Any]
    templates: Any
    frontend_dir: Path
    frontend_dist_dir: Path
    safe_str: Callable[[Any, str], str]
    set_error: Callable[[str], None]
    clear_error: Callable[[], None]
    redirect: Callable[[int], Any]
    json_error: Callable[..., Any]
    json_ok: Callable[..., Any]
    select_vue_api_domain: Callable[[str], str]
    load_project_detail: Callable[[str], dict[str, Any]]
    get_detect_task: Callable[[str], dict[str, Any] | None]
    build_page_context: Callable[..., dict[str, Any]]
    page_context_deps: Any
    get_global_settings: Callable[..., dict[str, Any]]
    save_global_settings_file: Callable[[Any], dict[str, Any]]
    database_file: Path


@dataclass(frozen=True)
class CoreRouteBundle:
    frontend_app_handler: Callable[[Request], Awaitable[Any]]
    frontend_routes: list[Route]
    system_routes: list[Route]
    page_routes: list[Route]


def build_core_route_bundle(deps: CoreRouteBundleDeps) -> CoreRouteBundle:
    # 先装配前端入口，再复用同一个 handler 给页面路由，最后拼系统路由。
    frontend_route_deps = FrontendRouteDeps(
        frontend_dir=deps.frontend_dir,
        frontend_dist_dir=deps.frontend_dist_dir,
        safe_str=deps.safe_str,
        json_error=deps.json_error,
    )
    frontend_app_handler = build_frontend_app_handler(frontend_route_deps)
    frontend_routes = build_frontend_routes(frontend_route_deps)

    system_routes = build_system_routes(
        SystemRouteDeps(
            json_ok=deps.json_ok,
            get_global_settings=deps.get_global_settings,
            save_global_settings_file=deps.save_global_settings_file,
            frontend_dist_dir=deps.frontend_dist_dir,
        )
    )
    auth_routes = build_auth_routes(
        AuthRouteDeps(
            json_ok=deps.json_ok,
            json_error=deps.json_error,
            database_file=deps.database_file,
        )
    )

    page_routes = build_page_routes(
        PageRouteDeps(
            ui_state=deps.ui_state,
            templates=deps.templates,
            safe_str=deps.safe_str,
            set_error=deps.set_error,
            clear_error=deps.clear_error,
            redirect=deps.redirect,
            frontend_app=frontend_app_handler,
            select_vue_api_domain=deps.select_vue_api_domain,
            load_project_detail=deps.load_project_detail,
            get_detect_task=deps.get_detect_task,
            build_page_context=deps.build_page_context,
            page_context_deps=deps.page_context_deps,
        )
    )

    return CoreRouteBundle(
        frontend_app_handler=frontend_app_handler,
        frontend_routes=frontend_routes,
        system_routes=[*system_routes, *auth_routes],
        page_routes=page_routes,
    )
