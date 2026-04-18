from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request as UrlRequest
from zipfile import ZIP_DEFLATED, ZipFile

from config import OUTPUTS_DIR, PROJECTS_DIR
from src.http_utils import safe_urlopen


WEB_EXPORT_DIR = OUTPUTS_DIR / "web_exports"


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _safe_file_token(value: str, default: str = "file") -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "_", _safe_str(value)).strip("._")
    return token or default


def _call_progress_callback(progress_callback, *args, **kwargs) -> None:
    if not progress_callback:
        return
    try:
        progress_callback(*args, **kwargs)
    except TypeError:
        progress_callback(*args)
    except Exception:
        pass


def _normalize_js_url_for_dedupe(raw_url: Any) -> str:
    value = _safe_str(raw_url)
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
    except Exception:
        return value
    scheme = _safe_str(parsed.scheme).lower()
    netloc = _safe_str(parsed.netloc).lower()
    path = _safe_str(parsed.path)
    if not path:
        path = "/"
    if scheme and netloc:
        return urlunsplit((scheme, netloc, path, "", ""))
    return value.split("?", 1)[0].strip()


def _dedupe_effective_js_urls(raw_urls: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in raw_urls:
        value = _safe_str(raw)
        if not value:
            continue
        key = _normalize_js_url_for_dedupe(value)
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _zip_entry_name_from_js_url(js_url: str, index: int) -> str:
    parsed = urlsplit(_safe_str(js_url))
    basename = Path(parsed.path).name or f"script_{index}.js"
    if not basename.lower().endswith(".js"):
        basename = f"{basename}.js"
    safe_basename = _safe_file_token(basename, default=f"script_{index}.js")
    digest = hashlib.sha1(_safe_str(js_url).encode("utf-8")).hexdigest()[:10]
    return f"{index:04d}_{digest}_{safe_basename}"


def _fetch_js_content(js_url: str, index: int) -> tuple[str, bytes]:
    request = UrlRequest(js_url, headers={"User-Agent": "Mozilla/5.0"})
    with safe_urlopen(request, timeout=30) as response:
        body = response.read()
    if not body:
        raise ValueError("empty response body")
    return _zip_entry_name_from_js_url(js_url, index), body


def _chunk_cache_file_name_from_js_url(js_url: str) -> str:
    parsed = urlsplit(_safe_str(js_url))
    basename = Path(parsed.path).name or "script.js"
    if not basename.lower().endswith(".js"):
        basename = f"{basename}.js"
    safe_basename = _safe_file_token(basename, default="script.js")
    normalized = _normalize_js_url_for_dedupe(js_url) or _safe_str(js_url)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    return f"{digest}_{safe_basename}"


def _fetch_js_bytes_for_cache(
    js_url: str,
    *,
    timeout: int = 30,
    max_bytes: int = 8 * 1024 * 1024,
) -> bytes:
    request = UrlRequest(js_url, headers={"User-Agent": "Mozilla/5.0"})
    with safe_urlopen(request, timeout=max(1, int(timeout))) as response:
        body = response.read(max_bytes + 1)
    if not body:
        raise ValueError("empty response body")
    if len(body) > max_bytes:
        raise ValueError(f"js too large ({len(body)} bytes)")
    return body


def cache_project_js_to_downchunk(
    domain: str,
    js_urls: list[str],
    *,
    concurrency: int = 24,
    progress_callback=None,
) -> dict[str, Any]:
    token = _safe_str(domain)
    if not token:
        raise ValueError("domain is required")

    normalized_urls = _dedupe_effective_js_urls(js_urls)
    total = len(normalized_urls)
    down_chunk_dir = PROJECTS_DIR / token / "downChunk"
    down_chunk_dir.mkdir(parents=True, exist_ok=True)

    if total <= 0:
        return {
            "total": 0,
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
            "concurrency": int(max(1, int(concurrency))),
        }

    downloaded = 0
    skipped = 0
    failed = 0
    done = 0
    success_map: dict[str, str] = {}
    failed_map: dict[str, str] = {}
    max_workers = max(1, min(int(concurrency), 32))

    def _worker(js_url: str) -> tuple[str, str, str, str]:
        file_name = _chunk_cache_file_name_from_js_url(js_url)
        file_path = down_chunk_dir / file_name
        try:
            if file_path.is_file() and file_path.stat().st_size > 0:
                return "skipped", js_url, file_name, ""
            body = _fetch_js_bytes_for_cache(js_url)
            file_path.write_bytes(body)
            return "downloaded", js_url, file_name, ""
        except Exception as exc:
            return "failed", js_url, file_name, str(exc)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_worker, js_url): js_url
            for js_url in normalized_urls
        }
        for future in as_completed(future_map):
            done += 1
            status, js_url, file_name, err = future.result()
            if status == "downloaded":
                downloaded += 1
                success_map[js_url] = file_name
            elif status == "skipped":
                skipped += 1
                success_map[js_url] = file_name
            else:
                failed += 1
                failed_map[js_url] = err

            _call_progress_callback(
                progress_callback,
                done,
                total,
                downloaded,
                skipped,
                failed,
                current_js_url=js_url,
                current_file_name=file_name,
                current_status=status,
            )

    manifest_file = PROJECTS_DIR / token / "vueRouter" / "download_manifest.json"
    if manifest_file.is_file():
        try:
            payload = json.loads(manifest_file.read_text(encoding="utf-8"))
            scripts = payload.get("scripts") if isinstance(payload, dict) else None
            if isinstance(scripts, list):
                success_norm = {
                    _normalize_js_url_for_dedupe(url): file_name
                    for url, file_name in success_map.items()
                    if _normalize_js_url_for_dedupe(url)
                }
                failed_norm = {
                    _normalize_js_url_for_dedupe(url): err
                    for url, err in failed_map.items()
                    if _normalize_js_url_for_dedupe(url)
                }
                for row in scripts:
                    if not isinstance(row, dict):
                        continue
                    row_url = _safe_str(row.get("url"))
                    row_key = _normalize_js_url_for_dedupe(row_url)
                    if not row_key:
                        continue
                    if row_key in success_norm:
                        row["status"] = "done"
                        row["file_name"] = _safe_str(success_norm[row_key])
                        row["error"] = ""
                    elif row_key in failed_norm and _safe_str(row.get("status")).lower() != "done":
                        row["status"] = "failed"
                        row["error"] = _safe_str(failed_norm[row_key])
                summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
                if not isinstance(summary, dict):
                    summary = {}
                summary["captured_script_count"] = len(scripts)
                summary["downloaded_script_count"] = len(
                    [row for row in scripts if isinstance(row, dict) and _safe_str(row.get("status")).lower() == "done"]
                )
                summary["failed_script_count"] = len(
                    [row for row in scripts if isinstance(row, dict) and _safe_str(row.get("status")).lower() == "failed"]
                )
                payload["summary"] = summary
                payload["scripts"] = scripts
                manifest_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    return {
        "total": int(total),
        "downloaded": int(downloaded),
        "skipped": int(skipped),
        "failed": int(failed),
        "concurrency": int(max_workers),
    }


def build_project_js_zip(
    domain: str,
    js_urls: list[str],
    *,
    concurrency: int = 24,
    progress_callback=None,
) -> tuple[Path, int, int]:
    safe_domain = _safe_file_token(domain, default="project")
    WEB_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    zip_path = WEB_EXPORT_DIR / f"{safe_domain}_captured_js_{stamp}.zip"

    normalized_urls: list[str] = []
    seen_urls: set[str] = set()
    for raw_url in js_urls:
        value = _safe_str(raw_url)
        if not value or value in seen_urls:
            continue
        seen_urls.add(value)
        normalized_urls.append(value)

    total_count = len(normalized_urls)
    if total_count <= 0:
        raise ValueError("no valid js urls for zip download")

    success_count = 0
    failures: list[str] = []
    done_count = 0
    max_workers = max(1, min(int(concurrency), 32))
    report_span = max(1, total_count // 20)

    with ZipFile(zip_path, mode="w", compression=ZIP_DEFLATED) as zf:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(_fetch_js_content, js_url, idx): (idx, js_url)
                for idx, js_url in enumerate(normalized_urls, start=1)
            }
            for future in as_completed(future_map):
                done_count += 1
                idx, js_url = future_map[future]
                current_status = "done"
                current_file_name = _zip_entry_name_from_js_url(js_url, idx)
                try:
                    entry_name, body = future.result()
                    zf.writestr(entry_name, body)
                    success_count += 1
                    current_file_name = entry_name
                except Exception as exc:
                    failures.append(f"{js_url} => {exc}")
                    current_status = "failed"

                if progress_callback and (
                    done_count == 1 or done_count == total_count or done_count % report_span == 0
                ):
                    _call_progress_callback(
                        progress_callback,
                        done_count,
                        total_count,
                        success_count,
                        len(failures),
                        current_js_url=js_url,
                        current_file_name=current_file_name,
                        current_status=current_status,
                    )

        if failures:
            zf.writestr("_download_errors.txt", "\n".join(failures))

    if success_count <= 0:
        try:
            zip_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise ValueError("all captured js download failed, no zip generated")

    return zip_path, success_count, len(failures)
