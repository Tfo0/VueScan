from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from src.vue_api.deepseek_auto_regex import DEFAULT_DEEPSEEK_BASE_URL, DEFAULT_DEEPSEEK_MODEL
from src.web.common import normalize_proxy_server, safe_str, to_int
from src.web.settings_store import load_settings_record, save_settings_record


def sanitize_global_settings(raw: Any, *, auto_scan_pattern: str) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    scan_concurrency = to_int(payload.get("scan_concurrency"), default=10, minimum=1)
    proxy_server = normalize_proxy_server(payload.get("proxy_server"))
    ai_provider = safe_str(payload.get("ai_provider") or payload.get("provider") or payload.get("deepseek_provider"), "deepseek")

    regex_list_raw = payload.get("regex_list")
    regex_list: list[str] = []
    if isinstance(regex_list_raw, list):
        for item in regex_list_raw:
            pattern = safe_str(item)
            if not pattern:
                continue
            if pattern in regex_list:
                continue
            regex_list.append(pattern)
    if not regex_list:
        regex_list = [auto_scan_pattern]

    default_regex_index = to_int(payload.get("default_regex_index"), default=0, minimum=0)
    if default_regex_index >= len(regex_list):
        default_regex_index = 0

    ai_api_key = safe_str(payload.get("ai_api_key") or payload.get("deepseek_api_key"))
    ai_base_url = safe_str(
        payload.get("ai_base_url") or payload.get("deepseek_base_url"),
        DEFAULT_DEEPSEEK_BASE_URL,
    ).rstrip("/")
    ai_model = safe_str(payload.get("ai_model") or payload.get("deepseek_model"), DEFAULT_DEEPSEEK_MODEL)

    return {
        "scan_concurrency": int(scan_concurrency),
        "proxy_server": proxy_server,
        "regex_list": regex_list,
        "default_regex_index": int(default_regex_index),
        "ai_provider": ai_provider or "deepseek",
        "ai_api_key": ai_api_key,
        "ai_base_url": ai_base_url or DEFAULT_DEEPSEEK_BASE_URL,
        "ai_model": ai_model or DEFAULT_DEEPSEEK_MODEL,
        "deepseek_api_key": ai_api_key,
        "deepseek_base_url": ai_base_url or DEFAULT_DEEPSEEK_BASE_URL,
        "deepseek_model": ai_model or DEFAULT_DEEPSEEK_MODEL,
    }


def load_global_settings_file(*, settings_file: Path, auto_scan_pattern: str) -> dict[str, Any]:
    if not settings_file.is_file():
        return sanitize_global_settings({}, auto_scan_pattern=auto_scan_pattern)
    try:
        payload = json.loads(settings_file.read_text(encoding="utf-8"))
    except Exception:
        return sanitize_global_settings({}, auto_scan_pattern=auto_scan_pattern)
    return sanitize_global_settings(payload, auto_scan_pattern=auto_scan_pattern)


def save_global_settings_file(
    raw: Any,
    *,
    database_file: Path,
    settings_file: Path,
    ui_state: dict[str, Any],
    auto_scan_pattern: str,
) -> dict[str, Any]:
    settings = sanitize_global_settings(raw, auto_scan_pattern=auto_scan_pattern)
    save_settings_record(settings, database_file=database_file, settings_file=settings_file)
    ui_state["global_settings"] = copy.deepcopy(settings)
    ui_state["global_settings_loaded"] = True
    return settings


def get_global_settings(
    *,
    ui_state: dict[str, Any],
    database_file: Path,
    settings_file: Path,
    auto_scan_pattern: str,
    force_reload: bool = False,
) -> dict[str, Any]:
    loaded = bool(ui_state.get("global_settings_loaded"))
    cached = ui_state.get("global_settings") if isinstance(ui_state.get("global_settings"), dict) else {}
    if force_reload or not loaded:
        raw_settings = load_settings_record(database_file=database_file, settings_file=settings_file)
        settings = sanitize_global_settings(raw_settings, auto_scan_pattern=auto_scan_pattern)
        save_settings_record(settings, database_file=database_file, settings_file=settings_file)
        ui_state["global_settings"] = copy.deepcopy(settings)
        ui_state["global_settings_loaded"] = True
        return copy.deepcopy(settings)
    if not cached:
        cached = sanitize_global_settings({}, auto_scan_pattern=auto_scan_pattern)
        ui_state["global_settings"] = copy.deepcopy(cached)
    return sanitize_global_settings(cached, auto_scan_pattern=auto_scan_pattern)


def resolve_scan_pattern(
    pattern_value: str = "",
    *,
    get_global_settings,
    auto_scan_pattern: str,
) -> str:
    value = safe_str(pattern_value)
    if value:
        return value
    settings = get_global_settings()
    regex_list = settings.get("regex_list") if isinstance(settings.get("regex_list"), list) else []
    patterns = [safe_str(item) for item in regex_list if safe_str(item)]
    if not patterns:
        return auto_scan_pattern
    index = to_int(settings.get("default_regex_index"), default=0, minimum=0)
    if index >= len(patterns):
        index = 0
    return patterns[index] if patterns[index] else auto_scan_pattern
