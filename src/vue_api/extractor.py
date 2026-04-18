from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request as UrlRequest

from src.http_utils import safe_urlopen

from config import PROJECTS_DIR
from src.vue_api.models import ApiEndpoint


API_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}


def _normalize_method(value: str | None) -> str:
    method = (value or "GET").strip().upper()
    if method not in API_METHODS:
        return "GET"
    return method


def _clean_token(value: str | None) -> str:
    token = (value or "").strip()
    if not token:
        return ""

    token = token.rstrip(",;)")
    if len(token) >= 2:
        if token[0] == token[-1] and token[0] in {"'", '"', "`"}:
            token = token[1:-1].strip()
    return token


def _looks_like_method(value: str) -> bool:
    return value.strip().upper() in API_METHODS


def _extract_method_path(match: re.Match[str]) -> tuple[str, str]:
    group_map = match.groupdict()
    method = ""
    path = ""

    for key in ("method", "http_method"):
        if key in group_map and group_map[key]:
            method = _clean_token(group_map[key])
            break

    for key in ("path", "url", "api", "endpoint"):
        if key in group_map and group_map[key]:
            path = _clean_token(group_map[key])
            break

    groups = [g for g in match.groups() if g is not None]
    if not path and groups:
        first = _clean_token(groups[0])
        if _looks_like_method(first) and len(groups) >= 2:
            method = method or first
            path = _clean_token(groups[1])
        else:
            path = first

    if not path:
        path = _clean_token(match.group(0))

    method = _normalize_method(method)
    return method, path


def _build_full_url(baseurl: str, baseapi: str, path: str) -> str:
    raw_path = (path or "").strip()
    if raw_path.startswith(("http://", "https://")):
        return raw_path

    normalized_baseurl = (baseurl or "").strip().rstrip("/")
    normalized_baseapi = (baseapi or "").strip()
    normalized_path = raw_path.lstrip("/")

    prefix = normalized_baseapi.strip("/")
    if prefix:
        target = f"{prefix}/{normalized_path}" if normalized_path else prefix
    else:
        target = normalized_path

    if normalized_baseurl:
        if target:
            return f"{normalized_baseurl}/{target}"
        return normalized_baseurl

    return "/" + target if target else raw_path


def _iter_chunk_files(chunk_dir: Path) -> Iterable[Path]:
    return sorted(path for path in chunk_dir.glob("*.js") if path.is_file())


def _iter_js_urls_from_router(domain: str) -> list[str]:
    path = PROJECTS_DIR / domain / "vueRouter" / "js.txt"
    if not path.is_file():
        return []
    seen: set[str] = set()
    result: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        url = line.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        result.append(url)
    return result


def _normalize_js_url_for_dedupe(raw_url: str) -> str:
    value = (raw_url or "").strip()
    if not value:
        return ""

    parsed = urlsplit(value)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        path = parsed.path or "/"
        path = re.sub(r"/{2,}", "/", path)
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))

    return value.split("#", 1)[0].split("?", 1)[0].strip()


def _iter_effective_js_urls_from_router(domain: str) -> list[str]:
    raw_urls = _iter_js_urls_from_router(domain)
    seen: set[str] = set()
    result: list[str] = []
    for js_url in raw_urls:
        key = _normalize_js_url_for_dedupe(js_url)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(js_url)
    return result


def _load_local_cached_js_url_keys(domain: str) -> set[str]:
    token = (domain or "").strip()
    if not token:
        return set()

    down_chunk_dir = PROJECTS_DIR / token / "downChunk"
    manifest_file = PROJECTS_DIR / token / "vueRouter" / "download_manifest.json"
    if not manifest_file.is_file():
        return set()

    try:
        payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    except Exception:
        return set()
    scripts = payload.get("scripts") if isinstance(payload, dict) else None
    if not isinstance(scripts, list):
        return set()

    result: set[str] = set()
    for row in scripts:
        if not isinstance(row, dict):
            continue
        url_key = _normalize_js_url_for_dedupe(str(row.get("url") or ""))
        if not url_key:
            continue
        status = str(row.get("status") or "").strip().lower()
        file_name = str(row.get("file_name") or "").strip()

        if status == "done":
            result.add(url_key)
            continue

        if not file_name:
            continue
        file_path = down_chunk_dir / file_name
        if file_path.is_file():
            try:
                if file_path.stat().st_size > 0:
                    result.add(url_key)
            except Exception:
                continue
    return result


def _source_name_from_url(js_url: str, index: int) -> str:
    parsed = urlsplit(js_url.strip())
    basename = Path(parsed.path).name or f"remote_{index}.js"
    if not basename.lower().endswith(".js"):
        basename = f"{basename}.js"
    return basename


def _fetch_js_text(js_url: str, timeout: int = 30, max_bytes: int = 2 * 1024 * 1024) -> str:
    request = UrlRequest(js_url, headers={"User-Agent": "Mozilla/5.0"})
    with safe_urlopen(request, timeout=max(1, int(timeout))) as response:
        body = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise ValueError(f"js too large: {js_url}")
    return body.decode("utf-8", errors="ignore")


def _extract_endpoints_from_all_sources(
    domain: str,
    regex: re.Pattern[str],
    baseurl: str,
    baseapi: str,
    max_items: int | None = None,
) -> list[ApiEndpoint]:
    endpoints: list[ApiEndpoint] = []
    seen: set[tuple[str, str]] = set()
    has_source = False

    chunk_dir = PROJECTS_DIR / domain / "downChunk"
    local_chunk_files: list[Path] = []
    if chunk_dir.is_dir():
        has_source = True
        local_chunk_files = list(_iter_chunk_files(chunk_dir))
        for file_path in local_chunk_files:
            _extract_from_file(
                file_path=file_path,
                regex=regex,
                baseurl=baseurl,
                baseapi=baseapi,
                endpoints=endpoints,
                seen=seen,
                max_items=max_items,
            )
            if max_items is not None and len(endpoints) >= max_items:
                return endpoints

    js_urls = _iter_effective_js_urls_from_router(domain)
    remote_urls = list(js_urls)
    if remote_urls and local_chunk_files:
        local_cached_keys = _load_local_cached_js_url_keys(domain)
        if local_cached_keys:
            remote_urls = [
                js_url for js_url in remote_urls
                if _normalize_js_url_for_dedupe(js_url) not in local_cached_keys
            ]
        elif len(local_chunk_files) >= len(js_urls):
            # Fallback when manifest is missing/invalid: if local count already covers
            # captured js count, skip remote fetch to avoid full-network extraction.
            remote_urls = []

    if remote_urls:
        has_source = True
        for idx, js_url in enumerate(remote_urls, start=1):
            parsed = urlsplit(js_url)
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
                continue
            try:
                text = _fetch_js_text(js_url)
            except Exception:
                continue

            _extract_from_text(
                source_name=_source_name_from_url(js_url, idx),
                text=text,
                regex=regex,
                baseurl=baseurl,
                baseapi=baseapi,
                endpoints=endpoints,
                seen=seen,
                max_items=max_items,
            )
            if max_items is not None and len(endpoints) >= max_items:
                return endpoints

    if not has_source:
        raise FileNotFoundError(
            "chunk sources not found: "
            f"{PROJECTS_DIR / domain / 'downChunk'} and {PROJECTS_DIR / domain / 'vueRouter' / 'js.txt'}"
        )
    return endpoints


def _get_extract_output_path(domain: str) -> Path:
    output_dir = PROJECTS_DIR / domain / "vueApi"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / "endpoints.json"


def list_project_js_files(domain: str) -> list[str]:
    if not domain.strip():
        return []
    chunk_dir = PROJECTS_DIR / domain / "downChunk"
    if not chunk_dir.is_dir():
        return []
    return [path.name for path in _iter_chunk_files(chunk_dir)]


def _extract_from_file(
    file_path: Path,
    regex: re.Pattern[str],
    baseurl: str,
    baseapi: str,
    endpoints: list[ApiEndpoint],
    seen: set[tuple[str, str]],
    max_items: int | None = None,
) -> None:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    _extract_from_text(
        source_name=file_path.name,
        text=text,
        regex=regex,
        baseurl=baseurl,
        baseapi=baseapi,
        endpoints=endpoints,
        seen=seen,
        max_items=max_items,
    )


def _extract_from_text(
    source_name: str,
    text: str,
    regex: re.Pattern[str],
    baseurl: str,
    baseapi: str,
    endpoints: list[ApiEndpoint],
    seen: set[tuple[str, str]],
    max_items: int | None = None,
) -> None:
    for match in regex.finditer(text):
        method, path = _extract_method_path(match)
        if not path:
            continue

        url = _build_full_url(baseurl=baseurl, baseapi=baseapi, path=path)
        key = (method, url)
        if key in seen:
            continue
        seen.add(key)

        endpoints.append(
            ApiEndpoint(
                id=len(endpoints) + 1,
                method=method,
                path=path,
                url=url,
                source_file=source_name,
                source_line=text.count("\n", 0, match.start()) + 1,
                match_text=match.group(0)[:240],
            )
        )
        if max_items is not None and len(endpoints) >= max_items:
            return


def preview_endpoints_from_js(
    domain: str,
    js_file: str,
    pattern: str,
    baseurl: str,
    baseapi: str,
    limit: int = 80,
) -> list[ApiEndpoint]:
    if not domain.strip():
        raise ValueError("domain is required")
    if not js_file.strip():
        raise ValueError("js_file is required")
    if not pattern.strip():
        raise ValueError("pattern is required")

    try:
        regex = re.compile(pattern, re.MULTILINE)
    except re.error as exc:
        raise ValueError(f"invalid regex pattern: {exc}") from exc

    file_path = PROJECTS_DIR / domain / "downChunk" / js_file
    if not file_path.is_file():
        raise FileNotFoundError(f"js file not found: {file_path}")

    endpoints: list[ApiEndpoint] = []
    seen: set[tuple[str, str]] = set()
    _extract_from_file(
        file_path=file_path,
        regex=regex,
        baseurl=baseurl,
        baseapi=baseapi,
        endpoints=endpoints,
        seen=seen,
        max_items=max(1, int(limit)),
    )
    return endpoints


def preview_endpoints_from_text(
    source_name: str,
    text: str,
    pattern: str,
    baseurl: str,
    baseapi: str,
    limit: int = 80,
) -> list[ApiEndpoint]:
    if not source_name.strip():
        raise ValueError("source_name is required")
    if not text.strip():
        raise ValueError("js text is empty")
    if not pattern.strip():
        raise ValueError("pattern is required")

    try:
        regex = re.compile(pattern, re.MULTILINE)
    except re.error as exc:
        raise ValueError(f"invalid regex pattern: {exc}") from exc

    endpoints: list[ApiEndpoint] = []
    seen: set[tuple[str, str]] = set()
    _extract_from_text(
        source_name=source_name,
        text=text,
        regex=regex,
        baseurl=baseurl,
        baseapi=baseapi,
        endpoints=endpoints,
        seen=seen,
        max_items=max(1, int(limit)),
    )
    return endpoints


def preview_endpoints_from_chunks(
    domain: str,
    pattern: str,
    baseurl: str,
    baseapi: str,
    limit: int | None = None,
) -> list[ApiEndpoint]:
    if not domain.strip():
        raise ValueError("domain is required")
    if not pattern.strip():
        raise ValueError("pattern is required")

    try:
        regex = re.compile(pattern, re.MULTILINE)
    except re.error as exc:
        raise ValueError(f"invalid regex pattern: {exc}") from exc

    chunk_dir = PROJECTS_DIR / domain / "downChunk"
    if not chunk_dir.is_dir():
        raise FileNotFoundError(f"chunk directory not found: {chunk_dir}")

    max_items: int | None = None
    if limit is not None:
        parsed_limit = int(limit)
        if parsed_limit > 0:
            max_items = parsed_limit
    endpoints: list[ApiEndpoint] = []
    seen: set[tuple[str, str]] = set()

    for file_path in _iter_chunk_files(chunk_dir):
        _extract_from_file(
            file_path=file_path,
            regex=regex,
            baseurl=baseurl,
            baseapi=baseapi,
            endpoints=endpoints,
            seen=seen,
            max_items=max_items,
        )
        if max_items is not None and len(endpoints) >= max_items:
            break

    return endpoints


def preview_endpoints_from_js_urls(
    domain: str,
    pattern: str,
    baseurl: str,
    baseapi: str,
    limit: int | None = None,
) -> list[ApiEndpoint]:
    if not domain.strip():
        raise ValueError("domain is required")
    if not pattern.strip():
        raise ValueError("pattern is required")

    try:
        regex = re.compile(pattern, re.MULTILINE)
    except re.error as exc:
        raise ValueError(f"invalid regex pattern: {exc}") from exc

    js_urls = _iter_effective_js_urls_from_router(domain)
    if not js_urls:
        raise FileNotFoundError(f"captured js urls not found: {PROJECTS_DIR / domain / 'vueRouter' / 'js.txt'}")

    max_items: int | None = None
    if limit is not None:
        parsed_limit = int(limit)
        if parsed_limit > 0:
            max_items = parsed_limit

    endpoints: list[ApiEndpoint] = []
    seen: set[tuple[str, str]] = set()

    for idx, js_url in enumerate(js_urls, start=1):
        parsed = urlsplit(js_url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            continue
        try:
            text = _fetch_js_text(js_url)
        except Exception:
            continue

        _extract_from_text(
            source_name=_source_name_from_url(js_url, idx),
            text=text,
            regex=regex,
            baseurl=baseurl,
            baseapi=baseapi,
            endpoints=endpoints,
            seen=seen,
            max_items=max_items,
        )
        if max_items is not None and len(endpoints) >= max_items:
            break

    return endpoints


def extract_endpoints_from_chunks(
    domain: str,
    pattern: str,
    baseurl: str,
    baseapi: str,
) -> list[ApiEndpoint]:
    if not domain.strip():
        raise ValueError("domain is required")
    if not pattern.strip():
        raise ValueError("pattern is required")

    try:
        regex = re.compile(pattern, re.MULTILINE)
    except re.error as exc:
        raise ValueError(f"invalid regex pattern: {exc}") from exc

    chunk_dir = PROJECTS_DIR / domain / "downChunk"
    if not chunk_dir.is_dir():
        raise FileNotFoundError(f"chunk directory not found: {chunk_dir}")

    endpoints: list[ApiEndpoint] = []
    seen: set[tuple[str, str]] = set()

    for file_path in _iter_chunk_files(chunk_dir):
        _extract_from_file(
            file_path=file_path,
            regex=regex,
            baseurl=baseurl,
            baseapi=baseapi,
            endpoints=endpoints,
            seen=seen,
            max_items=None,
        )

    output_path = _get_extract_output_path(domain)
    payload = {
        "domain": domain,
        "baseurl": baseurl,
        "baseapi": baseapi,
        "pattern": pattern,
        "total": len(endpoints),
        "endpoints": [endpoint.to_dict() for endpoint in endpoints],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return endpoints


def extract_endpoints_from_js_urls(
    domain: str,
    pattern: str,
    baseurl: str,
    baseapi: str,
) -> list[ApiEndpoint]:
    if not domain.strip():
        raise ValueError("domain is required")
    if not pattern.strip():
        raise ValueError("pattern is required")

    try:
        regex = re.compile(pattern, re.MULTILINE)
    except re.error as exc:
        raise ValueError(f"invalid regex pattern: {exc}") from exc

    js_urls = _iter_effective_js_urls_from_router(domain)
    if not js_urls:
        raise FileNotFoundError(f"captured js urls not found: {PROJECTS_DIR / domain / 'vueRouter' / 'js.txt'}")

    endpoints: list[ApiEndpoint] = []
    seen: set[tuple[str, str]] = set()

    for idx, js_url in enumerate(js_urls, start=1):
        parsed = urlsplit(js_url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            continue
        try:
            text = _fetch_js_text(js_url)
        except Exception:
            continue

        _extract_from_text(
            source_name=_source_name_from_url(js_url, idx),
            text=text,
            regex=regex,
            baseurl=baseurl,
            baseapi=baseapi,
            endpoints=endpoints,
            seen=seen,
            max_items=None,
        )

    output_path = _get_extract_output_path(domain)
    payload = {
        "domain": domain,
        "baseurl": baseurl,
        "baseapi": baseapi,
        "pattern": pattern,
        "total": len(endpoints),
        "source": "captured_js_urls",
        "endpoints": [endpoint.to_dict() for endpoint in endpoints],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return endpoints


def preview_endpoints_from_all_chunks(
    domain: str,
    pattern: str,
    baseurl: str,
    baseapi: str,
    limit: int | None = None,
) -> list[ApiEndpoint]:
    if not domain.strip():
        raise ValueError("domain is required")
    if not pattern.strip():
        raise ValueError("pattern is required")

    try:
        regex = re.compile(pattern, re.MULTILINE)
    except re.error as exc:
        raise ValueError(f"invalid regex pattern: {exc}") from exc

    max_items: int | None = None
    if limit is not None:
        parsed_limit = int(limit)
        if parsed_limit > 0:
            max_items = parsed_limit

    return _extract_endpoints_from_all_sources(
        domain=domain,
        regex=regex,
        baseurl=baseurl,
        baseapi=baseapi,
        max_items=max_items,
    )


def extract_endpoints_from_all_chunks(
    domain: str,
    pattern: str,
    baseurl: str,
    baseapi: str,
) -> list[ApiEndpoint]:
    if not domain.strip():
        raise ValueError("domain is required")
    if not pattern.strip():
        raise ValueError("pattern is required")

    try:
        regex = re.compile(pattern, re.MULTILINE)
    except re.error as exc:
        raise ValueError(f"invalid regex pattern: {exc}") from exc

    endpoints = _extract_endpoints_from_all_sources(
        domain=domain,
        regex=regex,
        baseurl=baseurl,
        baseapi=baseapi,
        max_items=None,
    )

    output_path = _get_extract_output_path(domain)
    payload = {
        "domain": domain,
        "baseurl": baseurl,
        "baseapi": baseapi,
        "pattern": pattern,
        "total": len(endpoints),
        "source": "all_chunks",
        "endpoints": [endpoint.to_dict() for endpoint in endpoints],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return endpoints


def load_extracted_endpoints(domain: str) -> list[ApiEndpoint]:
    output_path = _get_extract_output_path(domain)
    if not output_path.is_file():
        raise FileNotFoundError(f"extracted endpoints not found: {output_path}")

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    return [ApiEndpoint.from_dict(item) for item in payload.get("endpoints", [])]
