from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.routing import Route


@dataclass(frozen=True)
class VueDetectActionRouteDeps:
    # VueDetect 表单动作保持原路径不变，只把实现从 app.py 迁出。
    ui_state: dict[str, Any]
    safe_str: Callable[[Any, str], str]
    to_int: Callable[[Any, int, int], int]
    set_error: Callable[[str], None]
    clear_error: Callable[[], None]
    redirect: Callable[[int], Any]
    redirect_detect_task: Callable[[str], Any]
    save_uploaded_file: Callable[[UploadFile], Awaitable[str]]
    create_job: Callable[..., dict[str, Any]]
    append_log: Callable[[str, str], None]
    create_detect_task: Callable[..., dict[str, Any]]
    spawn_background: Callable[..., None]
    run_module1_detect_background: Callable[..., Any]
    update_detect_task: Callable[..., Any]
    update_job: Callable[..., Any]
    get_detect_task: Callable[[str], dict[str, Any] | None]
    delete_detect_task: Callable[[str], Any]
    upsert_project_from_url: Callable[..., dict[str, Any]]
    select_vue_api_domain: Callable[[Any], str]
    detect_default_concurrency: int
    detect_default_timeout: int
    detect_default_wait_ms: int
    module1_detect_job_step: str


def _bind_route(
    handler: Callable[[Request, VueDetectActionRouteDeps], Awaitable[Any]],
    deps: VueDetectActionRouteDeps,
) -> Callable[[Request], Awaitable[Any]]:
    async def endpoint(request: Request):
        return await handler(request, deps)

    endpoint.__name__ = handler.__name__.lstrip("_")
    return endpoint


async def _action_vue_detect_detect(request: Request, deps: VueDetectActionRouteDeps):
    form = await request.form()

    detect_form = deps.ui_state["detect_form"]
    task_name = deps.safe_str(form.get("task_name"), detect_form.get("task_name", ""))
    concurrency = deps.to_int(form.get("concurrency"), default=deps.detect_default_concurrency, minimum=1)
    upload_file = form.get("upload_file")
    detect_form["task_name"] = task_name
    detect_form["concurrency"] = str(concurrency)

    if not task_name:
        deps.set_error("task_name is required")
        return deps.redirect(1)

    if not isinstance(upload_file, UploadFile) or not deps.safe_str(upload_file.filename):
        deps.set_error("upload_file is required")
        return deps.redirect(1)

    try:
        input_path = await deps.save_uploaded_file(upload_file)
    except Exception as exc:
        deps.set_error(str(exc))
        return deps.redirect(1)

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
        deps.ui_state["detect_form"]["task_name"] = ""
        deps.clear_error()
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
        deps.set_error(str(exc))
    return deps.redirect(1)


async def _action_vue_detect_task_select(request: Request, deps: VueDetectActionRouteDeps):
    form = await request.form()
    task_id = deps.safe_str(form.get("task_id"))
    if not task_id:
        deps.set_error("task_id is required")
        return deps.redirect(1)

    task = deps.get_detect_task(task_id)
    if task is None:
        deps.set_error(f"detection task not found: {task_id}")
        return deps.redirect(1)

    deps.ui_state["selected_task_id"] = task_id
    deps.ui_state["detect_result"] = copy.deepcopy(task.get("result") or {})
    deps.clear_error()
    return deps.redirect_detect_task(task_id)


async def _action_vue_detect_task_delete(request: Request, deps: VueDetectActionRouteDeps):
    form = await request.form()
    task_id = deps.safe_str(form.get("task_id"))
    if not task_id:
        deps.set_error("task_id is required")
        return deps.redirect(1)

    try:
        deps.delete_detect_task(task_id)
        if deps.safe_str(deps.ui_state.get("selected_task_id")) == task_id:
            deps.ui_state["selected_task_id"] = ""
            deps.ui_state["detect_result"] = {}
        deps.clear_error()
    except Exception as exc:
        deps.set_error(str(exc))

    return deps.redirect(1)


async def _action_vue_detect_project_create(request: Request, deps: VueDetectActionRouteDeps):
    form = await request.form()
    url = deps.safe_str(form.get("url") or form.get("target_url"))
    task_id = deps.safe_str(form.get("task_id") or deps.ui_state.get("selected_task_id"))
    if not url:
        deps.set_error("url is required")
        return deps.redirect(1)

    try:
        project = deps.upsert_project_from_url(url=url, source="module1_detect", task_id=task_id or None)
        domain = deps.safe_str(project.get("domain"))
        deps.select_vue_api_domain(domain)
        deps.ui_state["chunk_form"]["target_url"] = url
        deps.clear_error()
        return deps.redirect(2)
    except Exception as exc:
        deps.set_error(str(exc))
        return deps.redirect(1)


def build_vue_detect_action_routes(deps: VueDetectActionRouteDeps) -> list[Route]:
    # 只迁表单动作层，保留现有 action 路径和行为。
    return [
        Route("/actions/module1/detect", endpoint=_bind_route(_action_vue_detect_detect, deps), methods=["POST"]),
        Route(
            "/actions/module1/task/select",
            endpoint=_bind_route(_action_vue_detect_task_select, deps),
            methods=["POST"],
        ),
        Route(
            "/actions/module1/task/delete",
            endpoint=_bind_route(_action_vue_detect_task_delete, deps),
            methods=["POST"],
        ),
        Route(
            "/actions/module1/project/create",
            endpoint=_bind_route(_action_vue_detect_project_create, deps),
            methods=["POST"],
        ),
    ]
