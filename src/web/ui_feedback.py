from __future__ import annotations

from typing import Any


def set_error(ui_state: dict[str, Any], message: str) -> None:
    # Web 页面共用同一份错误槽位，这里统一负责写入。
    ui_state["error"] = str(message).strip()


def clear_error(ui_state: dict[str, Any]) -> None:
    ui_state["error"] = ""
