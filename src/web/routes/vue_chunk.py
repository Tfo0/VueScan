from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.routing import Route
from src.vue_chunk.job_state import describe_vue_chunk_job_phase


@dataclass(frozen=True)
class VueChunkRouteDeps:
    # VueChunk 的 JSON API 路由先从 app.py 拆出，业务计算仍通过显式依赖注入调用原有服务。
    ui_state: dict[str, Any]
    safe_str: Callable[[Any, str], str]
    to_int: Callable[[Any, int, int], int]
    to_bool: Callable[[Any], bool]
    json_ok: Callable[..., Any]
    json_error: Callable[..., Any]
    clear_error: Callable[[], None]
    merge_project_domains: Callable[[list[Any]], list[str]]
    list_projects: Callable[..., list[Any]]
    list_detect_tasks: Callable[..., list[Any]]
    get_project: Callable[[str], dict[str, Any] | None]
    upsert_project_from_url: Callable[..., dict[str, Any]]
    update_project_title: Callable[[str, str | None], dict[str, Any]]
    delete_project: Callable[..., dict[str, Any]]
    clear_selected_project_domain: Callable[[], None]
    select_vue_api_domain: Callable[[str], str]
    load_project_detail: Callable[..., dict[str, Any]]
    load_project_metrics: Callable[[str], dict[str, int]]
    serialize_project: Callable[[dict[str, Any]], dict[str, Any]]
    normalize_detect_url_rows: Callable[[Any], list[dict[str, Any]]]
    collect_sync_state_map: Callable[..., dict[str, dict[str, Any]]]
    collect_js_download_state_map: Callable[..., dict[str, dict[str, Any]]]
    collect_request_capture_state_map: Callable[..., dict[str, dict[str, Any]]]
    normalize_sync_status: Callable[[Any], str]
    resolve_scan_pattern: Callable[[str], str]
    get_global_settings: Callable[..., dict[str, Any]]
    normalize_proxy_server: Callable[[Any], str]
    domain_from_target_url: Callable[[str], str]
    resolve_target_url: Callable[[str, str], str]
    queue_project_sync: Callable[..., tuple[dict[str, Any], dict[str, Any]]]
    queue_js_download: Callable[..., dict[str, Any]]
    queue_request_capture: Callable[..., dict[str, Any]]
    locate_request_in_chunks: Callable[..., dict[str, Any]]
    load_manual_request_items: Callable[[str], list[dict[str, Any]]]
    save_manual_request_items: Callable[[str, Any], list[dict[str, Any]]]
    load_route_url_profile: Callable[[str], dict[str, Any]]
    save_route_url_profile: Callable[..., dict[str, Any]]
    normalize_hash_style: Callable[[Any], str]
    normalize_basepath: Callable[[Any], str]
    default_route_url_profile: Callable[[], dict[str, Any]]
    read_job: Callable[[str], dict[str, Any]]
    update_job: Callable[..., dict[str, Any]]
    append_log: Callable[[str, str], None]
    sync_control_progress: Callable[..., dict[str, Any]]
    request_capture_job_control: Callable[[str, str], None]
    serialize_sync_job: Callable[..., dict[str, Any]]
    serialize_js_download_job: Callable[..., dict[str, Any]]
    serialize_request_capture_job: Callable[..., dict[str, Any]]
    module2_sync_job_step: str
    module2_js_download_job_step: str
    module2_request_capture_job_step: str
    js_download_default_concurrency: int
    module2_request_default_concurrency: int


def _chunk_form_from_state(deps: VueChunkRouteDeps) -> dict[str, Any]:
    form = deps.ui_state.get("chunk_form")
    if isinstance(form, dict):
        return form
    form = {}
    deps.ui_state["chunk_form"] = form
    return form


async def _read_json_payload(request: Request) -> dict[str, Any]:
    try:
        raw_payload = await request.json()
    except Exception:
        return {}
    return raw_payload if isinstance(raw_payload, dict) else {}


def _bind_route(
    handler: Callable[[Request, VueChunkRouteDeps], Awaitable[Any]],
    deps: VueChunkRouteDeps,
) -> Callable[[Request], Awaitable[Any]]:
    async def endpoint(request: Request):
        return await handler(request, deps)

    endpoint.__name__ = handler.__name__.lstrip("_")
    return endpoint


def _extract_seed_url(project_item: dict[str, Any], deps: VueChunkRouteDeps) -> str:
    candidates = project_item.get("seed_urls", []) if isinstance(project_item.get("seed_urls"), list) else []
    for candidate in candidates:
        token = deps.safe_str(candidate)
        if token:
            return token
    return ""


def _extract_request_capture_child_job_id(result: dict[str, Any], deps: VueChunkRouteDeps) -> str:
    request_capture = result.get("request_capture") if isinstance(result.get("request_capture"), dict) else {}
    return deps.safe_str(result.get("request_capture_job_id") or request_capture.get("job_id"))


def _normalize_job_logs(raw_job: dict[str, Any], deps: VueChunkRouteDeps, *, limit: int = 8) -> list[dict[str, str]]:
    logs = raw_job.get("logs") if isinstance(raw_job.get("logs"), list) else []
    rows: list[dict[str, str]] = []
    for item in logs[-max(1, int(limit)) :]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "time": deps.safe_str(item.get("time")),
                "message": deps.safe_str(item.get("message")),
            }
        )
    return rows


def _enrich_vue_chunk_job_detail(
    job_row: dict[str, Any],
    raw_job: dict[str, Any],
    deps: VueChunkRouteDeps,
) -> dict[str, Any]:
    enriched = dict(job_row)
    result = raw_job.get("result") if isinstance(raw_job.get("result"), dict) else {}
    logs = _normalize_job_logs(raw_job, deps)
    enriched["logs"] = logs
    enriched["log_count"] = len(raw_job.get("logs")) if isinstance(raw_job.get("logs"), list) else len(logs)

    for key in ("current_route_url", "current_js_url", "current_file_name"):
        value = deps.safe_str(result.get(key))
        if value:
            enriched[key] = value

    for key in ("recent_chunks", "recent_requests", "recent_js_urls"):
        rows = result.get(key) if isinstance(result.get(key), list) else []
        enriched[key] = [deps.safe_str(item) for item in rows if deps.safe_str(item)]

    return enriched


async def _api_vue_chunk_projects(request: Request, deps: VueChunkRouteDeps):
    query = request.query_params
    keyword = deps.safe_str(query.get("q")).lower()
    page = deps.to_int(query.get("page"), default=1, minimum=1)
    page_size = deps.to_int(query.get("page_size"), default=10, minimum=1)
    page_size = min(page_size, 100)
    sort = deps.safe_str(query.get("sort"), "updated_desc").lower()

    project_records = deps.list_projects(limit=3000)
    project_domains = deps.merge_project_domains(project_records)
    project_map = {str(item.get("domain")): item for item in project_records if str(item.get("domain")).strip()}
    sync_map = deps.collect_sync_state_map(limit=1200)
    js_download_map = deps.collect_js_download_state_map(limit=1200)
    request_capture_map = deps.collect_request_capture_state_map(limit=1200)
    detect_task_records = deps.list_detect_tasks(limit=5000)
    detect_task_map = {
        deps.safe_str(item.get("task_id")): item
        for item in detect_task_records
        if deps.safe_str(item.get("task_id"))
    }

    projects: list[dict[str, Any]] = []
    for domain in project_domains:
        metrics = deps.load_project_metrics(domain)
        raw = project_map.get(domain)
        if raw is None:
            project_item = {
                "domain": domain,
                "title": "",
                "source": "filesystem",
                "seed_urls": [],
                "task_ids": [],
                "created_at": "",
                "updated_at": "",
            }
        else:
            project_item = deps.serialize_project(raw)

        if not deps.safe_str(project_item.get("title")):
            task_ids = project_item.get("task_ids", []) if isinstance(project_item.get("task_ids"), list) else []
            seed_urls = {
                deps.safe_str(candidate)
                for candidate in project_item.get("seed_urls", [])
                if deps.safe_str(candidate)
            }
            domain_lower = deps.safe_str(domain).lower()
            for task_id in task_ids:
                task_row = detect_task_map.get(deps.safe_str(task_id))
                if not isinstance(task_row, dict):
                    continue
                detected_urls = deps.normalize_detect_url_rows(task_row.get("urls"))
                for row in detected_urls:
                    row_url = deps.safe_str(row.get("url"))
                    if not row_url:
                        continue
                    row_domain = deps.safe_str(urlsplit(row_url).hostname).lower()
                    if seed_urls and row_url not in seed_urls and row_domain != domain_lower:
                        continue
                    row_title = deps.safe_str(row.get("title"))
                    if row_title:
                        project_item["title"] = row_title
                        break
                if deps.safe_str(project_item.get("title")):
                    break

        seed_url = _extract_seed_url(project_item, deps)
        sync_info = sync_map.get(domain) or {
            "job_id": "",
            "status": "idle",
            "error": "",
            "updated_at": "",
            "target_url": seed_url,
            "concurrency": 5,
            "detect_routes": True,
            "detect_js": True,
            "detect_request": True,
        }
        js_download_info = js_download_map.get(domain) or {
            "job_id": "",
            "status": "idle",
            "error": "",
            "updated_at": "",
            "step": deps.module2_js_download_job_step,
        }
        request_capture_info = request_capture_map.get(domain) or {
            "job_id": "",
            "status": "idle",
            "error": "",
            "updated_at": "",
            "step": deps.module2_request_capture_job_step,
        }

        active_status_values = {"running", "queued", "paused"}
        # 优先展示用户当前最关心的活跃阶段，避免只显示同步状态造成“卡住”的错觉。
        visible_job = sync_info
        if deps.safe_str(request_capture_info.get("status")) in active_status_values:
            visible_job = request_capture_info
        elif deps.safe_str(js_download_info.get("status")) in active_status_values:
            visible_job = js_download_info
        elif deps.safe_str(sync_info.get("status")) in active_status_values:
            visible_job = sync_info
        else:
            candidates = [sync_info, request_capture_info, js_download_info]
            candidates = [item for item in candidates if deps.safe_str(item.get("status")) != "idle"]
            if candidates:
                visible_job = max(
                    candidates,
                    key=lambda item: deps.safe_str(item.get("updated_at") or item.get("created_at")),
                )

        project_item.update(metrics)
        project_item["sync"] = sync_info
        project_item["js_download"] = js_download_info
        project_item["request_capture"] = request_capture_info
        project_item["sync_status"] = deps.normalize_sync_status(visible_job.get("status"))
        project_item["sync_job_id"] = deps.safe_str(visible_job.get("job_id"))
        project_item["sync_updated_at"] = deps.safe_str(visible_job.get("updated_at"))
        project_item["sync_error"] = deps.safe_str(visible_job.get("error"))
        project_item["sync_step"] = deps.safe_str(visible_job.get("step"))
        phase_info = describe_vue_chunk_job_phase(
            visible_job,
            sync_step=deps.module2_sync_job_step,
            js_download_step=deps.module2_js_download_job_step,
            request_capture_step=deps.module2_request_capture_job_step,
        )
        project_item["sync_phase"] = deps.safe_str(phase_info.get("phase"))
        project_item["sync_phase_text"] = deps.safe_str(phase_info.get("phase_text"))
        last_activity = deps.safe_str(project_item.get("sync_updated_at") or project_item.get("updated_at"))
        if not last_activity:
            last_activity = deps.safe_str(project_item.get("created_at"))
        project_item["last_activity_at"] = last_activity
        projects.append(project_item)

    if keyword:
        projects = [
            item
            for item in projects
            if keyword in deps.safe_str(item.get("domain")).lower()
            or keyword in deps.safe_str(item.get("source")).lower()
        ]

    if sort == "domain_asc":
        projects.sort(key=lambda item: deps.safe_str(item.get("domain")).lower())
    elif sort == "domain_desc":
        projects.sort(key=lambda item: deps.safe_str(item.get("domain")).lower(), reverse=True)
    elif sort == "updated_asc":
        projects.sort(key=lambda item: deps.safe_str(item.get("last_activity_at")))
    else:
        projects.sort(key=lambda item: deps.safe_str(item.get("last_activity_at")), reverse=True)

    total = len(projects)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    if total_pages > 0 and page > total_pages:
        page = total_pages
    start = (page - 1) * page_size
    rows = projects[start : start + page_size]
    has_running_jobs = any(
        deps.safe_str(item.get("sync_status")) in {"queued", "running", "paused"} for item in projects
    )
    return deps.json_ok(
        {
            "projects": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_running_jobs": has_running_jobs,
        }
    )


async def _api_vue_chunk_project_create(request: Request, deps: VueChunkRouteDeps):
    payload = await _read_json_payload(request)

    target_url = deps.safe_str(payload.get("target_url") or payload.get("url"))
    source = deps.safe_str(payload.get("source"), "module2_manual") or "module2_manual"
    concurrency = deps.to_int(payload.get("concurrency"), default=5, minimum=1)
    has_detect_routes = "detect_routes" in payload
    has_detect_js = "detect_js" in payload
    has_detect_request = "detect_request" in payload
    detect_routes = deps.to_bool(payload.get("detect_routes")) if has_detect_routes else True
    detect_js = deps.to_bool(payload.get("detect_js")) if has_detect_js else True
    detect_request = deps.to_bool(payload.get("detect_request")) if has_detect_request else True
    has_auto_pipeline = ("auto_pipeline" in payload) or ("automation" in payload)
    auto_pipeline = (
        deps.to_bool(payload.get("auto_pipeline") or payload.get("automation")) if has_auto_pipeline else True
    )
    scan_pattern = deps.resolve_scan_pattern(deps.safe_str(payload.get("pattern"))) if auto_pipeline else ""

    if not target_url:
        return deps.json_error("target_url is required", status_code=400)

    try:
        if auto_pipeline:
            detect_routes = True
            detect_js = True
            detect_request = True
        if detect_routes or detect_js or detect_request:
            project, job = deps.queue_project_sync(
                target_url=target_url,
                source=source,
                concurrency=concurrency,
                detect_routes=detect_routes,
                detect_js=detect_js,
                detect_request=detect_request,
                auto_scan_pattern=scan_pattern,
                auto_pipeline=auto_pipeline,
            )
            sync_job = deps.serialize_sync_job(job, fallback_domain=deps.safe_str(project.get("domain")))
        else:
            project = deps.upsert_project_from_url(url=target_url, source=source)
            domain = deps.safe_str(project.get("domain"))
            deps.select_vue_api_domain(domain)
            chunk_form = _chunk_form_from_state(deps)
            chunk_form["target_url"] = target_url
            chunk_form["concurrency"] = str(concurrency)
            chunk_form["detect_routes"] = ""
            chunk_form["detect_js"] = ""
            chunk_form["detect_request"] = ""
            sync_job = {
                "job_id": "",
                "step": deps.module2_sync_job_step,
                "status": "idle",
                "error": "",
                "created_at": "",
                "updated_at": "",
                "finished_at": "",
                "domain": domain,
                "target_url": target_url,
                "concurrency": concurrency,
                "detect_routes": False,
                "detect_js": False,
                "detect_request": False,
                "auto_pipeline": False,
                "result": {},
            }
        deps.clear_error()
        return deps.json_ok({"project": deps.serialize_project(project), "sync_job": sync_job}, status_code=201)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_chunk_project_title_update(request: Request, deps: VueChunkRouteDeps):
    domain = deps.safe_str(request.path_params.get("domain"))
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    payload = await _read_json_payload(request)
    title = deps.safe_str(payload.get("title"))
    try:
        project = deps.update_project_title(domain, title)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    return deps.json_ok({"project": deps.serialize_project(project)})


async def _api_vue_chunk_project_retry(request: Request, deps: VueChunkRouteDeps):
    domain = deps.safe_str(request.path_params.get("domain"))
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    payload = await _read_json_payload(request)
    project = deps.get_project(domain)
    detail = deps.load_project_detail(domain)
    if project is None and not detail:
        return deps.json_error(f"project not found: {domain}", status_code=404)

    sync_map = deps.collect_sync_state_map(limit=1200)
    last_sync = sync_map.get(domain) or {}
    target_url = deps.safe_str(payload.get("target_url") or last_sync.get("target_url"))
    if not target_url and isinstance(project, dict):
        target_url = _extract_seed_url(project, deps)
    if not target_url:
        candidates = detail.get("urls_preview", []) if isinstance(detail.get("urls_preview"), list) else []
        for candidate in candidates:
            token = deps.safe_str(candidate)
            if token:
                target_url = token
                break

    if not target_url:
        return deps.json_error("target_url is required for retry", status_code=400)

    source = deps.safe_str(payload.get("source"), "module2_retry") or "module2_retry"
    default_concurrency = deps.to_int(last_sync.get("concurrency"), default=5, minimum=1)
    concurrency = deps.to_int(payload.get("concurrency"), default=default_concurrency, minimum=1)
    has_detect_routes = "detect_routes" in payload
    has_detect_js = "detect_js" in payload
    has_detect_request = "detect_request" in payload
    detect_routes = (
        deps.to_bool(payload.get("detect_routes"))
        if has_detect_routes
        else bool(last_sync.get("detect_routes", True))
    )
    detect_js = (
        deps.to_bool(payload.get("detect_js")) if has_detect_js else bool(last_sync.get("detect_js", True))
    )
    detect_request = (
        deps.to_bool(payload.get("detect_request"))
        if has_detect_request
        else bool(last_sync.get("detect_request", True))
    )
    has_auto_pipeline = "auto_pipeline" in payload
    auto_pipeline = (
        deps.to_bool(payload.get("auto_pipeline")) if has_auto_pipeline else bool(last_sync.get("auto_pipeline", False))
    )
    retry_pattern = deps.resolve_scan_pattern(deps.safe_str(payload.get("pattern"))) if auto_pipeline else ""

    try:
        updated_project, job = deps.queue_project_sync(
            target_url=target_url,
            source=source,
            concurrency=concurrency,
            detect_routes=detect_routes,
            detect_js=detect_js,
            detect_request=detect_request,
            auto_scan_pattern=retry_pattern,
            auto_pipeline=auto_pipeline,
        )
        deps.clear_error()
        return deps.json_ok(
            {
                "project": deps.serialize_project(updated_project),
                "sync_job": deps.serialize_sync_job(job, fallback_domain=domain),
            },
            status_code=202,
        )
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_chunk_project_scan(request: Request, deps: VueChunkRouteDeps):
    domain = deps.safe_str(request.path_params.get("domain"))
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    payload = await _read_json_payload(request)
    source = deps.safe_str(payload.get("source"), "vueChunk_scan") or "vueChunk_scan"
    global_settings = deps.get_global_settings()
    default_scan_concurrency = deps.to_int(global_settings.get("scan_concurrency"), default=10, minimum=1)
    concurrency = deps.to_int(payload.get("concurrency"), default=default_scan_concurrency, minimum=1)
    pattern = deps.resolve_scan_pattern(deps.safe_str(payload.get("pattern")))
    proxy_server = deps.normalize_proxy_server(payload.get("proxy_server") or global_settings.get("proxy_server"))
    target_url = deps.safe_str(payload.get("target_url") or payload.get("url"))

    if target_url:
        target_domain = deps.domain_from_target_url(target_url)
        if not target_domain:
            return deps.json_error("invalid target_url", status_code=400)
        if target_domain != domain:
            return deps.json_error("target_url domain does not match selected project", status_code=400)
    else:
        target_url = deps.resolve_target_url(domain)

    if not target_url:
        return deps.json_error("target_url is required for scan", status_code=400)

    try:
        updated_project, job = deps.queue_project_sync(
            target_url=target_url,
            source=source,
            concurrency=concurrency,
            detect_routes=True,
            detect_js=True,
            detect_request=True,
            proxy_server=proxy_server,
            auto_scan_pattern=pattern,
            auto_pipeline=True,
        )
        deps.clear_error()
        return deps.json_ok(
            {
                "project": deps.serialize_project(updated_project),
                "sync_job": deps.serialize_sync_job(job, fallback_domain=domain),
                "pattern": pattern,
                "proxy_server": proxy_server,
            },
            status_code=202,
        )
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_chunk_project_delete(request: Request, deps: VueChunkRouteDeps):
    domain = deps.safe_str(request.path_params.get("domain"))
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    remove_files = True
    query_value = deps.safe_str(request.query_params.get("remove_files"))
    if query_value:
        remove_files = deps.to_bool(query_value)

    try:
        deleted = deps.delete_project(domain, remove_files=remove_files)
        if deps.safe_str(deps.ui_state.get("selected_project_domain")) == domain:
            deps.clear_selected_project_domain()
        deps.clear_error()
        return deps.json_ok({"deleted_project": deps.serialize_project(deleted)})
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_chunk_project_js_download(request: Request, deps: VueChunkRouteDeps):
    domain = deps.safe_str(request.path_params.get("domain"))
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    payload = await _read_json_payload(request)
    concurrency = deps.to_int(payload.get("concurrency"), default=deps.js_download_default_concurrency, minimum=1)

    try:
        job = deps.queue_js_download(domain=domain, concurrency=concurrency, mode="zip")
        deps.clear_error()
        return deps.json_ok({"job": deps.serialize_js_download_job(job, fallback_domain=domain)}, status_code=202)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_chunk_project_js_download_local(request: Request, deps: VueChunkRouteDeps):
    domain = deps.safe_str(request.path_params.get("domain"))
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    payload = await _read_json_payload(request)
    concurrency = deps.to_int(payload.get("concurrency"), default=deps.js_download_default_concurrency, minimum=1)

    try:
        job = deps.queue_js_download(domain=domain, concurrency=concurrency, mode="local")
        deps.clear_error()
        return deps.json_ok({"job": deps.serialize_js_download_job(job, fallback_domain=domain)}, status_code=202)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_chunk_project_request_capture(request: Request, deps: VueChunkRouteDeps):
    domain = deps.safe_str(request.path_params.get("domain"))
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    payload = await _read_json_payload(request)
    concurrency = deps.to_int(payload.get("concurrency"), default=deps.module2_request_default_concurrency, minimum=1)
    global_settings = deps.get_global_settings()
    proxy_server = deps.normalize_proxy_server(payload.get("proxy_server") or global_settings.get("proxy_server"))

    try:
        job = deps.queue_request_capture(domain=domain, concurrency=concurrency, proxy_server=proxy_server)
        deps.clear_error()
        return deps.json_ok({"job": deps.serialize_request_capture_job(job, fallback_domain=domain)}, status_code=202)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_chunk_project_request_locate(request: Request, deps: VueChunkRouteDeps):
    domain = deps.safe_str(request.path_params.get("domain"))
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    payload = await _read_json_payload(request)
    request_url = deps.safe_str(payload.get("request_url") or payload.get("url"))
    method = deps.safe_str(payload.get("method"), "GET").upper()
    route_url = deps.safe_str(payload.get("route_url"))
    scan_scope = deps.safe_str(payload.get("scan_scope"), "auto").lower()
    max_files = deps.to_int(payload.get("max_files"), default=240, minimum=1)
    max_results = deps.to_int(payload.get("max_results"), default=80, minimum=1)

    try:
        result = deps.locate_request_in_chunks(
            domain=domain,
            request_url=request_url,
            method=method,
            route_url=route_url,
            scan_scope=scan_scope,
            max_files=max_files,
            max_results=max_results,
        )
        deps.clear_error()
        return deps.json_ok({"result": result})
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_chunk_project_manual_requests(request: Request, deps: VueChunkRouteDeps):
    domain = deps.safe_str(request.path_params.get("domain"))
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    detail = deps.load_project_detail(domain)
    if not detail:
        return deps.json_error(f"project not found: {domain}", status_code=404)

    if request.method.upper() == "GET":
        return deps.json_ok({"manual_requests": deps.load_manual_request_items(domain)})

    payload = await _read_json_payload(request)
    try:
        rows = deps.save_manual_request_items(domain, payload.get("requests"))
        deps.clear_error()
        return deps.json_ok({"manual_requests": rows})
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_chunk_project_route_rewrite(request: Request, deps: VueChunkRouteDeps):
    domain = deps.safe_str(request.path_params.get("domain"))
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    detail = deps.load_project_detail(domain)
    if not detail:
        return deps.json_error(f"project not found: {domain}", status_code=404)

    payload = await _read_json_payload(request)
    current_profile = deps.load_route_url_profile(domain)
    has_hash_style = "hash_style" in payload
    has_basepath = "basepath_override" in payload or "basepath" in payload
    hash_style = (
        deps.normalize_hash_style(payload.get("hash_style"))
        if has_hash_style
        else deps.normalize_hash_style(current_profile.get("hash_style"))
    )
    basepath_raw = payload.get("basepath_override") if "basepath_override" in payload else payload.get("basepath")
    basepath_override = (
        deps.normalize_basepath(basepath_raw)
        if has_basepath
        else deps.normalize_basepath(current_profile.get("basepath_override"))
    )
    if "manual_lock" in payload:
        manual_lock = bool(deps.to_bool(payload.get("manual_lock")))
    else:
        manual_lock = True

    try:
        profile = deps.save_route_url_profile(
            domain,
            hash_style=hash_style,
            basepath_override=basepath_override,
            manual_lock=manual_lock,
            source="manual" if manual_lock else "default",
        )
        deps.clear_error()
        return deps.json_ok({"profile": profile})
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_chunk_job_detail(request: Request, deps: VueChunkRouteDeps):
    job_id = deps.safe_str(request.path_params.get("job_id"))
    if not job_id:
        return deps.json_error("job_id is required", status_code=400)

    try:
        job = deps.read_job(job_id)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    step = deps.safe_str(job.get("step"))
    if step == deps.module2_sync_job_step:
        return deps.json_ok(
            {
                "job": _enrich_vue_chunk_job_detail(
                    deps.serialize_sync_job(job),
                    job,
                    deps,
                )
            }
        )
    if step == deps.module2_js_download_job_step:
        return deps.json_ok(
            {
                "job": _enrich_vue_chunk_job_detail(
                    deps.serialize_js_download_job(job),
                    job,
                    deps,
                )
            }
        )
    if step == deps.module2_request_capture_job_step:
        return deps.json_ok(
            {
                "job": _enrich_vue_chunk_job_detail(
                    deps.serialize_request_capture_job(
                        job,
                        default_concurrency=deps.module2_request_default_concurrency,
                    ),
                    job,
                    deps,
                )
            }
        )
    return deps.json_ok(
        {
            "job": {
                "job_id": deps.safe_str(job.get("job_id")),
                "step": step,
                "status": deps.safe_str(job.get("status")),
                "error": deps.safe_str(job.get("error")),
                "created_at": deps.safe_str(job.get("created_at")),
                "updated_at": deps.safe_str(job.get("updated_at")),
                "finished_at": deps.safe_str(job.get("finished_at")),
                "result": job.get("result") if isinstance(job.get("result"), dict) else {},
            }
        }
    )


async def _api_vue_chunk_job_stop(request: Request, deps: VueChunkRouteDeps):
    job_id = deps.safe_str(request.path_params.get("job_id"))
    if not job_id:
        return deps.json_error("job_id is required", status_code=400)

    try:
        job = deps.read_job(job_id)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    step = deps.safe_str(job.get("step"))
    if step not in {deps.module2_request_capture_job_step, deps.module2_sync_job_step}:
        return deps.json_error("only project sync/request capture jobs support stop", status_code=400)

    current_status = deps.normalize_sync_status(job.get("status"))
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    merged_result = dict(result)
    merged_result["stop_requested"] = True
    phase = deps.safe_str(
        merged_result.get("progress", {}).get("phase") if isinstance(merged_result.get("progress"), dict) else "",
        "stopping",
    )
    merged_result["progress"] = deps.sync_control_progress(
        merged_result,
        phase=phase,
        stop_requested=True,
    )

    if step == deps.module2_sync_job_step:
        capture_job_id = _extract_request_capture_child_job_id(merged_result, deps)
        if capture_job_id:
            deps.request_capture_job_control(capture_job_id, "stop")

    try:
        if current_status in {"queued", "paused"}:
            updated = deps.update_job(job_id=job_id, status="stopped", result=merged_result)
        elif current_status == "running":
            updated = deps.update_job(job_id=job_id, status="running", result=merged_result)
        else:
            updated = job
        deps.append_log(job_id, "web action stop requested")
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    if step == deps.module2_sync_job_step:
        return deps.json_ok({"job": deps.serialize_sync_job(updated)})
    return deps.json_ok({"job": deps.serialize_request_capture_job(updated)})


async def _api_vue_chunk_job_pause(request: Request, deps: VueChunkRouteDeps):
    job_id = deps.safe_str(request.path_params.get("job_id"))
    if not job_id:
        return deps.json_error("job_id is required", status_code=400)

    try:
        job = deps.read_job(job_id)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    step = deps.safe_str(job.get("step"))
    if step not in {deps.module2_request_capture_job_step, deps.module2_sync_job_step}:
        return deps.json_error("only project sync/request capture jobs support pause", status_code=400)

    current_status = deps.normalize_sync_status(job.get("status"))
    if current_status != "running":
        return deps.json_error("only running jobs can be paused", status_code=400)

    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    merged_result = dict(result)
    stop_requested = bool(merged_result.get("stop_requested"))
    phase = deps.safe_str(
        merged_result.get("progress", {}).get("phase") if isinstance(merged_result.get("progress"), dict) else "",
        "running",
    )
    merged_result["stop_requested"] = stop_requested
    merged_result["progress"] = deps.sync_control_progress(
        merged_result,
        phase=phase,
        stop_requested=stop_requested,
    )

    if step == deps.module2_sync_job_step:
        capture_job_id = _extract_request_capture_child_job_id(merged_result, deps)
        if capture_job_id:
            deps.request_capture_job_control(capture_job_id, "pause")

    try:
        updated = deps.update_job(job_id=job_id, status="paused", result=merged_result)
        deps.append_log(job_id, "web action pause requested")
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    if step == deps.module2_sync_job_step:
        return deps.json_ok({"job": deps.serialize_sync_job(updated)})
    return deps.json_ok({"job": deps.serialize_request_capture_job(updated)})


async def _api_vue_chunk_job_resume(request: Request, deps: VueChunkRouteDeps):
    job_id = deps.safe_str(request.path_params.get("job_id"))
    if not job_id:
        return deps.json_error("job_id is required", status_code=400)

    try:
        job = deps.read_job(job_id)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    step = deps.safe_str(job.get("step"))
    if step not in {deps.module2_request_capture_job_step, deps.module2_sync_job_step}:
        return deps.json_error("only project sync/request capture jobs support resume", status_code=400)

    current_status = deps.normalize_sync_status(job.get("status"))
    if current_status != "paused":
        return deps.json_error("only paused jobs can be resumed", status_code=400)

    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    merged_result = dict(result)
    phase = deps.safe_str(
        merged_result.get("progress", {}).get("phase") if isinstance(merged_result.get("progress"), dict) else "",
        "running",
    )
    merged_result["stop_requested"] = False
    merged_result["progress"] = deps.sync_control_progress(
        merged_result,
        phase=phase,
        stop_requested=False,
    )

    if step == deps.module2_sync_job_step:
        capture_job_id = _extract_request_capture_child_job_id(merged_result, deps)
        if capture_job_id:
            deps.request_capture_job_control(capture_job_id, "resume")

    try:
        updated = deps.update_job(job_id=job_id, status="running", result=merged_result)
        deps.append_log(job_id, "web action resume requested")
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    if step == deps.module2_sync_job_step:
        return deps.json_ok({"job": deps.serialize_sync_job(updated)})
    return deps.json_ok({"job": deps.serialize_request_capture_job(updated)})


async def _api_vue_chunk_project_detail(request: Request, deps: VueChunkRouteDeps):
    domain = deps.safe_str(request.path_params.get("domain"))
    if not domain:
        return deps.json_error("domain is required", status_code=400)

    query = request.query_params
    route_page = deps.to_int(query.get("route_page"), default=1, minimum=1)
    route_page_size = deps.to_int(query.get("route_page_size"), default=120, minimum=1)
    js_page = deps.to_int(query.get("js_page"), default=1, minimum=1)
    js_page_size = deps.to_int(query.get("js_page_size"), default=120, minimum=1)
    request_page = deps.to_int(query.get("request_page"), default=1, minimum=1)
    request_page_size = deps.to_int(query.get("request_page_size"), default=120, minimum=1)
    map_page = deps.to_int(query.get("map_page"), default=1, minimum=1)
    map_page_size = deps.to_int(query.get("map_page_size"), default=120, minimum=1)
    map_q = deps.safe_str(query.get("map_q"))

    detail = deps.load_project_detail(
        domain,
        route_page=route_page,
        route_page_size=route_page_size,
        js_page=js_page,
        js_page_size=js_page_size,
        request_page=request_page,
        request_page_size=request_page_size,
        map_page=map_page,
        map_page_size=map_page_size,
        map_q=map_q,
    )
    if not detail:
        return deps.json_error(f"project not found: {domain}", status_code=404)

    project = deps.get_project(domain) or {
        "domain": domain,
        "source": "filesystem",
        "seed_urls": [],
        "task_ids": [],
        "created_at": "",
        "updated_at": "",
    }
    deps.select_vue_api_domain(domain)
    sync_map = deps.collect_sync_state_map(limit=1200)
    sync = sync_map.get(domain) or {
        "job_id": "",
        "status": "idle",
        "error": "",
        "updated_at": "",
        "target_url": "",
        "concurrency": 5,
        "detect_routes": True,
        "detect_js": True,
        "detect_request": True,
    }
    sync_job_id = deps.safe_str(sync.get("job_id"))
    if sync_job_id:
        try:
            raw_sync_job = deps.read_job(sync_job_id)
            sync = _enrich_vue_chunk_job_detail(
                deps.serialize_sync_job(raw_sync_job, fallback_domain=domain),
                raw_sync_job,
                deps,
            )
        except Exception:
            pass
    js_download_map = deps.collect_js_download_state_map(limit=1200)
    js_download = js_download_map.get(domain) or {
        "job_id": "",
        "step": deps.module2_js_download_job_step,
        "status": "idle",
        "error": "",
        "created_at": "",
        "updated_at": "",
        "finished_at": "",
        "domain": domain,
        "mode": "zip",
        "concurrency": deps.js_download_default_concurrency,
        "total": 0,
        "downloaded_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "progress": {"done": 0, "total": 0, "downloaded": 0, "skipped": 0, "failed": 0},
        "zip_path": "",
        "local_dir": "",
        "download_url": "",
        "result": {},
    }
    js_download_job_id = deps.safe_str(js_download.get("job_id"))
    if js_download_job_id:
        try:
            raw_js_download_job = deps.read_job(js_download_job_id)
            js_download = _enrich_vue_chunk_job_detail(
                deps.serialize_js_download_job(raw_js_download_job, fallback_domain=domain),
                raw_js_download_job,
                deps,
            )
        except Exception:
            pass
    request_capture_map = deps.collect_request_capture_state_map(limit=1200)
    route_profile = (
        detail.get("route_url_profile")
        if isinstance(detail.get("route_url_profile"), dict)
        else deps.default_route_url_profile()
    )
    route_hash_style = deps.normalize_hash_style(route_profile.get("hash_style"))
    route_basepath_override = deps.normalize_basepath(route_profile.get("basepath_override"))
    route_manual_lock = bool(route_profile.get("manual_lock"))
    request_capture = request_capture_map.get(domain) or {
        "job_id": "",
        "step": deps.module2_request_capture_job_step,
        "status": "idle",
        "error": "",
        "created_at": "",
        "updated_at": "",
        "finished_at": "",
        "domain": domain,
        "concurrency": deps.module2_request_default_concurrency,
        "total": 0,
        "visited_route_count": 0,
        "failed_route_count": 0,
        "request_total": 0,
        "hash_style": route_hash_style,
        "basepath_override": route_basepath_override,
        "manual_lock": route_manual_lock,
        "probe": {},
        "stop_requested": False,
        "capture_file": "",
        "progress": {
            "done": 0,
            "total": 0,
            "visited_route_count": 0,
            "failed_route_count": 0,
            "request_total": 0,
            "phase": "capturing",
            "stop_requested": False,
        },
        "result": {},
    }
    request_capture_job_id = deps.safe_str(request_capture.get("job_id"))
    if request_capture_job_id:
        try:
            raw_request_capture_job = deps.read_job(request_capture_job_id)
            request_capture = _enrich_vue_chunk_job_detail(
                deps.serialize_request_capture_job(
                    raw_request_capture_job,
                    fallback_domain=domain,
                    default_concurrency=deps.module2_request_default_concurrency,
                ),
                raw_request_capture_job,
                deps,
            )
        except Exception:
            pass
    metrics = deps.load_project_metrics(domain)
    project_payload = {
        **deps.serialize_project(project),
        **metrics,
    }
    return deps.json_ok(
        {
            "project": project_payload,
            "detail": detail,
            "sync": sync,
            "js_download": js_download,
            "request_capture": request_capture,
        }
    )


def build_vue_chunk_routes(deps: VueChunkRouteDeps) -> list[Route]:
    # 这里先承接 VueChunk 的 JSON API 路由，保持 URL 不变，让 app.py 只做注册。
    return [
        Route("/api/module2/projects", endpoint=_bind_route(_api_vue_chunk_projects, deps), methods=["GET"]),
        Route("/api/module2/projects", endpoint=_bind_route(_api_vue_chunk_project_create, deps), methods=["POST"]),
        Route(
            "/api/module2/projects/{domain}",
            endpoint=_bind_route(_api_vue_chunk_project_delete, deps),
            methods=["DELETE"],
        ),
        Route(
            "/api/module2/projects/{domain}/title",
            endpoint=_bind_route(_api_vue_chunk_project_title_update, deps),
            methods=["POST"],
        ),
        Route(
            "/api/module2/projects/{domain}/retry",
            endpoint=_bind_route(_api_vue_chunk_project_retry, deps),
            methods=["POST"],
        ),
        Route(
            "/api/module2/projects/{domain}/scan",
            endpoint=_bind_route(_api_vue_chunk_project_scan, deps),
            methods=["POST"],
        ),
        Route(
            "/api/module2/projects/{domain}/js-download",
            endpoint=_bind_route(_api_vue_chunk_project_js_download, deps),
            methods=["POST"],
        ),
        Route(
            "/api/module2/projects/{domain}/js-download-local",
            endpoint=_bind_route(_api_vue_chunk_project_js_download_local, deps),
            methods=["POST"],
        ),
        Route(
            "/api/module2/projects/{domain}/request-capture",
            endpoint=_bind_route(_api_vue_chunk_project_request_capture, deps),
            methods=["POST"],
        ),
        Route(
            "/api/module2/projects/{domain}/request-locate",
            endpoint=_bind_route(_api_vue_chunk_project_request_locate, deps),
            methods=["POST"],
        ),
        Route(
            "/api/module2/projects/{domain}/manual-requests",
            endpoint=_bind_route(_api_vue_chunk_project_manual_requests, deps),
            methods=["GET", "POST"],
        ),
        Route(
            "/api/module2/projects/{domain}/route-rewrite",
            endpoint=_bind_route(_api_vue_chunk_project_route_rewrite, deps),
            methods=["POST"],
        ),
        Route(
            "/api/module2/projects/{domain}",
            endpoint=_bind_route(_api_vue_chunk_project_detail, deps),
            methods=["GET"],
        ),
        Route("/api/module2/jobs/{job_id}", endpoint=_bind_route(_api_vue_chunk_job_detail, deps), methods=["GET"]),
        Route(
            "/api/module2/jobs/{job_id}/stop",
            endpoint=_bind_route(_api_vue_chunk_job_stop, deps),
            methods=["POST"],
        ),
        Route(
            "/api/module2/jobs/{job_id}/pause",
            endpoint=_bind_route(_api_vue_chunk_job_pause, deps),
            methods=["POST"],
        ),
        Route(
            "/api/module2/jobs/{job_id}/resume",
            endpoint=_bind_route(_api_vue_chunk_job_resume, deps),
            methods=["POST"],
        ),
        Route("/api/vueChunk/projects", endpoint=_bind_route(_api_vue_chunk_projects, deps), methods=["GET"]),
        Route("/api/vueChunk/projects", endpoint=_bind_route(_api_vue_chunk_project_create, deps), methods=["POST"]),
        Route(
            "/api/vueChunk/projects/{domain}",
            endpoint=_bind_route(_api_vue_chunk_project_delete, deps),
            methods=["DELETE"],
        ),
        Route(
            "/api/vueChunk/projects/{domain}/title",
            endpoint=_bind_route(_api_vue_chunk_project_title_update, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueChunk/projects/{domain}/retry",
            endpoint=_bind_route(_api_vue_chunk_project_retry, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueChunk/projects/{domain}/scan",
            endpoint=_bind_route(_api_vue_chunk_project_scan, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueChunk/projects/{domain}/js-download",
            endpoint=_bind_route(_api_vue_chunk_project_js_download, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueChunk/projects/{domain}/js-download-local",
            endpoint=_bind_route(_api_vue_chunk_project_js_download_local, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueChunk/projects/{domain}/request-capture",
            endpoint=_bind_route(_api_vue_chunk_project_request_capture, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueChunk/projects/{domain}/request-locate",
            endpoint=_bind_route(_api_vue_chunk_project_request_locate, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueChunk/projects/{domain}/manual-requests",
            endpoint=_bind_route(_api_vue_chunk_project_manual_requests, deps),
            methods=["GET", "POST"],
        ),
        Route(
            "/api/vueChunk/projects/{domain}/route-rewrite",
            endpoint=_bind_route(_api_vue_chunk_project_route_rewrite, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueChunk/projects/{domain}",
            endpoint=_bind_route(_api_vue_chunk_project_detail, deps),
            methods=["GET"],
        ),
        Route("/api/vueChunk/jobs/{job_id}", endpoint=_bind_route(_api_vue_chunk_job_detail, deps), methods=["GET"]),
        Route(
            "/api/vueChunk/jobs/{job_id}/stop",
            endpoint=_bind_route(_api_vue_chunk_job_stop, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueChunk/jobs/{job_id}/pause",
            endpoint=_bind_route(_api_vue_chunk_job_pause, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueChunk/jobs/{job_id}/resume",
            endpoint=_bind_route(_api_vue_chunk_job_resume, deps),
            methods=["POST"],
        ),
    ]
