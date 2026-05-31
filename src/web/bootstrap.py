from __future__ import annotations

# 启动入口只保留应用构建结果导出，具体装配下沉到工厂模块。
from src.web.app_factory import app

__all__ = ["app"]
