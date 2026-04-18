from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from starlette.requests import Request
from starlette.routing import Route


@dataclass(frozen=True)
class SystemRouteDeps:
    # 系统级接口只保留最薄的一层 HTTP 适配，具体配置读写继续通过依赖注入下沉。
    json_ok: Callable[..., Any]
    get_global_settings: Callable[..., dict[str, Any]]
    save_global_settings_file: Callable[[Any], dict[str, Any]]
    frontend_dist_dir: Path


async def _read_json_payload(request: Request) -> dict[str, Any]:
    try:
        raw_payload = await request.json()
    except Exception:
        return {}
    return raw_payload if isinstance(raw_payload, dict) else {}


def _bind_route(
    handler: Callable[[Request, SystemRouteDeps], Awaitable[Any]],
    deps: SystemRouteDeps,
) -> Callable[[Request], Awaitable[Any]]:
    async def endpoint(request: Request):
        return await handler(request, deps)

    endpoint.__name__ = handler.__name__.lstrip("_")
    return endpoint


async def _api_health(request: Request, deps: SystemRouteDeps):
    return deps.json_ok(
        {
            "service": "VueScan Web API",
            "frontend_dist_ready": (deps.frontend_dist_dir / "index.html").is_file(),
        }
    )


async def _api_global_settings_get(request: Request, deps: SystemRouteDeps):
    settings = deps.get_global_settings(force_reload=True)
    return deps.json_ok({"settings": settings})


async def _api_global_settings_save(request: Request, deps: SystemRouteDeps):
    payload = await _read_json_payload(request)
    target_payload = payload.get("settings") if isinstance(payload.get("settings"), dict) else payload
    settings = deps.save_global_settings_file(target_payload)
    return deps.json_ok({"settings": settings})


def build_system_routes(deps: SystemRouteDeps) -> list[Route]:
    return [
        Route("/api/health", endpoint=_bind_route(_api_health, deps), methods=["GET"]),
        Route("/api/settings/global", endpoint=_bind_route(_api_global_settings_get, deps), methods=["GET"]),
        Route(
            "/api/settings/global",
            endpoint=_bind_route(_api_global_settings_save, deps),
            methods=["POST", "PUT"],
        ),
    ]
