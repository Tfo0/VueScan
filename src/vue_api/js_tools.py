from __future__ import annotations

from urllib.parse import urlsplit
from urllib.request import Request as UrlRequest

from src.http_utils import safe_urlopen


def _safe_text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def fetch_text_from_url(url: str, timeout: int = 30, max_bytes: int = 2 * 1024 * 1024) -> str:
    target = _safe_text(url)
    parsed = urlsplit(target)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("invalid js url, expected http(s) url")

    request = UrlRequest(target, headers={"User-Agent": "Mozilla/5.0"})
    with safe_urlopen(request, timeout=max(1, int(timeout))) as response:
        body = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise ValueError(f"js content too large (> {max_bytes} bytes)")
    return body.decode("utf-8", errors="ignore")


def collapse_extra_blank_lines(text: str, max_consecutive: int = 2) -> str:
    rows = text.splitlines()
    result: list[str] = []
    blank_count = 0
    for row in rows:
        item = row.rstrip()
        if not item.strip():
            blank_count += 1
            if blank_count > max_consecutive:
                continue
        else:
            blank_count = 0
        result.append(item)
    return "\n".join(result).strip()


def simple_js_beautify(text: str, indent_size: int = 2) -> str:
    source = str(text or "")
    if not source.strip():
        return ""

    indent_token = " " * max(1, int(indent_size))
    out: list[str] = []
    indent_level = 0
    line_start = True
    pending_space = False
    mode = "normal"
    quote_char = ""
    escaped = False
    i = 0
    size = len(source)

    def _write(value: str) -> None:
        nonlocal line_start, pending_space
        if not value:
            return
        if line_start:
            out.append(indent_token * max(0, indent_level))
            line_start = False
        if pending_space and out:
            last_piece = out[-1]
            if not last_piece.endswith((" ", "\n")) and value[0] not in ".,;:)]}":
                out.append(" ")
        pending_space = False
        out.append(value)

    def _newline() -> None:
        nonlocal line_start, pending_space
        if not out:
            return
        if not out[-1].endswith("\n"):
            out.append("\n")
        line_start = True
        pending_space = False

    while i < size:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < size else ""

        if mode == "string":
            _write(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote_char:
                mode = "normal"
            i += 1
            continue

        if mode == "line_comment":
            if ch in "\r\n":
                _newline()
                mode = "normal"
            else:
                _write(ch)
            i += 1
            continue

        if mode == "block_comment":
            if ch == "*" and nxt == "/":
                _write("*/")
                i += 2
                mode = "normal"
                pending_space = True
                continue
            if ch in "\r\n":
                _newline()
            else:
                _write(ch)
            i += 1
            continue

        if ch in " \t":
            pending_space = True
            i += 1
            continue

        if ch in "\r\n":
            _newline()
            i += 1
            continue

        if ch == "/" and nxt == "/":
            _write("//")
            mode = "line_comment"
            i += 2
            continue

        if ch == "/" and nxt == "*":
            _write("/*")
            mode = "block_comment"
            i += 2
            continue

        if ch in {"'", '"', "`"}:
            _write(ch)
            mode = "string"
            quote_char = ch
            escaped = False
            i += 1
            continue

        if ch == "{":
            _write("{")
            indent_level += 1
            _newline()
            i += 1
            continue

        if ch == "}":
            indent_level = max(0, indent_level - 1)
            _newline()
            _write("}")
            if nxt and nxt not in ",;)]}":
                _newline()
            i += 1
            continue

        if ch == ";":
            _write(";")
            _newline()
            i += 1
            continue

        if ch == ",":
            _write(",")
            pending_space = True
            i += 1
            continue

        _write(ch)
        i += 1

    beautified = "".join(out)
    return collapse_extra_blank_lines(beautified)


def beautify_js_code(text: str) -> str:
    # 优先走 jsbeautifier；依赖缺失时退回项目内置的轻量整理器。
    raw = str(text or "")
    if not raw.strip():
        return ""
    try:
        import jsbeautifier  # type: ignore

        options = jsbeautifier.default_options()
        options.indent_size = 2
        options.indent_with_tabs = False
        options.wrap_line_length = 120
        options.preserve_newlines = True
        options.max_preserve_newlines = 2
        return collapse_extra_blank_lines(jsbeautifier.beautify(raw, options))
    except Exception:
        return simple_js_beautify(raw, indent_size=2)
