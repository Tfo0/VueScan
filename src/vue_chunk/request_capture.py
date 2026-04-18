from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from config import PROJECTS_DIR
from src.vue_chunk.browser_init import initialize_browser


HASH_STYLE_SLASH = "slash"
HASH_STYLE_PLAIN = "plain"
HASH_STYLE_VALUES = {HASH_STYLE_SLASH, HASH_STYLE_PLAIN}

STATIC_SUFFIXES = {
    ".js",
    ".mjs",
    ".css",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp4",
    ".mp3",
    ".webm",
    ".pdf",
    ".txt",
    ".xml",
}
REQUEST_BODY_MAX_CHARS = 20000
REQUEST_TEMPLATE_MAX_SAMPLES = 8
CAPTURE_HEADER_ALLOWLIST = {
    "accept",
    "accept-language",
    "authorization",
    "content-type",
    "cookie",
    "origin",
    "referer",
    "user-agent",
    "x-requested-with",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def normalize_hash_style(raw_style: Any) -> str:
    value = str(raw_style or "").strip().lower()
    if value in HASH_STYLE_VALUES:
        return value
    if value in {"noslash", "plain_hash", "hash"}:
        return HASH_STYLE_PLAIN
    return HASH_STYLE_SLASH


def normalize_basepath(raw_basepath: Any) -> str:
    value = str(raw_basepath or "").strip()
    if not value:
        return ""
    parsed = urlsplit(value)
    path = parsed.path if parsed.scheme and parsed.netloc else value
    if not path:
        return ""
    normalized = "/" + path.lstrip("/")
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized


def _normalize_dynamic_route_segments(raw_value: str) -> str:
    text = str(raw_value or "").strip()
    if not text:
        return ""

    # 将 Vue Router 风格的动态段统一替换成 1，避免后续访问 /:id? 这类无效 URL。
    normalized = re.sub(r"(?<=/):[A-Za-z0-9_]+\??", "1", text)
    normalized = re.sub(r"/{2,}", "/", normalized)
    return normalized


def rewrite_route_url(
    raw_url: str,
    *,
    hash_style: str = HASH_STYLE_SLASH,
    basepath_override: str = "",
) -> str:
    parsed = urlsplit((raw_url or "").strip())
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.netloc:
        return ""

    mode = normalize_hash_style(hash_style)
    override_path = normalize_basepath(basepath_override)
    path = _normalize_dynamic_route_segments(parsed.path or "/") or "/"
    fragment = (parsed.fragment or "").strip()
    if fragment:
        if not fragment.startswith("/"):
            fragment = f"/{fragment}"
        fragment = _normalize_dynamic_route_segments(fragment)
        if override_path:
            path = override_path
        if mode == HASH_STYLE_SLASH:
            if not path.endswith("/"):
                path = f"{path}/"
        else:
            if len(path) > 1 and path.endswith("/"):
                path = path.rstrip("/")
    return urlunsplit(
        (
            scheme,
            parsed.netloc,
            path or "/",
            parsed.query,
            fragment,
        )
    )


def _normalize_url(raw_url: str) -> str:
    parsed = urlsplit((raw_url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            parsed.query,
            "",
        )
    )


def _normalize_chunk_url(raw_url: str) -> str:
    parsed = urlsplit((raw_url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            "",
            "",
        )
    )


def _build_chunk_file_name(chunk_url: str) -> str:
    parsed = urlsplit((chunk_url or "").strip())
    base_name = Path(parsed.path or "").name or "script.js"
    if not base_name.lower().endswith(".js"):
        base_name = f"{base_name}.js"
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", base_name)
    digest = hashlib.sha1((chunk_url or "").encode("utf-8")).hexdigest()[:10]
    return f"{digest}_{safe_name}"


def _normalize_request_path(raw_path: str) -> str:
    path = str(raw_path or "").strip()
    if not path:
        return "/"
    if not path.startswith("/"):
        path = f"/{path}"
    path = re.sub(r"/{2,}", "/", path)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return path or "/"


def _parse_query_params(query_text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    query = str(query_text or "").strip()
    if not query:
        return result

    for key, value in parse_qsl(query, keep_blank_values=True):
        name = str(key or "").strip()
        if not name:
            continue
        text = str(value or "")
        current = result.get(name)
        if current is None:
            result[name] = text
            continue
        if isinstance(current, list):
            current.append(text)
            continue
        result[name] = [current, text]
    return result


def _extract_query_context(raw_url: str) -> tuple[str, dict[str, Any]]:
    parsed = urlsplit(str(raw_url or "").strip())
    query = str(parsed.query or "")
    return query, _parse_query_params(query)


def _filter_request_headers(raw_headers: Any) -> dict[str, str]:
    if not isinstance(raw_headers, dict):
        return {}

    rows: dict[str, str] = {}
    for key, value in raw_headers.items():
        name = str(key or "").strip()
        if not name or name.startswith(":"):
            continue

        lower = name.lower()
        if lower in {"host", "content-length", "connection"}:
            continue
        if (
            lower not in CAPTURE_HEADER_ALLOWLIST
            and not lower.startswith("x-")
            and not lower.startswith("sec-ch-")
            and not lower.startswith("sec-fetch-")
        ):
            continue

        text = str(value or "").strip()
        if not text:
            continue
        if len(text) > 2000:
            text = f"{text[:2000]}...[truncated]"
        rows[name] = text
        if len(rows) >= 40:
            break
    return rows


def _parse_request_body_context(request_body: str, content_type: str) -> dict[str, Any]:
    text = str(request_body or "").strip()
    if not text:
        return {
            "body_type": "empty",
            "body_text": "",
            "body_json": None,
            "body_form": None,
        }

    normalized_ct = str(content_type or "").split(";", 1)[0].strip().lower()
    result: dict[str, Any] = {
        "body_type": "text",
        "body_text": text,
        "body_json": None,
        "body_form": None,
    }

    def _try_load_json(raw_text: str) -> Any:
        try:
            return json.loads(raw_text)
        except Exception:
            return None

    if "application/json" in normalized_ct or normalized_ct.endswith("+json"):
        loaded = _try_load_json(text)
        if loaded is not None:
            result["body_type"] = "json"
            result["body_json"] = loaded
        return result

    if "application/x-www-form-urlencoded" in normalized_ct:
        form_map = _parse_query_params(text)
        result["body_type"] = "form"
        result["body_form"] = form_map if form_map else None
        return result

    loaded = _try_load_json(text)
    if loaded is not None:
        result["body_type"] = "json"
        result["body_json"] = loaded
        return result

    if "=" in text:
        form_map = _parse_query_params(text)
        if form_map:
            result["body_type"] = "form"
            result["body_form"] = form_map
    return result


def _normalize_stored_request_headers(raw_headers: Any) -> dict[str, str]:
    if not isinstance(raw_headers, dict):
        return {}
    rows: dict[str, str] = {}
    for key, value in raw_headers.items():
        name = _safe_text(key)
        if not name:
            continue
        text = _safe_text(value)
        if not text:
            continue
        rows[name] = text
    return rows


def normalize_captured_request_row(raw_item: Any, route_url: str = "") -> dict[str, Any] | None:
    # Web 层读取 request_capture.json / manual 请求时，统一收敛成稳定结构。
    if not isinstance(raw_item, dict):
        method = "GET"
        url = _safe_text(raw_item)
        count = 1
        status = 0
        resource_type = "manual"
        content_type = ""
        request_body = ""
        query_string = ""
        query_params: dict[str, Any] = {}
        request_headers: dict[str, str] = {}
        body_type = "empty"
        body_json = None
        body_form = None
    else:
        method = _safe_text(raw_item.get("method"), "GET").upper() or "GET"
        url = _safe_text(raw_item.get("url") or raw_item.get("request_url"))
        count = _coerce_int(raw_item.get("count"), default=1, minimum=1)
        status = _coerce_int(raw_item.get("status"), default=0, minimum=0)
        resource_type = _safe_text(raw_item.get("resource_type"), "manual") or "manual"
        content_type = _safe_text(raw_item.get("content_type"))
        request_body = _safe_text(raw_item.get("request_body"))
        query_string = _safe_text(raw_item.get("query_string"))
        query_params = raw_item.get("query_params") if isinstance(raw_item.get("query_params"), dict) else {}
        request_headers = _normalize_stored_request_headers(raw_item.get("request_headers"))
        body_type = _safe_text(raw_item.get("body_type")).lower()
        body_json = raw_item.get("body_json")
        body_form = raw_item.get("body_form") if isinstance(raw_item.get("body_form"), dict) else None

    if method not in {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"}:
        method = "GET"
    if not url:
        return None

    if not query_string:
        query_string, query_fallback = _extract_query_context(url)
    else:
        query_fallback = _parse_query_params(query_string)
    if not query_params:
        query_params = query_fallback

    if not body_type:
        if body_json is not None:
            body_type = "json"
        elif isinstance(body_form, dict) and body_form:
            body_type = "form"
        elif request_body:
            body_type = "text"
        else:
            body_type = "empty"
    if body_type == "json" and body_json is None and request_body:
        try:
            body_json = json.loads(request_body)
        except Exception:
            body_json = None
    if body_type == "form" and body_form is None and request_body:
        body_form = _parse_query_params(request_body) or None

    return {
        "route_url": _safe_text(route_url or (raw_item.get("route_url") if isinstance(raw_item, dict) else "")),
        "method": method,
        "url": url,
        "path": _normalize_request_path(urlsplit(url).path) if urlsplit(url).path else "",
        "count": count,
        "status": status,
        "resource_type": resource_type,
        "content_type": content_type,
        "query_string": query_string,
        "query_params": query_params,
        "request_body": request_body,
        "body_type": body_type,
        "body_json": body_json,
        "body_form": body_form,
        "request_headers": request_headers,
    }


def merge_captured_request_rows(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    # 合并同 method + url 的请求样本，优先保留更完整的一侧字段。
    merged = dict(base)
    merged["count"] = _coerce_int(base.get("count"), default=1, minimum=1) + _coerce_int(
        incoming.get("count"),
        default=1,
        minimum=1,
    )
    merged["status"] = _coerce_int(base.get("status"), default=0, minimum=0) or _coerce_int(
        incoming.get("status"),
        default=0,
        minimum=0,
    )

    if not _safe_text(merged.get("resource_type")) and _safe_text(incoming.get("resource_type")):
        merged["resource_type"] = _safe_text(incoming.get("resource_type"))
    if not _safe_text(merged.get("content_type")) and _safe_text(incoming.get("content_type")):
        merged["content_type"] = _safe_text(incoming.get("content_type"))
    if not _safe_text(merged.get("query_string")) and _safe_text(incoming.get("query_string")):
        merged["query_string"] = _safe_text(incoming.get("query_string"))
    if (not isinstance(merged.get("query_params"), dict) or not merged.get("query_params")) and isinstance(
        incoming.get("query_params"),
        dict,
    ):
        merged["query_params"] = incoming.get("query_params")
    if not _safe_text(merged.get("request_body")) and _safe_text(incoming.get("request_body")):
        merged["request_body"] = _safe_text(incoming.get("request_body"))
        merged["body_type"] = _safe_text(incoming.get("body_type"))
        merged["body_json"] = incoming.get("body_json")
        merged["body_form"] = incoming.get("body_form")
    if (not isinstance(merged.get("request_headers"), dict) or not merged.get("request_headers")) and isinstance(
        incoming.get("request_headers"),
        dict,
    ):
        merged["request_headers"] = incoming.get("request_headers")
    if not _safe_text(merged.get("route_url")) and _safe_text(incoming.get("route_url")):
        merged["route_url"] = _safe_text(incoming.get("route_url"))
    return merged


def _manual_requests_path(domain: str) -> Path:
    token = _safe_text(domain)
    return PROJECTS_DIR / token / "vueRouter" / "manual_requests.json"


def normalize_manual_request_items(raw_items: Any) -> list[dict[str, Any]]:
    # 手工补录的请求样本也统一整理成和 capture 一致的最小结构。
    items = raw_items if isinstance(raw_items, list) else []
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    allowed_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"}

    for item in items:
        if isinstance(item, dict):
            method = _safe_text(item.get("method"), "GET").upper() or "GET"
            url = _safe_text(item.get("url") or item.get("request_url"))
            route_url = _safe_text(item.get("route_url"))
            count = _coerce_int(item.get("count"), default=1, minimum=1)
            status = _coerce_int(item.get("status"), default=0, minimum=0)
            resource_type = _safe_text(item.get("resource_type"), "manual") or "manual"
            content_type = _safe_text(item.get("content_type"))
            request_body = _safe_text(item.get("request_body"))
        else:
            method = "GET"
            url = _safe_text(item)
            route_url = ""
            count = 1
            status = 0
            resource_type = "manual"
            content_type = ""
            request_body = ""

        if method not in allowed_methods:
            method = "GET"
        if not url:
            continue

        dedupe_key = (method, url, route_url)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        rows.append(
            {
                "route_url": route_url,
                "method": method,
                "url": url,
                "count": count,
                "status": status,
                "resource_type": resource_type,
                "content_type": content_type,
                "request_body": request_body,
            }
        )

    return rows


def load_manual_request_items(domain: str) -> list[dict[str, Any]]:
    token = _safe_text(domain)
    if not token:
        return []
    path = _manual_requests_path(token)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(payload, dict):
        items = payload.get("requests")
    else:
        items = payload
    return normalize_manual_request_items(items)


def save_manual_request_items(domain: str, raw_items: Any) -> list[dict[str, Any]]:
    token = _safe_text(domain)
    if not token:
        raise ValueError("domain is required")

    rows = normalize_manual_request_items(raw_items)
    payload = {
        "requests": rows,
        "count": len(rows),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    output_path = _manual_requests_path(token)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def _capture_file_path(domain: str) -> Path:
    token = _safe_text(domain)
    return PROJECTS_DIR / token / "vueRouter" / "request_capture.json"


def _load_capture_payload(domain: str) -> dict[str, Any]:
    capture_file = _capture_file_path(domain)
    payload: dict[str, Any] = {}
    if capture_file.is_file():
        try:
            loaded = json.loads(capture_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except Exception:
            payload = {}
    return payload


def _split_request_path_segments(path_value: str) -> list[str]:
    normalized = _normalize_request_path(path_value)
    if not normalized:
        return []
    return [segment for segment in normalized.split("/") if segment]


def _path_is_suffix_by_segments(request_path: str, endpoint_path: str) -> bool:
    req_segments = _split_request_path_segments(request_path)
    api_segments = _split_request_path_segments(endpoint_path)
    if not req_segments or not api_segments:
        return False
    if len(req_segments) < len(api_segments):
        return False
    return req_segments[-len(api_segments) :] == api_segments


def load_captured_request_items(domain: str) -> list[dict[str, Any]]:
    # 从 request_capture.json 和 manual_requests.json 读取并合并请求样本。
    token = _safe_text(domain)
    if not token:
        return []

    payload = _load_capture_payload(token)
    rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}

    def _push(raw_item: Any, route_url: str = "") -> None:
        normalized = normalize_captured_request_row(raw_item, route_url=route_url)
        if not isinstance(normalized, dict):
            return
        key = (_safe_text(normalized.get("method"), "GET").upper(), _safe_text(normalized.get("url")))
        if not key[1]:
            return
        existed = rows_by_key.get(key)
        if existed is None:
            rows_by_key[key] = normalized
            return
        rows_by_key[key] = merge_captured_request_rows(existed, normalized)

    top_rows = payload.get("requests", [])
    if isinstance(top_rows, list):
        for item in top_rows:
            _push(item)

    if not rows_by_key:
        route_rows = payload.get("routes", [])
        if isinstance(route_rows, list):
            for route_item in route_rows:
                if not isinstance(route_item, dict):
                    continue
                route_url = _safe_text(route_item.get("route_url"))
                requests_data = route_item.get("requests", [])
                if not isinstance(requests_data, list):
                    continue
                for item in requests_data:
                    _push(item, route_url=route_url)

    for row in load_manual_request_items(token):
        _push(row)

    result = list(rows_by_key.values())
    result.sort(
        key=lambda row: (
            -_coerce_int(row.get("count"), default=1, minimum=1),
            _safe_text(row.get("url")),
        )
    )
    return result


def load_captured_request_templates(domain: str) -> list[dict[str, Any]]:
    # 优先读取 capture 产出的模板；如果缺失，则从请求样本反推模板视图。
    token = _safe_text(domain)
    if not token:
        return []

    payload = _load_capture_payload(token)
    templates_raw = payload.get("request_templates")
    normalized_templates: list[dict[str, Any]] = []
    if isinstance(templates_raw, list):
        for row in templates_raw:
            if not isinstance(row, dict):
                continue
            method = _safe_text(row.get("method"), "GET").upper() or "GET"
            path = _normalize_request_path(_safe_text(row.get("path"), "/")) or "/"
            samples_raw = row.get("samples", [])
            samples: list[dict[str, Any]] = []
            if isinstance(samples_raw, list):
                for sample in samples_raw:
                    if not isinstance(sample, dict):
                        continue
                    normalized = normalize_captured_request_row({**sample, "method": method})
                    if isinstance(normalized, dict):
                        samples.append(normalized)
            if not samples:
                best_sample = row.get("best_sample")
                if isinstance(best_sample, dict):
                    normalized = normalize_captured_request_row({**best_sample, "method": method})
                    if isinstance(normalized, dict):
                        samples.append(normalized)
            if not samples:
                continue
            samples.sort(
                key=lambda item: (
                    -_coerce_int(item.get("count"), default=1, minimum=1),
                    _safe_text(item.get("url")),
                )
            )
            normalized_templates.append(
                {
                    "method": method,
                    "path": path,
                    "sample_count": _coerce_int(row.get("sample_count"), default=len(samples), minimum=1),
                    "total_count": _coerce_int(
                        row.get("total_count"),
                        default=sum(_coerce_int(item.get("count"), default=1, minimum=1) for item in samples),
                        minimum=1,
                    ),
                    "samples": samples[:8],
                    "best_sample": samples[0],
                }
            )

    if normalized_templates:
        normalized_templates.sort(
            key=lambda row: (
                -_coerce_int(row.get("total_count"), default=0, minimum=0),
                -_coerce_int(row.get("sample_count"), default=0, minimum=0),
                _safe_text(row.get("method")),
                _safe_text(row.get("path")),
            )
        )
        return normalized_templates

    fallback_rows = load_captured_request_items(token)
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in fallback_rows:
        method = _safe_text(row.get("method"), "GET").upper() or "GET"
        path = _normalize_request_path(_safe_text(row.get("path")) or _safe_text(urlsplit(_safe_text(row.get("url"))).path)) or "/"
        key = (method, path)
        sample = dict(row)
        entry = grouped.get(key)
        if entry is None:
            grouped[key] = {
                "method": method,
                "path": path,
                "sample_count": 1,
                "total_count": _coerce_int(sample.get("count"), default=1, minimum=1),
                "samples": [sample],
                "best_sample": sample,
            }
            continue
        entry["sample_count"] = _coerce_int(entry.get("sample_count"), default=1, minimum=1) + 1
        entry["total_count"] = _coerce_int(entry.get("total_count"), default=1, minimum=1) + _coerce_int(
            sample.get("count"),
            default=1,
            minimum=1,
        )
        samples = entry.get("samples")
        if isinstance(samples, list):
            samples.append(sample)

    rows = list(grouped.values())
    for row in rows:
        samples = row.get("samples")
        if not isinstance(samples, list):
            row["samples"] = []
            row["best_sample"] = {}
            continue
        samples.sort(
            key=lambda item: (
                -_coerce_int(item.get("count"), default=1, minimum=1),
                _safe_text(item.get("url")),
            )
        )
        row["samples"] = samples[:8]
        row["best_sample"] = row["samples"][0] if row["samples"] else {}

    rows.sort(
        key=lambda row: (
            -_coerce_int(row.get("total_count"), default=0, minimum=0),
            -_coerce_int(row.get("sample_count"), default=0, minimum=0),
            _safe_text(row.get("method")),
            _safe_text(row.get("path")),
        )
    )
    return rows


def _template_path_match_score(template_path: str, endpoint_path: str) -> tuple[int, str]:
    tpl = _normalize_request_path(template_path)
    api = _normalize_request_path(endpoint_path)
    if not tpl or not api:
        return 0, "none"
    if tpl == api:
        return 1000, "exact"

    if _path_is_suffix_by_segments(tpl, api):
        seg_gap = abs(len(_split_request_path_segments(tpl)) - len(_split_request_path_segments(api)))
        return 880 - seg_gap * 10, "suffix"
    if _path_is_suffix_by_segments(api, tpl):
        seg_gap = abs(len(_split_request_path_segments(tpl)) - len(_split_request_path_segments(api)))
        return 840 - seg_gap * 10, "suffix-reverse"

    tpl_segments = _split_request_path_segments(tpl)
    api_segments = _split_request_path_segments(api)
    if tpl_segments and api_segments and tpl_segments[-1] == api_segments[-1]:
        return 500, "tail"
    return 0, "none"


def match_capture_template_for_endpoint(
    template_rows: list[dict[str, Any]],
    endpoint_path: str,
    endpoint_method: str,
) -> dict[str, Any]:
    # 为 API 请求重放挑出最匹配的 capture 模板。
    method = _safe_text(endpoint_method, "GET").upper() or "GET"
    path = _normalize_request_path(endpoint_path)
    if not path:
        return {}
    if not isinstance(template_rows, list) or not template_rows:
        return {}

    best: dict[str, Any] = {}
    for row in template_rows:
        if not isinstance(row, dict):
            continue
        row_method = _safe_text(row.get("method"), "GET").upper() or "GET"
        row_path = _normalize_request_path(_safe_text(row.get("path"), "/")) or "/"
        path_score, match_type = _template_path_match_score(row_path, path)
        if path_score <= 0:
            continue
        method_bonus = 40 if row_method == method else 0
        sample_count = _coerce_int(row.get("sample_count"), default=0, minimum=0)
        total_count = _coerce_int(row.get("total_count"), default=0, minimum=0)
        score = path_score + method_bonus + min(30, total_count) + min(10, sample_count)
        best_score = _coerce_int(best.get("score"), default=-1, minimum=-1)
        if score <= best_score:
            continue
        samples = row.get("samples")
        best_sample = {}
        if isinstance(samples, list) and samples:
            first = samples[0]
            if isinstance(first, dict):
                best_sample = first
        sample_from_row = row.get("best_sample")
        if not best_sample and isinstance(sample_from_row, dict):
            best_sample = sample_from_row
        best = {
            "score": score,
            "match_type": match_type,
            "method_matched": row_method == method,
            "template": row,
            "sample": best_sample,
        }
    return best


def _extract_post_request_body(req: Any, method: str) -> str:
    if str(method or "").upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return ""
    try:
        raw = req.post_data  # type: ignore[attr-defined]
    except Exception:
        raw = ""
    text = str(raw or "").strip()
    if not text:
        return ""
    if len(text) > REQUEST_BODY_MAX_CHARS:
        return f"{text[:REQUEST_BODY_MAX_CHARS]}\n...[truncated]"
    return text


def _normalize_route_url(
    raw_url: str,
    *,
    hash_style: str = HASH_STYLE_SLASH,
    basepath_override: str = "",
) -> str:
    normalized = rewrite_route_url(
        raw_url,
        hash_style=hash_style,
        basepath_override=basepath_override,
    )
    if not normalized:
        return ""
    parsed = urlsplit(normalized)
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            parsed.query,
            parsed.fragment or "",
        )
    )


def _is_static_like(url: str, content_type: str, resource_type: str) -> bool:
    res = (resource_type or "").strip().lower()
    if res in {"image", "media", "font", "stylesheet"}:
        return True

    path = urlsplit(url).path.lower()
    for suffix in STATIC_SUFFIXES:
        if path.endswith(suffix):
            return True

    ct = (content_type or "").strip().lower()
    if not ct:
        return False
    if "javascript" in ct or "text/css" in ct or ct.startswith("image/") or ct.startswith("font/"):
        return True
    return False


def _is_js_chunk_like(url: str, content_type: str, resource_type: str) -> bool:
    res = (resource_type or "").strip().lower()
    if res == "script":
        return True
    path = urlsplit(url).path.lower()
    if path.endswith(".js") or path.endswith(".mjs"):
        return True
    ct = (content_type or "").strip().lower()
    if "javascript" in ct or "ecmascript" in ct:
        return True
    return False


def _is_api_like(*, method: str, url: str, resource_type: str, content_type: str) -> bool:
    res = (resource_type or "").strip().lower()
    if res in {"xhr", "fetch"}:
        return True

    http_method = (method or "GET").upper()
    if http_method not in {"GET", "HEAD", "OPTIONS"}:
        return True

    path = urlsplit(url).path.lower()
    if "/api/" in path:
        return True

    ct = (content_type or "").strip().lower()
    if not ct:
        return False
    return (
        "application/json" in ct
        or "application/xml" in ct
        or "text/xml" in ct
        or "text/plain" in ct
    )


def _is_ping_like(url: str) -> bool:
    parsed = urlsplit(url or "")
    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()

    # Ignore heartbeat/ping style requests to reduce noise in captured api list.
    ping_tokens = (
        "/ping",
        "/heartbeat",
        "/heart-beat",
        "/keepalive",
        "/keep-alive",
    )
    if any(token in path for token in ping_tokens):
        return True

    query_tokens = (
        "ping=",
        "heartbeat=",
        "keepalive=",
        "keep_alive=",
    )
    if any(token in query for token in query_tokens):
        return True
    return False


def rewrite_route_urls(
    urls: list[str],
    *,
    hash_style: str = HASH_STYLE_SLASH,
    basepath_override: str = "",
) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in urls:
        value = _normalize_route_url(
            raw,
            hash_style=hash_style,
            basepath_override=basepath_override,
        )
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _build_navigation_candidates(url: str) -> list[str]:
    raw = str(url or "").strip()
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return [raw] if raw else []

    candidates: list[str] = []
    seen: set[str] = set()

    def add(item: str) -> None:
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


async def _probe_style_score(
    *,
    route_urls: list[str],
    hash_style: str,
    basepath_override: str,
    proxy_server: str = "",
) -> dict[str, int]:
    target_urls = rewrite_route_urls(
        route_urls,
        hash_style=hash_style,
        basepath_override=basepath_override,
    )
    if not target_urls:
        return {
            "sample_total": 0,
            "visited_route_count": 0,
            "failed_route_count": 0,
            "request_hits": 0,
        }

    playwright, browser, context, page = await initialize_browser(proxy_server=proxy_server)
    visited_route_count = 0
    failed_route_count = 0
    request_hits = 0
    try:
        for route_url in target_urls:
            pending_tasks: set[asyncio.Task] = set()
            loop = asyncio.get_running_loop()
            last_seen = loop.time()
            hits = 0

            async def handle_response_async(response) -> None:
                nonlocal last_seen, hits
                req = response.request
                if req is None:
                    return
                req_url = _normalize_url(response.url)
                if not req_url:
                    return
                method = str(req.method or "GET").upper()
                resource_type = str(req.resource_type or "").strip().lower()
                content_type = str((response.headers or {}).get("content-type", "")).split(";", 1)[0].strip().lower()
                if _is_static_like(req_url, content_type, resource_type):
                    return
                if not _is_api_like(
                    method=method,
                    url=req_url,
                    resource_type=resource_type,
                    content_type=content_type,
                ):
                    return
                hits += 1
                last_seen = loop.time()

            def handle_response(response) -> None:
                task = asyncio.create_task(handle_response_async(response))
                pending_tasks.add(task)
                task.add_done_callback(lambda done: pending_tasks.discard(done))

            page.on("response", handle_response)
            try:
                await _goto_with_retry(page, route_url, max_attempts=1)
                visited_route_count += 1
                try:
                    await page.wait_for_load_state("networkidle", timeout=5500)
                except PlaywrightTimeoutError:
                    pass

                start = loop.time()
                while True:
                    now = loop.time()
                    elapsed = now - start
                    quiet = now - last_seen
                    if elapsed >= 8.0:
                        break
                    if hits > 0 and not pending_tasks and quiet >= 1.0 and elapsed >= 0.8:
                        break
                    if hits <= 0 and not pending_tasks and elapsed >= 2.3:
                        break
                    await page.wait_for_timeout(180)
                if pending_tasks:
                    await asyncio.gather(*list(pending_tasks), return_exceptions=True)
                request_hits += hits
            except Exception:
                failed_route_count += 1
            finally:
                page.remove_listener("response", handle_response)
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
        "sample_total": len(target_urls),
        "visited_route_count": visited_route_count,
        "failed_route_count": failed_route_count,
        "request_hits": request_hits,
    }


async def probe_route_hash_style(
    *,
    route_urls: list[str],
    sample_size: int = 5,
    basepath_override: str = "",
    preferred_style: str = HASH_STYLE_SLASH,
    proxy_server: str = "",
) -> dict[str, Any]:
    sample_limit = max(1, min(int(sample_size or 1), 20))
    samples: list[str] = []
    seen_sample_keys: set[tuple[str, str, str, str, str]] = set()
    for raw in route_urls:
        parsed = urlsplit(str(raw or "").strip())
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"} or not parsed.netloc:
            continue
        key_path = parsed.path or "/"
        if len(key_path) > 1 and key_path.endswith("/"):
            key_path = key_path.rstrip("/")
        key_fragment = (parsed.fragment or "").strip()
        if key_fragment and not key_fragment.startswith("/"):
            key_fragment = f"/{key_fragment}"
        key = (scheme, parsed.netloc.lower(), key_path, parsed.query, key_fragment)
        if key in seen_sample_keys:
            continue
        seen_sample_keys.add(key)
        samples.append(urlunsplit((scheme, parsed.netloc, parsed.path or "/", parsed.query, parsed.fragment or "")))
        if len(samples) >= sample_limit:
            break

    if not samples:
        picked_style = normalize_hash_style(preferred_style)
        return {
            "picked_style": picked_style,
            "basepath_override": normalize_basepath(basepath_override),
            "sample_total": 0,
            "slash": {"sample_total": 0, "visited_route_count": 0, "failed_route_count": 0, "request_hits": 0},
            "plain": {"sample_total": 0, "visited_route_count": 0, "failed_route_count": 0, "request_hits": 0},
        }

    basepath = normalize_basepath(basepath_override)
    slash_score = await _probe_style_score(
        route_urls=samples,
        hash_style=HASH_STYLE_SLASH,
        basepath_override=basepath,
        proxy_server=proxy_server,
    )
    plain_score = await _probe_style_score(
        route_urls=samples,
        hash_style=HASH_STYLE_PLAIN,
        basepath_override=basepath,
        proxy_server=proxy_server,
    )

    picked_style = HASH_STYLE_SLASH
    if int(plain_score.get("request_hits") or 0) > int(slash_score.get("request_hits") or 0):
        picked_style = HASH_STYLE_PLAIN
    elif int(plain_score.get("request_hits") or 0) < int(slash_score.get("request_hits") or 0):
        picked_style = HASH_STYLE_SLASH
    else:
        plain_visited = int(plain_score.get("visited_route_count") or 0)
        slash_visited = int(slash_score.get("visited_route_count") or 0)
        if plain_visited > slash_visited:
            picked_style = HASH_STYLE_PLAIN
        elif plain_visited < slash_visited:
            picked_style = HASH_STYLE_SLASH
        else:
            picked_style = normalize_hash_style(preferred_style)

    return {
        "picked_style": picked_style,
        "basepath_override": basepath,
        "sample_total": len(samples),
        "slash": slash_score,
        "plain": plain_score,
    }


async def _goto_with_retry(page, url: str, max_attempts: int = 2) -> None:
    last_error: Exception | None = None
    candidates = _build_navigation_candidates(url)
    wait_modes = ("domcontentloaded", "commit")
    for candidate in candidates:
        for wait_mode in wait_modes:
            for attempt in range(1, max_attempts + 1):
                try:
                    await page.goto(candidate, wait_until=wait_mode, timeout=90000)
                    return
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    if attempt < max_attempts:
                        await page.wait_for_timeout(650 * attempt)
    if last_error:
        raise last_error


async def capture_route_requests(
    *,
    domain: str,
    route_urls: list[str],
    concurrency: int = 8,
    hash_style: str = HASH_STYLE_SLASH,
    basepath_override: str = "",
    proxy_server: str = "",
    progress_callback: Callable[..., None] | None = None,
    stop_check: Callable[[], bool] | None = None,
    pause_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    target_domain = str(domain or "").strip()
    if not target_domain:
        raise ValueError("domain is required")

    style = normalize_hash_style(hash_style)
    basepath = normalize_basepath(basepath_override)
    target_urls = rewrite_route_urls(
        route_urls,
        hash_style=style,
        basepath_override=basepath,
    )
    if not target_urls:
        raise ValueError("no route urls found for request capture")

    total_count = len(target_urls)
    worker_count = max(1, min(int(concurrency or 1), total_count))

    playwright, browser, context, page = await initialize_browser(proxy_server=proxy_server)
    worker_pages = [page]
    for _ in range(worker_count - 1):
        worker_pages.append(await context.new_page())

    queue: asyncio.Queue[str] = asyncio.Queue()
    for url in target_urls:
        queue.put_nowait(url)

    state_lock = asyncio.Lock()
    route_rows: dict[str, dict[str, Any]] = {}
    failed_routes: dict[str, str] = {}
    done_count = 0
    total_request_hits = 0

    def _should_stop() -> bool:
        if not stop_check:
            return False
        try:
            return bool(stop_check())
        except Exception:
            return False

    async def _wait_if_paused() -> None:
        if not pause_check:
            return
        while True:
            if _should_stop():
                return
            paused = False
            try:
                paused = bool(pause_check())
            except Exception:
                paused = False
            if not paused:
                return
            await asyncio.sleep(0.35)

    def _emit_progress(
        done: int,
        total_items: int,
        visited_route_count: int,
        failed_route_count: int,
        request_total: int,
        **context: Any,
    ) -> None:
        if not progress_callback:
            return
        try:
            progress_callback(
                int(done),
                int(total_items),
                int(visited_route_count),
                int(failed_route_count),
                int(request_total),
                **context,
            )
        except TypeError:
            progress_callback(
                int(done),
                int(total_items),
                int(visited_route_count),
                int(failed_route_count),
                int(request_total),
            )

    async def process_route(worker_page, route_url: str) -> None:
        nonlocal done_count, total_request_hits
        pending_tasks: set[asyncio.Task] = set()
        route_bucket: dict[tuple[str, str], dict[str, Any]] = {}
        route_chunks: set[str] = set()
        loop = asyncio.get_running_loop()
        last_seen = loop.time()
        saw_candidate = False

        async def handle_response_async(response) -> None:
            nonlocal last_seen, saw_candidate
            req = response.request
            if req is None:
                return
            req_url = _normalize_url(response.url)
            if not req_url:
                return

            method = str(req.method or "GET").upper()
            request_body = _extract_post_request_body(req, method)
            resource_type = str(req.resource_type or "").strip().lower()
            content_type = str((response.headers or {}).get("content-type", "")).split(";", 1)[0].strip().lower()
            request_headers = _filter_request_headers(getattr(req, "headers", {}))
            query_string, query_params = _extract_query_context(req_url)
            body_context = _parse_request_body_context(request_body, content_type)

            # Drop browser ping/beacon telemetry noise early.
            if resource_type in {"ping", "beacon"}:
                return

            if _is_js_chunk_like(req_url, content_type, resource_type):
                chunk_url = _normalize_chunk_url(req_url)
                if chunk_url:
                    route_chunks.add(chunk_url)
                last_seen = loop.time()

            if _is_static_like(req_url, content_type, resource_type):
                return
            if _is_ping_like(req_url):
                return

            if not _is_api_like(
                method=method,
                url=req_url,
                resource_type=resource_type,
                content_type=content_type,
            ):
                return

            key = (method, req_url)
            row = route_bucket.get(key)
            if row is None:
                row = {
                    "method": method,
                    "url": req_url,
                    "status": int(response.status or 0),
                    "resource_type": resource_type,
                    "content_type": content_type,
                    "count": 0,
                    "query_string": query_string,
                    "query_params": query_params,
                    "request_body": body_context.get("body_text", ""),
                    "body_type": str(body_context.get("body_type") or "empty"),
                    "body_json": body_context.get("body_json"),
                    "body_form": body_context.get("body_form"),
                    "request_headers": request_headers,
                }
                route_bucket[key] = row
            row["count"] = int(row.get("count") or 0) + 1
            row["status"] = int(response.status or row.get("status") or 0)
            if content_type:
                row["content_type"] = content_type
            if resource_type:
                row["resource_type"] = resource_type
            if query_string and not str(row.get("query_string") or "").strip():
                row["query_string"] = query_string
            if query_params and (
                not isinstance(row.get("query_params"), dict)
                or not row.get("query_params")
            ):
                row["query_params"] = query_params
            if request_body and not str(row.get("request_body") or "").strip():
                row["request_body"] = body_context.get("body_text", request_body)
                row["body_type"] = str(body_context.get("body_type") or "text")
                row["body_json"] = body_context.get("body_json")
                row["body_form"] = body_context.get("body_form")
            if request_headers and (
                not isinstance(row.get("request_headers"), dict)
                or not row.get("request_headers")
            ):
                row["request_headers"] = request_headers
            saw_candidate = True
            last_seen = loop.time()

        def handle_response(response) -> None:
            task = asyncio.create_task(handle_response_async(response))
            pending_tasks.add(task)
            task.add_done_callback(lambda done: pending_tasks.discard(done))

        worker_page.on("response", handle_response)
        try:
            _emit_progress(
                done_count,
                total_count,
                len(route_rows),
                len(failed_routes),
                total_request_hits,
                current_route_url=route_url,
                recent_chunks=[],
                recent_requests=[],
                route_status="running",
            )
            await _wait_if_paused()
            await _goto_with_retry(worker_page, route_url, max_attempts=2)
            try:
                await worker_page.wait_for_load_state("networkidle", timeout=7000)
            except PlaywrightTimeoutError:
                pass

            start = loop.time()
            min_wait = 0.8
            quiet_wait = 1.2
            max_wait = 12.0
            while True:
                await _wait_if_paused()
                if _should_stop():
                    break
                now = loop.time()
                elapsed = now - start
                quiet_elapsed = now - last_seen
                pending = bool(pending_tasks)

                if elapsed >= max_wait:
                    break
                if saw_candidate and (not pending) and elapsed >= min_wait and quiet_elapsed >= quiet_wait:
                    break
                if (not saw_candidate) and (not pending) and elapsed >= (min_wait + quiet_wait):
                    break
                await worker_page.wait_for_timeout(180)

            if pending_tasks:
                await asyncio.gather(*list(pending_tasks), return_exceptions=True)
        finally:
            worker_page.remove_listener("response", handle_response)

        async with state_lock:
            route_rows[route_url] = {
                "requests": route_bucket,
                "chunks": sorted(route_chunks),
            }
            done_count += 1
            total_request_hits += sum(int(item.get("count") or 0) for item in route_bucket.values())
            recent_requests = [
                str(item.get("url") or "").strip()
                for item in sorted(
                    route_bucket.values(),
                    key=lambda row: (-int(row.get("count") or 0), str(row.get("url") or "")),
                )
                if str(item.get("url") or "").strip()
            ][:3]
            recent_chunks = [str(item).strip() for item in sorted(route_chunks) if str(item).strip()][:3]
            _emit_progress(
                done_count,
                total_count,
                len(route_rows),
                len(failed_routes),
                total_request_hits,
                current_route_url=route_url,
                recent_chunks=recent_chunks,
                recent_requests=recent_requests,
                route_status="done",
            )

    async def worker_loop(worker_page) -> None:
        nonlocal done_count
        while True:
            await _wait_if_paused()
            if _should_stop():
                break
            try:
                route_url = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            try:
                await process_route(worker_page, route_url)
            except Exception as exc:  # noqa: BLE001
                async with state_lock:
                    failed_routes[route_url] = str(exc)
                    done_count += 1
                    _emit_progress(
                        done_count,
                        total_count,
                        len(route_rows),
                        len(failed_routes),
                        total_request_hits,
                        current_route_url=route_url,
                        recent_chunks=[],
                        recent_requests=[],
                        route_status="failed",
                        route_error=str(exc),
                    )
            finally:
                queue.task_done()

    try:
        await asyncio.gather(*(worker_loop(worker_page) for worker_page in worker_pages))
    finally:
        for extra_page in worker_pages[1:]:
            try:
                await extra_page.close()
            except Exception:
                pass
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

    route_items: list[dict[str, Any]] = []
    api_aggregate: dict[tuple[str, str], dict[str, Any]] = {}
    all_chunks: set[str] = set()
    chunk_route_map: dict[str, set[str]] = {}
    for route_url in target_urls:
        route_row = route_rows.get(route_url, {})
        bucket = route_row.get("requests", {}) if isinstance(route_row, dict) else {}
        chunk_urls = route_row.get("chunks", []) if isinstance(route_row, dict) else []
        chunks = [str(item).strip() for item in chunk_urls if str(item).strip()]
        for chunk_url in chunks:
            all_chunks.add(chunk_url)
            routes = chunk_route_map.setdefault(chunk_url, set())
            routes.add(route_url)
        request_items = sorted(
            [dict(item) for item in bucket.values()],
            key=lambda row: (-int(row.get("count") or 0), str(row.get("url") or "")),
        )
        route_items.append(
            {
                "route_url": route_url,
                "chunk_count": len(chunks),
                "chunks": chunks,
                "request_count": sum(int(item.get("count") or 0) for item in request_items),
                "unique_request_count": len(request_items),
                "requests": request_items,
            }
        )
        for item in request_items:
            method = str(item.get("method") or "GET").upper()
            req_url = str(item.get("url") or "").strip()
            if not req_url:
                continue
            agg_key = (method, req_url)
            agg = api_aggregate.get(agg_key)
            if agg is None:
                agg = {
                    "method": method,
                    "url": req_url,
                    "count": 0,
                    "route_count": 0,
                    "routes": [],
                    "status": int(item.get("status") or 0),
                    "resource_type": str(item.get("resource_type") or ""),
                    "content_type": str(item.get("content_type") or ""),
                    "query_string": str(item.get("query_string") or ""),
                    "query_params": item.get("query_params") if isinstance(item.get("query_params"), dict) else {},
                    "request_body": str(item.get("request_body") or ""),
                    "body_type": str(item.get("body_type") or "empty"),
                    "body_json": item.get("body_json"),
                    "body_form": item.get("body_form") if isinstance(item.get("body_form"), dict) else None,
                    "request_headers": (
                        item.get("request_headers") if isinstance(item.get("request_headers"), dict) else {}
                    ),
                }
                api_aggregate[agg_key] = agg
            agg["count"] = int(agg.get("count") or 0) + int(item.get("count") or 0)
            routes = agg.get("routes")
            if isinstance(routes, list) and route_url not in routes:
                routes.append(route_url)
                agg["route_count"] = len(routes)
            if not int(agg.get("status") or 0):
                agg["status"] = int(item.get("status") or 0)
            if not str(agg.get("content_type") or "").strip() and str(item.get("content_type") or "").strip():
                agg["content_type"] = str(item.get("content_type") or "")
            if not str(agg.get("resource_type") or "").strip() and str(item.get("resource_type") or "").strip():
                agg["resource_type"] = str(item.get("resource_type") or "")
            if not str(agg.get("query_string") or "").strip() and str(item.get("query_string") or "").strip():
                agg["query_string"] = str(item.get("query_string") or "")
            if (
                not isinstance(agg.get("query_params"), dict)
                or not agg.get("query_params")
            ) and isinstance(item.get("query_params"), dict):
                agg["query_params"] = item.get("query_params")
            if not str(agg.get("request_body") or "").strip() and str(item.get("request_body") or "").strip():
                agg["request_body"] = str(item.get("request_body") or "")
                agg["body_type"] = str(item.get("body_type") or "text")
                agg["body_json"] = item.get("body_json")
                agg["body_form"] = item.get("body_form") if isinstance(item.get("body_form"), dict) else None
            if (
                not isinstance(agg.get("request_headers"), dict)
                or not agg.get("request_headers")
            ) and isinstance(item.get("request_headers"), dict):
                agg["request_headers"] = item.get("request_headers")

    request_items = sorted(
        api_aggregate.values(),
        key=lambda row: (-int(row.get("count") or 0), str(row.get("url") or "")),
    )
    request_templates_map: dict[tuple[str, str], dict[str, Any]] = {}
    for item in request_items:
        method = str(item.get("method") or "GET").upper()
        req_url = str(item.get("url") or "").strip()
        if not req_url:
            continue
        parsed = urlsplit(req_url)
        path = _normalize_request_path(parsed.path or "/")
        template_key = (method, path)

        sample = {
            "url": req_url,
            "count": int(item.get("count") or 0),
            "route_count": int(item.get("route_count") or 0),
            "routes": list(item.get("routes") or []) if isinstance(item.get("routes"), list) else [],
            "status": int(item.get("status") or 0),
            "resource_type": str(item.get("resource_type") or ""),
            "content_type": str(item.get("content_type") or ""),
            "query_string": str(item.get("query_string") or ""),
            "query_params": item.get("query_params") if isinstance(item.get("query_params"), dict) else {},
            "request_body": str(item.get("request_body") or ""),
            "body_type": str(item.get("body_type") or "empty"),
            "body_json": item.get("body_json"),
            "body_form": item.get("body_form") if isinstance(item.get("body_form"), dict) else None,
            "request_headers": item.get("request_headers") if isinstance(item.get("request_headers"), dict) else {},
        }

        template = request_templates_map.get(template_key)
        if template is None:
            template = {
                "method": method,
                "path": path,
                "sample_count": 0,
                "total_count": 0,
                "samples": [],
            }
            request_templates_map[template_key] = template

        template["sample_count"] = int(template.get("sample_count") or 0) + 1
        template["total_count"] = int(template.get("total_count") or 0) + max(1, int(sample.get("count") or 0))
        samples = template.get("samples")
        if isinstance(samples, list):
            samples.append(sample)

    request_templates = sorted(
        request_templates_map.values(),
        key=lambda row: (
            -int(row.get("total_count") or 0),
            -int(row.get("sample_count") or 0),
            str(row.get("method") or ""),
            str(row.get("path") or ""),
        ),
    )
    for row in request_templates:
        samples = row.get("samples")
        if not isinstance(samples, list):
            row["samples"] = []
            row["best_sample"] = {}
            continue
        samples.sort(
            key=lambda sample: (
                -int(sample.get("count") or 0),
                -int(sample.get("route_count") or 0),
                str(sample.get("url") or ""),
            )
        )
        trimmed = samples[:REQUEST_TEMPLATE_MAX_SAMPLES]
        row["samples"] = trimmed
        row["best_sample"] = dict(trimmed[0]) if trimmed else {}

    output_dir = PROJECTS_DIR / target_domain / "vueRouter"
    output_dir.mkdir(parents=True, exist_ok=True)
    capture_file = output_dir / "request_capture.json"

    payload = {
        "generated_at": _utc_now_iso(),
        "domain": target_domain,
        "hash_style": style,
        "basepath_override": basepath,
        "stop_requested": bool(_should_stop()),
        "summary": {
            "route_total": total_count,
            "visited_route_count": len(route_rows),
            "failed_route_count": len(failed_routes),
            "chunk_unique_total": len(all_chunks),
            "request_total": sum(int(item.get("request_count") or 0) for item in route_items),
            "request_unique_total": len(request_items),
            "request_template_total": len(request_templates),
        },
        "routes": route_items,
        "requests": request_items,
        "request_templates": request_templates,
        "failed_routes": failed_routes,
    }
    capture_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    js_urls = sorted(all_chunks)
    js_file = output_dir / "js.txt"
    js_file.write_text("\n".join(js_urls), encoding="utf-8")

    manifest_file = output_dir / "download_manifest.json"
    manifest = {
        "summary": {
            "target_url_count": len(target_urls),
            "captured_script_count": len(js_urls),
            "downloaded_script_count": 0,
            "failed_script_count": 0,
            "failed_route_count": len(failed_routes),
        },
        "scripts": [
            {
                "url": chunk_url,
                "file_name": _build_chunk_file_name(chunk_url),
                "status": "captured",
                "source_routes": sorted(chunk_route_map.get(chunk_url, set())),
                "error": "",
            }
            for chunk_url in js_urls
        ],
    }
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "domain": target_domain,
        "capture_file": str(capture_file),
        "js_file": str(js_file),
        "manifest_file": str(manifest_file),
        "hash_style": style,
        "basepath_override": basepath,
        "route_total": int(payload["summary"]["route_total"]),
        "visited_route_count": int(payload["summary"]["visited_route_count"]),
        "failed_route_count": int(payload["summary"]["failed_route_count"]),
        "request_total": int(payload["summary"]["request_total"]),
        "request_unique_total": int(payload["summary"]["request_unique_total"]),
        "chunk_unique_total": int(payload["summary"]["chunk_unique_total"]),
        "failed_routes": failed_routes,
    }
