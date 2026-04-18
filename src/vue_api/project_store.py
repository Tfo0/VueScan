from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import PROJECTS_DIR


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _extract_file_path(domain: str) -> Path | None:
    token = _safe_text(domain)
    if not token:
        return None
    return PROJECTS_DIR / token / "vueApi" / "endpoints.json"


def _load_extract_payload(domain: str) -> dict[str, Any]:
    extract_file = _extract_file_path(domain)
    if extract_file is None or not extract_file.is_file():
        return {}
    try:
        payload = json.loads(extract_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_project_extract_config(domain: str) -> dict[str, str]:
    payload = _load_extract_payload(domain)
    if not payload:
        return {}
    return {"pattern": _safe_text(payload.get("pattern"))}


def load_project_extract_result(domain: str) -> dict[str, Any]:
    payload = _load_extract_payload(domain)
    if not payload:
        return {}
    endpoints = payload.get("endpoints")
    return {
        "domain": _safe_text(payload.get("domain")) or _safe_text(domain),
        "source_type": _safe_text(payload.get("source_type")) or _safe_text(payload.get("source")) or "all_chunks",
        "source": _safe_text(payload.get("source")),
        "source_name": _safe_text(payload.get("source_name")) or _safe_text(payload.get("source")) or "all_chunks",
        "count": len(endpoints) if isinstance(endpoints, list) else int(payload.get("total") or payload.get("count") or 0),
        "endpoint_count": len(endpoints) if isinstance(endpoints, list) else int(payload.get("total") or payload.get("count") or 0),
        "pattern": _safe_text(payload.get("pattern")),
        "baseurl": _safe_text(payload.get("baseurl")),
        "baseapi": _safe_text(payload.get("baseapi")),
        "endpoints": endpoints if isinstance(endpoints, list) else [],
        "output_path": str(_extract_file_path(domain) or ""),
    }


def load_project_request_config(domain: str) -> dict[str, str]:
    payload = _load_extract_payload(domain)
    if not payload:
        return {}
    return {
        "baseurl": _safe_text(payload.get("baseurl")),
        "baseapi": _safe_text(payload.get("baseapi")),
    }


def persist_project_request_config(domain: str, *, baseurl: str = "", baseapi: str = "") -> None:
    extract_file = _extract_file_path(domain)
    if extract_file is None or not extract_file.is_file():
        return
    payload = _load_extract_payload(domain)
    if not payload:
        return
    payload["baseurl"] = _safe_text(baseurl)
    payload["baseapi"] = _safe_text(baseapi)
    try:
        extract_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def persist_project_preview_extract(
    domain: str,
    *,
    pattern: str,
    endpoints: list[dict[str, Any]],
    source_type: str = "preview",
    source: str = "",
    source_name: str = "",
) -> str:
    """把 Preview Result 当前展示的接口列表直接落到 endpoints.json。

    这样后面的 BaseRequest / ApiRequest 可以直接复用这份结果，
    不要求用户必须再点一次“批量提取”。
    """

    extract_file = _extract_file_path(domain)
    if extract_file is None:
        raise ValueError("domain is required")

    extract_file.parent.mkdir(parents=True, exist_ok=True)
    payload = _load_extract_payload(domain)
    payload["domain"] = _safe_text(domain)
    payload["baseurl"] = _safe_text(payload.get("baseurl"))
    payload["baseapi"] = _safe_text(payload.get("baseapi"))
    payload["pattern"] = _safe_text(pattern)
    payload["total"] = len(endpoints)
    payload["count"] = len(endpoints)
    payload["source"] = _safe_text(source) or _safe_text(source_name) or _safe_text(source_type) or "preview"
    payload["source_type"] = _safe_text(source_type) or "preview"
    payload["source_name"] = _safe_text(source_name)
    payload["endpoints"] = list(endpoints or [])
    extract_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(extract_file)
