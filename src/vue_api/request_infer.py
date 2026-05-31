from __future__ import annotations

import re
from typing import Any, Callable
from urllib.parse import urlsplit

from src.vue_api.requester import compose_request_url
from src.vue_chunk.request_capture import load_captured_request_items


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


def normalize_url_path(value: str) -> str:
    # 统一把 URL / path 规整成无重复斜杠、无尾斜杠的路径形式。
    raw = _safe_text(value)
    if not raw:
        return ""
    parsed = urlsplit(raw)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        path = _safe_text(parsed.path, "/")
    else:
        path = _safe_text(raw.split("?", 1)[0])
    if not path:
        return ""
    if not path.startswith("/"):
        path = f"/{path}"
    path = re.sub(r"/{2,}", "/", path)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return path


def split_path_segments(path_value: str) -> list[str]:
    normalized = normalize_url_path(path_value)
    if not normalized:
        return []
    return [segment for segment in normalized.split("/") if segment]


def path_is_suffix_by_segments(request_path: str, endpoint_path: str) -> bool:
    req_segments = split_path_segments(request_path)
    api_segments = split_path_segments(endpoint_path)
    if not req_segments or not api_segments:
        return False
    if len(req_segments) < len(api_segments):
        return False
    return req_segments[-len(api_segments) :] == api_segments


def normalize_endpoint_rows_for_infer(raw_items: Any) -> list[dict[str, Any]]:
    # 把 endpoint 列表规整成稳定的 {id, method, path} 结构，便于后续推断。
    if not isinstance(raw_items, list):
        return []

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for index, item in enumerate(raw_items, start=1):
        endpoint_id = index
        method = "GET"
        path_value = ""

        if isinstance(item, dict):
            endpoint_id_raw = _coerce_int(item.get("id"), default=0, minimum=0)
            if endpoint_id_raw > 0:
                endpoint_id = endpoint_id_raw
            method = _safe_text(item.get("method"), "GET").upper() or "GET"
            path_value = _safe_text(
                item.get("path")
                or item.get("api_path")
                or item.get("endpoint_path")
                or item.get("url")
            )
        else:
            path_value = _safe_text(item)

        if not path_value:
            continue

        path_display = path_value
        if path_display.startswith(("http://", "https://")):
            parsed = urlsplit(path_display)
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
                continue
            path_display = _safe_text(parsed.path, "/")
            if parsed.query:
                path_display = f"{path_display}?{parsed.query}"

        normalized = normalize_url_path(path_display)
        if not normalized:
            continue
        if "?" in path_display:
            query_text = _safe_text(path_display.split("?", 1)[1])
            if query_text:
                normalized = f"{normalized}?{query_text}"

        dedupe_key = (method, normalize_url_path(normalized))
        if not dedupe_key[1] or dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        rows.append(
            {
                "id": endpoint_id,
                "method": method,
                "path": normalized,
            }
        )

    return rows


def infer_request_base(
    domain: str,
    *,
    load_api_endpoints: Callable[[str], list[Any]],
    serialize_api_endpoint: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    # 从项目 endpoints.json 读取接口后，复用统一的 baseurl/baseapi 推断流程。
    token = _safe_text(domain)
    if not token:
        raise ValueError("domain is required")
    try:
        endpoints = load_api_endpoints(token)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"api endpoints not found for domain: {token}") from exc
    endpoint_rows = normalize_endpoint_rows_for_infer([serialize_api_endpoint(item) for item in endpoints])
    return infer_request_base_from_endpoint_rows(token, endpoint_rows)


def infer_request_base_from_paths(domain: str, raw_paths: Any) -> dict[str, Any]:
    # 允许直接拿路径列表做推断，给 API 接口和后台流程共用。
    token = _safe_text(domain)
    if not token:
        raise ValueError("domain is required")
    endpoint_rows = normalize_endpoint_rows_for_infer(raw_paths)
    if not endpoint_rows:
        raise ValueError("api path list is empty")
    return infer_request_base_from_endpoint_rows(token, endpoint_rows)


def infer_request_base_from_endpoint_rows(domain: str, endpoint_rows: list[dict[str, Any]]) -> dict[str, Any]:
    # 根据 endpoint path 和 capture 请求样本，反推出最可能的 baseurl/baseapi 组合。
    token = _safe_text(domain)
    if not token:
        raise ValueError("domain is required")
    if not endpoint_rows:
        raise ValueError("api endpoint list is empty")

    captured_rows = load_captured_request_items(token)
    if not captured_rows:
        raise FileNotFoundError("request capture result is empty, please run request capture first")

    candidates: dict[tuple[str, str], dict[str, Any]] = {}

    for endpoint_index, endpoint in enumerate(endpoint_rows):
        endpoint_path = _safe_text(endpoint.get("path"))
        endpoint_match_path = normalize_url_path(endpoint_path)
        if not endpoint_match_path:
            continue

        best_match: dict[str, Any] | None = None
        for capture in captured_rows:
            capture_url = _safe_text(capture.get("url"))
            if not capture_url:
                continue
            parsed = urlsplit(capture_url)
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
                continue
            capture_path = normalize_url_path(capture_url)
            if not path_is_suffix_by_segments(capture_path, endpoint_match_path):
                continue

            req_segments = split_path_segments(capture_path)
            api_segments = split_path_segments(endpoint_match_path)
            prefix_segments = (
                req_segments[: len(req_segments) - len(api_segments)]
                if len(req_segments) >= len(api_segments)
                else []
            )
            baseapi = "/" + "/".join(prefix_segments) if prefix_segments else ""
            weight = _coerce_int(capture.get("count"), default=1, minimum=1)
            candidate = {
                "baseurl": f"{parsed.scheme.lower()}://{parsed.netloc}",
                "baseapi": baseapi,
                "weight": weight,
                "capture": capture,
                "endpoint": endpoint,
            }
            if best_match is None or weight > _coerce_int(best_match.get("weight"), default=1, minimum=1):
                best_match = candidate

        if not best_match:
            continue

        key = (_safe_text(best_match.get("baseurl")), _safe_text(best_match.get("baseapi")))
        if not key[0]:
            continue
        current = candidates.get(key)
        if current is None:
            candidates[key] = {
                "baseurl": key[0],
                "baseapi": key[1],
                "score": _coerce_int(best_match.get("weight"), default=1, minimum=1),
                "match_count": 1,
                "first_endpoint_index": endpoint_index,
                "matched_capture": best_match.get("capture"),
                "matched_endpoint": best_match.get("endpoint"),
            }
            continue

        current["score"] = _coerce_int(current.get("score"), default=0, minimum=0) + _coerce_int(
            best_match.get("weight"),
            default=1,
            minimum=1,
        )
        current["match_count"] = _coerce_int(current.get("match_count"), default=0, minimum=0) + 1
        if endpoint_index < _coerce_int(current.get("first_endpoint_index"), default=999999, minimum=0):
            current["first_endpoint_index"] = endpoint_index
            current["matched_capture"] = best_match.get("capture")
            current["matched_endpoint"] = best_match.get("endpoint")

    if not candidates:
        return {
            "domain": token,
            "inferred": False,
            "baseurl": "",
            "baseapi": "",
            "captured_request_count": len(captured_rows),
            "endpoint_count": len(endpoint_rows),
            "matched": {},
            "compose_preview": [],
            "error": "no captured request matches current api paths",
        }

    selected = sorted(
        candidates.values(),
        key=lambda row: (
            -_coerce_int(row.get("match_count"), default=0, minimum=0),
            -_coerce_int(row.get("score"), default=0, minimum=0),
            -len(_safe_text(row.get("baseapi"))),
            _coerce_int(row.get("first_endpoint_index"), default=999999, minimum=0),
            _safe_text(row.get("baseurl")),
        ),
    )[0]

    selected_baseurl = _safe_text(selected.get("baseurl"))
    selected_baseapi = _safe_text(selected.get("baseapi"))
    matched_capture = selected.get("matched_capture") if isinstance(selected.get("matched_capture"), dict) else {}
    matched_endpoint = selected.get("matched_endpoint") if isinstance(selected.get("matched_endpoint"), dict) else {}

    compose_preview: list[dict[str, Any]] = []
    for endpoint in endpoint_rows:
        endpoint_path = _safe_text(endpoint.get("path"))
        compose_preview.append(
            {
                "id": _coerce_int(endpoint.get("id"), default=0, minimum=0),
                "method": _safe_text(endpoint.get("method"), "GET").upper(),
                "path": endpoint_path,
                "url": compose_request_url(selected_baseurl, selected_baseapi, endpoint_path),
            }
        )

    return {
        "domain": token,
        "inferred": True,
        "baseurl": selected_baseurl,
        "baseapi": selected_baseapi,
        "captured_request_count": len(captured_rows),
        "endpoint_count": len(endpoint_rows),
        "matched": {
            "endpoint_id": _coerce_int(matched_endpoint.get("id"), default=0, minimum=0),
            "endpoint_method": _safe_text(matched_endpoint.get("method"), "GET").upper(),
            "endpoint_path": _safe_text(matched_endpoint.get("path")),
            "request_url": _safe_text(matched_capture.get("url")),
            "request_method": _safe_text(matched_capture.get("method"), "GET").upper(),
            "request_count": _coerce_int(matched_capture.get("count"), default=1, minimum=1),
        },
        "compose_preview": compose_preview,
        "error": "",
    }
