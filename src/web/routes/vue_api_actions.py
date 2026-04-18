from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from starlette.requests import Request
from starlette.routing import Route


@dataclass(frozen=True)
class VueApiActionRouteDeps:
    # VueApi 表单动作仍然走老的 /actions/module3/* 路径，但实现迁出 app.py。
    ui_state: dict[str, Any]
    safe_str: Callable[[Any, str], str]
    set_error: Callable[[str], None]
    clear_error: Callable[[], None]
    redirect: Callable[[int], Any]
    list_project_js_files: Callable[[str], list[Any]]
    get_vue_api_config_for_domain: Callable[[str], dict[str, str]]
    select_vue_api_domain: Callable[[Any], str]
    reset_vue_api_runtime_outputs: Callable[[], None]
    apply_vue_api_form: Callable[[Any], None]
    save_vue_api_config: Callable[[str, str], None]
    load_project_js_source: Callable[..., tuple[str, str, str]]
    beautify_js_code: Callable[[str], str]
    js_source_name_from_url: Callable[[str], str]
    module3_js_max_display_chars: int
    set_vue_api_beautify_result: Callable[[dict[str, Any]], None]
    resolve_vue_api_pattern_config: Callable[[dict[str, Any]], tuple[str, str, str]]
    preview_endpoints_from_js: Callable[..., list[Any]]
    preview_endpoints_from_text: Callable[..., list[Any]]
    set_vue_api_preview_result: Callable[[dict[str, Any]], None]
    run_web_action: Callable[..., Awaitable[tuple[str, dict[str, Any]]]]
    run_api_extract: Callable[..., Any]
    set_vue_api_extract_result: Callable[[dict[str, Any]], None]


def _bind_route(
    handler: Callable[[Request, VueApiActionRouteDeps], Awaitable[Any]],
    deps: VueApiActionRouteDeps,
) -> Callable[[Request], Awaitable[Any]]:
    async def endpoint(request: Request):
        return await handler(request, deps)

    endpoint.__name__ = handler.__name__.lstrip("_")
    return endpoint


async def _action_vue_api_load(request: Request, deps: VueApiActionRouteDeps):
    form = await request.form()
    module3_form = deps.ui_state["module3_form"]
    previous_domain = deps.safe_str(module3_form.get("domain"))
    domain = deps.safe_str(form.get("domain"))
    selected_js_file = deps.safe_str(form.get("js_file"))
    if not domain:
        deps.set_error("domain is required")
        return deps.redirect(3)

    domain_changed = domain != previous_domain
    module3_form["domain"] = domain
    available_js_files = {
        token
        for token in (deps.safe_str(item) for item in deps.list_project_js_files(domain))
        if token
    }

    if domain_changed:
        module3_form["pattern"] = ""
        module3_form["js_file"] = ""
        module3_form["js_url"] = ""

    if selected_js_file:
        if selected_js_file in available_js_files:
            module3_form["js_file"] = selected_js_file
            module3_form["js_url"] = ""
        else:
            module3_form["js_file"] = ""
    else:
        current_js_file = deps.safe_str(module3_form.get("js_file"))
        if current_js_file and current_js_file not in available_js_files:
            module3_form["js_file"] = ""

    loaded_cfg = deps.get_vue_api_config_for_domain(domain)
    if loaded_cfg and (domain_changed or not deps.safe_str(module3_form.get("pattern"))):
        module3_form["pattern"] = loaded_cfg.get("pattern", "")

    deps.select_vue_api_domain(domain)
    deps.reset_vue_api_runtime_outputs()
    deps.clear_error()
    return deps.redirect(3)


async def _action_vue_api_beautify(request: Request, deps: VueApiActionRouteDeps):
    form = await request.form()
    deps.apply_vue_api_form(form)
    module3_form = deps.ui_state["module3_form"]

    try:
        domain = deps.safe_str(module3_form.get("domain"))
        if not domain:
            raise ValueError("domain is required")

        source_type, source_value, raw_js = deps.load_project_js_source(
            domain=domain,
            js_file=deps.safe_str(module3_form.get("js_file")),
            js_url=deps.safe_str(module3_form.get("js_url")),
        )
        deps.save_vue_api_config(domain, deps.safe_str(module3_form.get("pattern")))

        beautified = deps.beautify_js_code(raw_js)
        truncated = False
        if len(beautified) > deps.module3_js_max_display_chars:
            beautified = f"{beautified[:deps.module3_js_max_display_chars]}\n\n/* beautified output truncated */"
            truncated = True

        source_name = source_value if source_type == "file" else deps.js_source_name_from_url(source_value)
        deps.set_vue_api_beautify_result(
            {
                "domain": domain,
                "source_type": source_type,
                "source": source_value,
                "source_name": source_name,
                "raw_chars": len(raw_js),
                "beautified_chars": len(beautified),
                "truncated": truncated,
                "code": beautified,
            }
        )
        deps.select_vue_api_domain(domain)
        deps.clear_error()
    except Exception as exc:
        deps.set_error(str(exc))

    return deps.redirect(3)


async def _action_vue_api_preview(request: Request, deps: VueApiActionRouteDeps):
    form = await request.form()
    deps.apply_vue_api_form(form)
    module3_form = deps.ui_state["module3_form"]

    try:
        domain = deps.safe_str(module3_form.get("domain"))
        baseurl, baseapi, pattern = deps.resolve_vue_api_pattern_config(module3_form)
        deps.save_vue_api_config(domain, pattern)
        source_type, source_value, source_text = deps.load_project_js_source(
            domain=domain,
            js_file=deps.safe_str(module3_form.get("js_file")),
            js_url=deps.safe_str(module3_form.get("js_url")),
        )

        if source_type == "file":
            endpoints = deps.preview_endpoints_from_js(
                domain=domain,
                js_file=source_value,
                pattern=pattern,
                baseurl=baseurl,
                baseapi=baseapi,
                limit=120,
            )
            source_name = source_value
        else:
            source_name = deps.js_source_name_from_url(source_value)
            endpoints = deps.preview_endpoints_from_text(
                source_name=source_name,
                text=source_text,
                pattern=pattern,
                baseurl=baseurl,
                baseapi=baseapi,
                limit=120,
            )

        deps.set_vue_api_preview_result(
            {
                "domain": domain,
                "source_type": source_type,
                "source": source_value,
                "source_name": source_name,
                "count": len(endpoints),
                "endpoints": [item.to_dict() for item in endpoints],
            }
        )
        deps.select_vue_api_domain(domain)
        deps.clear_error()
    except Exception as exc:
        deps.set_error(str(exc))

    return deps.redirect(3)


async def _action_vue_api_extract(request: Request, deps: VueApiActionRouteDeps):
    form = await request.form()
    deps.apply_vue_api_form(form)
    module3_form = deps.ui_state["module3_form"]

    try:
        domain = deps.safe_str(module3_form.get("domain"))
        baseurl, baseapi, pattern = deps.resolve_vue_api_pattern_config(module3_form)
        deps.save_vue_api_config(domain, pattern)
        payload = {
            "domain": domain,
            "baseurl": baseurl,
            "baseapi": baseapi,
            "pattern": pattern,
        }
        job_id, result = await deps.run_web_action(
            "web_module3_api_extract",
            payload,
            lambda: deps.run_api_extract(
                domain=domain,
                pattern=pattern,
                baseurl=baseurl,
                baseapi=baseapi,
            ),
        )

        deps.set_vue_api_extract_result({"job_id": job_id, **result})
        deps.select_vue_api_domain(domain)
        deps.clear_error()
    except Exception as exc:
        deps.set_error(str(exc))

    return deps.redirect(3)


def build_vue_api_action_routes(deps: VueApiActionRouteDeps) -> list[Route]:
    # 保持原有 action 路径不变，只把实现迁到独立路由模块。
    return [
        Route("/actions/module3/load", endpoint=_bind_route(_action_vue_api_load, deps), methods=["POST"]),
        Route(
            "/actions/module3/js/beautify",
            endpoint=_bind_route(_action_vue_api_beautify, deps),
            methods=["POST"],
        ),
        Route("/actions/module3/preview", endpoint=_bind_route(_action_vue_api_preview, deps), methods=["POST"]),
        Route("/actions/module3/extract", endpoint=_bind_route(_action_vue_api_extract, deps), methods=["POST"]),
    ]
