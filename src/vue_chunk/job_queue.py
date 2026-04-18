from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from src.vue_chunk.request_capture import normalize_basepath, normalize_hash_style, rewrite_route_urls


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def pick_first_http_url(candidates: list[Any]) -> str:
    for candidate in candidates:
        value = _safe_text(candidate)
        parsed = urlsplit(value)
        if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
            return value
    return ""


def resolve_target_url(
    domain: str,
    *,
    preferred_target_url: str = "",
    get_project: Callable[[str], dict[str, Any] | None],
    collect_sync_state_map: Callable[..., dict[str, dict[str, Any]]],
    load_project_detail: Callable[[str], dict[str, Any]],
) -> str:
    token = _safe_text(domain)
    if not token:
        return ""

    preferred = _safe_text(preferred_target_url)
    if preferred:
        return preferred

    sync_map = collect_sync_state_map(limit=1200)
    last_sync = sync_map.get(token) or {}
    from_sync = _safe_text(last_sync.get("target_url"))
    if from_sync:
        return from_sync

    project = get_project(token)
    seed_urls = project.get("seed_urls") if isinstance(project, dict) else []
    if isinstance(seed_urls, list):
        from_seed = pick_first_http_url(seed_urls)
        if from_seed:
            return from_seed

    detail = load_project_detail(token)
    if isinstance(detail, dict):
        from_preview = detail.get("urls_preview")
        if isinstance(from_preview, list):
            return pick_first_http_url(from_preview)

    return ""


def queue_js_download(
    *,
    domain: str,
    concurrency: int,
    mode: str,
    load_project_detail: Callable[[str], dict[str, Any]],
    read_lines: Callable[[Path, int], list[str]],
    dedupe_effective_js_urls: Callable[[list[Any]], list[str]],
    safe_str: Callable[[Any, str], str],
    create_job: Callable[..., dict[str, Any]],
    append_log: Callable[[str, str], None],
    update_job: Callable[..., dict[str, Any]],
    module2_js_download_job_step: str,
    on_queued: Callable[[str, str, dict[str, Any]], None],
    spawn_background: Callable[..., None],
    run_background: Callable[..., Any],
) -> dict[str, Any]:
    detail = load_project_detail(domain)
    if not detail:
        raise FileNotFoundError(f"project not found: {domain}")

    js_file = Path(safe_str(detail.get("js_file")))
    js_urls = dedupe_effective_js_urls(read_lines(js_file, limit=200000))
    if not js_urls:
        js_urls = dedupe_effective_js_urls([safe_str(item) for item in detail.get("js_preview", []) if safe_str(item)])
    if not js_urls:
        raise ValueError("no captured js urls found for current project")

    mode_token = safe_str(mode, "zip").lower()
    if mode_token not in {"zip", "local"}:
        mode_token = "zip"

    payload = {
        "domain": domain,
        "total": len(js_urls),
        "concurrency": max(1, int(concurrency)),
        "mode": mode_token,
    }
    job = create_job(step=module2_js_download_job_step, payload=payload)
    job_id = safe_str(job.get("job_id"))
    if not job_id:
        raise ValueError("failed to create module2 js download job")

    append_log(job_id, f"web action queued: {module2_js_download_job_step}")
    queued_result = {
        "domain": domain,
        "mode": mode_token,
        "concurrency": max(1, int(concurrency)),
        "progress": {"done": 0, "total": len(js_urls), "downloaded": 0, "skipped": 0, "failed": 0},
    }
    job = update_job(job_id=job_id, status="queued", result=queued_result)
    on_queued(job_id, domain, payload)
    spawn_background(
        run_background,
        job_id=job_id,
        domain=domain,
        js_urls=js_urls,
        concurrency=max(1, int(concurrency)),
        mode=mode_token,
    )
    return job


def queue_request_capture(
    *,
    domain: str,
    concurrency: int,
    proxy_server: str,
    load_project_detail: Callable[[str], dict[str, Any]],
    read_lines: Callable[[Path, int], list[str]],
    safe_str: Callable[[Any, str], str],
    load_route_url_profile: Callable[[str], dict[str, Any]],
    normalize_proxy_server: Callable[[Any], str],
    get_global_settings: Callable[[], dict[str, Any]],
    create_job: Callable[..., dict[str, Any]],
    append_log: Callable[[str, str], None],
    update_job: Callable[..., dict[str, Any]],
    module2_request_capture_job_step: str,
    on_queued: Callable[[str, str], None],
    spawn_background: Callable[..., None],
    run_background: Callable[..., Any],
) -> dict[str, Any]:
    detail = load_project_detail(domain)
    if not detail:
        raise FileNotFoundError(f"project not found: {domain}")

    urls_file = Path(safe_str(detail.get("urls_file")))
    route_urls_raw = read_lines(urls_file, limit=300000)
    if not route_urls_raw:
        route_urls_raw = [
            safe_str(item.get("route_url"))
            for item in detail.get("routes_preview", [])
            if isinstance(item, dict) and safe_str(item.get("route_url"))
        ]

    seen_raw_urls: set[str] = set()
    candidate_urls: list[str] = []
    for candidate in route_urls_raw:
        value = safe_str(candidate)
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            continue
        if value in seen_raw_urls:
            continue
        seen_raw_urls.add(value)
        candidate_urls.append(value)

    route_profile = load_route_url_profile(domain)
    hash_style = normalize_hash_style(route_profile.get("hash_style"))
    basepath_override = normalize_basepath(route_profile.get("basepath_override"))
    manual_lock = bool(route_profile.get("manual_lock"))

    route_urls = (
        rewrite_route_urls(candidate_urls, hash_style=hash_style, basepath_override=basepath_override)
        if manual_lock
        else candidate_urls
    )
    if not route_urls:
        raise ValueError("no route urls found for request capture")

    resolved_proxy_server = normalize_proxy_server(proxy_server)
    if not resolved_proxy_server:
        global_settings = get_global_settings()
        resolved_proxy_server = normalize_proxy_server(global_settings.get("proxy_server"))

    payload = {
        "domain": domain,
        "total": len(route_urls),
        "concurrency": max(1, int(concurrency)),
        "proxy_server": resolved_proxy_server,
        "hash_style": hash_style,
        "basepath_override": basepath_override,
        "manual_lock": manual_lock,
    }
    job = create_job(step=module2_request_capture_job_step, payload=payload)
    job_id = safe_str(job.get("job_id"))
    if not job_id:
        raise ValueError("failed to create module2 request capture job")

    append_log(job_id, f"web action queued: {module2_request_capture_job_step}")
    job = update_job(
        job_id=job_id,
        status="queued",
        result={
            "domain": domain,
            "concurrency": max(1, int(concurrency)),
            "proxy_server": resolved_proxy_server,
            "hash_style": hash_style,
            "basepath_override": basepath_override,
            "manual_lock": manual_lock,
            "stop_requested": False,
            "progress": {
                "done": 0,
                "total": len(route_urls),
                "visited_route_count": 0,
                "failed_route_count": 0,
                "request_total": 0,
            },
        },
    )
    on_queued(job_id, domain)
    spawn_background(
        run_background,
        job_id=job_id,
        domain=domain,
        route_urls=route_urls,
        concurrency=max(1, int(concurrency)),
        proxy_server=resolved_proxy_server,
        preferred_hash_style=hash_style,
        preferred_basepath_override=basepath_override,
        manual_lock=manual_lock,
    )
    return job


def queue_project_sync(
    *,
    target_url: str,
    source: str,
    concurrency: int,
    detect_routes: bool,
    detect_js: bool,
    detect_request: bool,
    upsert_project_from_url: Callable[..., dict[str, Any]],
    safe_str: Callable[[Any, str], str],
    normalize_proxy_server: Callable[[Any], str],
    get_global_settings: Callable[[], dict[str, Any]],
    create_job: Callable[..., dict[str, Any]],
    append_log: Callable[[str, str], None],
    update_job: Callable[..., dict[str, Any]],
    module2_sync_job_step: str,
    on_queued: Callable[[dict[str, Any], str, dict[str, Any]], None],
    spawn_background: Callable[..., None],
    run_background: Callable[..., Any],
    proxy_server: str = "",
    auto_scan_pattern: str = "",
    task_id: str | None = None,
    auto_pipeline: bool = False,
    project_title: str = "",
    resolve_title: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    # 项目同步既要创建项目，也要排队后台任务，这里统一编排，避免 app.py 混杂业务细节。
    project = upsert_project_from_url(
        url=target_url,
        source=source,
        task_id=safe_str(task_id) or None,
        title=safe_str(project_title) or None,
        resolve_title=bool(resolve_title),
    )
    selected_domain = safe_str(project.get("domain"))
    scan_pattern = safe_str(auto_scan_pattern)
    resolved_proxy_server = normalize_proxy_server(proxy_server)
    if not resolved_proxy_server:
        global_settings = get_global_settings()
        resolved_proxy_server = normalize_proxy_server(global_settings.get("proxy_server"))

    payload = {
        "domain": selected_domain,
        "target_url": safe_str(target_url),
        "concurrency": max(1, int(concurrency)),
        "proxy_server": resolved_proxy_server,
        "detect_routes": bool(detect_routes),
        "detect_js": bool(detect_js),
        "detect_request": bool(detect_request),
        "auto_scan_pattern": scan_pattern,
        "auto_pipeline": bool(auto_pipeline),
    }
    job = create_job(step=module2_sync_job_step, payload=payload)
    job_id = safe_str(job.get("job_id"))
    if not job_id:
        raise ValueError("failed to create module2 sync job")

    append_log(job_id, f"web action queued: {module2_sync_job_step}")
    queued_result = {
        "domain": selected_domain,
        "target_url": safe_str(target_url),
        "concurrency": max(1, int(concurrency)),
        "proxy_server": resolved_proxy_server,
        "detect_routes": bool(detect_routes),
        "detect_js": bool(detect_js),
        "detect_request": bool(detect_request),
        "auto_scan": bool(scan_pattern),
        "auto_pipeline": bool(auto_pipeline),
        "stop_requested": False,
        "progress": {"phase": "queued", "stop_requested": False},
    }
    job = update_job(job_id=job_id, status="queued", result=queued_result)
    on_queued(project, job_id, payload)
    spawn_background(
        run_background,
        job_id=job_id,
        target_url=target_url,
        concurrency=max(1, int(concurrency)),
        proxy_server=resolved_proxy_server,
        detect_routes=bool(detect_routes),
        detect_js=bool(detect_js),
        detect_request=bool(detect_request),
        auto_scan_pattern=scan_pattern,
        auto_pipeline=bool(auto_pipeline),
    )
    return project, job
