from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.web.auth_service import AUTH_COOKIE_NAME, count_users, get_session_user


class ApiAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, *, database_file: Path):
        super().__init__(app)
        self.database_file = Path(database_file)
        self.public_api_paths = {
            "/api/health",
            "/api/auth/session",
            "/api/auth/login",
            "/api/auth/logout",
            "/api/auth/bootstrap",
        }

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        protected_api = path.startswith("/api/") and path not in self.public_api_paths
        protected_download = path.startswith("/downloads/")
        if not protected_api and not protected_download:
            return await call_next(request)

        token = str(request.cookies.get(AUTH_COOKIE_NAME) or "").strip()
        user = get_session_user(database_file=self.database_file, token=token)
        if not user:
            payload = {
                "ok": False,
                "error": "请先登录",
                "bootstrap_required": count_users(database_file=self.database_file) == 0,
            }
            return JSONResponse(payload, status_code=401)

        request.state.auth_user = user
        return await call_next(request)


__all__ = ["ApiAuthMiddleware"]
