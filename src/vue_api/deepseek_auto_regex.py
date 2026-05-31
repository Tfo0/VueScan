from __future__ import annotations

import json
import re
from typing import Any, Callable
from urllib import error, request
from urllib.parse import urljoin

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


def normalize_deepseek_settings(
    raw: Any,
    *,
    safe_str: Callable[[Any, str], str],
) -> dict[str, str]:
    payload = raw if isinstance(raw, dict) else {}
    provider = safe_str(payload.get("ai_provider") or payload.get("provider") or payload.get("deepseek_provider"), "deepseek")
    api_key = safe_str(payload.get("ai_api_key") or payload.get("deepseek_api_key"))
    base_url = safe_str(
        payload.get("ai_base_url") or payload.get("deepseek_base_url"),
        DEFAULT_DEEPSEEK_BASE_URL,
    ).rstrip("/")
    model = safe_str(payload.get("ai_model") or payload.get("deepseek_model"), DEFAULT_DEEPSEEK_MODEL)
    return {
        "provider": provider or "deepseek",
        "deepseek_api_key": api_key,
        "deepseek_base_url": base_url or DEFAULT_DEEPSEEK_BASE_URL,
        "deepseek_model": model or DEFAULT_DEEPSEEK_MODEL,
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    source = str(text or "").strip()
    if not source:
        return {}
    try:
        parsed = json.loads(source)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", source, flags=re.IGNORECASE)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass

    start = source.find("{")
    end = source.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(source[start : end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _normalize_ai_patterns(raw: Any) -> list[str]:
    result: list[str] = []
    items = raw if isinstance(raw, list) else []
    for item in items:
        token = str(item or "").strip()
        if not token or token in result:
            continue
        try:
            compiled = re.compile(token, re.MULTILINE)
        except re.error:
            continue
        # 这里要求 AI 生成的正则至少带一个捕获组，方便沿用当前提取链路。
        if int(getattr(compiled, "groups", 0) or 0) <= 0:
            continue
        result.append(token)
        if len(result) >= 6:
            break
    return result


def generate_deepseek_auto_regex_candidates(
    *,
    settings: Any,
    js_api_path: str,
    safe_str: Callable[[Any, str], str],
    max_candidates: int = 3,
) -> dict[str, Any]:
    normalized = normalize_deepseek_settings(settings, safe_str=safe_str)
    api_key = normalized["deepseek_api_key"]
    base_url = normalized["deepseek_base_url"]
    model = normalized["deepseek_model"]
    result = {
        "provider": normalized["provider"],
        "model": model,
        "enabled": bool(api_key),
        "used": False,
        "patterns": [],
        "selected_pattern": "",
        "error": "",
    }
    if not api_key:
        result["error"] = "AI API key not configured"
        return result

    endpoint = urljoin(f"{base_url.rstrip('/')}/", "chat/completions")
    sample_payload = {
        "js_api_path": safe_str(js_api_path),
        "max_candidates": max(1, min(int(max_candidates or 3), 6)),
    }
    body = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 900,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个擅长从 JavaScript 代码片段中生成 Python 正则表达式的助手。"
                    "你的目标是：根据提供的 js_api_path 代码片段，分析其中的关键词、调用形式、对象访问形式和字符串结构，"
                    "生成一个可以稳定提取 API 路径的 Python regex。"
                    "要求："
                    "1. 只生成用于提取 API 路径的正则。"
                    "2. 返回结果必须是合法的 Python 正则表达式。"
                    "3. 正则必须至少包含 1 个捕获组，且第 1 个捕获组只能捕获 API 路径本身。"
                    "4. 不要返回 /regex/flags 这种格式。"
                    "5. 尽量根据当前 js 片段生成最贴近当前写法的正则，不要过度泛化。"
                    "6. 只围绕当前提供的 js_api_path 片段分析，不要臆造不存在的上下文。"
                    "7. 输出 JSON，字段为：patterns、selected_pattern、reason。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请根据下面规则生成正则：\n"
                    "1. 如果遇到 . 需要转义为 \\\\.\n"
                    "2. 如果遇到 ( 或 ) 需要转义为 \\\\( 和 \\\\)\n"
                    "3. 如果遇到固定方法名如 get，考虑到其他场景可能是 post、put、delete、patch，可以用更通用的写法替代，例如 \\\\w+ 或更合适的方式。\n"
                    "4. 如果遇到单个字母变量名，例如 a、b、i、c 等，统一优先考虑用 \\\\w 替代，不要保留成固定字母。\n"
                    "5. 如果遇到方括号属性访问，且属性值本身也是单个字母，例如 [\"a\"]、[\"b\"]、['c']，也统一优先考虑泛化成 \\[\\s*\"\\\\w\"\\s*\\] 这种形式，不要固定死成某一个字母。\n"
                    "6. 如果遇到空白字符或不确定空格，统一用 \\\\s* 处理。\n"
                    "7. 如果遇到以下划线开头、后面跟一串数字或字符的变量名，优先考虑用 _\\\\d*\\\\w* 处理。\n"
                    "8. 生成的正则要尽量贴合当前片段结构，目标是提取其中的 API 路径。\n"
                    "9. 优先保留当前片段的原始结构，只做最小必要泛化，不要过度发散。\n"
                    "10. 但对于明显的压缩变量名、单字母变量名、单字母属性键，必须泛化，不要过拟合到具体字母。\n"
                    "11. 如果片段本身已经足够明确，优先生成与当前片段几乎同构的正则。\n\n"
                    "示例：\n"
                    'js_api_path: Object(b["a"])("/admin/sys/user/getUserInfo",\n'
                    'regex: Object\\(\\s*\\w\\[\\s*"\\w"\\s*\\]\\s*\\)\\s*\\(\\s*"([^"]+)"\\s*,\n\n'
                    f"下面是 js_api_path 片段：\n{safe_str(sample_payload.get('js_api_path'))}"
                ),
            },
        ],
    }
    req = request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
    except error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8", errors="ignore"))
            message = (
                detail.get("error", {}).get("message")
                if isinstance(detail.get("error"), dict)
                else detail.get("message")
            )
        except Exception:
            message = ""
        result["error"] = safe_str(message) or f"DeepSeek request failed: HTTP {exc.code}"
        return result
    except Exception as exc:
        result["error"] = f"DeepSeek request failed: {exc}"
        return result

    choices = payload.get("choices") if isinstance(payload, dict) else []
    first = choices[0] if isinstance(choices, list) and choices else {}
    message = first.get("message") if isinstance(first, dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    parsed = _extract_json_object(str(content or ""))
    patterns = _normalize_ai_patterns(parsed.get("patterns"))
    selected_pattern = safe_str(parsed.get("selected_pattern"))
    if selected_pattern and selected_pattern not in patterns:
        merged = _normalize_ai_patterns([selected_pattern, *patterns])
        patterns = merged or patterns
    result["patterns"] = patterns
    result["selected_pattern"] = selected_pattern if selected_pattern in patterns else (patterns[0] if patterns else "")
    result["used"] = bool(patterns)
    if not patterns and not result["error"]:
        result["error"] = "DeepSeek returned no valid regex candidates"
    return result


__all__ = [
    "DEFAULT_DEEPSEEK_BASE_URL",
    "DEFAULT_DEEPSEEK_MODEL",
    "generate_deepseek_auto_regex_candidates",
    "normalize_deepseek_settings",
]
