from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request as UrlRequest

from src.http_utils import safe_urlopen


_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE | re.DOTALL)
_ATTR_RE = re.compile(r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*([\"'])(.*?)\2", re.DOTALL)
_META_CHARSET_RE = re.compile(br"<meta[^>]+charset\s*=\s*[\"']?\s*([a-zA-Z0-9._-]+)", re.IGNORECASE)
_META_HTTP_EQUIV_RE = re.compile(
    br"<meta[^>]+content\s*=\s*[\"'][^\"'>]*charset\s*=\s*([a-zA-Z0-9._-]+)[^\"'>]*[\"']",
    re.IGNORECASE,
)


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _clean_title(raw_title: str) -> str:
    text = unescape(_safe_text(raw_title))
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _parse_meta_attributes(tag_text: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for key, _, value in _ATTR_RE.findall(tag_text):
        token = _safe_text(key).lower()
        if token and token not in attrs:
            attrs[token] = _safe_text(unescape(value))
    return attrs


def _extract_title_from_html(html_text: str) -> str:
    match = _TITLE_RE.search(html_text)
    if match:
        title = _clean_title(match.group(1))
        if title:
            return title

    # 部分站点不会在 <title> 中放标题，退回读 og:title / twitter:title。
    for match in _META_TAG_RE.finditer(html_text):
        attrs = _parse_meta_attributes(match.group(0))
        meta_name = _safe_text(attrs.get("property") or attrs.get("name")).lower()
        if meta_name not in {"og:title", "twitter:title", "title"}:
            continue
        title = _clean_title(attrs.get("content", ""))
        if title:
            return title
    return ""


def _resolve_title_via_browser(url: str, *, timeout: int) -> str:
    # SPA 页面常把标题放在前端路由完成后再写入，这里补一个浏览器级兜底。
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception:
        return ""

    timeout_ms = max(1000, int(timeout) * 1000)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                ignore_https_errors=True,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=min(max(timeout_ms, 3000), 9000))
                except PlaywrightTimeoutError:
                    pass
                page.wait_for_timeout(1200)
                title = _clean_title(page.title() or "")
                if not title:
                    try:
                        title = _clean_title(page.evaluate("() => document.title || ''") or "")
                    except PlaywrightError:
                        title = ""
                return title
            finally:
                context.close()
                browser.close()
    except Exception:
        return ""


def _candidate_encodings(body: bytes, header_charset: str = "") -> list[str]:
    encodings: list[str] = []

    def append(token: str) -> None:
        value = _safe_text(token).lower()
        if value and value not in encodings:
            encodings.append(value)

    append(header_charset)

    head = body[:4096]
    for pattern in (_META_CHARSET_RE, _META_HTTP_EQUIV_RE):
        match = pattern.search(head)
        if not match:
            continue
        try:
            append(match.group(1).decode("ascii", errors="ignore"))
        except Exception:
            continue

    for token in ("utf-8", "utf-8-sig", "gb18030", "gbk", "big5", "latin-1"):
        append(token)
    return encodings


def resolve_page_title(url: str, *, timeout: int = 10, max_bytes: int = 512 * 1024) -> str:
    # 这里做“尽力而为”的标题解析：失败时直接返回空串，避免影响手动创建项目。
    target = _safe_text(url)
    parsed = urlsplit(target)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""

    request = UrlRequest(
        target,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "close",
        },
    )

    try:
        with safe_urlopen(request, timeout=max(1, int(timeout))) as response:
            body = response.read(max_bytes + 1)
            header_charset = ""
            try:
                header_charset = _safe_text(response.headers.get_content_charset() or "")
            except Exception:
                header_charset = ""
    except Exception:
        return _resolve_title_via_browser(target, timeout=timeout)

    if not body:
        return _resolve_title_via_browser(target, timeout=timeout)
    if len(body) > max_bytes:
        body = body[:max_bytes]

    for encoding in _candidate_encodings(body, header_charset):
        try:
            html_text = body.decode(encoding, errors="strict")
        except Exception:
            continue
        title = _extract_title_from_html(html_text)
        if title:
            return title

    fallback_title = _extract_title_from_html(body.decode("utf-8", errors="ignore"))
    if fallback_title:
        return fallback_title

    return _resolve_title_via_browser(target, timeout=timeout)
