from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from starlette.datastructures import UploadFile


def safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, UploadFile):
        return default
    return str(value).strip()


def to_int(raw: Any, default: int, minimum: int = 0) -> int:
    text = safe_str(raw)
    if not text:
        return max(default, minimum)
    try:
        value = int(text)
    except ValueError:
        return max(default, minimum)
    return max(value, minimum)


def to_bool(raw: Any) -> bool:
    return safe_str(raw).lower() in {"1", "true", "yes", "on"}


def parse_module(raw: Any, default: int = 1) -> int:
    try:
        module = int(safe_str(raw, str(default)))
    except ValueError:
        return default
    if module not in {1, 2, 3, 4}:
        return default
    return module


def normalize_proxy_server(raw_proxy: Any) -> str:
    value = safe_str(raw_proxy)
    if not value:
        return ""
    if "://" not in value:
        return f"http://{value}"
    return value


def read_lines(path: Path, limit: int = 2000) -> list[str]:
    if not path.is_file():
        return []
    rows: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        value = line.strip()
        if not value:
            continue
        rows.append(value)
        if len(rows) >= max(1, int(limit)):
            break
    return rows


def normalize_js_url_for_dedupe(raw_url: Any) -> str:
    value = safe_str(raw_url)
    if not value:
        return ""

    parsed = urlsplit(value)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        path = parsed.path or "/"
        path = re.sub(r"/{2,}", "/", path)
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))

    text = value.split("#", 1)[0].split("?", 1)[0].strip()
    return text


def dedupe_effective_js_urls(raw_urls: list[Any]) -> list[str]:
    # JS URL 去重时既要保留原始 URL，也要消除 query/hash 带来的重复。
    rows: list[str] = []
    seen: set[str] = set()
    for item in raw_urls:
        url = safe_str(item)
        if not url:
            continue
        key = normalize_js_url_for_dedupe(url)
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(url)
    return rows


def read_detect_urls(txt_path: Any) -> list[str]:
    return read_lines(Path(safe_str(txt_path)), limit=4000)


def safe_file_token(value: str, default: str = "file") -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "_", safe_str(value)).strip("._")
    return token or default
