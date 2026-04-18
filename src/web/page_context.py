from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlsplit

from starlette.requests import Request


@dataclass(frozen=True)
class PageContextDeps:
    # 页面上下文只负责把现有状态和服务结果整理成模板可用的数据结构。
    ui_state: dict[str, Any]
    safe_str: Callable[[Any, str], str]
    to_int: Callable[[Any, int, int], int]
    normalize_detect_url_rows: Callable[[Any], list[dict[str, Any]]]
    read_detect_urls: Callable[[Any], list[str]]
    list_detect_tasks: Callable[..., list[dict[str, Any]]]
    list_projects: Callable[..., list[dict[str, Any]]]
    merge_project_domains: Callable[[list[dict[str, Any]]], list[str]]
    load_project_metrics: Callable[[str], dict[str, int]]
    set_selected_project_domain: Callable[[Any], str]
    get_project: Callable[[str], dict[str, Any] | None]
    load_project_detail: Callable[[str], dict[str, Any]]
    prepare_vue_api_context_state: Callable[..., dict[str, Any]]
    load_project_extract_config: Callable[[str], dict[str, str]]
    load_project_request_config: Callable[[str], dict[str, Any]]
    list_project_js_files: Callable[[str], list[Any]]
    load_api_endpoints: Callable[[str], list[Any]]
    read_job: Callable[[str], dict[str, Any]]


@dataclass(frozen=True)
class PageContextBuildDeps:
    # 这里只负责组装 PageContextDeps，避免 app.py 直接堆大段依赖清单。
    ui_state: dict[str, Any]
    safe_str: Callable[[Any, str], str]
    to_int: Callable[[Any, int, int], int]
    normalize_detect_url_rows: Callable[[Any], list[dict[str, Any]]]
    read_detect_urls: Callable[[Any], list[str]]
    list_detect_tasks: Callable[..., list[dict[str, Any]]]
    list_projects: Callable[..., list[dict[str, Any]]]
    merge_project_domains: Callable[[list[dict[str, Any]]], list[str]]
    load_project_metrics: Callable[[str], dict[str, int]]
    set_selected_project_domain: Callable[[Any], str]
    get_project: Callable[[str], dict[str, Any] | None]
    load_project_detail: Callable[[str], dict[str, Any]]
    prepare_vue_api_context_state: Callable[..., dict[str, Any]]
    load_project_extract_config: Callable[[str], dict[str, str]]
    load_project_request_config: Callable[[str], dict[str, Any]]
    list_project_js_files: Callable[[str], list[Any]]
    load_api_endpoints: Callable[[str], list[Any]]
    read_job: Callable[[str], dict[str, Any]]


def build_page_context_deps(deps: PageContextBuildDeps) -> PageContextDeps:
    return PageContextDeps(
        ui_state=deps.ui_state,
        safe_str=deps.safe_str,
        to_int=deps.to_int,
        normalize_detect_url_rows=deps.normalize_detect_url_rows,
        read_detect_urls=deps.read_detect_urls,
        list_detect_tasks=deps.list_detect_tasks,
        list_projects=deps.list_projects,
        merge_project_domains=deps.merge_project_domains,
        load_project_metrics=deps.load_project_metrics,
        set_selected_project_domain=deps.set_selected_project_domain,
        get_project=deps.get_project,
        load_project_detail=deps.load_project_detail,
        prepare_vue_api_context_state=deps.prepare_vue_api_context_state,
        load_project_extract_config=deps.load_project_extract_config,
        load_project_request_config=deps.load_project_request_config,
        list_project_js_files=deps.list_project_js_files,
        load_api_endpoints=deps.load_api_endpoints,
        read_job=deps.read_job,
    )


def _enrich_detect_tasks(deps: PageContextDeps) -> tuple[list[dict[str, Any]], bool]:
    # 统一整理检测任务列表，避免模板层重复处理 url/status 字段。
    enriched_tasks: list[dict[str, Any]] = []
    module1_has_running_tasks = False
    detect_tasks = deps.list_detect_tasks(limit=120)
    for item in detect_tasks:
        task_item = dict(item)
        task_item["urls"] = deps.normalize_detect_url_rows(task_item.get("urls"))
        task_item["url_count"] = len(task_item.get("urls", []) or [])
        status_text = deps.safe_str(task_item.get("status")).lower()
        if status_text in {"running", "queued"}:
            module1_has_running_tasks = True
        enriched_tasks.append(task_item)
    return enriched_tasks, module1_has_running_tasks


def _resolve_detect_context(
    deps: PageContextDeps,
    *,
    enriched_tasks: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any], list[str]]:
    # 计算当前选中的检测任务及其结果摘要，供首页和详情页共用。
    task_map = {
        str(item.get("task_id")): item
        for item in enriched_tasks
        if str(item.get("task_id")).strip()
    }
    selected_task_id = deps.safe_str(deps.ui_state.get("selected_task_id"))
    selected_detect_task = task_map.get(selected_task_id) if selected_task_id else None
    if selected_detect_task is None and enriched_tasks:
        selected_detect_task = enriched_tasks[0]
        deps.ui_state["selected_task_id"] = deps.safe_str(selected_detect_task.get("task_id"))

    if selected_detect_task is not None:
        detect_result = selected_detect_task.get("result") or {}
        detect_rows = deps.normalize_detect_url_rows(selected_detect_task.get("urls"))
        detect_urls = [
            str(item.get("url") or "").strip()
            for item in detect_rows
            if str(item.get("url") or "").strip()
        ]
    else:
        detect_result = copy.deepcopy(deps.ui_state.get("detect_result") or {})
        detect_urls = deps.read_detect_urls(detect_result.get("txt_path"))

    return selected_detect_task, detect_result, detect_urls


def _job_running(deps: PageContextDeps, job: dict[str, Any]) -> bool:
    status = deps.safe_str(job.get("status")).lower()
    return status in {"running", "queued"}


def _job_domain(deps: PageContextDeps, job: dict[str, Any]) -> str:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    domain = deps.safe_str(result.get("domain") or payload.get("domain"))
    if domain:
        return domain
    target_url = deps.safe_str(payload.get("target_url"))
    parsed = urlsplit(target_url)
    return deps.safe_str(parsed.hostname)


def build_page_context(
    *,
    request: Request,
    active_module: int,
    deps: PageContextDeps,
) -> dict[str, Any]:
    # 把 app.py 中的大块页面状态拼装下沉到独立模块，入口文件只负责依赖注入。
    detect_form = copy.deepcopy(deps.ui_state["detect_form"])
    chunk_form = copy.deepcopy(deps.ui_state["chunk_form"])
    module3_form = copy.deepcopy(deps.ui_state["module3_form"])
    module4_form = copy.deepcopy(deps.ui_state["module4_form"])
    chunk_form.setdefault("detect_routes", "1")
    chunk_form.setdefault("detect_js", "1")
    chunk_form.setdefault("detect_request", "1")

    enriched_tasks, module1_has_running_tasks = _enrich_detect_tasks(deps)
    selected_detect_task, detect_result, detect_urls = _resolve_detect_context(
        deps,
        enriched_tasks=enriched_tasks,
    )

    project_records = deps.list_projects(limit=500)
    project_domains = deps.merge_project_domains(project_records)
    project_map = {
        str(item.get("domain")): item
        for item in project_records
        if str(item.get("domain")).strip()
    }
    project_cards: list[dict[str, Any]] = []
    for domain in project_domains:
        metrics = deps.load_project_metrics(domain)
        raw = project_map.get(domain)
        if raw is None:
            project_cards.append(
                {
                    "domain": domain,
                    "source": "filesystem",
                    "seed_urls": [],
                    "task_ids": [],
                    **metrics,
                }
            )
        else:
            card = dict(raw)
            card.update(metrics)
            project_cards.append(card)

    project_total = len(project_cards)
    project_page_size = deps.to_int(request.query_params.get("project_size"), default=10, minimum=1)
    if project_page_size not in {10, 20, 50, 100}:
        project_page_size = 10

    project_total_pages = max(1, (project_total + project_page_size - 1) // project_page_size)
    project_page = deps.to_int(request.query_params.get("project_page"), default=1, minimum=1)
    if project_page > project_total_pages:
        project_page = project_total_pages

    project_slice_start = (project_page - 1) * project_page_size
    project_slice_end = project_slice_start + project_page_size
    project_cards = project_cards[project_slice_start:project_slice_end]
    project_serial_start = project_slice_start + 1 if project_total > 0 else 0

    selected_domain = deps.safe_str(deps.ui_state.get("selected_project_domain"))
    if not selected_domain and project_domains:
        selected_domain = project_domains[0]
        deps.set_selected_project_domain(selected_domain)

    selected_project = deps.get_project(selected_domain) if selected_domain else None
    if selected_project is None and selected_domain:
        selected_project = {
            "domain": selected_domain,
            "source": "filesystem",
            "seed_urls": [],
            "task_ids": [],
        }

    module2_detail = deps.load_project_detail(selected_domain) if selected_domain else {}

    if selected_project and selected_project.get("seed_urls") and not chunk_form.get("target_url"):
        chunk_form["target_url"] = str(selected_project["seed_urls"][0])
        deps.ui_state["chunk_form"]["target_url"] = chunk_form["target_url"]

    vue_api_context = deps.prepare_vue_api_context_state(
        deps.ui_state,
        selected_domain=selected_domain,
        module3_form=module3_form,
        module4_form=module4_form,
        safe_str=deps.safe_str,
        load_project_extract_config=deps.load_project_extract_config,
        load_project_request_config=deps.load_project_request_config,
        list_project_js_files=deps.list_project_js_files,
        load_api_endpoints=deps.load_api_endpoints,
    )
    module3_form = (
        vue_api_context.get("module3_form")
        if isinstance(vue_api_context.get("module3_form"), dict)
        else module3_form
    )
    module4_form = (
        vue_api_context.get("module4_form")
        if isinstance(vue_api_context.get("module4_form"), dict)
        else module4_form
    )
    module3_js_files = [
        deps.safe_str(item)
        for item in (vue_api_context.get("module3_js_files") or [])
        if deps.safe_str(item)
    ]
    module4_endpoints = (
        vue_api_context.get("module4_endpoints")
        if isinstance(vue_api_context.get("module4_endpoints"), list)
        else []
    )

    projects_for_select = [str(item) for item in project_domains]

    module2_sync_job: dict[str, Any] = {}
    module2_js_download_job: dict[str, Any] = {}
    module2_sync_job_id = deps.safe_str(deps.ui_state.get("module2_sync_job_id"))
    module2_js_download_job_id = deps.safe_str(deps.ui_state.get("module2_js_download_job_id"))
    if module2_sync_job_id:
        try:
            module2_sync_job = deps.read_job(module2_sync_job_id)
        except Exception:
            module2_sync_job = {}
    if module2_js_download_job_id:
        try:
            module2_js_download_job = deps.read_job(module2_js_download_job_id)
        except Exception:
            module2_js_download_job = {}

    module2_sync_job_domain = _job_domain(deps, module2_sync_job) if module2_sync_job else ""
    module2_js_download_job_domain = _job_domain(deps, module2_js_download_job) if module2_js_download_job else ""
    module2_sync_job_for_selected = bool(
        module2_sync_job
        and (
            not selected_domain
            or not module2_sync_job_domain
            or module2_sync_job_domain == selected_domain
        )
    )
    module2_js_download_job_for_selected = bool(
        module2_js_download_job
        and (
            not selected_domain
            or not module2_js_download_job_domain
            or module2_js_download_job_domain == selected_domain
        )
    )

    module2_has_running_jobs = (
        (_job_running(deps, module2_sync_job) and module2_sync_job_for_selected)
        or (_job_running(deps, module2_js_download_job) and module2_js_download_job_for_selected)
    )

    return {
        "request": request,
        "page_title": "VueScan Web Wizard",
        "active_module": active_module,
        "module_titles": {
            1: "Module 1 Vue Detection",
            2: "Module 2 Project Routes and Chunks",
            3: "Module 3 API Extraction",
            4: "Module 4 API Request",
        },
        "error": deps.safe_str(deps.ui_state.get("error")),
        "detect_form": detect_form,
        "detect_tasks": enriched_tasks,
        "module1_has_running_tasks": module1_has_running_tasks,
        "selected_detect_task": selected_detect_task,
        "module1_task_detail": selected_detect_task,
        "selected_detect_task_id": deps.safe_str(deps.ui_state.get("selected_task_id")),
        "detect_result": detect_result,
        "detect_urls": detect_urls,
        "chunk_form": chunk_form,
        "chunk_result": copy.deepcopy(deps.ui_state.get("chunk_result") or {}),
        "projects": projects_for_select,
        "projects_meta": project_records,
        "project_cards": project_cards,
        "project_total": project_total,
        "project_page": project_page,
        "project_page_size": project_page_size,
        "project_total_pages": project_total_pages,
        "project_serial_start": project_serial_start,
        "project_has_prev": project_page > 1,
        "project_has_next": project_page < project_total_pages,
        "project_prev_page": project_page - 1 if project_page > 1 else 1,
        "project_next_page": project_page + 1 if project_page < project_total_pages else project_total_pages,
        "project_page_size_options": [10, 20, 50, 100],
        "selected_project_domain": selected_domain,
        "selected_project": selected_project,
        "module2_detail": module2_detail,
        "module3_form": module3_form,
        "module3_js_files": module3_js_files,
        "module3_js_beautify": copy.deepcopy(deps.ui_state.get("module3_js_beautify") or {}),
        "module3_preview": copy.deepcopy(deps.ui_state.get("module3_preview") or {}),
        "module3_extract_result": copy.deepcopy(deps.ui_state.get("module3_extract_result") or {}),
        "module4_form": module4_form,
        "module4_endpoints": module4_endpoints,
        "module4_request_result": copy.deepcopy(deps.ui_state.get("module4_request_result") or {}),
        "module2_sync_job": module2_sync_job,
        "module2_js_download_job": module2_js_download_job,
        "module2_sync_job_domain": module2_sync_job_domain,
        "module2_js_download_job_domain": module2_js_download_job_domain,
        "module2_sync_job_for_selected": module2_sync_job_for_selected,
        "module2_js_download_job_for_selected": module2_js_download_job_for_selected,
        "module2_has_running_jobs": module2_has_running_jobs,
    }
