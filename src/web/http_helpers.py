from __future__ import annotations

from typing import Any, Callable
from urllib.parse import quote

from starlette.responses import JSONResponse, RedirectResponse


def redirect(module: int) -> RedirectResponse:
    # 页面模块切换统一走 303，避免表单重提交流程分散在 app.py。
    return RedirectResponse(url=f"/?module={module}", status_code=303)


def redirect_detect_task(
    task_id: str,
    *,
    safe_str: Callable[[Any, str], str],
) -> RedirectResponse:
    # 任务详情页需要对 task_id 做一次安全转义，避免 URL 拼接散落各处。
    token = quote(safe_str(task_id), safe="")
    return RedirectResponse(url=f"/detect-tasks/{token}", status_code=303)


def json_error(
    message: str,
    *,
    safe_str: Callable[[Any, str], str],
    status_code: int = 400,
) -> JSONResponse:
    return JSONResponse({"ok": False, "error": safe_str(message)}, status_code=status_code)


def json_ok(
    payload: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
) -> JSONResponse:
    data = {"ok": True}
    if payload:
        data.update(payload)
    return JSONResponse(data, status_code=status_code)
