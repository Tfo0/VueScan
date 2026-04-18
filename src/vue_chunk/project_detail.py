from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from config import PROJECTS_DIR
from src.vue_api.request_analysis import analyze_request_run_snapshots
from src.vue_api.saved_results import load_saved_request_results
from src.vue_chunk.request_capture import (
    load_manual_request_items,
    normalize_basepath,
    normalize_hash_style,
    rewrite_route_url,
)
from src.vue_chunk.route_profile import load_route_url_profile


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _coerce_int(raw: Any, default: int, minimum: int = 0) -> int:
    text = _safe_text(raw)
    if not text:
        return max(default, minimum)
    try:
        value = int(text)
    except ValueError:
        return max(default, minimum)
    return max(value, minimum)


def _read_lines(path: Path, limit: int = 2000) -> list[str]:
    if not path.is_file():
        return []
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        value = line.strip()
        if not value:
            continue
        lines.append(value)
        if len(lines) >= max(1, int(limit)):
            break
    return lines


def _normalize_js_url_for_dedupe(raw_url: Any) -> str:
    value = _safe_text(raw_url)
    if not value:
        return ""

    parsed = urlsplit(value)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        path = parsed.path or "/"
        path = re.sub(r"/{2,}", "/", path)
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))

    text = value.split("#", 1)[0].split("?", 1)[0].strip()
    return text


def _dedupe_effective_js_urls(raw_urls: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_urls:
        url = _safe_text(item)
        if not url:
            continue
        key = _normalize_js_url_for_dedupe(url)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(url)
    return result


def load_project_detail(
    domain: str,
    *,
    route_page: int = 1,
    route_page_size: int = 120,
    js_page: int = 1,
    js_page_size: int = 120,
    request_page: int = 1,
    request_page_size: int = 120,
    map_page: int = 1,
    map_page_size: int = 120,
    map_q: str = "",
) -> dict[str, Any]:
    # 项目详情页依赖很多落盘文件，这里统一拼成稳定结构，避免 web 层重复处理文件格式。
    value = _safe_text(domain)
    if not value:
        return {}

    base_dir = PROJECTS_DIR / value
    router_dir = base_dir / "vueRouter"
    chunk_dir = base_dir / "downChunk"
    routes_file = router_dir / "routes.json"
    urls_file = router_dir / "urls.txt"
    js_file = router_dir / "js.txt"
    manifest_file = router_dir / "download_manifest.json"
    request_capture_file = router_dir / "request_capture.json"
    route_profile_file = router_dir / "route_url_profile.json"

    routes: list[dict[str, Any]] = []
    route_extract_meta: dict[str, Any] = {}
    if routes_file.is_file():
        try:
            payload = json.loads(routes_file.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                data = payload.get("routes", [])
                if isinstance(data, list):
                    routes = [item for item in data if isinstance(item, dict)]
                raw_meta = payload.get("meta", {})
                if isinstance(raw_meta, dict):
                    route_extract_meta = {
                        "target_url": _safe_text(raw_meta.get("target_url")),
                        "used_url": _safe_text(raw_meta.get("used_url")),
                        "used_wait_until": _safe_text(raw_meta.get("used_wait_until")),
                        "navigation_error": _safe_text(raw_meta.get("navigation_error")),
                        "history_basepath": _safe_text(raw_meta.get("history_basepath")),
                    }
        except Exception:
            routes = []
            route_extract_meta = {}

    manifest_summary: dict[str, Any] = {}
    manifest_source_routes: list[str] = []
    if manifest_file.is_file():
        try:
            payload = json.loads(manifest_file.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                summary = payload.get("summary", {})
                if isinstance(summary, dict):
                    manifest_summary = summary
                scripts = payload.get("scripts", [])
                if isinstance(scripts, list):
                    for script_item in scripts:
                        if not isinstance(script_item, dict):
                            continue
                        source_routes = script_item.get("source_routes", [])
                        if not isinstance(source_routes, list):
                            continue
                        for source_route in source_routes:
                            route_url = _safe_text(source_route)
                            if route_url:
                                manifest_source_routes.append(route_url)
        except Exception:
            manifest_summary = {}
            manifest_source_routes = []

    urls_preview = _read_lines(urls_file, limit=300)

    def normalize_route_key(raw: str) -> str:
        text = _safe_text(raw)
        if not text:
            return ""
        text = text.split("?", 1)[0].strip()
        if not text:
            return ""
        if text in {"*", "/*"}:
            return "/*"
        if not text.startswith("/"):
            text = "/" + text
        if len(text) > 1 and text.endswith("/"):
            text = text.rstrip("/")
        return text

    seen_route_urls: set[str] = set()
    route_url_inputs: list[str] = []
    for raw_url in manifest_source_routes:
        route_url = _safe_text(raw_url)
        if route_url and route_url not in seen_route_urls:
            seen_route_urls.add(route_url)
            route_url_inputs.append(route_url)
    for raw_url in urls_preview:
        route_url = _safe_text(raw_url)
        if route_url and route_url not in seen_route_urls:
            seen_route_urls.add(route_url)
            route_url_inputs.append(route_url)

    route_url_profile = load_route_url_profile(value)
    profile_hash_style = normalize_hash_style(route_url_profile.get("hash_style"))
    profile_basepath_override = normalize_basepath(route_url_profile.get("basepath_override"))

    preferred_scheme = ""
    for raw_url in route_url_inputs:
        parsed = urlsplit(_safe_text(raw_url))
        scheme = parsed.scheme.lower()
        if scheme == "https":
            preferred_scheme = "https"
            break
        if scheme == "http" and not preferred_scheme:
            preferred_scheme = "http"

    def normalize_route_display_url(raw_url: str) -> str:
        display_value = _safe_text(raw_url)
        display_value = rewrite_route_url(
            display_value,
            hash_style=profile_hash_style,
            basepath_override=profile_basepath_override,
        ) or display_value
        parsed = urlsplit(display_value)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"} or not parsed.netloc:
            return display_value

        final_scheme = scheme
        if preferred_scheme == "https" and scheme == "http":
            final_scheme = "https"

        path = parsed.path or "/"
        fragment = parsed.fragment.strip()
        if fragment:
            if not fragment.startswith("/"):
                fragment = f"/{fragment}"
            if profile_hash_style == "slash":
                if not path.endswith("/"):
                    path = f"{path}/"
            else:
                if len(path) > 1 and path.endswith("/"):
                    path = path.rstrip("/")
        return urlunsplit((final_scheme, parsed.netloc, path, parsed.query, fragment))

    route_url_map: dict[str, str] = {}
    route_candidates: list[tuple[str, str]] = []
    history_candidates: list[tuple[str, str, str]] = []
    hash_mode_prefix = ""
    history_origin = ""

    for raw_url in route_url_inputs:
        normalized_raw_url = normalize_route_display_url(raw_url)
        parsed = urlsplit(_safe_text(normalized_raw_url))
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            continue
        if not history_origin:
            history_origin = f"{parsed.scheme.lower()}://{parsed.netloc}"
        if parsed.fragment:
            fragment_path = parsed.fragment.split("?", 1)[0].strip()
            key = normalize_route_key(fragment_path)
            if key:
                if key not in route_url_map:
                    route_url_map[key] = normalized_raw_url
                route_candidates.append((key, normalized_raw_url))
            if not hash_mode_prefix:
                hash_path = parsed.path or "/"
                if profile_hash_style == "slash":
                    if not hash_path.endswith("/"):
                        hash_path = f"{hash_path}/"
                else:
                    if len(hash_path) > 1 and hash_path.endswith("/"):
                        hash_path = hash_path.rstrip("/")
                hash_mode_prefix = urlunsplit((parsed.scheme.lower(), parsed.netloc, hash_path, "", ""))
        if parsed.path:
            key = normalize_route_key(parsed.path)
            if key:
                if key not in route_url_map:
                    route_url_map[key] = normalized_raw_url
                route_candidates.append((key, normalized_raw_url))
                candidate_tail = key.lstrip("/") if key != "/" else ""
                history_candidates.append((key, candidate_tail, normalized_raw_url))

    inferred_history_prefix = ""
    history_prefix_votes = 0
    history_prefix_counter: Counter[str] = Counter()
    if history_candidates:
        for item in routes:
            route_key = normalize_route_key(_safe_text(item.get("path")))
            if not route_key or route_key in {"/", "/*"}:
                continue
            route_tail = route_key.lstrip("/")
            if not route_tail:
                continue
            for _, candidate_tail, _ in history_candidates:
                if candidate_tail and candidate_tail.endswith(route_tail):
                    prefix = candidate_tail[: -len(route_tail)]
                    history_prefix_counter[prefix] += 1
        if history_prefix_counter:
            inferred_history_prefix, history_prefix_votes = history_prefix_counter.most_common(1)[0]
            if history_prefix_votes < 3:
                inferred_history_prefix = ""

    routes_preview: list[dict[str, Any]] = []
    for item in routes:
        path_value = _safe_text(item.get("path"))
        route_key = normalize_route_key(path_value)
        route_url = ""

        if path_value.startswith(("http://", "https://")):
            route_url = normalize_route_display_url(path_value)
        elif route_key:
            route_url = route_url_map.get(route_key, "")
            if not route_url and (":" in route_key or "*" in route_key):
                pattern = re.escape(route_key)
                pattern = re.sub(r":[A-Za-z0-9_]+(?:\\\?)?", r"[^/]+", pattern)
                pattern = pattern.replace(r"\*", ".*")
                try:
                    route_regex = re.compile(f"^{pattern}$")
                    for candidate_key, candidate_url in route_candidates:
                        if route_regex.match(candidate_key):
                            route_url = candidate_url
                            break
                except re.error:
                    pass
            if not route_url and route_key not in {"", "/", "/*"}:
                route_tail = route_key.lstrip("/")
                suffix_matches: list[tuple[int, int, str]] = []
                for _, candidate_tail, candidate_url in history_candidates:
                    if candidate_tail.endswith(route_tail):
                        suffix_matches.append(
                            (len(candidate_tail) - len(route_tail), len(candidate_tail), candidate_url)
                        )
                if suffix_matches:
                    suffix_matches.sort(key=lambda row: (row[0], row[1]))
                    route_url = suffix_matches[0][2]
            if not route_url and history_origin and history_prefix_votes >= 3:
                if route_key == "/":
                    if inferred_history_prefix:
                        route_url = f"{history_origin}/{inferred_history_prefix}"
                    else:
                        route_url = f"{history_origin}/"
                elif route_key not in {"", "/*"} and ":" not in route_key and "*" not in route_key:
                    route_url = f"{history_origin}/{inferred_history_prefix}{route_key.lstrip('/')}"
            if not route_url and hash_mode_prefix:
                route_url = f"{hash_mode_prefix}#{route_key}"

        row = dict(item)
        row["route_url"] = normalize_route_display_url(route_url)
        routes_preview.append(row)

    route_page = max(1, int(route_page))
    route_page_size = max(1, min(int(route_page_size), 500))
    route_total = len(routes_preview)
    route_total_pages = (route_total + route_page_size - 1) // route_page_size if route_total > 0 else 0
    if route_total_pages > 0 and route_page > route_total_pages:
        route_page = route_total_pages
    route_start = (route_page - 1) * route_page_size
    route_rows = routes_preview[route_start : route_start + route_page_size]

    js_rows = _dedupe_effective_js_urls(_read_lines(js_file, limit=300000))
    js_page = max(1, int(js_page))
    js_page_size = max(1, min(int(js_page_size), 500))
    js_total = len(js_rows)
    js_total_pages = (js_total + js_page_size - 1) // js_page_size if js_total > 0 else 0
    if js_total_pages > 0 and js_page > js_total_pages:
        js_page = js_total_pages
    js_start = (js_page - 1) * js_page_size
    js_preview = js_rows[js_start : js_start + js_page_size]

    request_rows_all: list[dict[str, Any]] = []
    request_route_map_rows: list[dict[str, Any]] = []
    manual_request_rows = load_manual_request_items(value)
    request_summary: dict[str, Any] = {
        "route_total": 0,
        "visited_route_count": 0,
        "failed_route_count": 0,
        "request_total": 0,
        "request_unique_total": 0,
        "generated_at": "",
    }
    if request_capture_file.is_file():
        try:
            payload = json.loads(request_capture_file.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                summary_raw = payload.get("summary", {})
                if isinstance(summary_raw, dict):
                    request_summary = {
                        "route_total": _coerce_int(summary_raw.get("route_total"), default=0, minimum=0),
                        "visited_route_count": _coerce_int(summary_raw.get("visited_route_count"), default=0, minimum=0),
                        "failed_route_count": _coerce_int(summary_raw.get("failed_route_count"), default=0, minimum=0),
                        "request_total": _coerce_int(summary_raw.get("request_total"), default=0, minimum=0),
                        "request_unique_total": _coerce_int(
                            summary_raw.get("request_unique_total"),
                            default=0,
                            minimum=0,
                        ),
                        "generated_at": _safe_text(payload.get("generated_at")),
                    }
                routes_data = payload.get("routes", [])
                if isinstance(routes_data, list):
                    for route_item in routes_data:
                        if not isinstance(route_item, dict):
                            continue
                        route_url = normalize_route_display_url(_safe_text(route_item.get("route_url")))
                        chunk_items = route_item.get("chunks", [])
                        chunk_urls: list[str] = []
                        if isinstance(chunk_items, list):
                            chunk_seen: set[str] = set()
                            for chunk_item in chunk_items:
                                chunk_url_raw = _safe_text(chunk_item)
                                chunk_url = _normalize_js_url_for_dedupe(chunk_url_raw) or chunk_url_raw
                                if not chunk_url or chunk_url in chunk_seen:
                                    continue
                                chunk_seen.add(chunk_url)
                                chunk_urls.append(chunk_url)
                        requests_data = route_item.get("requests", [])
                        if not isinstance(requests_data, list):
                            requests_data = []
                        route_request_total = 0
                        route_request_items: list[dict[str, Any]] = []
                        for request_item in requests_data:
                            if not isinstance(request_item, dict):
                                continue
                            resource_type_value = _safe_text(request_item.get("resource_type")).lower()
                            if resource_type_value in {"ping", "beacon"}:
                                continue
                            request_count = _coerce_int(request_item.get("count"), default=1, minimum=1)
                            route_request_total += request_count
                            api_url = _safe_text(request_item.get("url"))
                            if not api_url:
                                continue
                            request_rows_all.append(
                                {
                                    "route_url": route_url,
                                    "method": _safe_text(request_item.get("method"), "GET").upper(),
                                    "url": api_url,
                                    "count": request_count,
                                    "status": _coerce_int(request_item.get("status"), default=0, minimum=0),
                                    "resource_type": _safe_text(request_item.get("resource_type")),
                                    "content_type": _safe_text(request_item.get("content_type")),
                                    "request_body": _safe_text(request_item.get("request_body")),
                                }
                            )
                            route_request_items.append(
                                {
                                    "method": _safe_text(request_item.get("method"), "GET").upper(),
                                    "url": api_url,
                                    "count": request_count,
                                    "status": _coerce_int(request_item.get("status"), default=0, minimum=0),
                                    "resource_type": _safe_text(request_item.get("resource_type")),
                                    "content_type": _safe_text(request_item.get("content_type")),
                                }
                            )
                        route_request_items.sort(
                            key=lambda row: (-_coerce_int(row.get("count"), default=1, minimum=1), _safe_text(row.get("url")))
                        )
                        request_route_map_rows.append(
                            {
                                "route_url": route_url,
                                "chunk_count": len(chunk_urls),
                                "request_count": route_request_total,
                                "unique_request_count": len(route_request_items),
                                "chunks": chunk_urls,
                                "requests": route_request_items,
                            }
                        )
        except Exception:
            request_rows_all = []
            request_route_map_rows = []

    request_page = max(1, int(request_page))
    request_page_size = max(1, min(int(request_page_size), 500))
    request_total = len(request_rows_all)
    request_total_pages = (request_total + request_page_size - 1) // request_page_size if request_total > 0 else 0
    if request_total_pages > 0 and request_page > request_total_pages:
        request_page = request_total_pages
    request_start = (request_page - 1) * request_page_size
    request_preview = request_rows_all[request_start : request_start + request_page_size]

    map_query = _safe_text(map_q).lower()
    if map_query:
        filtered_map_rows: list[dict[str, Any]] = []
        for row in request_route_map_rows:
            route_url = _safe_text(row.get("route_url")).lower()
            chunk_values = [
                _safe_text(item).lower()
                for item in (row.get("chunks") if isinstance(row.get("chunks"), list) else [])
                if _safe_text(item)
            ]
            request_values = [
                _safe_text(item.get("url")).lower()
                for item in (row.get("requests") if isinstance(row.get("requests"), list) else [])
                if isinstance(item, dict) and _safe_text(item.get("url"))
            ]
            if (
                map_query in route_url
                or any(map_query in chunk for chunk in chunk_values)
                or any(map_query in request_url for request_url in request_values)
            ):
                filtered_map_rows.append(row)
        request_route_map_rows = filtered_map_rows

    map_page = max(1, int(map_page))
    map_page_size = max(1, min(int(map_page_size), 500))
    request_route_map_total = len(request_route_map_rows)
    request_route_map_total_pages = (
        (request_route_map_total + map_page_size - 1) // map_page_size if request_route_map_total > 0 else 0
    )
    if request_route_map_total_pages > 0 and map_page > request_route_map_total_pages:
        map_page = request_route_map_total_pages
    map_start = (map_page - 1) * map_page_size
    request_route_map_preview = request_route_map_rows[map_start : map_start + map_page_size]

    if request_summary.get("request_total", 0) <= 0:
        request_summary["request_total"] = sum(
            _coerce_int(item.get("count"), default=1, minimum=1) for item in request_rows_all
        )
    if request_summary.get("request_unique_total", 0) <= 0:
        request_summary["request_unique_total"] = len(request_rows_all)
    if request_summary.get("visited_route_count", 0) <= 0:
        request_summary["visited_route_count"] = len(
            {
                str(item.get("route_url") or "").strip()
                for item in request_rows_all
                if str(item.get("route_url") or "").strip()
            }
        )
    if request_summary.get("route_total", 0) <= 0:
        request_summary["route_total"] = len(request_route_map_rows)

    captured_js_count = js_total
    downloaded_chunk_count = len(list(chunk_dir.glob("*.js"))) if chunk_dir.is_dir() else 0
    chunk_count = captured_js_count if captured_js_count > 0 else downloaded_chunk_count

    return {
        "domain": value,
        "project_dir": str(base_dir),
        "routes_file": str(routes_file),
        "urls_file": str(urls_file),
        "js_file": str(js_file),
        "request_capture_file": str(request_capture_file),
        "route_profile_file": str(route_profile_file),
        "route_url_profile": route_url_profile,
        "route_extract_meta": route_extract_meta,
        "route_count": len(routes),
        "routes_preview": route_rows,
        "routes_pagination": {
            "page": route_page,
            "page_size": route_page_size,
            "total": route_total,
            "total_pages": route_total_pages,
        },
        "urls_preview": urls_preview,
        "js_preview": js_preview,
        "js_pagination": {
            "page": js_page,
            "page_size": js_page_size,
            "total": js_total,
            "total_pages": js_total_pages,
        },
        "request_preview": request_preview,
        "manual_request_preview": manual_request_rows,
        "request_pagination": {
            "page": request_page,
            "page_size": request_page_size,
            "total": request_total,
            "total_pages": request_total_pages,
        },
        "request_route_map_total": request_route_map_total,
        "request_route_map_pagination": {
            "page": map_page,
            "page_size": map_page_size,
            "total": request_route_map_total,
            "total_pages": request_route_map_total_pages,
        },
        "request_route_map_preview": request_route_map_preview,
        "request_summary": request_summary,
        "chunk_count": chunk_count,
        "downloaded_chunk_count": downloaded_chunk_count,
        "manifest_summary": manifest_summary,
    }


def load_project_metrics(domain: str) -> dict[str, object]:
    value = _safe_text(domain)
    if not value:
        return {
            "route_count": 0,
            "js_count": 0,
            "saved_result_count": 0,
            "request_value_level": "",
            "request_value_label": "",
            "request_value_reason": "",
            "request_value_score": 0,
            "request_value_snapshot_count": 0,
            "request_value_sample_count": 0,
        }

    base_dir = PROJECTS_DIR / value
    router_dir = base_dir / "vueRouter"
    chunk_dir = base_dir / "downChunk"
    routes_file = router_dir / "routes.json"
    js_file = router_dir / "js.txt"

    route_count = 0
    if routes_file.is_file():
        try:
            payload = json.loads(routes_file.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                routes = payload.get("routes", [])
                if isinstance(routes, list):
                    route_count = len([item for item in routes if isinstance(item, dict)])
        except Exception:
            route_count = 0

    js_count = len(_dedupe_effective_js_urls(_read_lines(js_file, limit=400000)))
    if js_count <= 0 and chunk_dir.is_dir():
        js_count = len(list(chunk_dir.glob("*.js")))
    try:
        saved_result_count = len(load_saved_request_results(value))
    except Exception:
        saved_result_count = 0
    try:
        request_value = analyze_request_run_snapshots(value)
    except Exception:
        request_value = {
            "request_value_level": "",
            "request_value_label": "",
            "request_value_reason": "",
            "request_value_score": 0,
            "request_value_snapshot_count": 0,
            "request_value_sample_count": 0,
        }
    return {
        "route_count": route_count,
        "js_count": js_count,
        "saved_result_count": saved_result_count,
        **request_value,
    }
