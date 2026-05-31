from __future__ import annotations

import ssl
from urllib.error import URLError
from urllib.request import Request, urlopen


def _clone_request(request: Request) -> Request:
    headers = {key: value for key, value in request.header_items()}
    method = request.get_method() if hasattr(request, "get_method") else None
    cloned = Request(
        url=request.full_url,
        data=request.data,
        headers=headers,
        method=method,
    )
    return cloned


def _build_legacy_ssl_context() -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    # Compatibility for legacy TLS stacks that fail with modern defaults.
    if hasattr(ssl, "TLSVersion"):
        try:
            context.minimum_version = ssl.TLSVersion.TLSv1
        except Exception:
            pass

    try:
        context.set_ciphers("DEFAULT:@SECLEVEL=1")
    except Exception:
        pass

    # Some legacy banking / enterprise sites still require unsafe legacy
    # renegotiation. If OpenSSL exposes the switch, enable it in fallback mode.
    legacy_flag = getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0)
    if legacy_flag:
        try:
            context.options |= legacy_flag
        except Exception:
            pass

    return context


def _looks_like_ssl_error(exc: BaseException) -> bool:
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ssl.SSLError):
        return True
    text = str(reason).lower()
    markers = (
        "ssl",
        "tls",
        "handshake",
        "certificate",
        "wrong version number",
        "unexpected eof while reading",
    )
    return any(marker in text for marker in markers)


def safe_urlopen(request: Request, timeout: int | float = 30):
    normalized_timeout = max(1, int(timeout))

    try:
        return urlopen(request, timeout=normalized_timeout)
    except Exception as exc:
        if not str(getattr(request, "full_url", "")).lower().startswith("https://"):
            raise
        if not _looks_like_ssl_error(exc):
            raise

        fallback_request = _clone_request(request)
        if not any(key.lower() == "connection" for key, _ in fallback_request.header_items()):
            fallback_request.add_header("Connection", "close")
        context = _build_legacy_ssl_context()
        return urlopen(fallback_request, timeout=normalized_timeout, context=context)
