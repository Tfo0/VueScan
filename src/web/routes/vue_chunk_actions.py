from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import quote

from starlette.requests import Request
from starlette.responses import FileResponse, RedirectResponse
from starlette.routing import Route


@dataclass(frozen=True)
class VueChunkActionRouteDeps:
    # VueChunk 的表单动作和下载入口先迁出 app.py，路径保持不变。
    ui_state: dict[str, Any]
    safe_str: Callable[[Any, str], str]
    to_int: Callable[[Any, int, int], int]
    to_bool: Callable[[Any], bool]
    set_error: Callable[[str], None]
    clear_error: Callable[[], None]
    redirect: Callable[[int], Any]
    run_web_action: Callable[..., Awaitable[tuple[str, dict[str, Any]]]]
    run_chunk_download: Callable[..., Any]
    upsert_project_from_url: Callable[..., dict[str, Any]]
    get_project: Callable[[str], dict[str, Any] | None]
    queue_project_sync: Callable[..., tuple[dict[str, Any], dict[str, Any]]]
    select_vue_api_domain: Callable[[Any], str]
    set_selected_project_domain: Callable[[Any], str]
    load_project_detail: Callable[[str], dict[str, Any]]
    dedupe_effective_js_urls: Callable[[list[Any]], list[str]]
    read_lines: Callable[[Path, int], list[str]]
    create_job: Callable[..., dict[str, Any]]
    append_log: Callable[[str, str], None]
    spawn_background: Callable[..., None]
    run_module2_js_download_background: Callable[..., Any]
    read_job: Callable[[str], dict[str, Any]]
    safe_file_token: Callable[[str, str], str]
    module2_js_download_job_step: str
    js_download_default_concurrency: int


def _bind_route(
    handler: Callable[[Request, VueChunkActionRouteDeps], Awaitable[Any]],
    deps: VueChunkActionRouteDeps,
) -> Callable[[Request], Awaitable[Any]]:
    async def endpoint(request: Request):
        return await handler(request, deps)

    endpoint.__name__ = handler.__name__.lstrip("_")
    return endpoint


def _redirect_project_detail(domain: str, deps: VueChunkActionRouteDeps):
    token = deps.safe_str(domain)
    if not token:
        return deps.redirect(2)
    encoded = quote(token, safe=".-_")
    return RedirectResponse(url=f"/projects/{encoded}", status_code=303)


async def _action_vue_chunk_download(request: Request, deps: VueChunkActionRouteDeps):
    form = await request.form()

    chunk_form = deps.ui_state["chunk_form"]
    target_url = deps.safe_str(form.get("target_url"), chunk_form.get("target_url", ""))
    urls_list = deps.safe_str(form.get("urls_list"), chunk_form.get("urls_list", ""))
    concurrency = deps.to_int(form.get("concurrency"), default=5, minimum=1)

    chunk_form.update(
        {
            "target_url": target_url,
            "urls_list": urls_list,
            "concurrency": str(concurrency),
        }
    )

    if not target_url and not urls_list:
        deps.set_error("target_url or urls_list is required")
        return deps.redirect(2)

    payload = {
        "target_url": target_url,
        "urls_list": urls_list,
        "concurrency": concurrency,
    }

    try:
        job_id, result = await deps.run_web_action(
            "web_module2_chunk_download",
            payload,
            lambda: deps.run_chunk_download(
                target_url=target_url or None,
                urls_list=urls_list or None,
                concurrency=concurrency,
            ),
        )
        deps.ui_state["chunk_result"] = {"job_id": job_id, **result}

        domain = deps.safe_str(result.get("domain"))
        if target_url:
            deps.upsert_project_from_url(url=target_url, source="module2_chunk")
        if domain:
            deps.select_vue_api_domain(domain)

        deps.clear_error()
    except Exception as exc:
        deps.set_error(str(exc))

    return deps.redirect(2)


async def _action_vue_chunk_project_create(request: Request, deps: VueChunkActionRouteDeps):
    form = await request.form()
    domain = deps.safe_str(form.get("domain") or deps.ui_state.get("selected_project_domain"))
    target_url = deps.safe_str(form.get("target_url") or form.get("url"))
    concurrency = deps.to_int(form.get("concurrency"), default=5, minimum=1)
    detect_routes = deps.to_bool(form.get("detect_routes"))
    detect_js = deps.to_bool(form.get("detect_js"))
    detect_request = deps.to_bool(form.get("detect_request"))

    if not target_url and domain:
        existed = deps.get_project(domain)
        if existed and existed.get("seed_urls"):
            target_url = str(existed["seed_urls"][0])

    if not target_url:
        deps.set_error("target_url is required")
        return deps.redirect(2)

    try:
        if detect_routes or detect_js or detect_request:
            deps.queue_project_sync(
                target_url=target_url,
                source="module2_manual",
                concurrency=concurrency,
                detect_routes=detect_routes,
                detect_js=detect_js,
                detect_request=detect_request,
            )
        else:
            project = deps.upsert_project_from_url(url=target_url, source="module2_manual")
            selected_domain = deps.safe_str(project.get("domain"))
            deps.select_vue_api_domain(selected_domain)
            deps.ui_state["chunk_form"]["target_url"] = target_url
            deps.ui_state["chunk_form"]["concurrency"] = str(concurrency)
            deps.ui_state["chunk_form"]["detect_routes"] = ""
            deps.ui_state["chunk_form"]["detect_js"] = ""
            deps.ui_state["chunk_form"]["detect_request"] = ""

        deps.clear_error()
    except Exception as exc:
        deps.set_error(str(exc))
    return deps.redirect(2)


async def _action_vue_chunk_project_select(request: Request, deps: VueChunkActionRouteDeps):
    form = await request.form()
    domain = deps.safe_str(form.get("domain"))
    if not domain:
        deps.set_error("domain is required")
        return deps.redirect(2)

    deps.select_vue_api_domain(domain)

    project = deps.get_project(domain)
    if project and project.get("seed_urls"):
        deps.ui_state["chunk_form"]["target_url"] = str(project["seed_urls"][0])

    deps.clear_error()
    return _redirect_project_detail(domain, deps)


async def _action_vue_chunk_project_sync(request: Request, deps: VueChunkActionRouteDeps):
    form = await request.form()
    domain = deps.safe_str(form.get("domain") or deps.ui_state.get("selected_project_domain"))
    target_url = deps.safe_str(form.get("target_url"))
    concurrency = deps.to_int(form.get("concurrency"), default=5, minimum=1)
    detect_routes = deps.to_bool(form.get("detect_routes"))
    detect_js = deps.to_bool(form.get("detect_js"))
    detect_request = deps.to_bool(form.get("detect_request"))

    if not target_url and domain:
        project = deps.get_project(domain)
        if project and project.get("seed_urls"):
            target_url = str(project["seed_urls"][0])

    if not target_url:
        deps.set_error("target_url is required")
        return deps.redirect(2)

    try:
        deps.queue_project_sync(
            target_url=target_url,
            source="module2_sync",
            concurrency=concurrency,
            detect_routes=detect_routes,
            detect_js=detect_js,
            detect_request=detect_request,
        )
        deps.clear_error()
    except Exception as exc:
        deps.set_error(str(exc))

    return deps.redirect(2)


async def _action_vue_chunk_js_download(request: Request, deps: VueChunkActionRouteDeps):
    form = await request.form()
    domain = deps.safe_str(form.get("domain") or deps.ui_state.get("selected_project_domain"))
    if not domain:
        deps.set_error("domain is required")
        return deps.redirect(2)

    detail = deps.load_project_detail(domain)
    js_file = Path(deps.safe_str(detail.get("js_file")))
    js_urls = deps.dedupe_effective_js_urls(deps.read_lines(js_file, limit=200000))
    if not js_urls:
        js_urls = deps.dedupe_effective_js_urls(
            [deps.safe_str(item) for item in detail.get("js_preview", []) if deps.safe_str(item)]
        )
    if not js_urls:
        deps.set_error("no captured js urls found for current project")
        return _redirect_project_detail(domain, deps)

    try:
        payload = {
            "domain": domain,
            "total": len(js_urls),
            "concurrency": deps.js_download_default_concurrency,
        }
        job = deps.create_job(step=deps.module2_js_download_job_step, payload=payload)
        job_id = deps.safe_str(job.get("job_id"))
        if not job_id:
            raise ValueError("failed to create module2 js download job")
        deps.append_log(job_id, f"web action queued: {deps.module2_js_download_job_step}")
        deps.ui_state["module2_js_download_job_id"] = job_id
        deps.set_selected_project_domain(domain)
        deps.ui_state["chunk_result"] = {
            "job_id": job_id,
            "status": "running",
            "step": deps.module2_js_download_job_step,
            **payload,
        }
        deps.spawn_background(
            deps.run_module2_js_download_background,
            job_id=job_id,
            domain=domain,
            js_urls=js_urls,
            concurrency=deps.js_download_default_concurrency,
        )
        deps.clear_error()
    except Exception as exc:
        deps.set_error(str(exc))

    return _redirect_project_detail(domain, deps)


async def _download_vue_chunk_js_zip(request: Request, deps: VueChunkActionRouteDeps):
    job_id = deps.safe_str(request.path_params.get("job_id"))
    if not job_id:
        deps.set_error("job_id is required")
        return deps.redirect(2)

    try:
        job = deps.read_job(job_id)
    except Exception as exc:
        deps.set_error(str(exc))
        return deps.redirect(2)

    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    domain = deps.safe_str(result.get("domain") or payload.get("domain") or deps.ui_state.get("selected_project_domain"))

    if deps.safe_str(job.get("step")) != deps.module2_js_download_job_step:
        deps.set_error("invalid job type for js zip download")
        return _redirect_project_detail(domain, deps)

    if deps.safe_str(job.get("status")).lower() != "completed":
        deps.set_error("js zip task is still running")
        return _redirect_project_detail(domain, deps)

    zip_path = Path(deps.safe_str(result.get("zip_path")))
    if not zip_path.is_file():
        deps.set_error("zip file not found")
        return _redirect_project_detail(domain, deps)

    deps.ui_state["module2_js_download_job_id"] = job_id
    if domain:
        deps.set_selected_project_domain(domain)
    deps.clear_error()
    download_name = f"{deps.safe_file_token(domain, default='project')}_captured_js.zip"
    return FileResponse(path=str(zip_path), media_type="application/zip", filename=download_name)


def build_vue_chunk_action_routes(deps: VueChunkActionRouteDeps) -> list[Route]:
    # 先拆 VueChunk 的表单动作层，后续再继续拆 module2 的 API 路由。
    return [
        Route("/actions/module2/chunk", endpoint=_bind_route(_action_vue_chunk_download, deps), methods=["POST"]),
        Route(
            "/actions/module2/project/create",
            endpoint=_bind_route(_action_vue_chunk_project_create, deps),
            methods=["POST"],
        ),
        Route(
            "/actions/module2/project/select",
            endpoint=_bind_route(_action_vue_chunk_project_select, deps),
            methods=["POST"],
        ),
        Route(
            "/actions/module2/project/sync",
            endpoint=_bind_route(_action_vue_chunk_project_sync, deps),
            methods=["POST"],
        ),
        Route(
            "/actions/module2/js/download",
            endpoint=_bind_route(_action_vue_chunk_js_download, deps),
            methods=["POST"],
        ),
        Route(
            "/downloads/vueChunk/jszip/{job_id}",
            endpoint=_bind_route(_download_vue_chunk_js_zip, deps),
            methods=["GET"],
        ),
        Route(
            "/downloads/module2/jszip/{job_id}",
            endpoint=_bind_route(_download_vue_chunk_js_zip, deps),
            methods=["GET"],
        ),
    ]
