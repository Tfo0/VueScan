from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable
from urllib import error, request
from urllib.parse import urljoin

from src.vue_api.deepseek_auto_regex import normalize_deepseek_settings

BATCH_SIZE = 60

_SYSTEM_PROMPT = (
    "你是一位资深 Web 安全研究员，擅长通过 API 接口路径反推业务逻辑并识别潜在的安全攻击面。"
    "你的分析要精准、实用，直接服务于渗透测试和漏洞挖掘。"
    "严格按要求的 JSON 格式输出，不要输出任何多余文字。"
)

# 第1批：输出全局分析 + 本批 api_analysis
_PHASE1_TEMPLATE = """\
以下是该系统全部 {total} 个 API 接口路径（全局上下文，用于理解整体业务与接口关联）：

{all_paths_text}

---
{param_keys_section}
请完成两项任务：

【任务一】基于全部接口完成整体安全分析：
- business_analysis：系统架构, 核心业务, 主要模块, 权限层级、敏感功能点（上传/下载/导出/注册等）
- unauthorized_suggestions：未授权访问风险高的接口（重点：admin/export/download/upload/register/reset/query/geturl）, 重点关注文件相关操作, 文件上传下载导出, 获取url等接口
- web_analysis：针对整个系统的 Web 漏洞总结，覆盖 SQL注入/XSS/SSRF/任意文件上传读取/越权/IDOR/逻辑漏洞等，每项给出受影响接口和利用思路
- attack_chains：跨接口的攻击链和组合拳（如：注册→验证绕过→提权；上传→路径遍历→执行）

【任务二】对下列第1批共 {batch_size} 个接口逐条分析：

{batch_paths_text}

严格按以下 JSON 格式输出：

{{
  "business_analysis": "系统整体业务描述，300字以内",
  "unauthorized_suggestions": [
    {{"path": "/api/xxx", "reason": "未授权风险说明"}}
  ],
  "web_analysis": [
    {{"vuln": "漏洞类型", "paths": ["/api/xxx"], "detail": "利用思路和payload方向"}}
  ],
  "attack_chains": [
    {{"title": "攻击链名称", "steps": ["/api/step1", "/api/step2"], "impact": "危害说明"}}
  ],
  "api_analysis": [
    {{"api": "/api/xxx", "llm": "业务含义", "attack": "攻击思路"}}
  ]
}}
"""

# 第2批以后：全量路径保留（保证全局关联性），并行执行
_PHASE2_TEMPLATE = """\
以下是该系统全部 {total} 个 API 接口路径（全局上下文）：

{all_paths_text}

---
{param_keys_section}
请对下列第 {batch_num} 批共 {batch_size} 个接口逐条分析业务含义和攻击思路，结合全局接口列表识别跨接口关联：

{batch_paths_text}

攻击思路参考：
- 含 id/uid/userId 参数 → 水平越权（IDOR）
- 含 url/path/file/src 参数 → SSRF 或任意文件读取
- admin/register/create → 尝试未授权创建或提权
- export/download/report → 未授权数据导出或路径遍历
- geturl/print/file/ -> 未授权个人信息相关操作
- upload → 任意文件上传（绕过类型校验）
- list/query/search + 无鉴权信号 → 未授权数据枚举
- delete/remove/disable → 越权删除

严格按以下 JSON 格式输出：

{{
  "api_analysis": [
    {{"api": "/api/xxx", "llm": "业务含义", "attack": "攻击思路"}}
  ]
}}
"""


def _build_param_keys_section(param_keys: list[str]) -> str:
    if not param_keys:
        return ""
    keys_text = "\n".join(param_keys[:200])
    return (
        f"以下是从响应中提取的字段名（参数字典，可用于构造 payload 或识别敏感字段）：\n\n"
        f"{keys_text}\n\n---\n"
    )


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


def _normalize_api_analysis(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        result.append({
            "api": str(item.get("api") or "").strip(),
            "llm": str(item.get("llm") or "").strip(),
            "attack": str(item.get("attack") or "").strip(),
        })
    return result


def _normalize_unauthorized_suggestions(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        result.append({
            "path": str(item.get("path") or "").strip(),
            "reason": str(item.get("reason") or "").strip(),
        })
    return result


def _normalize_web_analysis(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        paths = item.get("paths")
        result.append({
            "vuln": str(item.get("vuln") or "").strip(),
            "paths": [str(p).strip() for p in paths if str(p).strip()] if isinstance(paths, list) else [],
            "detail": str(item.get("detail") or "").strip(),
        })
    return result


def _normalize_attack_chains(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        steps = item.get("steps")
        result.append({
            "title": str(item.get("title") or "").strip(),
            "steps": [str(s).strip() for s in steps if str(s).strip()] if isinstance(steps, list) else [],
            "impact": str(item.get("impact") or "").strip(),
        })
    return result


_RETRYABLE_ERRORS = (
    "IncompleteRead",
    "ConnectionReset",
    "RemoteDisconnected",
    "BrokenPipe",
    "ConnectionError",
    "TimeoutError",
    "timeout",
)


def _call_llm(
    *,
    endpoint: str,
    api_key: str,
    model: str,
    user_content: str,
    safe_str: Callable[[Any, str], str],
    max_retries: int = 3,
) -> tuple[str, str]:
    """返回 (content, error_message)，网络截断/连接重置时自动重试。"""
    body = {
        "model": model,
        "temperature": 0.3,
        "max_tokens": 8000,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }
    last_err = ""
    for attempt in range(max_retries):
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
            with request.urlopen(req, timeout=180) as resp:
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
            # HTTP 4xx/5xx 不重试
            return "", safe_str(message) or f"LLM request failed: HTTP {exc.code}"
        except Exception as exc:
            err_str = str(exc)
            last_err = f"LLM request failed: {err_str}"
            retryable = any(kw.lower() in err_str.lower() for kw in _RETRYABLE_ERRORS)
            if retryable and attempt < max_retries - 1:
                time.sleep(3 * (attempt + 1))
                continue
            return "", last_err
        else:
            choices = payload.get("choices") if isinstance(payload, dict) else []
            first = choices[0] if isinstance(choices, list) and choices else {}
            msg = first.get("message") if isinstance(first, dict) else {}
            content = msg.get("content") if isinstance(msg, dict) else ""
            return str(content or ""), ""
    return "", last_err


def analyze_api_paths_with_llm(
    *,
    paths: list[str],
    settings: Any,
    safe_str: Callable[[Any, str], str],
    param_keys: list[str] | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    def _log(msg: str) -> None:
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass
    result: dict[str, Any] = {
        "business_analysis": "",
        "unauthorized_suggestions": [],
        "web_analysis": [],
        "attack_chains": [],
        "api_analysis": [],
        "batch_total": 0,
        "batch_done": 0,
        "error": "",
    }

    clean_paths = [str(p).strip() for p in (paths or []) if str(p).strip()]
    if not clean_paths:
        result["error"] = "接口列表为空"
        return result

    normalized = normalize_deepseek_settings(settings, safe_str=safe_str)
    api_key = normalized["deepseek_api_key"]
    base_url = normalized["deepseek_base_url"]
    model = normalized["deepseek_model"]

    if not api_key:
        result["error"] = "AI API key not configured"
        return result

    endpoint = urljoin(f"{base_url.rstrip('/')}/", "chat/completions")
    all_paths_text = "\n".join(clean_paths)
    total = len(clean_paths)
    param_keys_section = _build_param_keys_section(param_keys or [])

    batches = [clean_paths[i : i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    result["batch_total"] = len(batches)

    all_api_analysis: list[dict[str, str]] = []
    batch_errors: list[str] = []

    # ── Phase 1：串行，需要其输出作为后续上下文 ──
    phase1_content, phase1_err = _call_llm(
        endpoint=endpoint,
        api_key=api_key,
        model=model,
        user_content=_PHASE1_TEMPLATE.format(
            total=total,
            all_paths_text=all_paths_text,
            param_keys_section=param_keys_section,
            batch_size=len(batches[0]),
            batch_paths_text="\n".join(batches[0]),
        ),
        safe_str=safe_str,
    )
    result["batch_done"] = 1

    if phase1_err:
        batch_errors.append(f"批次1: {phase1_err}")
        _log(f"批次 1/{len(batches)} 失败: {phase1_err}")
    else:
        parsed1 = _extract_json_object(phase1_content)
        result["business_analysis"] = str(parsed1.get("business_analysis") or "").strip()
        result["unauthorized_suggestions"] = _normalize_unauthorized_suggestions(
            parsed1.get("unauthorized_suggestions")
        )
        result["web_analysis"] = _normalize_web_analysis(parsed1.get("web_analysis"))
        result["attack_chains"] = _normalize_attack_chains(parsed1.get("attack_chains"))
        all_api_analysis.extend(_normalize_api_analysis(parsed1.get("api_analysis")))
        _log(f"批次 1/{len(batches)} 完成，已获得全局分析 + {len(all_api_analysis)} 条接口")

    # ── Phase 2+：并行，各批独立，同时发出 ──
    def _run_phase2_batch(batch_index: int, batch: list[str]) -> tuple[int, str, str]:
        user_content = _PHASE2_TEMPLATE.format(
            total=total,
            all_paths_text=all_paths_text,
            param_keys_section=param_keys_section,
            batch_num=batch_index + 1,
            batch_size=len(batch),
            batch_paths_text="\n".join(batch),
        )
        content, err = _call_llm(
            endpoint=endpoint,
            api_key=api_key,
            model=model,
            user_content=user_content,
            safe_str=safe_str,
        )
        return batch_index, content, err

    if len(batches) > 1:
        # 并发数不超过批次数，也不超过 8
        max_workers = min(len(batches) - 1, 8)
        batch_results: dict[int, tuple[str, str]] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_run_phase2_batch, i, batch): i
                for i, batch in enumerate(batches[1:], start=1)
            }
            for future in as_completed(futures):
                batch_index, content, err = future.result()
                batch_results[batch_index] = (content, err)
                result["batch_done"] = 1 + len(batch_results)
                done_count = result["batch_done"]
                if err:
                    _log(f"批次 {done_count}/{len(batches)} 失败: {err}")
                else:
                    parsed_count = len(_normalize_api_analysis(_extract_json_object(content).get("api_analysis")))
                    _log(f"批次 {done_count}/{len(batches)} 完成，本批 {parsed_count} 条接口")

        # 按批次顺序合并，保证 api_analysis 顺序与原始路径一致
        for i in sorted(batch_results):
            content, err = batch_results[i]
            if err:
                batch_errors.append(f"批次{i + 1}: {err}")
            else:
                parsed = _extract_json_object(content)
                all_api_analysis.extend(_normalize_api_analysis(parsed.get("api_analysis")))

    result["api_analysis"] = all_api_analysis

    if batch_errors:
        result["error"] = "；".join(batch_errors)
    elif not result["business_analysis"] and not all_api_analysis:
        result["error"] = "LLM 未返回有效分析结果"

    return result


__all__ = ["analyze_api_paths_with_llm"]
