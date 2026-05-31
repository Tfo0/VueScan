from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Callable

from config import PROJECTS_DIR
from util.auto_regex_utils import dedupe_lower


def iter_auto_regex_js_paths(
    domain: str,
    preferred_js_file: str,
    target_path: str,
    *,
    safe_str: Callable[[Any, str], str],
    list_project_js_files: Callable[[str], list[Any]],
    locate_request_in_chunks: Callable[..., Any] | None = None,
    max_scan_files: int = 220,
) -> list[Path]:
    token = safe_str(domain)
    if not token:
        return []

    all_paths: list[Path] = []
    seen_file_keys: set[str] = set()
    for item in list_project_js_files(token):
        name = safe_str(item)
        if not name:
            continue
        key = name.lower()
        if key in seen_file_keys:
            continue
        seen_file_keys.add(key)
        path = PROJECTS_DIR / token / "downChunk" / name
        if path.is_file():
            all_paths.append(path)
    if not all_paths:
        return []

    prioritized_names: list[str] = []
    preferred = safe_str(preferred_js_file)
    if preferred:
        prioritized_names.append(preferred)

    if target_path and callable(locate_request_in_chunks):
        try:
            locate = locate_request_in_chunks(
                domain=token,
                request_url=target_path,
                method="GET",
                route_url="",
                max_files=max(1, int(max_scan_files)),
                max_results=120,
            )
            for hit in locate.get("hits", []) if isinstance(locate, dict) else []:
                if not isinstance(hit, dict):
                    continue
                name = safe_str(hit.get("file_name"))
                if name:
                    prioritized_names.append(name)
        except Exception:
            pass

    ordered_names = dedupe_lower(prioritized_names + [path.name for path in all_paths], safe_str=safe_str)
    file_map = {path.name.lower(): path for path in all_paths}

    result: list[Path] = []
    for name in ordered_names:
        row = file_map.get(name.lower())
        if row is None:
            continue
        result.append(row)
        if len(result) >= max(1, int(max_scan_files)):
            break
    return result


def collect_auto_regex_tokens(
    path_candidates: list[str],
    *,
    safe_str: Callable[[Any, str], str],
    normalize_path: Callable[[str], str],
) -> list[str]:
    tokens: list[str] = []
    for item in path_candidates:
        path = safe_str(normalize_path(safe_str(item)))
        if not path:
            continue
        tokens.append(path)
        plain = path.lstrip("/")
        if plain:
            tokens.append(plain)
    return dedupe_lower(tokens, safe_str=safe_str)


def find_segment_start(source: str, hit_index: int) -> int:
    # 按约定优先级反向找最近起点，尽量取到最小可用请求片段。
    prefix = str(source or "")[: max(0, int(hit_index))]
    if not prefix:
        return 0

    marker_patterns: list[tuple[str, re.Pattern[str] | None]] = [
        ("Object", re.compile(r"Object\b", re.IGNORECASE)),
        ("return", re.compile(r"\breturn\b", re.IGNORECASE)),
        ("function", re.compile(r"\bfunction\b", re.IGNORECASE)),
        ("this", re.compile(r"\bthis\b", re.IGNORECASE)),
        ("url", re.compile(r"\burl\b", re.IGNORECASE)),
        (";", None),
        (",", None),
    ]

    for marker, pattern in marker_patterns:
        if pattern is None:
            pos = prefix.rfind(marker)
            if pos >= 0:
                return pos
            continue
        matches = list(pattern.finditer(prefix))
        if matches:
            return matches[-1].start()
    return -1


def find_segment_end(source: str, search_start: int) -> int:
    text = str(source or "")
    start = max(0, min(int(search_start), len(text)))
    comma_pos = text.find(",", start)
    dot_pos = text.find(".", start)
    positions = [pos for pos in (comma_pos, dot_pos) if pos >= 0]
    if positions:
        return min(positions) + 1
    return -1


def extract_segment_bounds(text: str, index: int, token: str) -> tuple[int, int]:
    source = str(text or "")
    if not source:
        return 0, 0
    hit_index = max(0, min(int(index), len(source)))
    token_len = max(1, len(str(token or "")))
    default_prefix_span = 60
    default_suffix_span = 40
    start = find_segment_start(source, hit_index)
    end = find_segment_end(source, hit_index + token_len)
    default_left = max(0, hit_index - default_prefix_span)
    default_right = min(len(source), hit_index + token_len + default_suffix_span)
    if start < 0 or (hit_index - start) > default_prefix_span:
        start = default_left
    if end < 0 or (end - (hit_index + token_len)) > default_suffix_span:
        end = default_right
    if end <= start:
        end = default_right
    return start, end


def render_segment(text: str, start: int, end: int) -> str:
    source = str(text or "")
    left = max(0, min(int(start), len(source)))
    right = max(left, min(int(end), len(source)))
    value = source[left:right].replace("\r", " ").replace("\n", " ").strip()
    return re.sub(r"\s+", " ", value)


def auto_regex_snippet(text: str, index: int, token: str) -> str:
    start, end = extract_segment_bounds(text, index, token)
    return render_segment(text, start, end)


def find_auto_regex_occurrences(text: str, tokens: list[str], max_hits: int = 12) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    source = str(text or "")
    if not source or not tokens:
        return result

    for token in tokens:
        start = 0
        hit_count = 0
        while True:
            index = source.find(token, start)
            if index < 0:
                break
            next_index = index + len(token)
            prev_char = source[index - 1] if index > 0 else ""
            next_char = source[next_index] if next_index < len(source) else ""
            if (
                (prev_char and (prev_char.isalnum() or prev_char in {"_", "$"}) and token and token[0].isalnum())
                or (next_char and (next_char.isalnum() or next_char in {"_", "$"}))
            ):
                start = index + max(1, len(token))
                continue

            result.append((index, token))
            hit_count += 1
            if len(result) >= max(1, int(max_hits)):
                return result
            if hit_count >= 3:
                break
            start = index + max(1, len(token))
    return result


def extract_auto_regex_context(
    text: str,
    index: int,
    *,
    token: str,
    safe_str: Callable[[Any, str], str],
) -> dict[str, Any]:
    left = max(0, int(index) - 240)
    right = min(len(text), int(index) + 260)
    before = text[left:index]
    after = text[index:right]

    key_name = "url"
    key_matches = list(re.finditer(r"(url|uri|path)\s*:\s*[\"'`]?", before[-180:], flags=re.IGNORECASE))
    if key_matches:
        key_name = safe_str(key_matches[-1].group(1), "url").lower() or "url"

    return {
        "key_name": key_name if key_name in {"url", "uri", "path"} else "url",
        "has_return": bool(re.search(r"\breturn\b", before[-160:], flags=re.IGNORECASE)),
        "has_object_call": "Object(" in before[-200:],
        "has_method": bool(re.search(r"\bmethod\s*:\s*[\"'`]", f"{before[-220:]}{after[:220]}", flags=re.IGNORECASE)),
        "has_headers": bool(re.search(r"\bheaders\s*:", after[:180], flags=re.IGNORECASE)),
        "snippet": auto_regex_snippet(text, index, token),
    }


def clean_auto_regex_source_text(text: str) -> str:
    source = str(text or "")
    if not source:
        return ""
    cleaned = source
    cleaned = re.sub(r'class\s*=\s*["\'][^"\']*["\']\s*>', "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?span[^>]*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?code[^>]*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = (
        cleaned.replace("&quot;", '"')
        .replace("&#34;", '"')
        .replace("&apos;", "'")
        .replace("&#39;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
    )
    return cleaned


def collect_auto_regex_sample_snippets(
    *,
    js_paths: list[Path],
    target_candidates: list[str],
    safe_str: Callable[[Any, str], str],
    normalize_path: Callable[[str], str],
) -> dict[str, Any]:
    tokens = collect_auto_regex_tokens(
        target_candidates,
        safe_str=safe_str,
        normalize_path=normalize_path,
    )
    if not js_paths or not tokens:
        return {
            "sample_snippets": [],
            "scan_file_count": len(js_paths),
            "hit_count": 0,
        }

    snippets: list[str] = []
    hit_total = 0

    for path in js_paths:
        try:
            text_raw = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        text = clean_auto_regex_source_text(text_raw)
        if not text:
            continue

        hits = find_auto_regex_occurrences(text=text, tokens=tokens, max_hits=12)
        for index, hit_token in hits:
            context = extract_auto_regex_context(text=text, index=index, token=hit_token, safe_str=safe_str)
            hit_total += 1
            snippet = safe_str(context.get("snippet"))
            if snippet and len(snippets) < 10:
                snippets.append(snippet)
            if hit_total >= 80:
                break
        if hit_total >= 80:
            break

    return {
        "sample_snippets": snippets,
        "scan_file_count": len(js_paths),
        "hit_count": hit_total,
    }


__all__ = [
    "auto_regex_snippet",
    "clean_auto_regex_source_text",
    "collect_auto_regex_sample_snippets",
    "collect_auto_regex_tokens",
    "extract_auto_regex_context",
    "extract_segment_bounds",
    "find_auto_regex_occurrences",
    "find_segment_end",
    "find_segment_start",
    "iter_auto_regex_js_paths",
    "render_segment",
]
