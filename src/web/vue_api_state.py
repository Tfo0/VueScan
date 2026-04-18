from __future__ import annotations

from typing import Any, Callable


_MISSING = object()


def get_vue_api_config_store(ui_state: dict[str, Any]) -> dict[str, dict[str, str]]:
    # 维护按域名缓存的 VueApi pattern，避免每次都回读项目文件。
    store = ui_state.get("module3_config_by_domain")
    if not isinstance(store, dict):
        store = {}
        ui_state["module3_config_by_domain"] = store
    return store


def get_vue_api_config_for_domain(
    ui_state: dict[str, Any],
    domain: str,
    *,
    safe_str: Callable[[Any, str], str],
    load_project_extract_config: Callable[[str], dict[str, str]],
) -> dict[str, str]:
    value = safe_str(domain)
    if not value:
        return {}
    store = get_vue_api_config_store(ui_state)
    item = store.get(value)
    if isinstance(item, dict):
        return {"pattern": safe_str(item.get("pattern"))}
    loaded = load_project_extract_config(value)
    if loaded:
        store[value] = dict(loaded)
    return loaded


def save_vue_api_config(
    ui_state: dict[str, Any],
    domain: str,
    pattern: str,
    *,
    safe_str: Callable[[Any, str], str],
) -> None:
    value = safe_str(domain)
    if not value:
        return
    store = get_vue_api_config_store(ui_state)
    store[value] = {"pattern": safe_str(pattern)}


def apply_vue_api_form(
    ui_state: dict[str, Any],
    raw_form: Any,
    *,
    safe_str: Callable[[Any, str], str],
) -> None:
    # 这里只同步 VueApi 表单字段，不处理其他模块的 UI 状态。
    form = ui_state["module3_form"]
    form["domain"] = safe_str(raw_form.get("domain"), form.get("domain", ""))
    form["pattern"] = safe_str(raw_form.get("pattern"), form.get("pattern", ""))
    form["js_file"] = safe_str(raw_form.get("js_file"), form.get("js_file", ""))
    form["js_url"] = safe_str(raw_form.get("js_url"), form.get("js_url", ""))


def apply_vue_api_request_form(
    ui_state: dict[str, Any],
    raw_form: Any,
    *,
    safe_str: Callable[[Any, str], str],
) -> None:
    # Module 4 仍然属于 VueApi 相关页面，这里统一处理它的表单回填。
    form = ui_state["module4_form"]
    form["domain"] = safe_str(raw_form.get("domain"), form.get("domain", ""))
    form["baseurl"] = safe_str(raw_form.get("baseurl"), form.get("baseurl", ""))
    form["baseapi"] = safe_str(raw_form.get("baseapi"), form.get("baseapi", ""))
    form["api_id"] = safe_str(raw_form.get("api_id"), form.get("api_id", ""))
    form["method"] = safe_str(raw_form.get("method"), form.get("method", ""))
    timeout = safe_str(raw_form.get("timeout"), form.get("timeout", "20"))
    form["timeout"] = timeout or "20"
    form["json_body"] = safe_str(raw_form.get("json_body"), form.get("json_body", ""))
    form["headers"] = safe_str(raw_form.get("headers"), form.get("headers", ""))


def select_vue_api_domain(
    ui_state: dict[str, Any],
    domain: Any,
    *,
    safe_str: Callable[[Any, str], str],
) -> str:
    # VueApi 页面共用同一份项目选择，避免模块 3/4 的域名状态互相漂移。
    value = set_selected_project_domain(ui_state, domain, safe_str=safe_str)
    if not value:
        return ""
    ui_state["module3_form"]["domain"] = value
    ui_state["module4_form"]["domain"] = value
    return value


def set_selected_project_domain(
    ui_state: dict[str, Any],
    domain: Any,
    *,
    safe_str: Callable[[Any, str], str],
) -> str:
    # 有些流程只需要切换当前项目，不应该顺手覆盖 VueApi 表单的其他字段。
    value = safe_str(domain)
    if not value:
        return ""
    ui_state["selected_project_domain"] = value
    return value


def clear_selected_project_domain(ui_state: dict[str, Any]) -> None:
    # 删除项目后允许清空选中域名，避免界面继续指向不存在的项目。
    ui_state["selected_project_domain"] = ""


def ensure_vue_api_form_domains(
    ui_state: dict[str, Any],
    domain: Any,
    *,
    safe_str: Callable[[Any, str], str],
) -> str:
    # 只在表单域名为空时补默认值，避免覆盖用户已经手动切换的上下文。
    value = safe_str(domain)
    if not value:
        return ""
    if not safe_str(ui_state.get("selected_project_domain")):
        set_selected_project_domain(ui_state, value, safe_str=safe_str)
    module3_form = ui_state["module3_form"]
    if not safe_str(module3_form.get("domain")):
        module3_form["domain"] = value
    module4_form = ui_state["module4_form"]
    if not safe_str(module4_form.get("domain")):
        module4_form["domain"] = value
    return value


def ensure_vue_api_pattern(
    ui_state: dict[str, Any],
    pattern: Any,
    *,
    safe_str: Callable[[Any, str], str],
) -> str:
    # 只在 pattern 为空时回填默认值，避免把用户刚输入的表达式覆盖掉。
    value = safe_str(pattern)
    form = ui_state["module3_form"]
    if value and not safe_str(form.get("pattern")):
        form["pattern"] = value
    return safe_str(form.get("pattern"))


def ensure_vue_api_request_base_defaults(
    ui_state: dict[str, Any],
    *,
    safe_str: Callable[[Any, str], str],
    baseurl: Any = "",
    baseapi: Any = "",
) -> tuple[str, str]:
    # 只补请求页缺失的 baseurl/baseapi，不覆盖用户手工调整后的值。
    form = ui_state["module4_form"]
    baseurl_value = safe_str(baseurl)
    if baseurl_value and not safe_str(form.get("baseurl")):
        form["baseurl"] = baseurl_value
    baseapi_value = safe_str(baseapi)
    if baseapi_value and not safe_str(form.get("baseapi")):
        form["baseapi"] = baseapi_value
    return safe_str(form.get("baseurl")), safe_str(form.get("baseapi"))


def prepare_vue_api_context_state(
    ui_state: dict[str, Any],
    *,
    selected_domain: str,
    module3_form: dict[str, str],
    module4_form: dict[str, str],
    safe_str: Callable[[Any, str], str],
    load_project_extract_config: Callable[[str], dict[str, str]],
    load_project_request_config: Callable[[str], dict[str, str]],
    list_project_js_files: Callable[[str], list[Any]],
    load_api_endpoints: Callable[[str], list[Any]],
) -> dict[str, Any]:
    # 为页面上下文准备 VueApi 表单、JS 列表和 endpoint 列表，减少 app.py 的拼装细节。
    default_vue_api_domain = ""
    if selected_domain:
        default_vue_api_domain = ensure_vue_api_form_domains(ui_state, selected_domain, safe_str=safe_str)

    if not module3_form.get("domain") and default_vue_api_domain:
        module3_form["domain"] = default_vue_api_domain
    module3_domain = safe_str(module3_form.get("domain"))
    if module3_domain:
        saved_cfg = get_vue_api_config_for_domain(
            ui_state,
            module3_domain,
            safe_str=safe_str,
            load_project_extract_config=load_project_extract_config,
        )
        if saved_cfg and not safe_str(module3_form.get("pattern")):
            module3_form["pattern"] = ensure_vue_api_pattern(
                ui_state,
                saved_cfg.get("pattern", ""),
                safe_str=safe_str,
            )

    if not module4_form.get("domain") and default_vue_api_domain:
        module4_form["domain"] = default_vue_api_domain
    module4_domain = safe_str(module4_form.get("domain"))
    if module4_domain:
        module4_cfg = load_project_request_config(module4_domain)
        if module4_cfg:
            default_baseurl, default_baseapi = ensure_vue_api_request_base_defaults(
                ui_state,
                safe_str=safe_str,
                baseurl=module4_cfg.get("baseurl", ""),
                baseapi=module4_cfg.get("baseapi", ""),
            )
            if not safe_str(module4_form.get("baseurl")):
                module4_form["baseurl"] = default_baseurl
            if not safe_str(module4_form.get("baseapi")):
                module4_form["baseapi"] = default_baseapi

    module3_js_files: list[str] = []
    module3_js_seen: set[str] = set()
    for js_name in list_project_js_files(module3_form.get("domain", "")):
        token = safe_str(js_name)
        key = token.lower()
        if not token or key in module3_js_seen:
            continue
        module3_js_seen.add(key)
        module3_js_files.append(token)
    if module3_form.get("js_file") and module3_form["js_file"] not in module3_js_files:
        module3_form["js_file"] = ""
        sync_vue_api_source_form(ui_state, safe_str=safe_str, js_file="")

    module4_endpoints: list[Any] = []
    if module4_domain:
        try:
            module4_endpoints = load_api_endpoints(module4_domain)
        except Exception:
            module4_endpoints = []

    return {
        "module3_form": module3_form,
        "module4_form": module4_form,
        "module3_domain": module3_domain,
        "module4_domain": module4_domain,
        "module3_js_files": module3_js_files,
        "module4_endpoints": module4_endpoints,
    }


def sync_vue_api_source_form(
    ui_state: dict[str, Any],
    *,
    safe_str: Callable[[Any, str], str],
    domain: Any = _MISSING,
    pattern: Any = _MISSING,
    js_file: Any = _MISSING,
    js_url: Any = _MISSING,
) -> None:
    # 统一维护 VueApi 源码选择表单，允许显式传空串来清空字段。
    if domain is not _MISSING:
        select_vue_api_domain(ui_state, domain, safe_str=safe_str)

    form = ui_state["module3_form"]
    if pattern is not _MISSING:
        form["pattern"] = safe_str(pattern)
    if js_file is not _MISSING:
        form["js_file"] = safe_str(js_file)
    if js_url is not _MISSING:
        form["js_url"] = safe_str(js_url)


def sync_vue_api_request_state(
    ui_state: dict[str, Any],
    *,
    safe_str: Callable[[Any, str], str],
    domain: Any = _MISSING,
    baseurl: Any = _MISSING,
    baseapi: Any = _MISSING,
    api_id: Any = _MISSING,
    method: Any = _MISSING,
    timeout: Any = _MISSING,
    json_body: Any = _MISSING,
    headers: Any = _MISSING,
) -> None:
    # 统一维护 VueApi 请求表单，避免接口层散落一堆字段赋值。
    if domain is not _MISSING:
        select_vue_api_domain(ui_state, domain, safe_str=safe_str)

    form = ui_state["module4_form"]
    if baseurl is not _MISSING:
        form["baseurl"] = safe_str(baseurl)
    if baseapi is not _MISSING:
        form["baseapi"] = safe_str(baseapi)
    if api_id is not _MISSING:
        form["api_id"] = safe_str(api_id)
    if method is not _MISSING:
        form["method"] = safe_str(method)
    if timeout is not _MISSING:
        timeout_text = safe_str(timeout, form.get("timeout", "20"))
        form["timeout"] = timeout_text or "20"
    if json_body is not _MISSING:
        form["json_body"] = safe_str(json_body)
    if headers is not _MISSING:
        form["headers"] = safe_str(headers)


def reset_vue_api_runtime_outputs(ui_state: dict[str, Any]) -> None:
    # 切换项目或重新加载时清空旧结果，避免页面继续显示上一轮数据。
    ui_state["module3_js_beautify"] = {}
    ui_state["module3_preview"] = {}
    ui_state["module3_extract_result"] = {}


def set_vue_api_beautify_result(ui_state: dict[str, Any], payload: dict[str, Any]) -> None:
    # 统一封装结果槽写入，后续继续拆分时只需要改这里。
    ui_state["module3_js_beautify"] = dict(payload)


def set_vue_api_preview_result(ui_state: dict[str, Any], payload: dict[str, Any]) -> None:
    # 统一保存 VueApi 预览结果，避免 app.py 直接关心具体槽位名。
    ui_state["module3_preview"] = dict(payload)


def set_vue_api_extract_result(ui_state: dict[str, Any], payload: dict[str, Any]) -> None:
    # 提取结果也通过同一层写入，便于后续继续把状态层从入口文件剥离。
    ui_state["module3_extract_result"] = dict(payload)


def set_vue_api_request_result(ui_state: dict[str, Any], payload: dict[str, Any]) -> None:
    # 请求执行结果仍属于 VueApi 页面状态，先集中到这个模块管理。
    ui_state["module4_request_result"] = dict(payload)


def resolve_vue_api_pattern_config(
    form: dict[str, str],
    *,
    safe_str: Callable[[Any, str], str],
) -> tuple[str, str, str]:
    # 现阶段 VueApi 提取仍只关心 pattern，baseurl/baseapi 继续保持空串。
    domain = safe_str(form.get("domain"))
    if not domain:
        raise ValueError("domain is required")

    pattern = safe_str(form.get("pattern"))
    if not pattern:
        raise ValueError("pattern is required")
    return "", "", pattern
