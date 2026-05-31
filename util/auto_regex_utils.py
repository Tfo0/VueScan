from __future__ import annotations

from typing import Any, Callable


def dedupe_lower(values: list[str], *, safe_str: Callable[[Any, str], str]) -> list[str]:
    # 忽略大小写去重，但保留第一次出现时的原始顺序。
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        token = safe_str(item)
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(token)
    return result


__all__ = ["dedupe_lower"]
