import asyncio
import hashlib
import json
import os
import re
from collections import defaultdict
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from config import PROJECTS_DIR


def _normalize_script_url(url):
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", ""))


def _strip_fragment(url):
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def _is_script_response(response):
    request = response.request
    if request.resource_type == "script":
        return True

    path = urlsplit(response.url).path.lower()
    if path.endswith(".js"):
        return True

    content_type = response.headers.get("content-type", "").lower()
    return "javascript" in content_type


def _build_script_file_name(script_url):
    parsed = urlsplit(script_url)
    basename = os.path.basename(parsed.path) or "script.js"
    if not basename.lower().endswith(".js"):
        basename = f"{basename}.js"

    safe_basename = re.sub(r"[^A-Za-z0-9._-]", "_", basename)
    digest = hashlib.sha1(script_url.encode("utf-8")).hexdigest()[:10]
    return f"{digest}_{safe_basename}"


def _dedupe_urls(urls):
    seen = set()
    result = []
    for raw in urls:
        url = (raw or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        result.append(url)
    return result


def _build_navigation_candidates(url):
    raw = str(url or "").strip()
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return [raw] if raw else []

    candidates = []
    seen = set()

    def add(item):
        token = str(item or "").strip()
        if not token or token in seen:
            return
        seen.add(token)
        candidates.append(token)

    add(raw)

    path = parsed.path or "/"
    if path and path != "/":
        trimmed = path.rstrip("/")
        if trimmed and trimmed != path:
            add(urlunsplit((parsed.scheme, parsed.netloc, trimmed, parsed.query, parsed.fragment)))
        if not path.endswith("/"):
            add(urlunsplit((parsed.scheme, parsed.netloc, f"{path}/", parsed.query, parsed.fragment)))

    swapped_scheme = "http" if parsed.scheme.lower() == "https" else "https"
    add(urlunsplit((swapped_scheme, parsed.netloc, parsed.path or "/", parsed.query, parsed.fragment)))
    return candidates


async def download_js(page, full_urls, main_domain, concurrency, download_files=True):
    vue_router_dir = os.path.join(str(PROJECTS_DIR), main_domain, "vueRouter")
    down_chunk_dir = os.path.join(str(PROJECTS_DIR), main_domain, "downChunk")
    os.makedirs(vue_router_dir, exist_ok=True)
    os.makedirs(down_chunk_dir, exist_ok=True)

    target_urls = _dedupe_urls(full_urls)
    if not target_urls:
        print("No URLs to process.")
        return

    worker_count = max(1, min(int(concurrency), len(target_urls)))

    route_to_scripts = defaultdict(set)
    script_records = {}
    failed_routes = {}
    state_lock = asyncio.Lock()

    async def capture_script(response, route_url, context_request):
        if not _is_script_response(response):
            return False

        script_url = _normalize_script_url(_strip_fragment(response.url))
        file_name = _build_script_file_name(script_url)
        file_path = os.path.join(down_chunk_dir, file_name)

        async with state_lock:
            route_to_scripts[route_url].add(script_url)

            record = script_records.get(script_url)
            if record is None:
                record = {
                    "url": script_url,
                    "file_name": file_name,
                    "status": "pending",
                    "error": "",
                    "source_routes": set(),
                }
                script_records[script_url] = record

            record["source_routes"].add(route_url)

            if record["status"] in {"done", "captured"}:
                return True

            if record["status"] == "downloading":
                return True

            if not download_files:
                record["status"] = "captured"
                record["error"] = ""
                return True

            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                record["status"] = "done"
                print(f"Already exists, skip: {file_path}")
                return True

            record["status"] = "downloading"

        try:
            body = await response.body()
            if not body:
                raise ValueError("empty response body")

            with open(file_path, "wb") as f:
                f.write(body)

            async with state_lock:
                record["status"] = "done"
                record["error"] = ""
            print(f"Downloaded: {file_path}")
            return True
        except Exception as body_error:
            body_error_msg = str(body_error)

        try:
            fallback_resp = await context_request.get(script_url, timeout=30000)
            if not fallback_resp.ok:
                raise ValueError(f"fallback status {fallback_resp.status}")

            fallback_body = await fallback_resp.body()
            if not fallback_body:
                raise ValueError("empty fallback body")

            with open(file_path, "wb") as f:
                f.write(fallback_body)

            async with state_lock:
                record["status"] = "done"
                record["error"] = ""
            print(f"Downloaded: {file_path}")
            return True
        except Exception as fallback_error:
            async with state_lock:
                record["status"] = "failed"
                record["error"] = f"{body_error_msg}; fallback={fallback_error}"
            print(f"Download failed: {script_url} -> {record['error']}")
            return True

    async def goto_with_retry(worker_page, url, max_attempts=2):
        last_error = None
        candidates = _build_navigation_candidates(url)
        wait_modes = ("domcontentloaded", "commit")
        for candidate in candidates:
            for wait_mode in wait_modes:
                for attempt in range(1, max_attempts + 1):
                    try:
                        await worker_page.goto(candidate, wait_until=wait_mode, timeout=90000)
                        return
                    except Exception as e:
                        last_error = e
                        if attempt < max_attempts:
                            await worker_page.wait_for_timeout(700 * attempt)
        raise last_error

    async def process_url(worker_id, worker_page, url):
        pending_tasks = set()
        active_route = {"url": url}
        loop = asyncio.get_running_loop()
        route_state = {
            "script_seen": False,
            "last_script_at": loop.time(),
        }

        async def schedule_capture(response):
            route_url = active_route.get("url")
            if not route_url:
                return

            is_script = await capture_script(response, route_url, worker_page.context.request)
            if is_script:
                route_state["script_seen"] = True
                route_state["last_script_at"] = loop.time()

        def handle_response(response):
            task = asyncio.create_task(schedule_capture(response))
            pending_tasks.add(task)
            task.add_done_callback(lambda done_task: pending_tasks.discard(done_task))

        async def wait_route_settled(min_wait_ms=800, quiet_ms=1000, max_wait_ms=12000):
            start = loop.time()
            min_wait_s = min_wait_ms / 1000
            quiet_s = quiet_ms / 1000
            max_wait_s = max_wait_ms / 1000

            while True:
                now = loop.time()
                elapsed = now - start
                quiet_elapsed = now - route_state["last_script_at"]
                no_pending = len(pending_tasks) == 0

                if elapsed >= max_wait_s:
                    return

                if route_state["script_seen"] and no_pending and elapsed >= min_wait_s and quiet_elapsed >= quiet_s:
                    return

                # In case page has no script requests at all.
                if (not route_state["script_seen"]) and no_pending and elapsed >= (min_wait_s + quiet_s):
                    return

                await worker_page.wait_for_timeout(180)

        worker_page.on("response", handle_response)
        try:
            print(f"[worker-{worker_id}] Visit: {url}")
            await goto_with_retry(worker_page, url, max_attempts=2)
            try:
                await worker_page.wait_for_load_state("networkidle", timeout=9000)
            except PlaywrightTimeoutError:
                pass

            await wait_route_settled(min_wait_ms=800, quiet_ms=1000, max_wait_ms=12000)
        except Exception as e:
            failed_routes[url] = str(e)
            print(f"Visit failed: {url} -> {e}")
        finally:
            active_route["url"] = None
            if pending_tasks:
                await asyncio.gather(*list(pending_tasks), return_exceptions=True)
            worker_page.remove_listener("response", handle_response)

    context = page.context
    worker_pages = [page]
    for _ in range(worker_count - 1):
        worker_pages.append(await context.new_page())

    queue = asyncio.Queue()
    for url in target_urls:
        queue.put_nowait(url)

    async def worker_loop(worker_id, worker_page):
        while True:
            try:
                url = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            try:
                await process_url(worker_id, worker_page, url)
            finally:
                queue.task_done()

    try:
        await asyncio.gather(
            *(worker_loop(idx + 1, worker_page) for idx, worker_page in enumerate(worker_pages))
        )
        await queue.join()
    finally:
        for extra_page in worker_pages[1:]:
            try:
                await extra_page.close()
            except Exception:
                pass

    saved_scripts = sorted(
        [
            script_url
            for script_url, record in script_records.items()
            if record["status"] in {"done", "captured"}
        ]
    )
    downloaded_scripts = sorted(
        [script_url for script_url, record in script_records.items() if record["status"] == "done"]
    )

    print("\033[1m\033[32m=== Captured JS List ===\033[0m")
    for idx, script_url in enumerate(saved_scripts, 1):
        print(f"{idx}. {script_url}")

    js_file = os.path.join(vue_router_dir, "js.txt")
    with open(js_file, "w", encoding="utf-8") as f:
        f.write("\n".join(saved_scripts))
    print(f"\033[36mJS list saved: {js_file}\033[0m")

    log_entries = []
    for url in target_urls:
        log_entries.append(f"--- {url} ---")
        scripts = sorted(route_to_scripts.get(url, set()))
        if scripts:
            for script_url in scripts:
                log_entries.append(f"  - {script_url}")
        else:
            log_entries.append("  - (no script captured)")

    if failed_routes:
        log_entries.append("")
        log_entries.append("--- route_errors ---")
        for failed_url, err in sorted(failed_routes.items()):
            log_entries.append(f"  - {failed_url} => {err}")

    failed_scripts = sorted(
        [
            (script_url, record["error"])
            for script_url, record in script_records.items()
            if record["status"] == "failed"
        ]
    )
    if failed_scripts:
        log_entries.append("")
        log_entries.append("--- script_errors ---")
        for failed_script, err in failed_scripts:
            log_entries.append(f"  - {failed_script} => {err}")

    log_file = os.path.join(vue_router_dir, "download_log.txt")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("\n".join(log_entries))
    print(f"\033[36mLog saved: {log_file}\033[0m")

    manifest_file = os.path.join(vue_router_dir, "download_manifest.json")
    manifest = {
        "summary": {
            "target_url_count": len(target_urls),
            "captured_script_count": len(script_records),
            "downloaded_script_count": len(downloaded_scripts),
            "failed_script_count": len(failed_scripts),
            "failed_route_count": len(failed_routes),
        },
        "scripts": sorted(
            [
                {
                    "url": record["url"],
                    "file_name": record["file_name"],
                    "status": record["status"],
                    "source_routes": sorted(record["source_routes"]),
                    "error": record["error"],
                }
                for record in script_records.values()
            ],
            key=lambda item: item["url"],
        ),
    }
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"\033[36mManifest saved: {manifest_file}\033[0m")
