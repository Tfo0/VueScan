from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.routing import Route


@dataclass(frozen=True)
class VueApiRouteDeps:
    # 用显式依赖替代反向 import app.py，避免 routes 模块和入口文件循环引用。
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
    run_web_action: Callable[..., Awaitable[tuple[str, dict[str, Any]]]]
    run_api_extract: Callable[..., Any]
    load_api_endpoints: Callable[[str], list[Any]]
    serialize_api_endpoint: Callable[[Any], dict[str, Any]]
    persist_project_preview_extract: Callable[..., str]


def _module3_form_from_state(deps: VueApiRouteDeps) -> dict[str, Any]:
    form = deps.ui_state.get("module3_form")
    return form if isinstance(form, dict) else {}


async def _read_json_payload(request: Request) -> dict[str, Any]:
    try:
        raw_payload = await request.json()
    except Exception:
        return {}
    return raw_payload if isinstance(raw_payload, dict) else {}


def _bind_route(
    handler: Callable[[Request, VueApiRouteDeps], Awaitable[Any]],
    deps: VueApiRouteDeps,
) -> Callable[[Request], Awaitable[Any]]:
    async def endpoint(request: Request):
        return await handler(request, deps)

    endpoint.__name__ = handler.__name__.lstrip("_")
    return endpoint


async def _api_vue_api_context(request: Request, deps: VueApiRouteDeps):
    query = request.query_params
    projects = deps.merge_project_domains(deps.list_projects(limit=3000))
    module3_form = _module3_form_from_state(deps)
    selected_domain = deps.safe_str(query.get("domain"))
    if not selected_domain:
        selected_domain = deps.safe_str(module3_form.get("domain")) if isinstance(module3_form, dict) else ""
    if not selected_domain and projects:
        selected_domain = projects[0]

    js_files = deps.list_project_js_files(selected_domain) if selected_domain else []
    js_urls = deps.list_project_js_urls(selected_domain) if selected_domain else []
    extract_result = deps.load_project_extract_result(selected_domain) if selected_domain else {}
    pattern = deps.safe_str(query.get("pattern"))
    if not pattern and isinstance(module3_form, dict) and deps.safe_str(module3_form.get("domain")) == selected_domain:
        pattern = deps.safe_str(module3_form.get("pattern"))
    if not pattern and selected_domain:
        pattern = deps.safe_str(deps.get_vue_api_config_for_domain(selected_domain).get("pattern"))

    selected_js_file = deps.safe_str(query.get("js_file"))
    if not selected_js_file and isinstance(module3_form, dict) and deps.safe_str(module3_form.get("domain")) == selected_domain:
        selected_js_file = deps.safe_str(module3_form.get("js_file"))
    if selected_js_file and selected_js_file not in js_files:
        selected_js_file = ""

    js_url = deps.safe_str(query.get("js_url"))
    if not js_url and isinstance(module3_form, dict) and deps.safe_str(module3_form.get("domain")) == selected_domain:
        js_url = deps.safe_str(module3_form.get("js_url"))
    if not js_url and selected_js_file:
        parsed_selected_js_file = urlsplit(selected_js_file)
        if parsed_selected_js_file.scheme.lower() in {"http", "https"} and parsed_selected_js_file.netloc:
            js_url = selected_js_file
            selected_js_file = ""

    if not selected_js_file and not js_url:
        if js_files:
            selected_js_file = js_files[0]
        elif js_urls:
            js_url = js_urls[0]

    deps.sync_vue_api_source_form(
        domain=selected_domain,
        js_file=selected_js_file,
        js_url=js_url,
    )
    if pattern:
        deps.sync_vue_api_source_form(pattern=pattern)

    return deps.json_ok(
        {
            "projects": projects,
            "domain": selected_domain,
            "js_files": js_files,
            "js_urls": js_urls,
            "js_file": selected_js_file,
            "js_url": js_url,
            "pattern": pattern,
            "extract_result": extract_result,
        }
    )


async def _api_vue_api_source_preview(request: Request, deps: VueApiRouteDeps):
    payload = await _read_json_payload(request)
    domain = deps.safe_str(payload.get("domain"))
    js_file = deps.safe_str(payload.get("js_file"))
    js_url = deps.safe_str(payload.get("js_url"))
    pattern = deps.safe_str(payload.get("pattern"))

    if not domain:
        return deps.json_error("domain is required", status_code=400)
    if not js_file and not js_url:
        return deps.json_error("js_file or js_url is required", status_code=400)

    try:
        source_type, source_value, source_text = deps.load_project_js_source(
            domain=domain,
            js_file=js_file,
            js_url=js_url,
        )
        source_preview = deps.build_source_preview_payload(
            source_type=source_type,
            source_value=source_value,
            source_text=source_text,
        )
        if pattern:
            deps.save_vue_api_config(domain, pattern)
        deps.sync_vue_api_source_form(domain=domain, js_file=js_file, js_url=js_url)
        if pattern:
            deps.sync_vue_api_source_form(pattern=pattern)
        deps.clear_error()
        return deps.json_ok({"source_preview": source_preview})
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_api_beautify(request: Request, deps: VueApiRouteDeps):
    payload = await _read_json_payload(request)
    domain = deps.safe_str(payload.get("domain"))
    js_file = deps.safe_str(payload.get("js_file"))
    js_url = deps.safe_str(payload.get("js_url"))
    pattern = deps.safe_str(payload.get("pattern"))
    if not domain:
        return deps.json_error("domain is required", status_code=400)
    if not js_file and not js_url:
        return deps.json_error("js_file or js_url is required", status_code=400)

    try:
        source_type, source_value, source_text = deps.load_project_js_source(
            domain=domain,
            js_file=js_file,
            js_url=js_url,
        )
        source_preview = deps.build_source_preview_payload(
            source_type=source_type,
            source_value=source_value,
            source_text=source_text,
        )
        beautified = deps.beautify_js_code(source_text)
        beautify_truncated = False
        if len(beautified) > deps.module3_js_max_display_chars:
            beautified = (
                f"{beautified[:deps.module3_js_max_display_chars]}\n\n"
                "/* beautified output truncated */"
            )
            beautify_truncated = True
        source_name = source_value if source_type == "file" else deps.js_source_name_from_url(source_value)
        beautify_payload = {
            "domain": domain,
            "source_type": source_type,
            "source": source_value,
            "source_name": source_name,
            "raw_chars": len(source_text),
            "beautified_chars": len(beautified),
            "truncated": beautify_truncated,
            "code": beautified,
        }
        if pattern:
            deps.save_vue_api_config(domain, pattern)
        deps.sync_vue_api_source_form(domain=domain, js_file=js_file, js_url=js_url)
        if pattern:
            deps.sync_vue_api_source_form(pattern=pattern)
        deps.set_vue_api_beautify_result(beautify_payload)
        deps.clear_error()
        return deps.json_ok({"beautify": beautify_payload, "source_preview": source_preview})
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_api_preview(request: Request, deps: VueApiRouteDeps):
    payload = await _read_json_payload(request)
    domain = deps.safe_str(payload.get("domain"))
    pattern = deps.safe_str(payload.get("pattern"))
    js_file = deps.safe_str(payload.get("js_file"))
    js_url = deps.safe_str(payload.get("js_url"))
    if not domain:
        return deps.json_error("domain is required", status_code=400)
    if not pattern:
        return deps.json_error("pattern is required", status_code=400)

    try:
        js_files = deps.list_project_js_files(domain)
        js_urls = deps.list_project_js_urls(domain)

        source_type = "all_chunks"
        source_value = "downChunk + vueRouter/js.txt"
        source_name = "all_chunks"
        preview_limit = 5000

        if js_file:
            endpoints = deps.preview_endpoints_from_js(
                domain=domain,
                js_file=js_file,
                pattern=pattern,
                baseurl="",
                baseapi="",
                limit=preview_limit,
            )
            source_type = "file"
            source_value = js_file
            source_name = js_file
        elif js_url:
            loaded_source_type, loaded_source_value, source_text = deps.load_project_js_source(
                domain=domain,
                js_file="",
                js_url=js_url,
            )
            endpoints = deps.preview_endpoints_from_text(
                source_name=deps.js_source_name_from_url(loaded_source_value),
                text=source_text,
                pattern=pattern,
                baseurl="",
                baseapi="",
                limit=preview_limit,
            )
            source_type = loaded_source_type
            source_value = loaded_source_value
            source_name = deps.js_source_name_from_url(loaded_source_value)
        else:
            endpoints = deps.preview_endpoints_from_all_chunks(
                domain=domain,
                pattern=pattern,
                baseurl="",
                baseapi="",
            )

        preview_payload = {
            "domain": domain,
            "source_type": source_type,
            "source": source_value,
            "source_name": source_name,
            "js_file_count": len(js_files),
            "js_url_count": len(js_urls),
            "count": len(endpoints),
            "endpoints": [item.to_dict() for item in endpoints],
        }
        deps.save_vue_api_config(domain, pattern)
        deps.sync_vue_api_source_form(
            domain=domain,
            pattern=pattern,
            js_file=js_file,
            js_url=js_url,
        )
        deps.set_vue_api_preview_result(preview_payload)
        deps.clear_error()
        return deps.json_ok({"preview": preview_payload})
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_api_auto_regex(request: Request, deps: VueApiRouteDeps):
    payload = await _read_json_payload(request)
    domain = deps.safe_str(payload.get("domain"))
    js_api_path = deps.safe_str(payload.get("js_api_path") or payload.get("jsApiPath"))
    target_api = deps.safe_str(payload.get("target_api") or payload.get("targetApi"))
    js_file = deps.safe_str(payload.get("js_file") or payload.get("jsFile"))
    max_candidates = deps.to_int(
        payload.get("max_candidates") or payload.get("maxCandidates"),
        default=3,
        minimum=1,
    )

    if not domain:
        return deps.json_error("domain is required", status_code=400)

    try:
        result = await asyncio.to_thread(
            deps.run_vue_api_auto_regex,
            domain=domain,
            js_api_path=js_api_path,
            target_api=target_api,
            js_file=js_file,
            max_candidates=max_candidates,
        )
        selected_pattern = deps.safe_str(result.get("selected_pattern"))
        if selected_pattern:
            deps.save_vue_api_config(domain, selected_pattern)
            deps.sync_vue_api_source_form(domain=domain, pattern=selected_pattern)
            if js_file:
                deps.sync_vue_api_source_form(js_file=js_file)
        deps.clear_error()
        return deps.json_ok({"auto_regex": result})
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_api_extract(request: Request, deps: VueApiRouteDeps):
    payload = await _read_json_payload(request)
    domain = deps.safe_str(payload.get("domain"))
    pattern = deps.safe_str(payload.get("pattern"))
    if not domain:
        return deps.json_error("domain is required", status_code=400)
    if not pattern:
        return deps.json_error("pattern is required", status_code=400)

    try:
        deps.save_vue_api_config(domain, pattern)
        job_id, result = await deps.run_web_action(
            "web_vue_api_extract",
            {"domain": domain, "pattern": pattern},
            lambda: deps.run_api_extract(domain=domain, pattern=pattern, baseurl="", baseapi=""),
        )
        endpoint_rows: list[dict[str, Any]] = []
        try:
            endpoints = deps.load_api_endpoints(domain)
            endpoint_rows = [deps.serialize_api_endpoint(item) for item in endpoints]
        except Exception:
            endpoint_rows = []

        endpoint_count = deps.to_int(
            result.get("endpoint_count"),
            default=len(endpoint_rows),
            minimum=0,
        )
        extract_result = {
            "job_id": job_id,
            **result,
            "endpoint_count": endpoint_count,
            "count": endpoint_count,
            "endpoints": endpoint_rows,
        }
        deps.sync_vue_api_source_form(domain=domain, pattern=pattern)
        deps.set_vue_api_extract_result(extract_result)
        deps.clear_error()
        return deps.json_ok({"extract_result": extract_result})
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_api_save_preview(request: Request, deps: VueApiRouteDeps):
    payload = await _read_json_payload(request)
    domain = deps.safe_str(payload.get("domain"))
    pattern = deps.safe_str(payload.get("pattern"))
    source_type = deps.safe_str(payload.get("source_type") or payload.get("sourceType"))
    source = deps.safe_str(payload.get("source"))
    source_name = deps.safe_str(payload.get("source_name") or payload.get("sourceName"))
    raw_endpoints = payload.get("endpoints")

    if not domain:
        return deps.json_error("domain is required", status_code=400)
    if not pattern:
        return deps.json_error("pattern is required", status_code=400)
    if not isinstance(raw_endpoints, list) or not raw_endpoints:
        return deps.json_error("endpoints is required", status_code=400)

    endpoint_rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw_endpoints, start=1):
        if not isinstance(item, dict):
            continue
        endpoint_rows.append(
            {
                "id": deps.to_int(item.get("id"), default=index, minimum=1),
                "method": deps.safe_str(item.get("method"), "GET").upper() or "GET",
                "path": deps.safe_str(item.get("path")),
                "url": deps.safe_str(item.get("url")),
                "source_file": deps.safe_str(item.get("source_file")),
                "source_line": deps.to_int(item.get("source_line"), default=0, minimum=0),
                "match_text": deps.safe_str(item.get("match_text")),
            }
        )

    if not endpoint_rows:
        return deps.json_error("no valid endpoints to save", status_code=400)

    try:
        output_path = deps.persist_project_preview_extract(
            domain,
            pattern=pattern,
            endpoints=endpoint_rows,
            source_type=source_type or "preview",
            source=source,
            source_name=source_name,
        )
        extract_result = {
            "job_id": "",
            "domain": domain,
            "endpoint_count": len(endpoint_rows),
            "count": len(endpoint_rows),
            "endpoints": endpoint_rows,
            "output_path": output_path,
        }
        deps.save_vue_api_config(domain, pattern)
        deps.sync_vue_api_source_form(domain=domain, pattern=pattern)
        deps.set_vue_api_extract_result(extract_result)
        deps.clear_error()
        return deps.json_ok({"extract_result": extract_result})
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


def build_vue_api_routes(deps: VueApiRouteDeps) -> list[Route]:
    # 这里仅注册 VueApi 模块自己的 HTTP 路由，业务逻辑继续下沉到 src/vue_api。
    return [
        Route("/api/vueApi/context", endpoint=_bind_route(_api_vue_api_context, deps), methods=["GET"]),
        Route(
            "/api/vueApi/source-preview",
            endpoint=_bind_route(_api_vue_api_source_preview, deps),
            methods=["POST"],
        ),
        Route("/api/vueApi/beautify", endpoint=_bind_route(_api_vue_api_beautify, deps), methods=["POST"]),
        Route("/api/vueApi/preview", endpoint=_bind_route(_api_vue_api_preview, deps), methods=["POST"]),
        Route("/api/vueApi/auto-regex", endpoint=_bind_route(_api_vue_api_auto_regex, deps), methods=["POST"]),
        Route("/api/vueApi/extract", endpoint=_bind_route(_api_vue_api_extract, deps), methods=["POST"]),
        Route("/api/vueApi/save-preview", endpoint=_bind_route(_api_vue_api_save_preview, deps), methods=["POST"]),
    ]
