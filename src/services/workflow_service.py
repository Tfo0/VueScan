from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from config import PROJECTS_DIR
from src.vue_api.extractor import (
    extract_endpoints_from_all_chunks,
    load_extracted_endpoints,
)
from src.vue_api.models import ApiEndpoint
from src.vue_api.requester import append_query_to_url, compose_request_url, is_http_url, request_endpoint, save_call_result
from src.vue_chunk.browser_init import initialize_browser
from src.vue_chunk.chunk_download import download_js
from src.vue_chunk.request_capture import (
    capture_route_requests,
    normalize_basepath,
    normalize_hash_style,
    probe_route_hash_style,
    rewrite_route_urls,
)
from src.vue_chunk.route_extractor import extract_routes
from src.vue_detection.detector import run_batch_vue_detection


def _parse_domain(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"invalid url: {url}")
    if not parsed.hostname:
        raise ValueError(f"cannot resolve hostname from url: {url}")
    return parsed.hostname


def _build_request_url(baseurl: str, baseapi: str, endpoint: ApiEndpoint) -> str:
    raw_path = (endpoint.path or endpoint.url or "").strip()
    if raw_path.startswith(("http://", "https://")):
        return raw_path

    normalized_baseurl = (baseurl or "").strip().rstrip("/")
    normalized_baseapi = (baseapi or "").strip().strip("/")
    normalized_path = raw_path.lstrip("/")

    if normalized_baseapi:
        target = f"{normalized_baseapi}/{normalized_path}" if normalized_path else normalized_baseapi
    else:
        target = normalized_path

    if normalized_baseurl:
        return f"{normalized_baseurl}/{target}" if target else normalized_baseurl
    return f"/{target}" if target else raw_path


def _load_urls_from_file(file_path: str) -> list[str]:
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"urls file not found: {file_path}")
    urls = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not urls:
        raise ValueError(f"urls file is empty: {file_path}")
    return urls


def run_detect(
    input_path: str,
    output_html: str | None = None,
    concurrency: int = 5,
    timeout: int = 20,
    wait_ms: int = 1800,
    detect_limit: int | None = None,
    progress_callback=None,
    stop_check=None,
    pause_check=None,
) -> dict:
    txt_path, html_path, summary = run_batch_vue_detection(
        input_path=input_path,
        output_html=output_html,
        workers=concurrency,
        timeout=timeout,
        wait_ms=wait_ms,
        url_limit=detect_limit,
        progress_callback=progress_callback,
        stop_check=stop_check,
        pause_check=pause_check,
    )
    return {
        "txt_path": txt_path,
        "html_path": html_path,
        "summary": summary,
    }


async def run_chunk_download(
    target_url: str | None = None,
    urls_list: str | None = None,
    concurrency: int = 5,
) -> dict:
    if not target_url and not urls_list:
        raise ValueError("target_url or urls_list is required")

    if target_url:
        main_domain = _parse_domain(target_url)
        playwright, _browser, _context, page = await initialize_browser()
        try:
            full_urls = await extract_routes(page, main_domain, target_url)
            await download_js(page, full_urls, main_domain, concurrency)
        finally:
            await playwright.stop()
    else:
        full_urls = _load_urls_from_file(urls_list or "")
        main_domain = _parse_domain(full_urls[0])
        playwright, _browser, _context, page = await initialize_browser()
        try:
            await download_js(page, full_urls, main_domain, concurrency)
        finally:
            await playwright.stop()

    return {
        "domain": main_domain,
        "url_count": len(full_urls),
        "project_dir": str(PROJECTS_DIR / main_domain),
        "routes_file": str(PROJECTS_DIR / main_domain / "vueRouter" / "routes.json"),
        "urls_file": str(PROJECTS_DIR / main_domain / "vueRouter" / "urls.txt"),
        "js_file": str(PROJECTS_DIR / main_domain / "vueRouter" / "js.txt"),
    }


async def run_project_sync(
    target_url: str,
    concurrency: int = 5,
    detect_routes: bool = True,
    detect_js: bool = True,
    detect_request: bool = False,
    proxy_server: str = "",
    stop_check=None,
    pause_check=None,
) -> dict:
    if not target_url:
        raise ValueError("target_url is required")

    main_domain = _parse_domain(target_url)
    playwright, browser, context, page = await initialize_browser(proxy_server=proxy_server)
    full_urls: list[str] = []
    should_detect_js = bool(detect_js)
    should_detect_request = bool(detect_request)

    async def _wait_if_paused() -> None:
        while callable(pause_check) and bool(pause_check()):
            if callable(stop_check) and bool(stop_check()):
                raise RuntimeError("sync stopped")
            await asyncio.sleep(0.25)

    async def _check_stop() -> None:
        if callable(stop_check) and bool(stop_check()):
            raise RuntimeError("sync stopped")

    try:
        await _wait_if_paused()
        await _check_stop()
        if detect_routes:
            full_urls = await extract_routes(page, main_domain, target_url)
            if not full_urls:
                full_urls = [target_url]
                router_dir = PROJECTS_DIR / main_domain / "vueRouter"
                router_dir.mkdir(parents=True, exist_ok=True)
                (router_dir / "urls.txt").write_text("\n".join(full_urls), encoding="utf-8")
        else:
            full_urls = [target_url]
            router_dir = PROJECTS_DIR / main_domain / "vueRouter"
            router_dir.mkdir(parents=True, exist_ok=True)
            (router_dir / "urls.txt").write_text("\n".join(full_urls), encoding="utf-8")

        await _wait_if_paused()
        await _check_stop()
        # When request capture is enabled, JS/chunk mapping is collected
        # in request-capture phase together with API mapping to avoid double traversal.
        if should_detect_js and (not should_detect_request):
            await download_js(
                page,
                full_urls,
                main_domain,
                concurrency,
                download_files=False,
            )
    finally:
        try:
            await context.close()
        except Exception:
            pass
        try:
            await browser.close()
        except Exception:
            pass
        try:
            await playwright.stop()
        except Exception:
            pass

    return {
        "domain": main_domain,
        "target_url": target_url,
        "url_count": len(full_urls),
        "detect_routes": bool(detect_routes),
        "detect_js": bool(should_detect_js),
        "detect_request": bool(should_detect_request),
        "project_dir": str(PROJECTS_DIR / main_domain),
        "routes_file": str(PROJECTS_DIR / main_domain / "vueRouter" / "routes.json"),
        "urls_file": str(PROJECTS_DIR / main_domain / "vueRouter" / "urls.txt"),
        "js_file": str(PROJECTS_DIR / main_domain / "vueRouter" / "js.txt"),
    }


async def run_route_request_capture(
    *,
    domain: str,
    route_urls: list[str],
    concurrency: int = 8,
    hash_style: str = "slash",
    basepath_override: str = "",
    proxy_server: str = "",
    progress_callback=None,
    stop_check=None,
    pause_check=None,
) -> dict:
    target_domain = _parse_domain(f"https://{domain}") if domain and "://" not in domain else _parse_domain(domain)
    style = normalize_hash_style(hash_style)
    basepath = normalize_basepath(basepath_override)
    urls = rewrite_route_urls(route_urls, hash_style=style, basepath_override=basepath)
    if not urls:
        raise ValueError("no route urls found")
    return await capture_route_requests(
        domain=target_domain,
        route_urls=urls,
        concurrency=max(1, int(concurrency)),
        hash_style=style,
        basepath_override=basepath,
        proxy_server=proxy_server,
        progress_callback=progress_callback,
        stop_check=stop_check,
        pause_check=pause_check,
    )


async def run_route_hash_style_probe(
    *,
    route_urls: list[str],
    sample_size: int = 5,
    basepath_override: str = "",
    preferred_style: str = "slash",
    proxy_server: str = "",
) -> dict:
    return await probe_route_hash_style(
        route_urls=route_urls,
        sample_size=max(1, int(sample_size)),
        basepath_override=normalize_basepath(basepath_override),
        preferred_style=normalize_hash_style(preferred_style),
        proxy_server=proxy_server,
    )


def run_api_extract(domain: str, pattern: str, baseurl: str, baseapi: str) -> dict:
    endpoints = extract_endpoints_from_all_chunks(
        domain=domain,
        pattern=pattern,
        baseurl=baseurl,
        baseapi=baseapi,
    )
    output_path = PROJECTS_DIR / domain / "vueApi" / "endpoints.json"
    return {
        "domain": domain,
        "endpoint_count": len(endpoints),
        "output_path": str(output_path),
    }


def load_api_endpoints(domain: str) -> list[ApiEndpoint]:
    return load_extracted_endpoints(domain)


def run_api_request(
    domain: str,
    api_id: int,
    method: str | None = None,
    baseurl: str = "",
    baseapi: str = "",
    base_query: str = "",
    json_body: object | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
    request_url_override: str | None = None,
    body_text: str | None = None,
    content_type: str | None = None,
) -> dict:
    endpoints = load_extracted_endpoints(domain)
    endpoint = next((item for item in endpoints if item.id == api_id), None)
    if endpoint is None:
        raise ValueError(f"api id not found: {api_id}")

    override_url = str(request_url_override or "").strip()
    if override_url:
        if is_http_url(override_url):
            request_url = override_url
        else:
            request_url = compose_request_url(baseurl, "", override_url)
    else:
        request_url = _build_request_url(baseurl=baseurl, baseapi=baseapi, endpoint=endpoint)
    request_url = append_query_to_url(request_url, base_query)
    if not is_http_url(request_url):
        raise ValueError("request url is relative; please infer or fill baseurl before sending request")
    request_endpoint_model = ApiEndpoint(
        id=endpoint.id,
        method=endpoint.method,
        path=endpoint.path,
        url=request_url,
        source_file=endpoint.source_file,
        source_line=endpoint.source_line,
        match_text=endpoint.match_text,
    )

    result = request_endpoint(
        endpoint=request_endpoint_model,
        method=method,
        json_body=json_body,
        headers=headers,
        timeout=timeout,
        body_text=body_text,
        content_type=content_type,
    )
    response_path = save_call_result(domain=domain, result=result)

    return {
        "domain": domain,
        "api_id": endpoint.id,
        "method": result.method,
        "url": result.url,
        "baseurl": baseurl,
        "baseapi": baseapi,
        "base_query": base_query,
        "status_code": result.status_code,
        "ok": result.ok,
        "elapsed_ms": result.elapsed_ms,
        "error": result.error,
        "response_path": str(response_path),
        "request_url_override": override_url,
    }
