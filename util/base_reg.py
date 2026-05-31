from __future__ import annotations

from typing import Any, Callable

from util.auto_regex_utils import dedupe_lower


OBJECT_AUTO_REGEX_PATTERN = r'Object\([^)]*\)\s*\(\s*(?:\{\s*[\'"]?url[\'"]?\s*:\s*)?[\'"]([^\'"]*)[\'"]'
RETURN_AUTO_REGEX_PATTERN = r'(?:\burl\s*:\s*|[\w$]+(?:\[[\'"][^\'"]+[\'"]\]|\.[\w$]+)*\.get\s*\()[\'"](?P<api_path>/[^\'"]*)[\'"]'
URL_AUTO_REGEX_PATTERN = r'url\s*:\s*"([^"\'`?]*)'
PATH_AUTO_REGEX_PATTERN = r"path\s*:\s*([^\"'`?]*)"

BASE_AUTO_REGEX_PATTERNS: list[str] = [
    OBJECT_AUTO_REGEX_PATTERN,
    RETURN_AUTO_REGEX_PATTERN,
    URL_AUTO_REGEX_PATTERN,
    PATH_AUTO_REGEX_PATTERN,
]


def pick_builtin_auto_regex_pattern(
    *,
    sample_snippets: list[str],
    auto_scan_pattern: str,
    safe_str: Callable[[Any, str], str],
) -> str:
    # 内置正则直接看截断后的 JS 片段内容，按固定优先级选：
    # Object -> return -> url -> path
    snippets = sample_snippets if isinstance(sample_snippets, list) else []
    has_object = False
    has_return = False
    has_url = False
    has_path = False
    for item in snippets:
        snippet = safe_str(item)
        if not snippet:
            continue
        lower = snippet.lower()
        if "object(" in lower:
            has_object = True
        if "return" in lower:
            has_return = True
        if "url" in lower:
            has_url = True
        if "path" in lower:
            has_path = True

    if has_object:
        return OBJECT_AUTO_REGEX_PATTERN
    if has_return:
        return RETURN_AUTO_REGEX_PATTERN
    if has_url:
        return URL_AUTO_REGEX_PATTERN
    if has_path:
        return PATH_AUTO_REGEX_PATTERN

    patterns: list[str] = []
    if safe_str(auto_scan_pattern):
        patterns.append(safe_str(auto_scan_pattern))
    patterns.extend(BASE_AUTO_REGEX_PATTERNS)
    deduped = dedupe_lower(patterns, safe_str=safe_str)
    return deduped[0] if deduped else ""


__all__ = [
    "BASE_AUTO_REGEX_PATTERNS",
    "OBJECT_AUTO_REGEX_PATTERN",
    "PATH_AUTO_REGEX_PATTERN",
    "RETURN_AUTO_REGEX_PATTERN",
    "URL_AUTO_REGEX_PATTERN",
    "pick_builtin_auto_regex_pattern",
]
