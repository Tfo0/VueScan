from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def module3_js_source_name_from_url(js_url: str) -> str:
    parsed = urlsplit(str(js_url or "").strip())
    basename = Path(parsed.path).name or "remote.js"
    if not basename.lower().endswith(".js"):
        basename = f"{basename}.js"
    return basename


def module3_source_preview_payload(
    source_type: str,
    source_value: str,
    source_text: str,
    *,
    max_display_chars: int = 260000,
) -> dict[str, Any]:
    raw_text = str(source_text or "")
    code = raw_text
    truncated = False
    if len(code) > max(1, int(max_display_chars)):
        code = f"{code[:max(1, int(max_display_chars))]}\n\n/* source preview truncated */"
        truncated = True
    source_name = source_value if source_type == "file" else module3_js_source_name_from_url(source_value)
    return {
        "source_type": source_type,
        "source": source_value,
        "source_name": source_name,
        "raw_chars": len(raw_text),
        "code": code,
        "truncated": truncated,
    }
