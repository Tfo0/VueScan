from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.routing import Route


@dataclass(frozen=True)
class FrontendRouteDeps:
    # 前端入口和静态文件只负责 HTTP 适配，避免继续堆在 app.py 里。
    frontend_dir: Path
    frontend_dist_dir: Path
    safe_str: Callable[[Any, str], str]
    json_error: Callable[..., Any]


def _frontend_dist_file(path: str, deps: FrontendRouteDeps) -> Path:
    token = deps.safe_str(path).lstrip("/")
    if not token:
        return deps.frontend_dist_dir / "index.html"
    normalized = token.replace("\\", "/")
    if ".." in normalized.split("/"):
        return deps.frontend_dist_dir / "index.html"
    return deps.frontend_dist_dir / normalized


def _frontend_favicon_file(deps: FrontendRouteDeps) -> Path:
    candidates = [
        deps.frontend_dist_dir / "vue.svg",
        deps.frontend_dir / "public" / "vue.svg",
        deps.frontend_dist_dir / "vite.svg",
        deps.frontend_dir / "public" / "vite.svg",
    ]
    for item in candidates:
        if item.is_file():
            return item
    return deps.frontend_dist_dir / "index.html"


def _bind_route(
    handler: Callable[[Request, FrontendRouteDeps], Awaitable[Any]],
    deps: FrontendRouteDeps,
) -> Callable[[Request], Awaitable[Any]]:
    async def endpoint(request: Request):
        return await handler(request, deps)

    endpoint.__name__ = handler.__name__.lstrip("_")
    return endpoint


async def _serve_frontend_favicon(request: Request, deps: FrontendRouteDeps):
    target = _frontend_favicon_file(deps)
    if not target.is_file():
        return deps.json_error("favicon file not found", status_code=404)
    media_type = "image/x-icon" if target.suffix.lower() == ".ico" else "image/svg+xml"
    return FileResponse(path=str(target), media_type=media_type)


async def _serve_frontend_app(request: Request, deps: FrontendRouteDeps):
    if not deps.frontend_dist_dir.is_dir():
        return deps.json_error("frontend dist not found, run: cd frontend && npm run build", status_code=503)
    index_path = deps.frontend_dist_dir / "index.html"
    if not index_path.is_file():
        return deps.json_error("frontend index.html not found, run: cd frontend && npm run build", status_code=503)
    return FileResponse(path=str(index_path), media_type="text/html")


async def _serve_frontend_assets_or_app(request: Request, deps: FrontendRouteDeps):
    if not deps.frontend_dist_dir.is_dir():
        return deps.json_error("frontend dist not found, run: cd frontend && npm run build", status_code=503)
    path_value = deps.safe_str(request.path_params.get("path"))
    target = _frontend_dist_file(path_value, deps)
    if target.is_file():
        return FileResponse(path=str(target))

    index_path = deps.frontend_dist_dir / "index.html"
    if not index_path.is_file():
        return deps.json_error("frontend index.html not found, run: cd frontend && npm run build", status_code=503)
    return FileResponse(path=str(index_path), media_type="text/html")


async def _serve_frontend_assets(request: Request, deps: FrontendRouteDeps):
    if not deps.frontend_dist_dir.is_dir():
        return deps.json_error("frontend dist not found, run: cd frontend && npm run build", status_code=503)
    path_value = deps.safe_str(request.path_params.get("path"))
    normalized = path_value.replace("\\", "/").lstrip("/")
    if not normalized or ".." in normalized.split("/"):
        return deps.json_error("invalid asset path", status_code=400)
    target = deps.frontend_dist_dir / "assets" / normalized
    if not target.is_file():
        return deps.json_error(f"frontend asset not found: {normalized}", status_code=404)
    return FileResponse(path=str(target))


def build_frontend_app_handler(deps: FrontendRouteDeps) -> Callable[[Request], Awaitable[Any]]:
    # 首页和页面路由复用同一个前端入口处理器，避免在 app.py 里重复保留实现。
    return _bind_route(_serve_frontend_app, deps)


def build_frontend_routes(deps: FrontendRouteDeps) -> list[Route]:
    return [
        Route("/favicon.ico", endpoint=_bind_route(_serve_frontend_favicon, deps), methods=["GET"]),
        Route("/vue.svg", endpoint=_bind_route(_serve_frontend_favicon, deps), methods=["GET"]),
        Route("/assets/{path:path}", endpoint=_bind_route(_serve_frontend_assets, deps), methods=["GET"]),
        Route("/vue", endpoint=_bind_route(_serve_frontend_app, deps), methods=["GET"]),
        Route("/vue/{path:path}", endpoint=_bind_route(_serve_frontend_assets_or_app, deps), methods=["GET"]),
        Route("/app", endpoint=_bind_route(_serve_frontend_app, deps), methods=["GET"]),
        Route("/app/{path:path}", endpoint=_bind_route(_serve_frontend_assets_or_app, deps), methods=["GET"]),
    ]
