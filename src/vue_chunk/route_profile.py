from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from config import PROJECTS_DIR
from src.vue_chunk.request_capture import HASH_STYLE_SLASH, normalize_basepath, normalize_hash_style


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _coerce_bool(raw: Any) -> bool:
    return _safe_text(raw).lower() in {"1", "true", "yes", "on"}


def _route_profile_path(domain: str):
    token = _safe_text(domain)
    return PROJECTS_DIR / token / "vueRouter" / "route_url_profile.json"


def default_route_url_profile() -> dict[str, Any]:
    return {
        "hash_style": HASH_STYLE_SLASH,
        "basepath_override": "",
        "manual_lock": False,
        "source": "default",
        "updated_at": "",
        "probe": {},
    }


def sanitize_route_url_profile(raw_profile: Any) -> dict[str, Any]:
    data = raw_profile if isinstance(raw_profile, dict) else {}
    hash_style = normalize_hash_style(data.get("hash_style"))
    basepath_override = normalize_basepath(data.get("basepath_override"))
    manual_lock = bool(_coerce_bool(data.get("manual_lock")))
    source = _safe_text(data.get("source")).lower()
    if source not in {"default", "manual", "auto_probe"}:
        source = "manual" if manual_lock else "default"
    updated_at = _safe_text(data.get("updated_at"))
    probe = data.get("probe") if isinstance(data.get("probe"), dict) else {}
    return {
        "hash_style": hash_style,
        "basepath_override": basepath_override,
        "manual_lock": manual_lock,
        "source": source,
        "updated_at": updated_at,
        "probe": probe,
    }


def load_route_url_profile(domain: str) -> dict[str, Any]:
    token = _safe_text(domain)
    if not token:
        return default_route_url_profile()
    profile_path = _route_profile_path(token)
    if not profile_path.is_file():
        return default_route_url_profile()
    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception:
        return default_route_url_profile()
    return sanitize_route_url_profile(payload)


def save_route_url_profile(
    domain: str,
    *,
    hash_style: str | None = None,
    basepath_override: str | None = None,
    manual_lock: bool | None = None,
    source: str | None = None,
    probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # 路由 URL 改写配置需要稳定落盘，供详情页、请求捕获和手工改写共用。
    token = _safe_text(domain)
    if not token:
        raise ValueError("domain is required")

    profile = load_route_url_profile(token)
    if hash_style is not None:
        profile["hash_style"] = normalize_hash_style(hash_style)
    if basepath_override is not None:
        profile["basepath_override"] = normalize_basepath(basepath_override)
    if manual_lock is not None:
        profile["manual_lock"] = bool(manual_lock)
    if source is not None:
        source_value = _safe_text(source).lower()
        profile["source"] = (
            source_value if source_value in {"default", "manual", "auto_probe"} else profile.get("source", "default")
        )
    if probe is not None:
        profile["probe"] = probe if isinstance(probe, dict) else {}
    profile["updated_at"] = datetime.now(timezone.utc).isoformat()

    output_path = _route_profile_path(token)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(sanitize_route_url_profile(profile), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return load_route_url_profile(token)
