from __future__ import annotations

import re
from typing import Any, Callable


_KEYWORD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Object", re.compile(r"object\s*\(", re.IGNORECASE)),
    ("return", re.compile(r"\breturn\b", re.IGNORECASE)),
    ("function", re.compile(r"\bfunction\b", re.IGNORECASE)),
    ("this", re.compile(r"\bthis\b", re.IGNORECASE)),
    ("get", re.compile(r"(?:\.\s*get\b|\bget\s*\()", re.IGNORECASE)),
    ("post", re.compile(r"(?:\.\s*post\b|\bpost\s*\()", re.IGNORECASE)),
    ("url", re.compile(r"\burl\b", re.IGNORECASE)),
    ("path", re.compile(r"\bpath\b", re.IGNORECASE)),
]


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _normalize_method(value: Any) -> str:
    token = _safe_str(value).upper()
    return token or "GET"


def _match_keyword(snippet: str) -> str:
    text = _safe_str(snippet)
    if not text:
        return ""
    for label, pattern in _KEYWORD_PATTERNS:
        if pattern.search(text):
            return label
    return ""


def _pick_gate_hit(hits: list[dict[str, Any]]) -> dict[str, Any]:
    for row in hits:
        if not isinstance(row, dict):
            continue
        snippet = _safe_str(row.get("snippet"))
        keyword = _match_keyword(snippet)
        if not keyword:
            continue
        return {
            "keyword": keyword,
            "js_api_path": snippet,
            "file_name": _safe_str(row.get("file_name")),
            "matched_path": _safe_str(row.get("matched_path")),
            "line": int(row.get("line") or 0),
            "chunk_url": _safe_str(row.get("chunk_url")),
        }
    return {}


def select_auto_pipeline_js_api_path(
    *,
    domain: str,
    load_captured_request_items: Callable[[str], list[dict[str, Any]]],
    locate_request_in_chunks: Callable[..., dict[str, Any]],
    max_api_items: int = 240,
    max_locate_files: int = 120,
    max_locate_results: int = 40,
) -> dict[str, Any]:
    token = _safe_str(domain)
    if not token:
        raise ValueError("domain is required")

    api_rows = load_captured_request_items(token)
    scanned_api_count = 0

    for item in api_rows[: max(1, int(max_api_items))]:
        if not isinstance(item, dict):
            continue
        request_url = _safe_str(item.get("url"))
        if not request_url:
            continue

        scanned_api_count += 1
        method = _normalize_method(item.get("method"))
        route_url = _safe_str(item.get("route_url"))
        locate_payload = locate_request_in_chunks(
            domain=token,
            request_url=request_url,
            method=method,
            route_url=route_url,
            scan_scope="auto",
            max_files=max(1, int(max_locate_files)),
            max_results=max(1, int(max_locate_results)),
        )
        hits = locate_payload.get("hits") if isinstance(locate_payload, dict) else []
        picked = _pick_gate_hit(hits if isinstance(hits, list) else [])
        if not picked:
            continue

        return {
            "selected": True,
            "domain": token,
            "request_url": request_url,
            "method": method,
            "route_url": route_url,
            "keyword": _safe_str(picked.get("keyword")),
            "js_api_path": _safe_str(picked.get("js_api_path")),
            "matched_path": _safe_str(picked.get("matched_path")),
            "file_name": _safe_str(picked.get("file_name")),
            "line": int(picked.get("line") or 0),
            "chunk_url": _safe_str(picked.get("chunk_url")),
            "hit_total": len(hits) if isinstance(hits, list) else 0,
            "scanned_api_count": scanned_api_count,
        }

    return {
        "selected": False,
        "domain": token,
        "request_url": "",
        "method": "",
        "route_url": "",
        "keyword": "",
        "js_api_path": "",
        "matched_path": "",
        "file_name": "",
        "line": 0,
        "chunk_url": "",
        "hit_total": 0,
        "scanned_api_count": scanned_api_count,
        "error": "no locate-js hit matched Object/return/function/this/get/post/url/path",
    }


__all__ = ["select_auto_pipeline_js_api_path"]
