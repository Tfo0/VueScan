from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request as UrlRequest

from src.http_utils import safe_urlopen
from src.vue_api.api_chunk import auto_regex_snippet

from config import PROJECTS_DIR


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _normalize_method(value: Any) -> str:
    method = _safe_str(value).upper()
    return method or "GET"


def _normalize_path(raw_url: str) -> str:
    value = _safe_str(raw_url)
    if not value:
        return ""

    parsed = urlsplit(value)
    if parsed.scheme and parsed.netloc:
        path = _safe_str(parsed.path, "/")
    else:
        text = value.split("#", 1)[0].split("?", 1)[0].strip()
        path = text
    if not path:
        return ""
    if not path.startswith("/"):
        path = f"/{path}"
    path = re.sub(r"/{2,}", "/", path)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return path


def _build_path_candidates(request_path: str) -> list[str]:
    path = _safe_str(request_path)
    if not path:
        return []
    if not path.startswith("/"):
        path = f"/{path}"
    parts = [part for part in path.split("/") if part]
    if not parts:
        return ["/"]
    candidates: list[str] = []
    for idx in range(len(parts)):
        token = "/" + "/".join(parts[idx:])
        if token not in candidates:
            candidates.append(token)
    return candidates


def _build_term_candidates(path_candidate: str) -> list[str]:
    token = _safe_str(path_candidate)
    if not token:
        return []
    terms: list[str] = []
    if token:
        terms.extend([f'"{token}"', f"'{token}'", f"`{token}`", token])
    if token.startswith("/") and len(token) > 1:
        plain = token[1:]
        terms.extend([f'"{plain}"', f"'{plain}'", f"`{plain}`", plain])
    ordered: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            ordered.append(term)
    return ordered


def _load_request_capture(domain: str) -> dict[str, Any]:
    token = _safe_str(domain)
    if not token:
        return {}
    capture_file = PROJECTS_DIR / token / "vueRouter" / "request_capture.json"
    if not capture_file.is_file():
        return {}
    try:
        payload = json.loads(capture_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _iter_down_chunk_files(domain: str) -> list[Path]:
    token = _safe_str(domain)
    if not token:
        return []
    chunk_dir = PROJECTS_DIR / token / "downChunk"
    if not chunk_dir.is_dir():
        return []
    return sorted([item for item in chunk_dir.glob("*.js") if item.is_file()], key=lambda p: p.name.lower())


def _chunk_dir_path(domain: str) -> Path:
    token = _safe_str(domain)
    return PROJECTS_DIR / token / "downChunk"


def _normalize_chunk_fetch_url(raw_url: str) -> str:
    value = _safe_str(raw_url)
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path or "/"
    path = re.sub(r"/{2,}", "/", path)
    return f"{parsed.scheme.lower()}://{parsed.netloc}{path}"


def _build_remote_cache_file_name(chunk_url: str) -> str:
    normalized = _normalize_chunk_fetch_url(chunk_url) or _safe_str(chunk_url)
    parsed = urlsplit(normalized)
    base_name = Path(parsed.path or "").name or "script.js"
    if not base_name.lower().endswith(".js"):
        base_name = f"{base_name}.js"
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", base_name)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    return f"{digest}_{safe_name}"


def _load_or_fetch_remote_chunk(domain: str, chunk_url: str, *, timeout: int = 20, max_bytes: int = 4 * 1024 * 1024) -> tuple[str, str]:
    normalized = _normalize_chunk_fetch_url(chunk_url)
    if not normalized:
        return "", ""

    chunk_dir = _chunk_dir_path(domain)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    file_name = _build_remote_cache_file_name(normalized)
    file_path = chunk_dir / file_name

    if file_path.is_file() and file_path.stat().st_size > 0:
        try:
            return file_name, file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass

    try:
        req = UrlRequest(normalized, headers={"User-Agent": "Mozilla/5.0"})
        with safe_urlopen(req, timeout=max(1, int(timeout))) as response:
            body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            return "", ""
        text = body.decode("utf-8", errors="ignore")
        if not text.strip():
            return "", ""
        file_path.write_text(text, encoding="utf-8")
        return file_name, text
    except Exception:
        return "", ""


def _build_manifest_maps(domain: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    token = _safe_str(domain)
    exact: dict[str, str] = {}
    basename_map: dict[str, list[str]] = {}
    files = _iter_down_chunk_files(token)
    file_names = [path.name for path in files]
    for file_name in file_names:
        lowered = file_name.lower()
        basename_map.setdefault(lowered, []).append(file_name)
        if "_" in lowered:
            tail = lowered.split("_", 1)[1]
            basename_map.setdefault(tail, []).append(file_name)

    manifest_path = PROJECTS_DIR / token / "vueRouter" / "download_manifest.json"
    if not manifest_path.is_file():
        return exact, basename_map
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return exact, basename_map
    if not isinstance(payload, dict):
        return exact, basename_map

    scripts = payload.get("scripts", [])
    if not isinstance(scripts, list):
        return exact, basename_map

    for item in scripts:
        if not isinstance(item, dict):
            continue
        url = _safe_str(item.get("url"))
        file_name = _safe_str(item.get("file_name"))
        if not url or not file_name:
            continue
        exact[url] = file_name
        parsed = urlsplit(url)
        base = Path(parsed.path).name.lower()
        if base:
            basename_map.setdefault(base, []).append(file_name)
    return exact, basename_map


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        token = _safe_str(item)
        key = token.lower()
        if not token or key in seen:
            continue
        seen.add(key)
        result.append(token)
    return result


def _resolve_chunk_files(
    chunk_urls: list[str],
    exact_url_map: dict[str, str],
    basename_map: dict[str, list[str]],
    available_files: list[str],
) -> tuple[list[str], dict[str, list[str]]]:
    chunk_to_files: dict[str, list[str]] = {}
    resolved: list[str] = []
    available_set = {item.lower() for item in available_files}
    for raw_url in chunk_urls:
        chunk_url = _safe_str(raw_url)
        if not chunk_url:
            continue
        candidates: list[str] = []
        exact_match = _safe_str(exact_url_map.get(chunk_url))
        if exact_match:
            candidates.append(exact_match)

        parsed = urlsplit(chunk_url)
        basename = Path(parsed.path).name.lower()
        if basename:
            candidates.extend(basename_map.get(basename, []))
        if chunk_url.lower() in basename_map:
            candidates.extend(basename_map.get(chunk_url.lower(), []))

        existing: list[str] = []
        for file_name in _dedupe(candidates):
            if file_name.lower() in available_set:
                existing.append(file_name)
        chunk_to_files[chunk_url] = existing
        resolved.extend(existing)
    return _dedupe(resolved), chunk_to_files


def _build_route_rows(routes_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in routes_data:
        if not isinstance(item, dict):
            continue
        route_url = _safe_str(item.get("route_url"))
        requests_data = item.get("requests", [])
        chunks_data = item.get("chunks", [])
        requests = [entry for entry in requests_data if isinstance(entry, dict)] if isinstance(requests_data, list) else []
        chunks = [str(entry).strip() for entry in chunks_data if str(entry).strip()] if isinstance(chunks_data, list) else []
        request_total = 0
        for req in requests:
            try:
                request_total += max(1, int(req.get("count") or 1))
            except Exception:
                request_total += 1
        rows.append(
            {
                "route_url": route_url,
                "chunk_count": len(chunks),
                "request_count": request_total,
                "unique_request_count": len(requests),
                "chunks": chunks,
                "requests": requests,
            }
        )
    return rows


def _find_related_routes(
    route_rows: list[dict[str, Any]],
    request_url: str,
    request_path: str,
    method: str,
    route_url_hint: str,
) -> list[dict[str, Any]]:
    method_token = _normalize_method(method)
    path_token = _safe_str(request_path)
    request_url_token = _safe_str(request_url)
    route_hint = _safe_str(route_url_hint)

    matched: list[dict[str, Any]] = []
    for row in route_rows:
        row_route = _safe_str(row.get("route_url"))
        if route_hint and row_route != route_hint:
            continue
        requests = row.get("requests", [])
        if not isinstance(requests, list):
            continue
        hit = False
        for req in requests:
            if not isinstance(req, dict):
                continue
            req_method = _normalize_method(req.get("method"))
            if method_token and req_method != method_token:
                continue
            req_url = _safe_str(req.get("url"))
            if not req_url:
                continue
            req_path = _normalize_path(req_url)
            if request_url_token and req_url == request_url_token:
                hit = True
                break
            if path_token and req_path == path_token:
                hit = True
                break
        if hit:
            matched.append(row)

    if matched:
        return matched
    if route_hint:
        return _find_related_routes(route_rows, request_url, request_path, method, "")

    fallback: list[dict[str, Any]] = []
    for row in route_rows:
        requests = row.get("requests", [])
        if not isinstance(requests, list):
            continue
        for req in requests:
            if not isinstance(req, dict):
                continue
            req_method = _normalize_method(req.get("method"))
            if method_token and req_method != method_token:
                continue
            req_path = _normalize_path(_safe_str(req.get("url")))
            if path_token and req_path and path_token.endswith(req_path):
                fallback.append(row)
                break
            if path_token and req_path and req_path.endswith(path_token):
                fallback.append(row)
                break
    return fallback


def _resolve_locate_hit(text: str, path_candidate: str, term: str, hit_index: int) -> tuple[int, str]:
    # Locate JS 要围绕真实 api_path 截断，而不是围绕带引号的 term 截断。
    source = str(text or "")
    path_token = _safe_str(path_candidate)
    term_token = _safe_str(term)
    index = max(0, int(hit_index))

    direct_offset = term_token.find(path_token) if path_token else -1
    if direct_offset >= 0:
        return index + direct_offset, path_token

    plain_token = path_token.lstrip("/")
    if plain_token:
        plain_offset = term_token.find(plain_token)
        if plain_offset >= 0:
            return index + plain_offset, plain_token

    search_tokens = [token for token in (path_token, plain_token, term_token.strip("\"'`")) if token]
    for token in search_tokens:
        found = source.find(token, index, min(len(source), index + len(term_token) + 4))
        if found >= 0:
            return found, token
    return index, term_token or path_token


def _find_hits_in_text(
    *,
    text: str,
    file_name: str,
    request_path_candidates: list[str],
    max_hits_per_file: int = 4,
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for path_candidate in request_path_candidates:
        terms = _build_term_candidates(path_candidate)
        matched_this_candidate = False
        for term in terms:
            start = 0
            while True:
                idx = text.find(term, start)
                if idx < 0:
                    break
                path_index, snippet_token = _resolve_locate_hit(text, path_candidate, term, idx)
                row = {
                    "file_name": file_name,
                    "matched_path": path_candidate,
                    "line": int(text.count("\n", 0, path_index)) + 1,
                    "snippet": auto_regex_snippet(text, path_index, snippet_token),
                }
                hits.append(row)
                matched_this_candidate = True
                if len(hits) >= max_hits_per_file:
                    return hits
                start = idx + max(1, len(term))
        if matched_this_candidate:
            return hits
    return hits


def _dedupe_hits(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = (
            _safe_str(row.get("file_name")).lower(),
            _safe_str(row.get("matched_path")),
            int(row.get("line") or 0),
            _safe_str(row.get("snippet")),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _hit_snippet_priority(row: dict[str, Any]) -> tuple[int, int, str, int]:
    snippet = _safe_str(row.get("snippet"))
    lower = snippet.lower()
    marker_patterns: list[tuple[str, re.Pattern[str]]] = [
        ("object", re.compile(r"object\s*\(", re.IGNORECASE)),
        ("return", re.compile(r"\breturn\b", re.IGNORECASE)),
        ("function", re.compile(r"\bfunction\b", re.IGNORECASE)),
        ("this", re.compile(r"\bthis\b", re.IGNORECASE)),
        ("get", re.compile(r"(?:\.\s*get\b|\bget\s*\()", re.IGNORECASE)),
        ("post", re.compile(r"(?:\.\s*post\b|\bpost\s*\()", re.IGNORECASE)),
        ("url", re.compile(r"\burl\b", re.IGNORECASE)),
        ("path", re.compile(r"\bpath\b", re.IGNORECASE)),
    ]
    priority_index = len(marker_patterns)
    for idx, (_, pattern) in enumerate(marker_patterns):
        if pattern.search(lower):
            priority_index = idx
            break
    return (
        priority_index,
        int(row.get("line") or 0),
        _safe_str(row.get("file_name")).lower(),
        0,
    )


def _fallback_file_order(files: list[str]) -> list[str]:
    keywords = ("app", "main", "vendor", "chunk-vendors", "index")
    return sorted(
        files,
        key=lambda name: (
            0 if any(token in name.lower() for token in keywords) else 1,
            name.lower(),
        ),
    )


def _collect_all_chunk_urls(route_rows: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for row in route_rows:
        chunks = row.get("chunks", [])
        if not isinstance(chunks, list):
            continue
        for chunk in chunks:
            token = _safe_str(chunk)
            if token:
                urls.append(token)
    return _dedupe(urls)


def locate_request_in_chunks(
    *,
    domain: str,
    request_url: str,
    method: str = "",
    route_url: str = "",
    scan_scope: str = "auto",
    max_files: int = 240,
    max_results: int = 80,
) -> dict[str, Any]:
    token = _safe_str(domain)
    if not token:
        raise ValueError("domain is required")

    request_url_token = _safe_str(request_url)
    if not request_url_token:
        raise ValueError("request_url is required")

    capture_payload = _load_request_capture(token)
    routes_data = capture_payload.get("routes", []) if isinstance(capture_payload, dict) else []
    route_rows = _build_route_rows(routes_data if isinstance(routes_data, list) else [])

    request_path = _normalize_path(request_url_token)
    path_candidates = _build_path_candidates(request_path)
    method_token = _normalize_method(method)
    scope_token = _safe_str(scan_scope, "auto").lower()
    if scope_token not in {"auto", "related", "global"}:
        scope_token = "auto"

    related_routes = _find_related_routes(
        route_rows=route_rows,
        request_url=request_url_token,
        request_path=request_path,
        method=method_token,
        route_url_hint=route_url,
    )

    related_chunk_urls: list[str] = []
    for row in related_routes:
        chunks = row.get("chunks", [])
        if isinstance(chunks, list):
            related_chunk_urls.extend([_safe_str(item) for item in chunks if _safe_str(item)])
    related_chunk_urls = _dedupe(related_chunk_urls)

    should_global_scan = False
    if scope_token == "global":
        should_global_scan = True
    elif scope_token == "auto":
        if (not _safe_str(route_url)) and (not related_routes):
            should_global_scan = True

    if should_global_scan:
        related_chunk_urls = _collect_all_chunk_urls(route_rows)

    down_chunk_files = _iter_down_chunk_files(token)
    down_chunk_file_names = [path.name for path in down_chunk_files]
    exact_url_map, basename_map = _build_manifest_maps(token)
    resolved_files, chunk_to_files = _resolve_chunk_files(
        chunk_urls=related_chunk_urls,
        exact_url_map=exact_url_map,
        basename_map=basename_map,
        available_files=down_chunk_file_names,
    )

    file_candidates = _dedupe(resolved_files)
    if should_global_scan:
        file_candidates = _fallback_file_order(down_chunk_file_names)
    elif not file_candidates:
        file_candidates = _fallback_file_order(down_chunk_file_names)

    max_files_value = max(1, int(max_files))
    max_results_value = max(1, int(max_results))
    if should_global_scan:
        # Global mode scans all local + all captured remote chunks.
        max_files_value = max(max_files_value, len(file_candidates) + len(related_chunk_urls))
    else:
        file_candidates = file_candidates[:max_files_value]

    candidate_pool_keys: set[str] = {name.lower() for name in file_candidates if _safe_str(name)}
    for chunk_url in related_chunk_urls:
        remote_name = _build_remote_cache_file_name(chunk_url)
        if remote_name:
            candidate_pool_keys.add(remote_name.lower())
        else:
            token_key = _safe_str(chunk_url).lower()
            if token_key:
                candidate_pool_keys.add(token_key)

    file_map = {path.name: path for path in down_chunk_files}
    reverse_chunk_map: dict[str, list[str]] = {}
    for chunk_url, names in chunk_to_files.items():
        for name in names:
            reverse_chunk_map.setdefault(name, []).append(chunk_url)

    hits: list[dict[str, Any]] = []
    scanned_files = 0
    scanned_name_keys: set[str] = set()
    for file_name in file_candidates:
        path = file_map.get(file_name)
        if path is None or (not path.is_file()):
            continue
        scanned_name_keys.add(file_name.lower())
        scanned_files += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        file_hits = _find_hits_in_text(
            text=text,
            file_name=file_name,
            request_path_candidates=path_candidates,
            max_hits_per_file=4,
        )
        for hit in file_hits:
            chunk_urls = reverse_chunk_map.get(file_name, [])
            if chunk_urls:
                hit["chunk_url"] = chunk_urls[0]
            hits.append(hit)
            if len(hits) >= max_results_value:
                break
        if len(hits) >= max_results_value:
            break

    remote_scanned_files = 0
    remote_hit_files = 0
    if len(hits) < max_results_value and related_chunk_urls:
        for chunk_url in related_chunk_urls:
            if scanned_files >= max_files_value:
                break
            file_name, text = _load_or_fetch_remote_chunk(token, chunk_url)
            if not file_name or not text:
                continue
            file_key = file_name.lower()
            if file_key in scanned_name_keys:
                continue
            scanned_name_keys.add(file_key)
            scanned_files += 1
            remote_scanned_files += 1

            file_hits = _find_hits_in_text(
                text=text,
                file_name=file_name,
                request_path_candidates=path_candidates,
                max_hits_per_file=4,
            )
            if file_hits:
                remote_hit_files += 1
            for hit in file_hits:
                hit["chunk_url"] = chunk_url
                hits.append(hit)
                if len(hits) >= max_results_value:
                    break
            if len(hits) >= max_results_value:
                break

    related_route_rows: list[dict[str, Any]] = []
    for row in related_routes[:80]:
        related_route_rows.append(
            {
                "route_url": _safe_str(row.get("route_url")),
                "chunk_count": int(row.get("chunk_count") or 0),
                "request_count": int(row.get("request_count") or 0),
                "unique_request_count": int(row.get("unique_request_count") or 0),
            }
        )

    hits = _dedupe_hits(hits)
    hits.sort(key=_hit_snippet_priority)

    return {
        "domain": token,
        "request_url": request_url_token,
        "request_path": request_path,
        "method": method_token,
        "scan_scope": "global" if should_global_scan else ("related" if scope_token == "related" else "auto"),
        "path_candidates": path_candidates,
        "related_route_total": len(related_routes),
        "related_chunk_total": len(related_chunk_urls),
        "candidate_file_total": len(candidate_pool_keys),
        "scanned_file_total": scanned_files,
        "remote_scanned_file_total": remote_scanned_files,
        "remote_hit_file_total": remote_hit_files,
        "hit_total": len(hits),
        "hits": hits,
        "related_routes": related_route_rows,
    }
