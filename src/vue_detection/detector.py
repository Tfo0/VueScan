import asyncio
import re
from collections import Counter
from html import escape
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from config import PLUGIN_DIR, VD_OUTPUT_DIR
from src.vue_detection.browser_init import initialize_vd_browser
from util.html_to_txt import collect_hrefs
from util.xlsx_to_urls import collect_urls


SUPPORTED_INPUT_EXTS = {".xlsx", ".xlsm", ".txt", ".html", ".htm"}
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
GREEN = "\033[32m"
RESET = "\033[0m"

VD_EVAL_SCRIPT = """
() => {
  const fallbackDetect = () => {
    const app = document.querySelector("#app");
    const hasRuntime = !!(
      window.__VUE__ ||
      window.Vue ||
      window.__VUE_DEVTOOLS_GLOBAL_HOOK__ ||
      (app && (app.__vue_app__ || app.__vue__ || app._vnode))
    );
    const hasScopedDom = !!document.querySelector("[data-v-]");
    const method = hasRuntime ? "runtime_fallback" : (hasScopedDom ? "dom_fallback" : "none");
    return {
      vueDetected: hasRuntime || hasScopedDom,
      method,
      href: location.href,
      title: document.title || "",
      routeCount: 0
    };
  };

  try {
    if (typeof window.__VD_DETECT__ === "function") {
      const result = window.__VD_DETECT__();
      if (result && typeof result === "object") {
        return result;
      }
    }
  } catch (e) {
    // Ignore detector script errors and continue with fallback.
  }

  return fallbackDetect();
}
"""


def _sanitize_url(value: str) -> str | None:
    candidate = (value or "").strip()
    if not candidate:
        return None

    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None

    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.strip(),
            parsed.path or "",
            parsed.query or "",
            parsed.fragment or "",
        )
    )


def _extract_urls_from_txt(file_path: Path) -> tuple[list[str], int]:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    values = [match.group(0) for match in URL_RE.finditer(text)]
    return values, len(values)


def _iter_input_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() not in SUPPORTED_INPUT_EXTS:
            raise ValueError(f"Unsupported file type: {input_path}")
        return [input_path]

    if not input_path.is_dir():
        raise FileNotFoundError(f"Input path not found: {input_path}")

    files = sorted(
        [p for p in input_path.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_INPUT_EXTS]
    )
    if not files:
        raise FileNotFoundError(f"No supported input file found in: {input_path}")
    return files


def _collect_input_urls(input_path: str, url_limit: int | None = None) -> tuple[list[str], dict]:
    files = _iter_input_files(Path(input_path))
    seen: set[str] = set()
    urls: list[str] = []
    raw_candidates = 0

    for file_path in files:
        suffix = file_path.suffix.lower()
        if suffix in {".xlsx", ".xlsm"}:
            raw_values, parsed_count = collect_urls(file_path, limit=None)
            raw_candidates += parsed_count
        elif suffix in {".html", ".htm"}:
            raw_values, parsed_count = collect_hrefs(file_path, limit=None, http_only=True)
            raw_candidates += parsed_count
        else:
            raw_values, parsed_count = _extract_urls_from_txt(file_path)
            raw_candidates += parsed_count

        for raw_value in raw_values:
            normalized = _sanitize_url(raw_value)
            if not normalized:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            urls.append(normalized)
            if url_limit is not None and len(urls) >= url_limit:
                return urls, {"input_files": len(files), "raw_candidates": raw_candidates}

    return urls, {"input_files": len(files), "raw_candidates": raw_candidates}


def _resolve_output_paths(output_html: str | None) -> tuple[Path, Path]:
    if output_html is None:
        output_dir = VD_OUTPUT_DIR
    else:
        output_path = Path(output_html)
        if output_path.suffix.lower() in {".html", ".htm", ".txt"}:
            output_dir = output_path.parent
        else:
            output_dir = output_path

    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / "url_vue.txt", output_dir / "url_vue.html"


def _to_non_negative_int(raw: object, default: int = 0) -> int:
    try:
        value = int(raw)
    except Exception:
        return max(0, int(default))
    return max(0, value)


async def _goto_with_retry(page, url: str, timeout_ms: int, max_attempts: int = 2) -> None:
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            return
        except Exception as exc:
            last_error = exc
            if attempt < max_attempts:
                await page.wait_for_timeout(400 * attempt)
    raise last_error


async def _detect_vue_single(page, url: str, timeout_sec: int, wait_ms: int) -> dict:
    timeout_ms = timeout_sec * 1000
    result = {
        "url": url,
        "final_url": url,
        "title": "",
        "is_vue": False,
        "method": "none",
        "route_count": 0,
        "error": "",
    }

    try:
        await _goto_with_retry(page, url, timeout_ms=timeout_ms, max_attempts=2)
        result["final_url"] = page.url or url

        try:
            await page.wait_for_load_state("networkidle", timeout=min(max(timeout_ms, 3000), 9000))
        except PlaywrightTimeoutError:
            pass

        if wait_ms > 0:
            await page.wait_for_timeout(wait_ms)

        def apply_payload(payload: dict) -> None:
            result["is_vue"] = bool(payload.get("vueDetected"))
            result["method"] = str(payload.get("method") or "unknown")
            result["title"] = str(payload.get("title") or "")
            result["final_url"] = str(payload.get("href") or page.url or url)
            result["route_count"] = _to_non_negative_int(
                payload.get("routeCount", payload.get("route_count", 0)),
                default=0,
            )

        detect_payload = await page.evaluate(VD_EVAL_SCRIPT)
        if isinstance(detect_payload, dict):
            apply_payload(detect_payload)
            if result["is_vue"] and result["route_count"] <= 0:
                try:
                    await page.wait_for_timeout(1200)
                    second_payload = await page.evaluate(VD_EVAL_SCRIPT)
                    if isinstance(second_payload, dict):
                        second_count = _to_non_negative_int(
                            second_payload.get("routeCount", second_payload.get("route_count", 0)),
                            default=0,
                        )
                        if second_count > result["route_count"]:
                            apply_payload(second_payload)
                except Exception:
                    pass
        else:
            result["error"] = "Unexpected detector payload."
    except Exception as exc:
        result["error"] = str(exc)

    return result


async def _run_detection_async(
    urls: list[str],
    workers: int,
    timeout: int,
    wait_ms: int,
    headless: bool,
    progress_callback=None,
    stop_check=None,
    pause_check=None,
) -> list[dict]:
    playwright, browser, context = await initialize_vd_browser(headless=headless)

    detector_script_path = PLUGIN_DIR / "core" / "vd_detect.js"
    if detector_script_path.is_file():
        context_script = detector_script_path.read_text(encoding="utf-8")
        await context.add_init_script(script=context_script)

    worker_count = max(1, min(int(workers), len(urls)))
    pages = [await context.new_page() for _ in range(worker_count)]
    queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()
    for idx, url in enumerate(urls):
        queue.put_nowait((idx, url))

    results: list[dict | None] = [None] * len(urls)
    print_lock = asyncio.Lock()
    progress = {"done": 0, "total": len(urls)}

    def _is_stop_requested() -> bool:
        if not callable(stop_check):
            return False
        try:
            return bool(stop_check())
        except Exception:
            return False

    async def _wait_if_paused() -> None:
        while callable(pause_check):
            paused = False
            try:
                paused = bool(pause_check())
            except Exception:
                paused = False
            if not paused:
                return
            if _is_stop_requested():
                raise RuntimeError("detection stopped")
            await asyncio.sleep(0.25)

    async def worker_loop(page) -> None:
        while True:
            await _wait_if_paused()
            if _is_stop_requested():
                raise RuntimeError("detection stopped")
            try:
                idx, target_url = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            try:
                await _wait_if_paused()
                if _is_stop_requested():
                    raise RuntimeError("detection stopped")
                result = await _detect_vue_single(
                    page=page,
                    url=target_url,
                    timeout_sec=timeout,
                    wait_ms=wait_ms,
                )
                results[idx] = result
                async with print_lock:
                    progress["done"] += 1
                    print(
                        _format_realtime_line(result, progress["done"], progress["total"]),
                        flush=True,
                    )
                    if callable(progress_callback):
                        try:
                            progress_callback(dict(result), int(progress["done"]), int(progress["total"]))
                        except Exception:
                            pass
            finally:
                queue.task_done()

    try:
        await asyncio.gather(*(worker_loop(page) for page in pages))
        await queue.join()
    finally:
        for page in pages:
            try:
                await page.close()
            except Exception:
                pass

        await context.close()
        await browser.close()
        await playwright.stop()

    return [item for item in results if item is not None]


def _write_vue_txt(vue_urls: list[str], output_txt: Path) -> None:
    output_txt.write_text("\n".join(vue_urls), encoding="utf-8")


def _write_vue_html(vue_urls: list[str], output_html: Path, summary: dict) -> None:
    rows = []
    for url in vue_urls:
        safe_url = escape(url)
        rows.append(
            f'<li><a href="{safe_url}" target="_blank" rel="noopener noreferrer">{safe_url}</a></li>'
        )

    body_rows = "\n".join(rows) if rows else "<li>(No Vue site detected)</li>"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Vue Detection Result</title>
  <style>
    body {{ font-family: Consolas, 'Courier New', monospace; margin: 24px; line-height: 1.6; }}
    h1 {{ margin: 0 0 8px; }}
    .meta {{ color: #333; margin-bottom: 16px; }}
    a {{ color: #005fcc; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <h1>Vue Sites</h1>
  <div class="meta">Total URLs: {summary['total_urls']} | Vue URLs: {summary['vue_sites']} | Failed: {summary['failed_sites']}</div>
  <ul>
    {body_rows}
  </ul>
</body>
</html>
"""
    output_html.write_text(html, encoding="utf-8")


def _format_realtime_line(item: dict, done: int, total: int) -> str:
    display_url = str(item.get("final_url") or item.get("url") or "").strip()
    if not display_url:
        display_url = "<empty-url>"

    prefix = f"[{done}/{total}] "
    if bool(item.get("is_vue")):
        route_count = _to_non_negative_int(item.get("route_count"), default=0)
        return f"{GREEN}{prefix}{display_url} 检测到vue框架 | 路由:{route_count}{RESET}"
    if item.get("error"):
        return f"{prefix}{display_url} 检测失败: {item['error']}"
    return f"{prefix}{display_url} 不是vue框架"


def run_batch_vue_detection(
    input_path: str,
    output_html: str | None = None,
    workers: int = 5,
    timeout: int = 20,
    wait_ms: int = 1800,
    url_limit: int | None = None,
    headless: bool = True,
    progress_callback=None,
    stop_check=None,
    pause_check=None,
) -> tuple[str, str, dict]:
    if workers < 1:
        raise ValueError("workers must be >= 1.")
    if timeout < 1:
        raise ValueError("timeout must be >= 1.")
    if wait_ms < 0:
        raise ValueError("wait_ms must be >= 0.")
    if url_limit is not None and url_limit < 1:
        raise ValueError("url_limit must be >= 1.")

    urls, input_summary = _collect_input_urls(input_path=input_path, url_limit=url_limit)
    if not urls:
        raise ValueError("No valid URL extracted from input.")

    results = asyncio.run(
        _run_detection_async(
            urls=urls,
            workers=workers,
            timeout=timeout,
            wait_ms=wait_ms,
            headless=headless,
            progress_callback=progress_callback,
            stop_check=stop_check,
            pause_check=pause_check,
        )
    )

    vue_item_map: dict[str, dict] = {}
    method_counter: Counter[str] = Counter()
    failed_sites = 0

    for item in results:
        if item["error"]:
            failed_sites += 1

        method_counter[str(item["method"])] += 1
        if not item["is_vue"]:
            continue

        output_url = str(item["final_url"] or item["url"]).strip()
        if not output_url:
            continue
        route_count = _to_non_negative_int(item.get("route_count"), default=0)
        title = str(item.get("title") or "").strip()
        existed = vue_item_map.get(output_url)
        if existed is None:
            vue_item_map[output_url] = {
                "url": output_url,
                "title": title,
                "route_count": route_count,
            }
            continue

        # Keep the richer row when the same final URL appears multiple times.
        if route_count > _to_non_negative_int(existed.get("route_count"), default=0):
            existed["route_count"] = route_count
        if not existed.get("title") and title:
            existed["title"] = title

    vue_items = sorted(
        list(vue_item_map.values()),
        key=lambda item: (
            -_to_non_negative_int(item.get("route_count"), default=0),
            str(item.get("url") or ""),
        ),
    )
    vue_urls = [str(item.get("url") or "").strip() for item in vue_items if str(item.get("url") or "").strip()]

    txt_path, html_path = _resolve_output_paths(output_html=output_html)
    _write_vue_txt(vue_urls, txt_path)

    summary = {
        "input_files": input_summary["input_files"],
        "raw_candidates": input_summary["raw_candidates"],
        "total_urls": len(results),
        "vue_sites": len(vue_urls),
        "non_vue_sites": max(0, len(results) - len(vue_urls)),
        "failed_sites": failed_sites,
        "methods": dict(method_counter),
        "vue_items": vue_items,
    }
    _write_vue_html(vue_urls, html_path, summary)
    return str(txt_path), str(html_path), summary
