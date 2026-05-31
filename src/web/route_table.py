from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from starlette.routing import Mount
from starlette.staticfiles import StaticFiles


@dataclass(frozen=True)
class WebRouteTableDeps:
    # 路由表顺序会影响前端页面与接口的匹配优先级，这里单独收口。
    frontend_routes: list[Any]
    page_routes: list[Any]
    system_routes: list[Any]
    vue_detect_routes: list[Any]
    vue_chunk_routes: list[Any]
    vue_api_routes: list[Any]
    vue_request_routes: list[Any]
    vue_detect_action_routes: list[Any]
    vue_chunk_action_routes: list[Any]
    vue_api_action_routes: list[Any]
    vue_request_action_routes: list[Any]
    static_dir: Path


def build_web_routes(deps: WebRouteTableDeps) -> list[Any]:
    return [
        *deps.frontend_routes[:2],
        *deps.page_routes[:1],
        *deps.frontend_routes[2:3],
        *deps.page_routes[1:2],
        *deps.frontend_routes[3:],
        *deps.system_routes,
        *deps.vue_detect_routes,
        *deps.vue_chunk_routes,
        *deps.vue_api_routes,
        *deps.vue_request_routes,
        *deps.page_routes[2:],
        *deps.vue_detect_action_routes,
        *deps.vue_chunk_action_routes,
        *deps.vue_api_action_routes,
        *deps.vue_request_action_routes,
        Mount("/static", app=StaticFiles(directory=str(deps.static_dir)), name="static"),
    ]
