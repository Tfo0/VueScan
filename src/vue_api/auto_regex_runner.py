from __future__ import annotations

from typing import Any, Callable

from src.vue_api.deepseek_auto_regex import generate_deepseek_auto_regex_candidates
from util.base_reg import pick_builtin_auto_regex_pattern


def run_vue_api_auto_regex(
    *,
    domain: str,
    js_api_path: str = "",
    target_api: str = "",
    js_file: str = "",
    max_candidates: int = 3,
    auto_scan_pattern: str = "",
    get_global_settings: Callable[..., dict[str, Any]] | None = None,
    safe_str: Callable[[Any, str], str],
    to_int: Callable[[Any, int, int], int],
    list_project_js_files: Callable[[str], list[Any]] | None = None,
    load_request_capture_items: Callable[[str], list[dict[str, Any]]] | None = None,
    normalize_target_path: Callable[[str], str] | None = None,
    locate_request_in_chunks: Callable[..., Any] | None = None,
    preview_endpoints_from_all_chunks: Callable[..., list[Any]] | None = None,
    max_scan_files: int = 220,
) -> dict[str, Any]:
    token = safe_str(domain)
    if not token:
        raise ValueError("domain is required")

    snippet = safe_str(js_api_path)
    if not snippet:
        raise ValueError("js_api_path is required")

    builtin_pattern = pick_builtin_auto_regex_pattern(
        sample_snippets=[snippet],
        auto_scan_pattern=auto_scan_pattern,
        safe_str=safe_str,
    )

    ai_info = {
        "provider": "deepseek",
        "model": "",
        "enabled": False,
        "used": False,
        "patterns": [],
        "selected_pattern": "",
        "error": "",
    }
    if callable(get_global_settings):
        try:
            ai_info = generate_deepseek_auto_regex_candidates(
                settings=get_global_settings(),
                js_api_path=snippet,
                safe_str=safe_str,
                max_candidates=max_candidates,
            )
        except Exception as exc:
            ai_info = {
                "provider": "deepseek",
                "model": "",
                "enabled": True,
                "used": False,
                "patterns": [],
                "selected_pattern": "",
                "error": f"DeepSeek auto regex failed: {exc}",
            }

    ai_patterns = ai_info.get("patterns") if isinstance(ai_info.get("patterns"), list) else []
    ai_selected_pattern = safe_str(ai_info.get("selected_pattern"))
    if not ai_selected_pattern and ai_patterns:
        ai_selected_pattern = safe_str(ai_patterns[0])

    candidates = [
        {
            "pattern": builtin_pattern,
            "source": "builtin",
            "label": "内置正则",
            "note": "根据提供的 js_api_path 片段匹配内置正则",
            "error": "" if builtin_pattern else "未找到可用的内置正则",
        },
        {
            "pattern": ai_selected_pattern,
            "source": "ai",
            "label": "AI生成",
            "note": f"DeepSeek {safe_str(ai_info.get('model'))}".strip(),
            "error": "" if ai_selected_pattern else safe_str(ai_info.get("error"), "DeepSeek 未返回有效正则"),
        },
    ]

    selected_pattern = builtin_pattern or ai_selected_pattern

    return {
        "domain": token,
        "js_api_path": snippet,
        "target_api": safe_str(target_api),
        "target_path": "",
        "target_candidates": [],
        "js_file": safe_str(js_file),
        "capture_path_count": 0,
        "scan_file_count": 0,
        "snippet_hit_count": 1,
        "sample_snippets": [snippet],
        "candidate_count": len(candidates),
        "candidates": candidates,
        "selected_pattern": selected_pattern,
        "mode": "builtin_ai_from_js_api_path",
        "ai_provider": safe_str(ai_info.get("provider")),
        "ai_model": safe_str(ai_info.get("model")),
        "ai_enabled": bool(ai_info.get("enabled")),
        "ai_used": bool(ai_info.get("used")),
        "ai_pattern_count": len(ai_patterns),
        "ai_error": safe_str(ai_info.get("error")),
    }


__all__ = ["run_vue_api_auto_regex"]
