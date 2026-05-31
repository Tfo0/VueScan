from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.routing import Route


@dataclass(frozen=True)
class VueDetectRouteDeps:
    # VueDetect 的 JSON API 路由从 app.py 拆出，保持现有任务流和返回结构不变。
    ui_state: dict[str, Any]
    safe_str: Callable[[Any, str], str]
    to_int: Callable[[Any, int, int], int]
    to_bool: Callable[[Any], bool]
    json_ok: Callable[..., Any]
    json_error: Callable[..., Any]
    clear_error: Callable[[], None]
    save_uploaded_file: Callable[[UploadFile], Awaitable[str]]
    create_job: Callable[..., dict[str, Any]]
    append_log: Callable[[str, str], None]
    create_detect_task: Callable[..., dict[str, Any]]
    spawn_background: Callable[..., None]
    run_module1_detect_background: Callable[..., Any]
    update_detect_task: Callable[..., dict[str, Any]]
    update_job: Callable[..., dict[str, Any]]
    read_job: Callable[[str], dict[str, Any]]
    get_detect_task: Callable[[str], dict[str, Any] | None]
    delete_detect_task: Callable[[str], dict[str, Any]]
    list_detect_tasks: Callable[..., list[dict[str, Any]]]
    serialize_detect_task: Callable[[dict[str, Any]], dict[str, Any]]
    serialize_module1_detect_job: Callable[[dict[str, Any]], dict[str, Any]]
    find_detect_task_by_job_id: Callable[[str], dict[str, Any] | None]
    task_status_is_running: Callable[[str], bool]
    queue_project_sync: Callable[..., tuple[dict[str, Any], dict[str, Any]]]
    serialize_project: Callable[[dict[str, Any]], dict[str, Any]]
    serialize_sync_job: Callable[..., dict[str, Any]]
    detect_default_concurrency: int
    detect_default_timeout: int
    detect_default_wait_ms: int
    module1_detect_job_step: str


def _detect_form_from_state(deps: VueDetectRouteDeps) -> dict[str, Any]:
    form = deps.ui_state.get("detect_form")
    if isinstance(form, dict):
        return form
    form = {}
    deps.ui_state["detect_form"] = form
    return form


async def _read_json_payload(request: Request) -> dict[str, Any]:
    try:
        raw_payload = await request.json()
    except Exception:
        return {}
    return raw_payload if isinstance(raw_payload, dict) else {}


def _bind_route(
    handler: Callable[[Request, VueDetectRouteDeps], Awaitable[Any]],
    deps: VueDetectRouteDeps,
) -> Callable[[Request], Awaitable[Any]]:
    async def endpoint(request: Request):
        return await handler(request, deps)

    endpoint.__name__ = handler.__name__.lstrip("_")
    return endpoint


async def _api_vue_detect_tasks(request: Request, deps: VueDetectRouteDeps):
    limit = deps.to_int(request.query_params.get("limit"), default=120, minimum=1)
    records = deps.list_detect_tasks(limit=min(limit, 500))
    tasks = [deps.serialize_detect_task(item) for item in records]

    selected_task_id = deps.safe_str(
        request.query_params.get("selected_task_id") or deps.ui_state.get("selected_task_id")
    )
    selected_task = next((item for item in tasks if item["task_id"] == selected_task_id), None)
    if selected_task is None and tasks:
        selected_task = tasks[0]
        selected_task_id = selected_task["task_id"]

    if selected_task_id:
        deps.ui_state["selected_task_id"] = selected_task_id
        deps.ui_state["detect_result"] = copy.deepcopy((selected_task or {}).get("result") or {})

    has_running_tasks = any(deps.task_status_is_running(str(item.get("status", ""))) for item in tasks)
    return deps.json_ok(
        {
            "tasks": tasks,
            "total": len(tasks),
            "selected_task_id": selected_task_id,
            "selected_task": selected_task,
            "has_running_tasks": has_running_tasks,
        }
    )


async def _api_vue_detect_task_detail(request: Request, deps: VueDetectRouteDeps):
    task_id = deps.safe_str(request.path_params.get("task_id"))
    if not task_id:
        return deps.json_error("task_id is required", status_code=400)

    task = deps.get_detect_task(task_id)
    if task is None:
        return deps.json_error(f"detection task not found: {task_id}", status_code=404)

    serialized = deps.serialize_detect_task(task)
    deps.ui_state["selected_task_id"] = task_id
    deps.ui_state["detect_result"] = copy.deepcopy(serialized.get("result") or {})
    return deps.json_ok({"task": serialized})


async def _api_vue_detect_task_create(request: Request, deps: VueDetectRouteDeps):
    form = await request.form()

    detect_form = _detect_form_from_state(deps)
    task_name = deps.safe_str(form.get("task_name"), detect_form.get("task_name", ""))
    concurrency = deps.to_int(
        form.get("concurrency"),
        default=deps.detect_default_concurrency,
        minimum=1,
    )
    upload_file = form.get("upload_file")
    detect_form["task_name"] = task_name
    detect_form["concurrency"] = str(concurrency)

    if not task_name:
        return deps.json_error("task_name is required", status_code=400)
    if not isinstance(upload_file, UploadFile) or not deps.safe_str(upload_file.filename):
        return deps.json_error("upload_file is required", status_code=400)

    try:
        input_path = await deps.save_uploaded_file(upload_file)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=400)

    timeout = deps.detect_default_timeout
    wait_ms = deps.detect_default_wait_ms
    detect_limit = None
    payload = {
        "task_name": task_name,
        "input_path": input_path,
        "output_path": "",
        "concurrency": concurrency,
        "timeout": timeout,
        "wait_ms": wait_ms,
        "limit": detect_limit,
    }

    job_id = ""
    task_id = ""
    try:
        job = deps.create_job(step=deps.module1_detect_job_step, payload=payload)
        job_id = deps.safe_str(job.get("job_id"))
        if not job_id:
            raise ValueError("failed to create detection job")
        deps.append_log(job_id, f"web action queued: {deps.module1_detect_job_step}")

        task = deps.create_detect_task(job_id=job_id, input_path=input_path, params=payload, title=task_name)
        task_id = deps.safe_str(task.get("task_id"))
        if not task_id:
            raise ValueError("failed to create detection task")

        deps.spawn_background(
            deps.run_module1_detect_background,
            job_id=job_id,
            task_id=task_id,
            input_path=input_path,
            concurrency=concurrency,
            timeout=timeout,
            wait_ms=wait_ms,
            detect_limit=detect_limit,
        )

        deps.ui_state["selected_task_id"] = task_id
        deps.ui_state["detect_result"] = {
            "job_id": job_id,
            "task_id": task_id,
            "status": "running",
            "summary": {},
        }
        detect_form["task_name"] = ""
        deps.clear_error()
        return deps.json_ok({"task": deps.serialize_detect_task(task), "job_id": job_id}, status_code=201)
    except Exception as exc:
        if task_id:
            try:
                deps.update_detect_task(
                    task_id,
                    status="failed",
                    result={},
                    urls=[],
                    error=str(exc),
                )
            except Exception:
                pass
        if job_id:
            try:
                deps.append_log(job_id, f"web action failed: {exc}")
                deps.update_job(job_id=job_id, status="failed", error=str(exc))
            except Exception:
                pass
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_detect_task_delete(request: Request, deps: VueDetectRouteDeps):
    task_id = deps.safe_str(request.path_params.get("task_id"))
    if not task_id:
        return deps.json_error("task_id is required", status_code=400)

    try:
        deleted = deps.delete_detect_task(task_id)
        if deps.safe_str(deps.ui_state.get("selected_task_id")) == task_id:
            deps.ui_state["selected_task_id"] = ""
            deps.ui_state["detect_result"] = {}
        deps.clear_error()
        return deps.json_ok({"deleted_task_id": task_id, "task": deps.serialize_detect_task(deleted)})
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


async def _api_vue_detect_job_pause(request: Request, deps: VueDetectRouteDeps):
    job_id = deps.safe_str(request.path_params.get("job_id"))
    if not job_id:
        return deps.json_error("job_id is required", status_code=400)

    try:
        job = deps.read_job(job_id)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    if deps.safe_str(job.get("step")) != deps.module1_detect_job_step:
        return deps.json_error("only vue detect jobs support pause", status_code=400)

    current_status = deps.safe_str(job.get("status")).lower()
    if current_status not in {"running", "queued"}:
        return deps.json_error("only running or queued detect jobs can be paused", status_code=400)

    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    merged_result = dict(result)
    progress = merged_result.get("progress") if isinstance(merged_result.get("progress"), dict) else {}
    merged_result["progress"] = {
        "done": deps.to_int(progress.get("done"), default=0, minimum=0),
        "total": deps.to_int(progress.get("total"), default=0, minimum=0),
    }

    try:
        updated_job = deps.update_job(job_id=job_id, status="paused", result=merged_result)
        deps.append_log(job_id, "web action pause requested")
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    updated_task = None
    try:
        hit_task = deps.find_detect_task_by_job_id(job_id)
        if hit_task:
            updated_task = deps.update_detect_task(
                deps.safe_str(hit_task.get("task_id")),
                status="paused",
            )
    except Exception:
        updated_task = None

    payload: dict[str, Any] = {"job": deps.serialize_module1_detect_job(updated_job)}
    if isinstance(updated_task, dict):
        payload["task"] = deps.serialize_detect_task(updated_task)
    return deps.json_ok(payload)


async def _api_vue_detect_job_resume(request: Request, deps: VueDetectRouteDeps):
    job_id = deps.safe_str(request.path_params.get("job_id"))
    if not job_id:
        return deps.json_error("job_id is required", status_code=400)

    try:
        job = deps.read_job(job_id)
    except FileNotFoundError as exc:
        return deps.json_error(str(exc), status_code=404)
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    if deps.safe_str(job.get("step")) != deps.module1_detect_job_step:
        return deps.json_error("only vue detect jobs support resume", status_code=400)

    current_status = deps.safe_str(job.get("status")).lower()
    if current_status != "paused":
        return deps.json_error("only paused detect jobs can be resumed", status_code=400)

    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    merged_result = dict(result)
    progress = merged_result.get("progress") if isinstance(merged_result.get("progress"), dict) else {}
    merged_result["progress"] = {
        "done": deps.to_int(progress.get("done"), default=0, minimum=0),
        "total": deps.to_int(progress.get("total"), default=0, minimum=0),
    }

    try:
        updated_job = deps.update_job(job_id=job_id, status="running", result=merged_result)
        deps.append_log(job_id, "web action resume requested")
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)

    updated_task = None
    try:
        hit_task = deps.find_detect_task_by_job_id(job_id)
        if hit_task:
            updated_task = deps.update_detect_task(
                deps.safe_str(hit_task.get("task_id")),
                status="running",
            )
    except Exception:
        updated_task = None

    payload: dict[str, Any] = {"job": deps.serialize_module1_detect_job(updated_job)}
    if isinstance(updated_task, dict):
        payload["task"] = deps.serialize_detect_task(updated_task)
    return deps.json_ok(payload)


async def _api_vue_detect_task_project_create(request: Request, deps: VueDetectRouteDeps):
    task_id = deps.safe_str(request.path_params.get("task_id"))
    if not task_id:
        return deps.json_error("task_id is required", status_code=400)

    task = deps.get_detect_task(task_id)
    if task is None:
        return deps.json_error(f"detection task not found: {task_id}", status_code=404)

    payload = await _read_json_payload(request)
    url = deps.safe_str(payload.get("url"))
    project_title = deps.safe_str(payload.get("title"))
    concurrency = deps.to_int(payload.get("concurrency"), default=5, minimum=1)
    has_detect_routes = "detect_routes" in payload
    has_detect_js = "detect_js" in payload
    has_detect_request = "detect_request" in payload
    detect_routes = deps.to_bool(payload.get("detect_routes")) if has_detect_routes else True
    detect_js = deps.to_bool(payload.get("detect_js")) if has_detect_js else True
    detect_request = deps.to_bool(payload.get("detect_request")) if has_detect_request else True
    # 检测任务里创建项目默认沿用手动创建的自动流程，确保后续抓包和本地 JS 缓存都会自动跑起来。
    has_auto_pipeline = ("auto_pipeline" in payload) or ("automation" in payload)
    auto_pipeline = (
        deps.to_bool(payload.get("auto_pipeline") or payload.get("automation")) if has_auto_pipeline else True
    )

    if not url:
        for candidate in task.get("urls", []) if isinstance(task.get("urls"), list) else []:
            if isinstance(candidate, dict):
                value = deps.safe_str(candidate.get("url") or candidate.get("final_url"))
                if not project_title:
                    project_title = deps.safe_str(candidate.get("title"))
            else:
                value = deps.safe_str(candidate)
            if value:
                url = value
                break

    if not url:
        return deps.json_error("url is required, and task has no detected urls", status_code=400)

    try:
        if auto_pipeline:
            detect_routes = True
            detect_js = True
            detect_request = True
        project, sync_job_raw = deps.queue_project_sync(
            target_url=url,
            source="module1_detect",
            concurrency=concurrency,
            detect_routes=detect_routes,
            detect_js=detect_js,
            detect_request=detect_request,
            auto_pipeline=auto_pipeline,
            task_id=task_id,
            project_title=project_title,
        )
        deps.clear_error()
        return deps.json_ok(
            {
                "project": deps.serialize_project(project),
                "sync_job": deps.serialize_sync_job(
                    sync_job_raw,
                    fallback_domain=deps.safe_str(project.get("domain")),
                ),
            },
            status_code=201,
        )
    except Exception as exc:
        return deps.json_error(str(exc), status_code=500)


def build_vue_detect_routes(deps: VueDetectRouteDeps) -> list[Route]:
    # 这里先接管 VueDetect 的 JSON API，保持旧路径和新路径同时可用。
    return [
        Route("/api/module1/tasks", endpoint=_bind_route(_api_vue_detect_tasks, deps), methods=["GET"]),
        Route("/api/module1/tasks", endpoint=_bind_route(_api_vue_detect_task_create, deps), methods=["POST"]),
        Route(
            "/api/module1/tasks/{task_id}",
            endpoint=_bind_route(_api_vue_detect_task_detail, deps),
            methods=["GET"],
        ),
        Route(
            "/api/module1/tasks/{task_id}",
            endpoint=_bind_route(_api_vue_detect_task_delete, deps),
            methods=["DELETE"],
        ),
        Route(
            "/api/module1/tasks/{task_id}/projects",
            endpoint=_bind_route(_api_vue_detect_task_project_create, deps),
            methods=["POST"],
        ),
        Route(
            "/api/module1/jobs/{job_id}/pause",
            endpoint=_bind_route(_api_vue_detect_job_pause, deps),
            methods=["POST"],
        ),
        Route(
            "/api/module1/jobs/{job_id}/resume",
            endpoint=_bind_route(_api_vue_detect_job_resume, deps),
            methods=["POST"],
        ),
        Route("/api/vueDetect/tasks", endpoint=_bind_route(_api_vue_detect_tasks, deps), methods=["GET"]),
        Route("/api/vueDetect/tasks", endpoint=_bind_route(_api_vue_detect_task_create, deps), methods=["POST"]),
        Route(
            "/api/vueDetect/tasks/{task_id}",
            endpoint=_bind_route(_api_vue_detect_task_detail, deps),
            methods=["GET"],
        ),
        Route(
            "/api/vueDetect/tasks/{task_id}",
            endpoint=_bind_route(_api_vue_detect_task_delete, deps),
            methods=["DELETE"],
        ),
        Route(
            "/api/vueDetect/tasks/{task_id}/projects",
            endpoint=_bind_route(_api_vue_detect_task_project_create, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueDetect/jobs/{job_id}/pause",
            endpoint=_bind_route(_api_vue_detect_job_pause, deps),
            methods=["POST"],
        ),
        Route(
            "/api/vueDetect/jobs/{job_id}/resume",
            endpoint=_bind_route(_api_vue_detect_job_resume, deps),
            methods=["POST"],
        ),
    ]
