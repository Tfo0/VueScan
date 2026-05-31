from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Route


@dataclass(frozen=True)
class PageRouteDeps:
    # 页面入口只负责参数校验、状态同步和模板响应，复杂上下文准备继续交给独立模块。
    ui_state: dict[str, Any]
    templates: Any
    safe_str: Callable[[Any, str], str]
    set_error: Callable[[str], None]
    clear_error: Callable[[], None]
    redirect: Callable[[int], Any]
    frontend_app: Callable[[Request], Awaitable[Any]]
    select_vue_api_domain: Callable[[str], str]
    load_project_detail: Callable[[str], dict[str, Any]]
    get_detect_task: Callable[[str], dict[str, Any] | None]
    build_page_context: Callable[..., dict[str, Any]]
    page_context_deps: Any


def _bind_route(
    handler: Callable[[Request, PageRouteDeps], Awaitable[Any]],
    deps: PageRouteDeps,
) -> Callable[[Request], Awaitable[Any]]:
    async def endpoint(request: Request):
        return await handler(request, deps)

    endpoint.__name__ = handler.__name__.lstrip("_")
    return endpoint


async def _home(request: Request, deps: PageRouteDeps):
    return await deps.frontend_app(request)


async def _redirect_root(request: Request, deps: PageRouteDeps):
    return RedirectResponse(url="/", status_code=302)


async def _project_detail(request: Request, deps: PageRouteDeps):
    domain = deps.safe_str(request.path_params.get("domain"))
    if not domain:
        deps.set_error("domain is required")
        return deps.redirect(2)

    deps.select_vue_api_domain(domain)
    detail = deps.load_project_detail(domain)
    if not detail:
        deps.set_error(f"project not found: {domain}")
        return deps.redirect(2)

    context = deps.build_page_context(request=request, active_module=2, deps=deps.page_context_deps)
    context["module1_detail_mode"] = False
    context["module2_detail_mode"] = True
    deps.clear_error()
    return deps.templates.TemplateResponse(request=request, name="index.html", context=context)


async def _detect_task_detail(request: Request, deps: PageRouteDeps):
    task_id = deps.safe_str(request.path_params.get("task_id"))
    if not task_id:
        deps.set_error("task_id is required")
        return deps.redirect(1)

    task = deps.get_detect_task(task_id)
    if task is None:
        deps.set_error(f"detection task not found: {task_id}")
        return deps.redirect(1)

    deps.ui_state["selected_task_id"] = task_id
    deps.ui_state["detect_result"] = copy.deepcopy(task.get("result") or {})

    context = deps.build_page_context(request=request, active_module=1, deps=deps.page_context_deps)
    context["module1_detail_mode"] = True
    context["module2_detail_mode"] = False
    deps.clear_error()
    return deps.templates.TemplateResponse(request=request, name="index.html", context=context)


def build_page_routes(deps: PageRouteDeps) -> list[Route]:
    return [
        Route("/", endpoint=_bind_route(_home, deps), methods=["GET"]),
        Route("/home", endpoint=_bind_route(_redirect_root, deps), methods=["GET"]),
        Route("/detect-tasks/{task_id}", endpoint=_bind_route(_detect_task_detail, deps), methods=["GET"]),
        Route("/projects/{domain}", endpoint=_bind_route(_project_detail, deps), methods=["GET"]),
    ]
