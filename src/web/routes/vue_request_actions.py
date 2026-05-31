from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from starlette.requests import Request
from starlette.routing import Route


@dataclass(frozen=True)
class VueRequestActionRouteDeps:
    # VueRequest 表单动作继续沿用老路径，但实现迁出 app.py。
    ui_state: dict[str, Any]
    safe_str: Callable[[Any, str], str]
    to_int: Callable[[Any, int, int], int]
    set_error: Callable[[str], None]
    clear_error: Callable[[], None]
    redirect: Callable[[int], Any]
    apply_vue_api_request_form: Callable[[Any], None]
    select_vue_api_domain: Callable[[Any], str]
    load_api_endpoints: Callable[[str], list[Any]]
    load_project_request_config: Callable[[str], dict[str, Any]]
    parse_request_dispatch_inputs: Callable[[dict[str, object]], dict[str, object]]
    parse_request_form_inputs: Callable[..., dict[str, object]]
    run_web_action: Callable[..., Awaitable[tuple[str, dict[str, Any]]]]
    run_api_request: Callable[..., Any]
    set_vue_api_request_result: Callable[[dict[str, Any]], None]


def _bind_route(
    handler: Callable[[Request, VueRequestActionRouteDeps], Awaitable[Any]],
    deps: VueRequestActionRouteDeps,
) -> Callable[[Request], Awaitable[Any]]:
    async def endpoint(request: Request):
        return await handler(request, deps)

    endpoint.__name__ = handler.__name__.lstrip("_")
    return endpoint


async def _action_vue_request_load(request: Request, deps: VueRequestActionRouteDeps):
    form = await request.form()
    deps.apply_vue_api_request_form(form)
    module4_form = deps.ui_state["module4_form"]
    domain = deps.safe_str(module4_form.get("domain"))
    if not domain:
        deps.set_error("domain is required")
        return deps.redirect(4)

    deps.select_vue_api_domain(domain)

    try:
        endpoints = deps.load_api_endpoints(domain)
        loaded_cfg = deps.load_project_request_config(domain)
        if loaded_cfg:
            if not deps.safe_str(module4_form.get("baseurl")):
                module4_form["baseurl"] = loaded_cfg.get("baseurl", "")
            if not deps.safe_str(module4_form.get("baseapi")):
                module4_form["baseapi"] = loaded_cfg.get("baseapi", "")
        if endpoints and not deps.safe_str(module4_form.get("api_id")):
            module4_form["api_id"] = str(endpoints[0].id)
        if endpoints and not deps.safe_str(module4_form.get("method")):
            selected_id = deps.safe_str(module4_form.get("api_id"))
            selected = next((item for item in endpoints if str(item.id) == selected_id), endpoints[0])
            module4_form["method"] = selected.method
        deps.clear_error()
    except Exception as exc:
        deps.set_error(str(exc))

    return deps.redirect(4)


async def _action_vue_request_request(request: Request, deps: VueRequestActionRouteDeps):
    form = await request.form()
    deps.apply_vue_api_request_form(form)
    module4_form = deps.ui_state["module4_form"]

    try:
        request_inputs = deps.parse_request_dispatch_inputs(module4_form)
        domain = deps.safe_str(request_inputs.get("domain"))
        api_id = deps.to_int(request_inputs.get("api_id"), default=0, minimum=0)
        method = deps.safe_str(request_inputs.get("method"))
        baseurl = deps.safe_str(request_inputs.get("baseurl"))
        baseapi = deps.safe_str(request_inputs.get("baseapi"))
        timeout = deps.to_int(request_inputs.get("timeout"), default=20, minimum=1)
        module4_form["timeout"] = str(timeout)

        parsed_inputs = deps.parse_request_form_inputs(
            raw_json_body=module4_form.get("json_body", ""),
            raw_headers=module4_form.get("headers", ""),
        )
        json_body = parsed_inputs.get("json_body")
        headers = parsed_inputs.get("headers") if isinstance(parsed_inputs.get("headers"), dict) else None

        payload = {
            "domain": domain,
            "api_id": api_id,
            "method": method,
            "baseurl": baseurl,
            "baseapi": baseapi,
            "timeout": timeout,
            "json_body": json_body,
            "headers": headers,
        }
        job_id, result = await deps.run_web_action(
            "web_module4_api_request",
            payload,
            lambda: deps.run_api_request(
                domain=domain,
                api_id=api_id,
                method=method or None,
                baseurl=baseurl,
                baseapi=baseapi,
                json_body=json_body,
                headers=headers,
                timeout=timeout,
            ),
        )
        deps.set_vue_api_request_result({"job_id": job_id, **result})
        deps.select_vue_api_domain(domain)
        deps.clear_error()
    except Exception as exc:
        deps.set_error(str(exc))

    return deps.redirect(4)


def build_vue_request_action_routes(deps: VueRequestActionRouteDeps) -> list[Route]:
    # 保持现有表单 action 路径不变，先把实现从 app.py 挪出来。
    return [
        Route("/actions/module4/load", endpoint=_bind_route(_action_vue_request_load, deps), methods=["POST"]),
        Route(
            "/actions/module4/request",
            endpoint=_bind_route(_action_vue_request_request, deps),
            methods=["POST"],
        ),
    ]
