from __future__ import annotations

from typing import Any


def default_detect_form(detect_default_concurrency: int) -> dict[str, str]:
    return {
        "task_name": "",
        "concurrency": str(detect_default_concurrency),
    }


def default_chunk_form() -> dict[str, str]:
    return {
        "target_url": "",
        "urls_list": "",
        "concurrency": "5",
        "detect_routes": "1",
        "detect_js": "1",
        "detect_request": "1",
    }


def default_vue_api_form() -> dict[str, str]:
    return {
        "domain": "",
        "pattern": "",
        "js_file": "",
        "js_url": "",
    }


def default_vue_request_form() -> dict[str, str]:
    return {
        "domain": "",
        "baseurl": "",
        "baseapi": "",
        "api_id": "",
        "method": "",
        "timeout": "20",
        "json_body": "",
        "headers": "",
    }


def default_global_settings(auto_scan_pattern: str) -> dict[str, Any]:
    return {
        "scan_concurrency": 10,
        "proxy_server": "",
        "regex_list": [str(auto_scan_pattern or "")],
        "default_regex_index": 0,
        "ai_provider": "deepseek",
        "ai_api_key": "",
        "ai_base_url": "https://api.deepseek.com",
        "ai_model": "deepseek-chat",
        "deepseek_api_key": "",
        "deepseek_base_url": "https://api.deepseek.com",
        "deepseek_model": "deepseek-chat",
    }


def build_default_ui_state(
    *,
    detect_default_concurrency: int,
    auto_scan_pattern: str,
) -> dict[str, Any]:
    # 这里统一维护 Web 默认状态，避免 app.py 继续堆积初始化细节。
    return {
        "error": "",
        "detect_form": default_detect_form(detect_default_concurrency),
        "detect_result": {},
        "selected_task_id": "",
        "chunk_form": default_chunk_form(),
        "chunk_result": {},
        "module2_sync_job_id": "",
        "module2_js_download_job_id": "",
        "module2_request_capture_job_id": "",
        "selected_project_domain": "",
        "module3_form": default_vue_api_form(),
        "module3_config_by_domain": {},
        "module3_js_beautify": {},
        "module3_preview": {},
        "module3_extract_result": {},
        "module4_form": default_vue_request_form(),
        "module4_request_result": {},
        "global_settings_loaded": False,
        "global_settings": default_global_settings(auto_scan_pattern),
    }
