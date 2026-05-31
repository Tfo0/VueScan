from __future__ import annotations

# Web 入口文件只保留应用导出，具体装配下沉到 bootstrap。
from src.web.bootstrap import app

__all__ = ["app"]
