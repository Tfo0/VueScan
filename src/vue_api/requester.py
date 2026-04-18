from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request

from src.http_utils import safe_urlopen

from config import PROJECTS_DIR
from src.vue_api.models import ApiCallResult, ApiEndpoint
from src.vue_chunk.request_capture import (
    load_captured_request_templates,
    match_capture_template_for_endpoint,
)


def _safe_text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _coerce_int(raw: object, default: int, minimum: int = 0) -> int:
    text = _safe_text(raw)
    if not text:
        return max(default, minimum)
    try:
        value = int(text)
    except ValueError:
        return max(default, minimum)
    return max(value, minimum)


def _normalize_path(value: str) -> str:
    raw = _safe_text(value)
    if not raw:
        return ""
    parsed = urlsplit(raw)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        path = _safe_text(parsed.path, "/")
    else:
        path = _safe_text(raw.split("?", 1)[0])
    if not path:
        return ""
    if not path.startswith("/"):
        path = f"/{path}"
    path = re.sub(r"/{2,}", "/", path)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return path


def _split_path_segments(path_value: str) -> list[str]:
    normalized = _normalize_path(path_value)
    if not normalized:
        return []
    return [segment for segment in normalized.split("/") if segment]


def is_http_url(url_value: object) -> bool:
    text = _safe_text(url_value)
    if not text:
        return False
    parsed = urlsplit(text)
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def compose_request_url(baseurl: str, baseapi: str, endpoint_path: str) -> str:
    # 根据 baseurl/baseapi 和 endpoint path 组装最终请求 URL。
    normalized_baseurl = _safe_text(baseurl).rstrip("/")
    raw_endpoint = _safe_text(endpoint_path)
    if not raw_endpoint:
        return normalized_baseurl
    if raw_endpoint.startswith(("http://", "https://")):
        return raw_endpoint

    query_text = ""
    endpoint_path_only = raw_endpoint
    if "?" in raw_endpoint:
        endpoint_path_only, query_text = raw_endpoint.split("?", 1)

    endpoint_segments = _split_path_segments(endpoint_path_only)
    baseapi_segments = _split_path_segments(baseapi)

    if baseapi_segments and endpoint_segments[: len(baseapi_segments)] == baseapi_segments:
        target_segments = endpoint_segments
    else:
        target_segments = baseapi_segments + endpoint_segments
    target_path = "/" + "/".join(target_segments) if target_segments else "/"
    if query_text:
        target_path = f"{target_path}?{query_text}"
    if not normalized_baseurl:
        return target_path
    return f"{normalized_baseurl}{target_path}"


def append_query_to_url(url_value: str, query_text: str) -> str:
    # 仅在目标 URL 本身没有 query 时，补上模板里带出的 query。
    url = _safe_text(url_value)
    query = _safe_text(query_text)
    if not url or not query:
        return url
    parsed = urlsplit(url)
    if _safe_text(parsed.query):
        return url
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))


def sanitize_replay_headers(raw_headers: object) -> dict[str, str]:
    # 重放请求时过滤掉 host/content-length 这类不该透传的头。
    if not isinstance(raw_headers, dict):
        return {}
    blocked = {"host", "content-length", "connection"}
    result: dict[str, str] = {}
    for key, value in raw_headers.items():
        name = _safe_text(key)
        if not name:
            continue
        if name.lower() in blocked:
            continue
        text = _safe_text(value)
        if not text:
            continue
        result[name] = text
    return result


def find_api_endpoint_by_id(endpoints: list[ApiEndpoint], api_id: int) -> ApiEndpoint | None:
    # 统一按 id 查找接口定义，避免入口层重复写同一套匹配逻辑。
    for endpoint in endpoints:
        if _coerce_int(getattr(endpoint, "id", 0), default=0, minimum=0) == api_id:
            return endpoint
    return None


def _parse_request_input_field(raw_value: object, label: str) -> object | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, (dict, list, int, float, bool)):
        return raw_value
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid {label} json: {exc}") from exc
    raise ValueError(f"invalid {label} value type")


def _parse_request_json_text(raw_value: object, label: str) -> object | None:
    text = _safe_text(raw_value)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label} json: {exc}") from exc


def _coerce_request_headers(headers_value: object | None) -> dict[str, str] | None:
    if headers_value is None:
        return None
    if not isinstance(headers_value, dict):
        raise ValueError("headers json must be an object")
    return {str(key): str(value) for key, value in headers_value.items()}


def parse_request_payload_inputs(
    *,
    raw_json_input: object,
    raw_headers_input: object,
) -> dict[str, object]:
    # 解析请求页传入的 body/headers，并保留“用户是否显式提供 body”的标记。
    json_text = raw_json_input.strip() if isinstance(raw_json_input, str) else ""
    json_body_provided = not (
        raw_json_input is None
        or (isinstance(raw_json_input, str) and json_text in {"", "{}", "null"})
    )

    json_body = _parse_request_input_field(raw_json_input, "json_body")
    headers_value = _parse_request_input_field(raw_headers_input, "headers")

    return {
        "json_body": json_body,
        "headers": _coerce_request_headers(headers_value),
        "json_body_provided": json_body_provided,
    }


def parse_request_form_inputs(
    *,
    raw_json_body: object,
    raw_headers: object,
) -> dict[str, object]:
    # 解析请求表单里的 json_body/headers 文本，供传统表单入口复用。
    return {
        "json_body": _parse_request_json_text(raw_json_body, "json_body"),
        "headers": _coerce_request_headers(_parse_request_json_text(raw_headers, "headers")),
    }


def parse_request_dispatch_inputs(raw_values: dict[str, object]) -> dict[str, object]:
    # 统一解析请求调度所需的基础参数，避免 API 路由和表单路由重复校验。
    domain = _safe_text(raw_values.get("domain"))
    if not domain:
        raise ValueError("domain is required")

    api_id_text = _safe_text(raw_values.get("api_id"))
    if not api_id_text:
        raise ValueError("api_id is required")
    try:
        api_id = int(api_id_text)
    except ValueError as exc:
        raise ValueError("api_id must be an integer") from exc

    return {
        "domain": domain,
        "api_id": api_id,
        "method": _safe_text(raw_values.get("method")).upper(),
        "baseurl": _safe_text(raw_values.get("baseurl")),
        "baseapi": _safe_text(raw_values.get("baseapi")),
        "timeout": _coerce_int(raw_values.get("timeout"), default=20, minimum=1),
    }


def resolve_template_replay_payload(
    *,
    domain: str,
    endpoint_path: str,
    endpoint_method: str,
    baseurl: str,
    baseapi: str,
) -> dict[str, object]:
    # 根据 capture 模板补齐请求 URL / headers / body，供 API Request 直接复用。
    templates = load_captured_request_templates(domain)
    match = match_capture_template_for_endpoint(
        templates,
        endpoint_path=endpoint_path,
        endpoint_method=endpoint_method,
    )
    if not match:
        return {}

    sample = match.get("sample") if isinstance(match.get("sample"), dict) else {}
    template = match.get("template") if isinstance(match.get("template"), dict) else {}
    sample_url = _safe_text(sample.get("url"))
    sample_query = _safe_text(sample.get("query_string"))
    composed_url = compose_request_url(baseurl, baseapi, endpoint_path)
    if is_http_url(composed_url):
        request_url = append_query_to_url(composed_url, sample_query)
    elif is_http_url(sample_url):
        request_url = append_query_to_url(sample_url, sample_query)
    else:
        request_url = append_query_to_url(composed_url, sample_query) if composed_url else sample_url
    if not request_url and sample_url:
        request_url = sample_url

    return {
        "matched": True,
        "score": _coerce_int(match.get("score"), default=0, minimum=0),
        "match_type": _safe_text(match.get("match_type")),
        "method": _safe_text(sample.get("method") or template.get("method"), endpoint_method).upper() or "GET",
        "request_url": request_url,
        "query_string": sample_query,
        "query_params": sample.get("query_params") if isinstance(sample.get("query_params"), dict) else {},
        "body_type": _safe_text(sample.get("body_type")),
        "body_json": sample.get("body_json"),
        "body_form": sample.get("body_form") if isinstance(sample.get("body_form"), dict) else None,
        "body_text": _safe_text(sample.get("request_body")),
        "content_type": _safe_text(sample.get("content_type")),
        "headers": sanitize_replay_headers(sample.get("request_headers")),
        "template_path": _safe_text(template.get("path")),
    }


def merge_template_replay_request(
    *,
    template_replay: dict[str, object],
    endpoint_method: str,
    headers: dict[str, str] | None,
    json_body: object | None,
    json_body_provided: bool,
) -> dict[str, object]:
    # 把 capture template 转成实际请求输入，接口层只负责把结果接起来。
    merged_headers = dict(headers) if isinstance(headers, dict) else None
    request_url_override = ""
    body_text = ""
    content_type = ""
    used_template_url = False
    used_template_headers = False
    used_template_body = False

    template_headers_raw = template_replay.get("headers")
    template_headers: dict[str, str] = {}
    if isinstance(template_headers_raw, dict):
        template_headers = {
            str(key): str(value)
            for key, value in template_headers_raw.items()
            if _safe_text(key) and _safe_text(value)
        }
    if template_headers:
        if merged_headers is None:
            merged_headers = dict(template_headers)
        else:
            inherited_headers = dict(template_headers)
            inherited_headers.update(merged_headers)
            merged_headers = inherited_headers
        used_template_headers = True

    template_url = _safe_text(template_replay.get("request_url"))
    if template_url:
        request_url_override = template_url
        used_template_url = True

    body_methods = {"POST", "PUT", "PATCH", "DELETE"}
    resolved_json_body = json_body
    if endpoint_method in body_methods and not json_body_provided:
        template_body_json = template_replay.get("body_json")
        if template_body_json is not None:
            resolved_json_body = template_body_json
            used_template_body = True
        else:
            template_body_text = _safe_text(template_replay.get("body_text"))
            if not template_body_text:
                template_form = template_replay.get("body_form")
                if isinstance(template_form, dict) and template_form:
                    try:
                        template_body_text = urlencode(template_form, doseq=True)
                    except Exception:
                        template_body_text = ""
                    if template_body_text and not _safe_text(template_replay.get("content_type")):
                        content_type = "application/x-www-form-urlencoded; charset=utf-8"
            if template_body_text:
                body_text = template_body_text
                used_template_body = True
        if not content_type:
            content_type = _safe_text(template_replay.get("content_type"))

    return {
        "headers": merged_headers,
        "json_body": resolved_json_body,
        "request_url_override": request_url_override,
        "body_text": body_text,
        "content_type": content_type,
        "used_template_url": used_template_url,
        "used_template_headers": used_template_headers,
        "used_template_body": used_template_body,
    }


def prepare_template_replay_request(
    *,
    domain: str,
    endpoint_path: str,
    endpoint_method: str,
    baseurl: str,
    baseapi: str,
    use_capture_template: bool,
    headers: dict[str, str] | None,
    json_body: object | None,
    json_body_provided: bool,
) -> dict[str, object]:
    # 串起模板匹配和运行时请求合并，接口层不再关心中间细节。
    template_replay: dict[str, object] = {}
    merged_headers = headers
    resolved_json_body = json_body
    request_url_override = ""
    body_text = ""
    content_type = ""
    used_template_url = False
    used_template_headers = False
    used_template_body = False

    if use_capture_template and endpoint_path:
        template_replay = resolve_template_replay_payload(
            domain=domain,
            endpoint_path=endpoint_path,
            endpoint_method=endpoint_method,
            baseurl=baseurl,
            baseapi=baseapi,
        )
        if template_replay:
            template_runtime = merge_template_replay_request(
                template_replay=template_replay,
                endpoint_method=endpoint_method,
                headers=headers,
                json_body=json_body,
                json_body_provided=json_body_provided,
            )
            merged_headers = (
                template_runtime.get("headers")
                if isinstance(template_runtime.get("headers"), dict)
                else None
            )
            resolved_json_body = template_runtime.get("json_body")
            request_url_override = _safe_text(template_runtime.get("request_url_override"))
            body_text = _safe_text(template_runtime.get("body_text"))
            content_type = _safe_text(template_runtime.get("content_type"))
            used_template_url = bool(template_runtime.get("used_template_url"))
            used_template_headers = bool(template_runtime.get("used_template_headers"))
            used_template_body = bool(template_runtime.get("used_template_body"))

    return {
        "template_replay": template_replay,
        "headers": merged_headers,
        "json_body": resolved_json_body,
        "request_url_override": request_url_override,
        "body_text": body_text,
        "content_type": content_type,
        "used_template_url": used_template_url,
        "used_template_headers": used_template_headers,
        "used_template_body": used_template_body,
    }


def load_saved_response_detail(response_path: object) -> dict[str, object]:
    # 读取落盘的响应详情，失败时返回空字典，不影响主请求结果。
    path = Path(_safe_text(response_path))
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def format_request_payload_text(
    raw_input: object,
    parsed_value: object | None,
    *,
    fallback_text: str = "",
) -> str:
    # 把请求输入回填成可展示的文本，优先保留用户原始输入。
    if isinstance(raw_input, str):
        return raw_input.strip()
    if parsed_value is not None:
        try:
            return json.dumps(parsed_value, ensure_ascii=False, indent=2)
        except Exception:
            return _safe_text(parsed_value)
    return _safe_text(fallback_text)


def build_template_replay_summary(
    *,
    use_capture_template: bool,
    template_replay: dict[str, object],
    used_template_url: bool,
    used_template_headers: bool,
    used_template_body: bool,
) -> dict[str, object]:
    # 统一整理 template replay 命中信息，避免入口层重复拼装摘要字段。
    return {
        "enabled": bool(use_capture_template),
        "matched": bool(template_replay),
        "template_path": _safe_text(template_replay.get("template_path")) if template_replay else "",
        "match_type": _safe_text(template_replay.get("match_type")) if template_replay else "",
        "score": _coerce_int(template_replay.get("score"), default=0, minimum=0) if template_replay else 0,
        "used_url": bool(used_template_url),
        "used_headers": bool(used_template_headers),
        "used_body": bool(used_template_body),
    }


def _decode_body(raw: bytes, content_type: str) -> str:
    charset = "utf-8"
    for part in content_type.split(";"):
        value = part.strip().lower()
        if value.startswith("charset="):
            charset = value.split("=", 1)[1].strip() or "utf-8"
            break
    return raw.decode(charset, errors="replace")


def _normalize_headers(headers: dict[str, str] | None) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in (headers or {}).items():
        normalized[str(key)] = str(value)
    return normalized


def request_endpoint(
    endpoint: ApiEndpoint,
    method: str | None = None,
    json_body: object | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
    body_text: str | None = None,
    content_type: str | None = None,
) -> ApiCallResult:
    req_method = (method or endpoint.method or "GET").strip().upper()
    url = endpoint.url
    req_headers = _normalize_headers(headers)

    data: bytes | None = None
    request_body_payload: object | None = json_body
    body_methods = {"POST", "PUT", "PATCH", "DELETE"}
    normalized_body_text = None if body_text is None else str(body_text)

    if req_method in body_methods:
        has_content_type = "Content-Type" in req_headers or "content-type" in {
            key.lower() for key in req_headers
        }
        if normalized_body_text is not None and normalized_body_text != "":
            if not has_content_type:
                fallback_type = str(content_type or "").strip() or "application/x-www-form-urlencoded; charset=utf-8"
                req_headers["Content-Type"] = fallback_type
            data = normalized_body_text.encode("utf-8")
            request_body_payload = normalized_body_text
        elif json_body is not None:
            if not has_content_type:
                req_headers["Content-Type"] = "application/json"
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            request_body_payload = json_body

    request = Request(url=url, method=req_method, headers=req_headers, data=data)
    start = time.perf_counter()

    try:
        with safe_urlopen(request, timeout=timeout) as response:
            raw = response.read()
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            content_type = response.headers.get("Content-Type", "")
            body_text = _decode_body(raw, content_type)
            response_headers = {k: v for k, v in response.headers.items()}

            return ApiCallResult(
                endpoint_id=endpoint.id,
                method=req_method,
                url=url,
                status_code=int(response.getcode() or 0),
                ok=200 <= int(response.getcode() or 0) < 300,
                elapsed_ms=elapsed_ms,
                response_headers=response_headers,
                response_text=body_text,
                error="",
                request_body=request_body_payload,
            )
    except HTTPError as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        raw = exc.read() if exc.fp else b""
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        body_text = _decode_body(raw, content_type) if raw else ""
        response_headers = {k: v for k, v in (exc.headers.items() if exc.headers else [])}
        return ApiCallResult(
            endpoint_id=endpoint.id,
            method=req_method,
            url=url,
            status_code=int(exc.code or 0),
            ok=False,
            elapsed_ms=elapsed_ms,
            response_headers=response_headers,
            response_text=body_text,
            error=f"HTTPError: {exc}",
            request_body=request_body_payload,
        )
    except URLError as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return ApiCallResult(
            endpoint_id=endpoint.id,
            method=req_method,
            url=url,
            status_code=0,
            ok=False,
            elapsed_ms=elapsed_ms,
            response_headers={},
            response_text="",
            error=f"URLError: {exc}",
            request_body=request_body_payload,
        )
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return ApiCallResult(
            endpoint_id=endpoint.id,
            method=req_method,
            url=url,
            status_code=0,
            ok=False,
            elapsed_ms=elapsed_ms,
            response_headers={},
            response_text="",
            error=f"RequestError: {exc}",
            request_body=request_body_payload,
        )


def save_call_result(domain: str, result: ApiCallResult) -> Path:
    response_dir = PROJECTS_DIR / domain / "vueApi" / "responses"
    response_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    file_name = f"{ts}_api{result.endpoint_id}.json"
    output_path = response_dir / file_name
    output_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path
