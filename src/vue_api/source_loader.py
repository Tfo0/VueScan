from __future__ import annotations

import json
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from config import PROJECTS_DIR


def _safe_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _read_lines(path: Path, *, limit: int) -> list[str]:
    if not path.is_file():
        return []
    try:
        rows = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    return rows[: max(1, int(limit))]


def list_project_js_urls(domain: str, limit: int = 5000) -> list[str]:
    # 读取项目记录过的 JS URL，供 VueApi 预览和调试接口复用。
    token = _safe_text(domain)
    if not token:
        return []

    result: list[str] = []
    seen: set[str] = set()

    js_file = PROJECTS_DIR / token / "vueRouter" / "js.txt"
    for item in _read_lines(js_file, limit=max(1, int(limit))):
        value = _safe_text(item)
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)

    manifest_file = PROJECTS_DIR / token / "vueRouter" / "download_manifest.json"
    if manifest_file.is_file():
        try:
            payload = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        scripts = payload.get("scripts") if isinstance(payload, dict) else []
        if isinstance(scripts, list):
            for row in scripts:
                if not isinstance(row, dict):
                    continue
                value = _safe_text(row.get("url"))
                if not value or value in seen:
                    continue
                seen.add(value)
                result.append(value)
                if len(result) >= max(1, int(limit)):
                    break

    return result


def load_project_js_source(
    domain: str,
    js_file: str,
    js_url: str,
    *,
    fetch_text_from_url: Callable[[str], str],
) -> tuple[str, str, str]:
    # 优先按 URL 加载；如果传入的是文件名，则从 downChunk 读取本地副本。
    target_domain = _safe_text(domain)
    target_file = _safe_text(js_file)
    target_url = _safe_text(js_url)
    if not target_domain:
        raise ValueError("domain is required")

    if target_url:
        text = fetch_text_from_url(target_url)
        return "url", target_url, text

    if target_file:
        parsed = urlsplit(target_file)
        if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
            text = fetch_text_from_url(target_file)
            return "url", target_file, text
        file_path = PROJECTS_DIR / target_domain / "downChunk" / target_file
        if not file_path.is_file():
            raise FileNotFoundError(f"js file not found: {file_path}")
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        return "file", target_file, text

    raise ValueError("js_file or js_url is required")
