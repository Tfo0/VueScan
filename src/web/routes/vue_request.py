from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from starlette.requests import Request
from starlette.routing import Route


@dataclass(frozen=True)
class VueRequestRouteDeps:
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
    run_web_action: Callable[..., Awaitable[tuple[str, dict[str, Any]]]]
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


def _module4_form_from_state(deps: VueRequestRouteDeps) -> dict[str, Any]:
    form = deps.ui_state.get("module4_form")
    return form if isinstance(form, dict) else {}


async def _read_json_payload(request: Request) -> dict[str, Any]:
    try:
        raw_payload = await request.json()
    except Exception:
        return {}
    return raw_payload if isinstance(raw_payload, dict) else {}


def _bind_route(
    handler: Callable[[Request, VueRequestRouteDeps], Awaitable[Any]],
    deps: VueRequestRouteDeps,
) -> Callable[[Request], Awaitable[Any]]:
    async def endpoint(request: Request):
        return await handler(request, deps)

    endpoint.__name__ = handler.__name__.lstrip("_")
    return endpoint


def _resolve_request_domain(
    request: Request,
    payload: dict[str, Any],
    deps: VueRequestRouteDeps,
) -> str:
    # 统一处理 domain 回退顺序，避免几个接口重复拼装同样的兜底逻辑。
    domain = deps.safe_str(payload.get("domain"))
    if not domain:
        domain = deps.safe_str(request.query_params.get("domain"))
    if not domain:
        module4_form = _module4_form_from_state(deps)
        domain = deps.safe_str(module4_form.get("domain")) if isinstance(module4_form, dict) else ""
    return domain


def _apply_inferred_request_state(
    deps: VueRequestRouteDeps,
    *,
    domain: str,
    result: dict[str, Any],
) -> None:
    # 推断成功后统一回填请求页状态，保持 API 和表单入口行为一致。
    if not bool(result.get("inferred")):
        return
    baseurl = deps.safe_str(result.get("baseurl"))
    baseapi = deps.safe_str(result.get("baseapi"))
    deps.sync_vue_api_request_state(
        domain=domain,
        baseurl=baseurl,
        baseapi=baseapi,
    )
    deps.persist_project_request_config(domain, baseurl=baseurl, baseapi=baseapi)
    matched = result.get("matched") if isinstance(result.get("matched"), dict) else {}
    endpoint_id = deps.safe_str(matched.get("endpoint_id"))
    endpoint_method = deps.safe_str(matched.get("endpoint_method"))
    if endpoint_id:
        deps.sync_vue_api_request_state(api_id=endpoint_id)
    if endpoint_method:
        deps.sync_vue_api_request_state(method=endpoint_method)


def _resolve_effective_request_base(
    deps: VueRequestRouteDeps,
    *,
    domain: str,
    baseurl: str = "",
    baseapi: str = "",
    infer_rows: Any = None,
) -> tuple[str, str]:
    # 统一处理基址回退：显式入参 -> 页面状态 -> 项目配置 -> 自动推断。
    module4_form = _module4_form_from_state(deps)
    loaded_cfg = deps.load_project_request_config(domain) if domain else {}

    effective_baseurl = deps.safe_str(baseurl)
    effective_baseapi = deps.safe_str(baseapi)

    if not effective_baseurl:
        if isinstance(module4_form, dict) and deps.safe_str(module4_form.get("domain")) == domain:
            effective_baseurl = deps.safe_str(module4_form.get("baseurl"))
        if not effective_baseurl:
            effective_baseurl = deps.safe_str(loaded_cfg.get("baseurl"))

    if not effective_baseapi:
        if isinstance(module4_form, dict) and deps.safe_str(module4_form.get("domain")) == domain:
            effective_baseapi = deps.safe_str(module4_form.get("baseapi"))
        if not effective_baseapi:
            effective_baseapi = deps.safe_str(loaded_cfg.get("baseapi"))

    if effective_baseurl:
        return effective_baseurl, effective_baseapi

    try:
        if infer_rows is None:
            infer_result = deps.infer_request_base(
                domain,
                load_api_endpoints=deps.load_api_endpoints,
                serialize_api_endpoint=deps.serialize_api_endpoint,
            )
        else:
            infer_result = deps.infer_request_base_from_paths(domain, infer_rows)
    except Exception:
        infer_result = {}

    if bool(infer_result.get("inferred")):
        _apply_inferred_request_state(deps, domain=domain, result=infer_result)
        effective_baseurl = deps.safe_str(infer_result.get("baseurl"))
        effective_baseapi = deps.safe_str(infer_result.get("baseapi"))

    return effective_baseurl, effective_baseapi


def _request_batch_job_result(raw_job: dict[str, Any]) -> dict[str, Any]:
    result = raw_job.get("result")
    return result if isinstance(result, dict) else {}


def _request_batch_job_status(raw_job: dict[str, Any], deps: VueRequestRouteDeps) -> str:
    return deps.safe_str(raw_job.get("status")).lower()


def _is_vue_request_batch_job(raw_job: dict[str, Any], deps: VueRequestRouteDeps) -> bool:
    return deps.safe_str(raw_job.get("step")) == deps.vue_request_batch_job_step


async def _api_vue_request_context(request: Request, deps: VueRequestRouteDeps):
    query = request.query_params
    projects = deps.merge_project_domains(deps.list_projects(limit=3000))
    module4_form = _module4_form_from_state(deps)

    domain = deps.safe_str(query.get("domain"))
    if not domain:
        domain = deps.safe_str(module4_form.get("domain")) if isinstance(module4_form, dict) else ""
    if not domain and projects:
        domain = projects[0]

    loaded_cfg = deps.load_project_request_config(domain) if domain else {}
    baseurl = deps.safe_str(query.get("baseurl"))
    baseapi = deps.safe_str(query.get("baseapi"))
    if not baseurl:
        if isinstance(module4_form, dict) and deps.safe_str(module4_form.get("domain")) == domain:
            baseurl = deps.safe_str(module4_form.get("baseurl"))
        if not baseurl:
            baseurl = deps.safe_str(loaded_cfg.get("baseurl"))
    if not baseapi:
        if isinstance(module4_form, dict) and deps.safe_str(module4_form.get("domain")) == domain:
            baseapi = deps.safe_str(module4_form.get("baseapi"))
        if not baseapi:
            baseapi = deps.safe_str(loaded_cfg.get("baseapi"))

    endpoints: list[Any] = []
    endpoints_error = ""
    if domain:
        try:
            endpoints = deps.load_api_endpoints(domain)
        except Exception as exc:
            endpoints_error = str(exc)

    endpoint_rows = [deps.serialize_api_endpoint(item) for item in endpoints]
    selected_api_id = deps.safe_str(query.get("api_id"))
    if not selected_api_id and isinstance(module4_form, dict) and deps.safe_str(module4_form.get("domain")) == domain:
        selected_api_id = deps.safe_str(module4_form.get("api_id"))
    if not selected_api_id and endpoint_rows:
        selected_api_id = str(endpoint_rows[0].get("id"))

    selected_endpoint = next((item for item in endpoint_rows if str(item.get("id")) == selected_api_id), None)
    method = deps.safe_str(query.get("method"))
    if not method and isinstance(module4_form, dict) and deps.safe_str(module4_form.get("domain")) == domain:
        method = deps.safe_str(module4_form.get("method"))
    if not method and selected_endpoint:
        method = deps.safe_str(selected_endpoint.get("method"), "GET").upper()

    timeout = deps.to_int(
        query.get("timeout"),
        default=deps.to_int(module4_form.get("timeout"), default=20, minimum=1),
        minimum=1,
    )
    json_body = ""
    headers = ""
    if isinstance(module4_form, dict) and deps.safe_str(module4_form.get("domain")) == domain:
        json_body = deps.safe_str(module4_form.get("json_body"))
        headers = deps.safe_str(module4_form.get("headers"))

    deps.sync_vue_api_request_state(
        domain=domain,
        baseurl=baseurl,
        baseapi=baseapi,
        api_id=selected_api_id,
        method=method,
        timeout=str(timeout),
    )

    capture_request_total = 0
    capture_template_total = 0
    captured_requests: list[dict[str, Any]] = []
    saved_results: list[dict[str, object]] = []
    request_snapshots: list[dict[str, object]] = []
    if domain:
        try:
            captured_requests = deps.load_captured_request_items(domain)
            capture_request_total = len(captured_requests)
            capture_template_total = len(deps.load_captured_request_templates(domain))
        except Exception:
            captured_requests = []
        try:
            saved_results = deps.load_saved_request_results(domain)
        except Exception:
            saved_results = []
        try:
            request_snapshots = deps.load_request_run_snapshots(domain)
        except Exception:
            request_snapshots = []

    return deps.json_ok(
        {
            "projects": projects,
            "domain": domain,
            "baseurl": baseurl,
            "baseapi": baseapi,
            "endpoints": endpoint_rows,
            "endpoints_error": endpoints_error,
            "api_id": selected_api_id,
            "method": method,
            "timeout": timeout,
            "json_body": json_body,
            "headers": headers,
            "capture_request_total": capture_request_total,
            "capture_template_total": capture_template_total,
            "captured_requests": captured_requests,
            "saved_results": saved_results,
            "request_snapshots": request_snapshots,
        }
    )


async def _api_vue_request_infer_base(request: Request, deps: VueRequestRouteDeps):
    payload = await _read_json_payload(request)
    domain = _resolve_request_domain(request, payload, deps)
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    try:
        result = deps.infer_request_base(
            domain,
            load_api_endpoints=deps.load_api_endpoints,
            serialize_api_endpoint=deps.serialize_api_endpoint,
        )
        _apply_inferred_request_state(deps, domain=domain, result=result)
        deps.clear_error()
        return deps.json_ok({"infer_result": result})
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_request_infer_base_from_paths(request: Request, deps: VueRequestRouteDeps):
    payload = await _read_json_payload(request)
    domain = _resolve_request_domain(request, payload, deps)
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    endpoint_rows = payload.get("endpoints")
    if endpoint_rows is None:
        endpoint_rows = payload.get("api_paths")

    try:
        result = deps.infer_request_base_from_paths(domain, endpoint_rows)
        _apply_inferred_request_state(deps, domain=domain, result=result)
        deps.clear_error()
        return deps.json_ok({"infer_result": result})
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_request_send(request: Request, deps: VueRequestRouteDeps):
    payload = await _read_json_payload(request)

    try:
        request_inputs = deps.parse_request_dispatch_inputs(payload)
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)

    domain = deps.safe_str(request_inputs.get("domain"))
    api_id = deps.to_int(request_inputs.get("api_id"), default=0, minimum=0)
    method = deps.safe_str(request_inputs.get("method")).upper()
    baseurl = deps.safe_str(request_inputs.get("baseurl"))
    baseapi = deps.safe_str(request_inputs.get("baseapi"))
    base_query = deps.safe_str(payload.get("base_query"))
    timeout = deps.to_int(request_inputs.get("timeout"), default=20, minimum=1)

    use_capture_template = True
    if "use_capture_template" in payload:
        use_capture_template = deps.to_bool(payload.get("use_capture_template"))
    request_url_override_input = deps.safe_str(payload.get("request_url_override"))

    body_type = deps.safe_str(payload.get("body_type")).lower()
    explicit_body_text = ""
    explicit_content_type = ""
    raw_json_input = payload.get("json_body")
    raw_headers_input = payload.get("headers")
    parse_json_input = raw_json_input
    if body_type == "form":
        explicit_body_text = deps.safe_str(payload.get("body_text"))
        if not explicit_body_text:
            explicit_body_text = deps.safe_str(raw_json_input)
        explicit_content_type = (
            deps.safe_str(payload.get("content_type"))
            or "application/x-www-form-urlencoded; charset=utf-8"
        )
        parse_json_input = ""
    try:
        parsed_inputs = deps.parse_request_payload_inputs(
            raw_json_input=parse_json_input,
            raw_headers_input=raw_headers_input,
        )
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)

    json_body = parsed_inputs.get("json_body")
    headers = parsed_inputs.get("headers") if isinstance(parsed_inputs.get("headers"), dict) else None
    json_body_provided = bool(parsed_inputs.get("json_body_provided"))

    try:
        endpoints = deps.load_api_endpoints(domain)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    baseurl, baseapi = _resolve_effective_request_base(
        deps,
        domain=domain,
        baseurl=baseurl,
        baseapi=baseapi,
    )

    endpoint = deps.find_api_endpoint_by_id(endpoints, api_id)
    if endpoint is None:
        return deps.json_error(f"api id not found: {api_id}", status_code=404)

    endpoint_path = deps.safe_str(getattr(endpoint, "path", "") or getattr(endpoint, "url", ""))
    endpoint_method = deps.safe_str(method or getattr(endpoint, "method", "GET"), "GET").upper() or "GET"
    if not method:
        method = endpoint_method

    template_runtime = deps.prepare_template_replay_request(
        domain=domain,
        endpoint_path=endpoint_path,
        endpoint_method=endpoint_method,
        baseurl=baseurl,
        baseapi=baseapi,
        use_capture_template=use_capture_template,
        headers=headers,
        json_body=json_body,
        json_body_provided=json_body_provided,
    )
    template_replay = (
        template_runtime.get("template_replay")
        if isinstance(template_runtime.get("template_replay"), dict)
        else {}
    )
    headers = template_runtime.get("headers") if isinstance(template_runtime.get("headers"), dict) else None
    json_body = template_runtime.get("json_body")
    request_url_override = deps.safe_str(template_runtime.get("request_url_override"))
    if request_url_override_input:
        # 允许请求页临时覆盖单条请求 URL，便于在响应区就地微调 path/query 后重放。
        request_url_override = request_url_override_input
    body_text = explicit_body_text or deps.safe_str(template_runtime.get("body_text"))
    content_type = explicit_content_type or deps.safe_str(template_runtime.get("content_type"))
    used_template_url = bool(template_runtime.get("used_template_url"))
    used_template_headers = bool(template_runtime.get("used_template_headers"))
    used_template_body = bool(template_runtime.get("used_template_body"))

    try:
        job_id, result = await deps.run_web_action(
            "web_vue_request_api_request",
            {
                "domain": domain,
                "api_id": api_id,
                "method": method,
                "baseurl": baseurl,
                "baseapi": baseapi,
                "base_query": base_query,
                "timeout": timeout,
                "use_capture_template": use_capture_template,
                "template_matched": bool(template_replay),
                "request_url_override": request_url_override,
            },
            lambda: deps.run_api_request(
                domain=domain,
                api_id=api_id,
                method=method or None,
                baseurl=baseurl,
                baseapi=baseapi,
                base_query=base_query,
                json_body=json_body,
                headers=headers,
                timeout=timeout,
                request_url_override=request_url_override or None,
                body_text=body_text or None,
                content_type=content_type or None,
            ),
        )

        response_detail = deps.load_saved_response_detail(result.get("response_path"))
        raw_body_input = payload.get("body_text") if body_type == "form" else payload.get("json_body")
        json_body_text = deps.format_request_payload_text(raw_body_input, json_body, fallback_text=body_text)
        headers_text = deps.format_request_payload_text(payload.get("headers"), headers)

        deps.sync_vue_api_request_state(
            domain=domain,
            baseurl=baseurl,
            baseapi=baseapi,
            api_id=str(api_id),
            method=method,
            timeout=str(timeout),
            json_body=json_body_text,
            headers=headers_text,
        )

        request_result = {"job_id": job_id, **result}
        request_result["template_replay"] = deps.build_template_replay_summary(
            use_capture_template=use_capture_template,
            template_replay=template_replay,
            used_template_url=used_template_url,
            used_template_headers=used_template_headers,
            used_template_body=used_template_body,
        )
        deps.set_vue_api_request_result(request_result)
        deps.clear_error()
        return deps.json_ok({"request_result": request_result, "response_detail": response_detail})
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_request_batch(request: Request, deps: VueRequestRouteDeps):
    payload = await _read_json_payload(request)
    domain = _resolve_request_domain(request, payload, deps)
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    request_rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    if not request_rows:
        request_rows = payload.get("endpoints") if isinstance(payload.get("endpoints"), list) else []
    if not request_rows:
        return deps.json_error("rows are required", status_code=400)

    method = deps.safe_str(payload.get("method"), "GET").upper() or "GET"
    baseurl = deps.safe_str(payload.get("baseurl"))
    baseapi = deps.safe_str(payload.get("baseapi"))
    base_query = deps.safe_str(payload.get("base_query"))
    timeout = deps.to_int(payload.get("timeout"), default=20, minimum=1)
    concurrency = deps.to_int(payload.get("concurrency"), default=16, minimum=1)
    use_capture_template = True
    if "use_capture_template" in payload:
        use_capture_template = deps.to_bool(payload.get("use_capture_template"))
    body_type = deps.safe_str(payload.get("body_type")).lower()
    explicit_body_text = ""
    explicit_content_type = ""
    raw_json_input = payload.get("json_body")
    parse_json_input = raw_json_input
    if body_type == "form":
        explicit_body_text = deps.safe_str(payload.get("body_text"))
        if not explicit_body_text:
            explicit_body_text = deps.safe_str(raw_json_input)
        explicit_content_type = (
            deps.safe_str(payload.get("content_type"))
            or "application/x-www-form-urlencoded; charset=utf-8"
        )
        parse_json_input = ""

    try:
        parsed_inputs = deps.parse_request_payload_inputs(
            raw_json_input=parse_json_input,
            raw_headers_input=payload.get("headers"),
        )
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)

    json_body = parsed_inputs.get("json_body")
    headers = parsed_inputs.get("headers") if isinstance(parsed_inputs.get("headers"), dict) else None
    json_body_provided = bool(parsed_inputs.get("json_body_provided"))
    baseurl, baseapi = _resolve_effective_request_base(
        deps,
        domain=domain,
        baseurl=baseurl,
        baseapi=baseapi,
        infer_rows=request_rows,
    )

    try:
        job = deps.queue_request_batch(
            domain=domain,
            request_rows=request_rows,
            method=method,
            baseurl=baseurl,
            baseapi=baseapi,
            base_query=base_query,
            timeout=timeout,
            headers=headers,
            json_body=json_body,
            json_body_provided=json_body_provided,
            body_text=explicit_body_text,
            content_type=explicit_content_type,
            use_capture_template=use_capture_template,
            concurrency=concurrency,
        )
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    raw_body_input = payload.get("body_text") if body_type == "form" else payload.get("json_body")
    json_body_text = deps.format_request_payload_text(raw_body_input, json_body, fallback_text=explicit_body_text)
    headers_text = deps.format_request_payload_text(payload.get("headers"), headers)
    deps.sync_vue_api_request_state(
        domain=domain,
        baseurl=baseurl,
        baseapi=baseapi,
        method=method,
        timeout=str(timeout),
        json_body=json_body_text,
        headers=headers_text,
    )
    deps.clear_error()
    return deps.json_ok({"job": deps.serialize_request_batch_job(job)})


async def _api_vue_request_job_detail(request: Request, deps: VueRequestRouteDeps):
    job_id = deps.safe_str(request.path_params.get("job_id"))
    if not job_id:
        return deps.json_error("job_id is required", status_code=400)

    try:
        job = deps.read_job(job_id)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    if not _is_vue_request_batch_job(job, deps):
        return deps.json_error("vue request batch job not found", status_code=404)
    return deps.json_ok({"job": deps.serialize_request_batch_job(job)})


async def _api_vue_request_job_pause(request: Request, deps: VueRequestRouteDeps):
    job_id = deps.safe_str(request.path_params.get("job_id"))
    if not job_id:
        return deps.json_error("job_id is required", status_code=400)

    try:
        job = deps.read_job(job_id)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    if not _is_vue_request_batch_job(job, deps):
        return deps.json_error("vue request batch job not found", status_code=404)

    current_status = _request_batch_job_status(job, deps)
    if current_status != "running":
        return deps.json_error("only running jobs can be paused", status_code=400)

    result = _request_batch_job_result(job)
    merged_result = dict(result)
    progress = merged_result.get("progress") if isinstance(merged_result.get("progress"), dict) else {}
    progress = dict(progress)
    progress["phase"] = deps.safe_str(progress.get("phase"), "running")
    progress["stop_requested"] = bool(merged_result.get("stop_requested"))
    merged_result["progress"] = progress

    try:
        updated = deps.update_job(job_id=job_id, status="paused", result=merged_result)
        deps.append_log(job_id, "request batch pause requested")
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)
    return deps.json_ok({"job": deps.serialize_request_batch_job(updated)})


async def _api_vue_request_job_resume(request: Request, deps: VueRequestRouteDeps):
    job_id = deps.safe_str(request.path_params.get("job_id"))
    if not job_id:
        return deps.json_error("job_id is required", status_code=400)

    try:
        job = deps.read_job(job_id)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    if not _is_vue_request_batch_job(job, deps):
        return deps.json_error("vue request batch job not found", status_code=404)

    current_status = _request_batch_job_status(job, deps)
    if current_status != "paused":
        return deps.json_error("only paused jobs can be resumed", status_code=400)

    result = _request_batch_job_result(job)
    merged_result = dict(result)
    merged_result["stop_requested"] = False
    progress = merged_result.get("progress") if isinstance(merged_result.get("progress"), dict) else {}
    progress = dict(progress)
    progress["phase"] = "running"
    progress["stop_requested"] = False
    merged_result["progress"] = progress

    try:
        updated = deps.update_job(job_id=job_id, status="running", result=merged_result)
        deps.append_log(job_id, "request batch resume requested")
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)
    return deps.json_ok({"job": deps.serialize_request_batch_job(updated)})


async def _api_vue_request_job_stop(request: Request, deps: VueRequestRouteDeps):
    job_id = deps.safe_str(request.path_params.get("job_id"))
    if not job_id:
        return deps.json_error("job_id is required", status_code=400)

    try:
        job = deps.read_job(job_id)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    if not _is_vue_request_batch_job(job, deps):
        return deps.json_error("vue request batch job not found", status_code=404)

    current_status = _request_batch_job_status(job, deps)
    if current_status in {"completed", "failed", "stopped", "cancelled", "canceled"}:
        return deps.json_ok({"job": deps.serialize_request_batch_job(job)})

    result = _request_batch_job_result(job)
    merged_result = dict(result)
    merged_result["stop_requested"] = True
    progress = merged_result.get("progress") if isinstance(merged_result.get("progress"), dict) else {}
    progress = dict(progress)
    progress["stop_requested"] = True
    progress["phase"] = "stopping" if current_status == "running" else "stopped"
    merged_result["progress"] = progress

    try:
        if current_status in {"queued", "paused"}:
            updated = deps.update_job(job_id=job_id, status="stopped", result=merged_result)
        else:
            updated = deps.update_job(job_id=job_id, status="running", result=merged_result)
        deps.append_log(job_id, "request batch stop requested")
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)
    return deps.json_ok({"job": deps.serialize_request_batch_job(updated)})


async def _api_vue_request_response_detail(request: Request, deps: VueRequestRouteDeps):
    response_path = deps.safe_str(request.query_params.get("response_path"))
    if not response_path:
        return deps.json_error("response_path is required", status_code=400)

    detail = deps.load_saved_response_detail(response_path)
    if not detail:
        return deps.json_error("response detail not found", status_code=404)
    return deps.json_ok({"response_detail": detail})


async def _api_vue_request_save_result(request: Request, deps: VueRequestRouteDeps):
    payload = await _read_json_payload(request)
    domain = _resolve_request_domain(request, payload, deps)
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    request_result = payload.get("request_result") if isinstance(payload.get("request_result"), dict) else {}
    if not request_result:
        return deps.json_error("request_result is required", status_code=400)

    response_path = deps.safe_str(request_result.get("response_path"))
    if not response_path:
        return deps.json_error("response_path is required", status_code=400)

    response_detail = payload.get("response_detail") if isinstance(payload.get("response_detail"), dict) else {}
    if not response_detail:
        response_detail = deps.load_saved_response_detail(response_path)

    try:
        saved_result = deps.save_saved_request_result(
            domain=domain,
            row_key=deps.safe_str(payload.get("row_key")),
            endpoint_id=deps.to_int(payload.get("endpoint_id"), default=0, minimum=0),
            path=deps.safe_str(payload.get("path")),
            request_result=request_result,
            response_detail=response_detail,
            response_length=deps.to_int(payload.get("response_length"), default=0, minimum=0),
            packet_length=deps.to_int(payload.get("packet_length"), default=0, minimum=0),
        )
        saved_results = deps.load_saved_request_results(domain)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    return deps.json_ok({"saved_result": saved_result, "saved_results": saved_results})


async def _api_vue_request_save_results(request: Request, deps: VueRequestRouteDeps):
    payload = await _read_json_payload(request)
    domain = _resolve_request_domain(request, payload, deps)
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    if not rows:
        return deps.json_error("rows are required", status_code=400)

    saved_count = 0
    try:
        for item in rows:
            if not isinstance(item, dict):
                continue
            request_result = item.get("request_result") if isinstance(item.get("request_result"), dict) else {}
            if not request_result:
                continue
            response_path = deps.safe_str(request_result.get("response_path"))
            if not response_path:
                continue
            response_detail = item.get("response_detail") if isinstance(item.get("response_detail"), dict) else {}
            if not response_detail:
                response_detail = deps.load_saved_response_detail(response_path)
            deps.save_saved_request_result(
                domain=domain,
                row_key=deps.safe_str(item.get("row_key")),
                endpoint_id=deps.to_int(item.get("endpoint_id"), default=0, minimum=0),
                path=deps.safe_str(item.get("path")),
                request_result=request_result,
                response_detail=response_detail,
                response_length=deps.to_int(item.get("response_length"), default=0, minimum=0),
                packet_length=deps.to_int(item.get("packet_length"), default=0, minimum=0),
            )
            saved_count += 1
        saved_results = deps.load_saved_request_results(domain)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    return deps.json_ok({"saved_count": saved_count, "saved_results": saved_results})


async def _api_vue_request_snapshots(request: Request, deps: VueRequestRouteDeps):
    domain = _resolve_request_domain(request, {}, deps)
    if not domain:
        return deps.json_error("domain is required", status_code=400)
    try:
        snapshots = deps.load_request_run_snapshots(domain)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)
    return deps.json_ok({"snapshots": snapshots})


async def _api_vue_request_save_snapshot(request: Request, deps: VueRequestRouteDeps):
    payload = await _read_json_payload(request)
    domain = _resolve_request_domain(request, payload, deps)
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    job_id = deps.safe_str(payload.get("job_id"))
    request_payload = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    if not job_id:
        return deps.json_error("job_id is required", status_code=400)
    if not rows:
        return deps.json_error("rows are required", status_code=400)

    try:
        snapshot = deps.save_request_run_snapshot(
            domain=domain,
            job_id=job_id,
            status=deps.safe_str(payload.get("status")),
            request=request_payload,
            rows=[item for item in rows if isinstance(item, dict)],
        )
        snapshots = deps.load_request_run_snapshots(domain)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    return deps.json_ok({"snapshot": snapshot, "snapshots": snapshots})


async def _api_vue_request_delete_snapshot(request: Request, deps: VueRequestRouteDeps):
    payload = await _read_json_payload(request)
    domain = _resolve_request_domain(request, payload, deps)
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    snapshot_id = deps.safe_str(payload.get("snapshot_id"))
    if not snapshot_id:
        return deps.json_error("snapshot_id is required", status_code=400)

    try:
        snapshots = deps.delete_request_run_snapshot(domain=domain, snapshot_id=snapshot_id)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    return deps.json_ok({"snapshots": snapshots})


def build_vue_request_routes(deps: VueRequestRouteDeps) -> list[Route]:
    # 这里只注册 VueRequest 自己的 HTTP 路由，业务逻辑继续留在 src/vue_api 和 src/vue_chunk。
    return [
        Route("/api/vueRequest/context", endpoint=_bind_route(_api_vue_request_context, deps), methods=["GET"]),
        Route("/api/vueRequest/infer-base", endpoint=_bind_route(_api_vue_request_infer_base, deps), methods=["POST"]),
        Route(
            "/api/vueRequest/infer-base-from-paths",
            endpoint=_bind_route(_api_vue_request_infer_base_from_paths, deps),
            methods=["POST"],
        ),
        Route("/api/vueRequest/request", endpoint=_bind_route(_api_vue_request_send, deps), methods=["POST"]),
        Route("/api/vueRequest/request-batch", endpoint=_bind_route(_api_vue_request_batch, deps), methods=["POST"]),
        Route("/api/vueRequest/jobs/{job_id}", endpoint=_bind_route(_api_vue_request_job_detail, deps), methods=["GET"]),
        Route(
            "/api/vueRequest/jobs/{job_id}/pause",
            endpoint=_bind_route(_api_vue_request_job_pause, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueRequest/jobs/{job_id}/resume",
            endpoint=_bind_route(_api_vue_request_job_resume, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueRequest/jobs/{job_id}/stop",
            endpoint=_bind_route(_api_vue_request_job_stop, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueRequest/response-detail",
            endpoint=_bind_route(_api_vue_request_response_detail, deps),
            methods=["GET"],
        ),
        Route(
            "/api/vueRequest/save-result",
            endpoint=_bind_route(_api_vue_request_save_result, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueRequest/save-results",
            endpoint=_bind_route(_api_vue_request_save_results, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueRequest/run-snapshots",
            endpoint=_bind_route(_api_vue_request_snapshots, deps),
            methods=["GET"],
        ),
        Route(
            "/api/vueRequest/save-snapshot",
            endpoint=_bind_route(_api_vue_request_save_snapshot, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueRequest/delete-snapshot",
            endpoint=_bind_route(_api_vue_request_delete_snapshot, deps),
            methods=["POST"],
        ),
    ]
